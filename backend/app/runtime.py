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

from backend.app.config import Settings
from backend.app.media.recorders import PairedRecorder
from backend.app.media.storage import PROTECTED_PREFIX, RESTRICTED_PREFIX
from backend.app.vision.engine import VisionEngine
from backend.app.vision.renderer import full_shield
from shared.contracts import FramePacket, OutputState


class Session:
    def __init__(self, settings: Settings, source, face_models, source_label: str, signals=None, storage=None):
        self.settings = settings
        self.session_id = "s_" + secrets.token_hex(4)
        self.source = source
        self.source_label = source_label  # "CAMERA" or "TEST INPUT: <file>"
        self.engine = VisionEngine(self.session_id, face_models.detect, face_models.feature, signals=signals)
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

    def now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def start(self) -> None:
        self.source.open()
        self._thread = threading.Thread(target=self._loop, name="vision-worker", daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        rec = self.stop_recording()
        self.source.close()
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
        while not self._stop.is_set():
            frame = self.source.read()
            t_ms = self.now_ms()
            if frame is None:
                self.error = "camera frame unavailable"
                time.sleep(0.05)
                continue
            self.error = None
            self.frame_id += 1
            frame.setflags(write=False)  # source is immutable from here on
            pkt = FramePacket(self.session_id, self.frame_id, t_ms, frame)
            try:
                res = self.engine.step(pkt)
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
            ok, jpg = cv2.imencode(".jpg", protected, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                self.latest_jpeg = jpg.tobytes()
            self.latest_tracks, self.output_state = tracks, state
            self.frame_times.append(time.monotonic())
            self._emit(events)

    def metrics(self) -> dict:
        ft = list(self.frame_times)
        fps = (len(ft) - 1) / (ft[-1] - ft[0]) if len(ft) > 1 and ft[-1] > ft[0] else 0.0
        vm = sorted(self.vision_ms)
        p = lambda q: round(vm[min(len(vm) - 1, int(q * len(vm)))], 1) if vm else None
        return {"processed_fps": round(fps, 1), "vision_ms_p50": p(0.5), "vision_ms_p95": p(0.95),
                "frames": self.frame_id}

    def snapshot(self) -> dict:
        rec = self.recorder.info() if self.recorder else None
        return {
            "session_id": self.session_id,
            "source": self.source_label,
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
