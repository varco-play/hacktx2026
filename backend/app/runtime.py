"""Session runtime: one capture thread -> VisionEngine.step -> preview + recorders."""
from __future__ import annotations

import secrets
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import cv2

from backend.app.capture import CaptureWorker
from backend.app.config import Settings
from backend.app.profiles import PROFILES, ThermalGovernor
from backend.app.media.recorders import PairedRecorder
from backend.app.media.storage import PROTECTED_PREFIX, RESTRICTED_PREFIX
from backend.app.vision.engine import VisionEngine
from backend.app.vision.renderer import full_shield
from shared.contracts import FramePacket, OutputState


def admit_frame(now: float, next_due: float, interval: float) -> bool:
    """Rate limiter with 25% jitter tolerance: frames arriving slightly early still count,
    so a 11 fps source isn't halved to 5.5 fps by a 10 fps target (measured bug)."""
    return now >= next_due - 0.25 * interval


def preview_labels(protected, tracks: list):
    """Live-preview-only feedback so a bystander can SEE their request worked.
    Drawn on a copy; the recorded protected file never gets these labels."""
    marks = [t for t in tracks if t.get("shielded")]
    if not marks:
        return protected
    out = protected.copy()
    for t in marks:
        x, y, w, h = t["box"]
        ok = t.get("privacy") == "BLURRED_BY_REQUEST"
        label, color = ("blurred", (90, 200, 90)) if ok else ("checking...", (40, 170, 240))
        ty = max(14, int(y) - 8)
        cv2.rectangle(out, (int(x), ty - 13), (int(x) + 9 * len(label) + 8, ty + 4), (25, 25, 25), -1)
        cv2.putText(out, label, (int(x) + 4, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return out


class Session:
    def __init__(self, settings: Settings, source, face_models, source_label: str, signals=None, storage=None):
        self.settings = settings
        self.session_id = "s_" + secrets.token_hex(4)
        self.source = source
        self.source_label = source_label  # "CAMERA" or "TEST INPUT: <file>"
        self.engine = VisionEngine(self.session_id, face_models.detect, face_models.feature, signals=signals)
        self.engine.strict = settings.privacy_default == "protect"
        self.recorder: Optional[PairedRecorder] = None
        self.finished_recordings: list[dict] = []
        self.storage = storage  # R2Storage or None (local files)
        self._t0 = time.monotonic()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.latest_jpeg: Optional[bytes] = None
        self.latest_tracks: list = []
        self.output_state = OutputState.NORMAL
        self.frame_id = 0
        self.vision_ms = deque(maxlen=60)
        self.frame_times = deque(maxlen=60)
        self.error: Optional[str] = None
        self.listeners: list = []  # callables(event dict), thread-safe enqueue
        self.capture = CaptureWorker(source, self.now_ms, self._source_event)
        self.governor = ThermalGovernor(settings.profile)
        self.e2e_ms = deque(maxlen=120)
        self.rate_skipped = 0
        self.analyzed = 0
        self.camera_connected = True
        self._proc = None

    def now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def _source_event(self, type_: str, details: dict) -> None:
        """Camera lifecycle events go into the same audited timeline as privacy events."""
        self.camera_connected = type_ != "CAMERA_DISCONNECTED"
        ev = self.engine._event(type("P", (), {"t_ms": self.now_ms()})(), type_, details=details)
        self.engine.event_log.append(ev)
        self._emit([ev])

    def start(self) -> None:
        self.capture.start()
        self._thread = threading.Thread(target=self._loop, name="vision-worker", daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        rec = self.stop_recording()
        self.capture.stop()
        removed = self.engine.registry.clear_biometrics()
        return {"session_id": self.session_id, "embeddings_deleted": removed, "recording": rec}

    def start_recording(self) -> dict:
        with self._lock:
            if self.recorder is not None:
                return self.recorder.info()
            s = self.settings
            if self.storage is not None:
                # R2 mode: encode into a temp folder; deleted after a confirmed upload.
                out_dir = Path(tempfile.mkdtemp(prefix="consentlens_rec_"))
                raw = s.diagnostic_original and s.raw_upload  # raw only if explicitly allowed
            else:
                out_dir, raw = Path(s.recordings_dir), s.diagnostic_original
            self.recorder = PairedRecorder(out_dir, s.width, s.height, s.fps, raw, self.now_ms())
            return self.recorder.info()

    def stop_recording(self) -> Optional[dict]:
        with self._lock:
            if self.recorder is None:
                return None
            rec = self.recorder
            info = rec.close()
            info["storage"] = "r2" if self.storage is not None else "local"
            self.finished_recordings.append(info)
            self.recorder = None
        if self.storage is not None:
            info["upload"] = "uploading"
            threading.Thread(target=self._upload, args=(rec, info), name="r2-upload", daemon=True).start()
        return info

    def _upload(self, rec: PairedRecorder, info: dict) -> None:
        """Upload finished files to R2, then delete the local temp copies.
        On failure the local file is KEPT (never silently lose the protected video)."""
        rid = rec.recording_id
        jobs = [(rec.protected.path, f"{PROTECTED_PREFIX}{self.session_id}/{rid}.mp4", "protected_key")]
        if rec.original is not None:
            jobs.append((rec.original.path, f"{RESTRICTED_PREFIX}{self.session_id}/{rid}_original.mp4",
                         "restricted_key"))
        try:
            for path, key, field in jobs:
                self.storage.upload(path, key)
                info[field] = key
                path.unlink(missing_ok=True)
            try:
                rec.protected.path.parent.rmdir()
            except OSError:
                pass
            info["upload"] = "uploaded"
        except Exception as exc:
            info["upload"] = f"FAILED ({type(exc).__name__}) — kept locally until retried"
            info["local_path"] = str(rec.protected.path)

    def _emit(self, events: list) -> None:
        for ev in events:
            for fn in list(self.listeners):
                try:
                    fn(ev)
                except Exception:
                    pass

    def _loop(self) -> None:
        next_due = 0.0
        next_analysis = 0.0
        while not self._stop.is_set():
            change = self.governor.tick()
            if change:
                self._source_event(change, {"thermal": self.governor.state, "profile": self.governor.active})
            prof = self.governor.profile()
            self.engine.signals_every = 1  # cadence is decided here via `analyze`
            f = self.capture.take(timeout_s=0.5)
            if f is None:
                if not self.capture.connected:
                    # no camera: show a slate (never stale/raw frames); recording gets no frames
                    self.error = "camera disconnected — waiting for the same device"
                    ok, jpg = cv2.imencode(".jpg", full_shield((self.settings.height, self.settings.width, 3),
                                                               "CAMERA DISCONNECTED"))
                    if ok:
                        self.latest_jpeg = jpg.tobytes()
                continue
            now = time.monotonic()
            interval = 1.0 / prof["process_fps"]
            if not admit_frame(now, next_due, interval):
                self.rate_skipped += 1
                continue  # faster than the profile's processing rate: drop (never queue)
            next_due = max(next_due + interval, now)
            self.error = None
            self.frame_id += 1
            frame, t_ms = f.bgr, f.t_capture_ms
            pkt = FramePacket(self.session_id, self.frame_id, t_ms, frame)
            a_int = 1.0 / prof["analyze_hz"]
            analyze = admit_frame(now, next_analysis, a_int)
            if analyze:
                next_analysis = max(next_analysis + a_int, now)
                self.analyzed += 1
            try:
                res = self.engine.step(pkt, analyze=analyze)
                protected = res.protected_bgr
                state = res.output_state
                self.vision_ms.append(res.vision_ms)
                events, tracks = res.events, res.tracks
            except Exception as exc:
                protected = full_shield(frame.shape, "ENGINE ERROR - SHIELDED")
                state, events, tracks = OutputState.ERROR, [], []
                self.error = type(exc).__name__
            with self._lock:
                if self.recorder is not None:
                    self.recorder.write(frame, protected, t_ms)
            # labels are drawn by the dashboard overlay now (crisper, animated); burn-in only if asked
            shown = preview_labels(protected, tracks) if self.settings.burn_in_labels else protected
            ok, jpg = cv2.imencode(".jpg", shown,
                                   [cv2.IMWRITE_JPEG_QUALITY, prof["jpeg_quality"]])
            if ok:
                self.latest_jpeg = jpg.tobytes()
            self.e2e_ms.append(self.now_ms() - t_ms)
            self.latest_tracks, self.output_state = tracks, state
            self.frame_times.append(time.monotonic())
            self._emit(events)

    def metrics(self) -> dict:
        ft = list(self.frame_times)
        fps = (len(ft) - 1) / (ft[-1] - ft[0]) if len(ft) > 1 and ft[-1] > ft[0] else 0.0

        def pct(values, q):
            v = sorted(values)
            return round(v[min(len(v) - 1, int(q * len(v)))], 1) if v else None

        try:
            import psutil
            self._proc = self._proc or psutil.Process()
            cpu, rss = round(self._proc.cpu_percent(None), 1), round(self._proc.memory_info().rss / 2**20)
        except Exception:
            cpu = rss = "unavailable"
        caps = self.source.capabilities() if hasattr(self.source, "capabilities") else {}
        return {"input_fps": self.capture.input_fps(), "processed_fps": round(fps, 1),
                "vision_ms_p50": pct(self.vision_ms, .5), "vision_ms_p95": pct(self.vision_ms, .95),
                "e2e_ms_p50": pct(self.e2e_ms, .5), "e2e_ms_p95": pct(self.e2e_ms, .95),
                "frames": self.frame_id, "captured": self.capture.frames_in,
                "dropped": self.capture.dropped, "rate_skipped": self.rate_skipped, "analyzed": self.analyzed,
                "analyze_hz": self.governor.profile()["analyze_hz"], "queue_depth": self.capture.queue_depth(),
                "active_tracks": len([t for t in self.latest_tracks if not t.get("coasting")]),
                "cpu_percent": cpu, "rss_mb": rss,
                "profile": self.governor.active, "profile_chosen": self.governor.chosen,
                "host_thermal": self.governor.state, "throttled": self.governor.throttled,
                "device_thermal": caps.get("thermal", "unavailable"),
                "device_battery": caps.get("battery", "unavailable")}

    def snapshot(self) -> dict:
        rec = self.recorder.info() if self.recorder else None
        return {
            "session_id": self.session_id,
            "source": self.source_label,
            "source_status": self.source.status() if hasattr(self.source, "status") else {},
            "source_capabilities": self.source.capabilities() if hasattr(self.source, "capabilities") else {},
            "camera_connected": self.capture.connected,
            "strict": self.engine.strict,
            "t_ms": self.now_ms(),
            "output_state": self.output_state.value,
            "error": self.error,
            "tracks": self.latest_tracks,
            "persons": self.engine.registry.snapshot(),
            "recording": rec,
            "finished_recordings": self.finished_recordings,
            "metrics": self.metrics(),
            "landmark_stalls": {"timeouts": getattr(self.engine.signals, "timeouts", 0),
                                "restarts": getattr(self.engine.signals, "restarts", 0)},
            "speaker_binding": "lip_motion_heuristic + single_candidate" if self.engine.signals else "single_candidate only (landmarker unavailable)",
            "gestures": "eyes closed 2 s / hands over eyes 1.5 s = blur; peace sign 1 s = unblur own face" if self.engine.signals else "unavailable",
            "events": list(self.engine.event_log)[-30:],
        }
