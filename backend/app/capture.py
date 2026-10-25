"""Camera source layer: every input (USB phone, built-in camera, video file, companion-app
stream from Meta glasses / Meta Mock Device) implements the same interface, so the
engine, consent logic and recorder never know where frames come from.

Only ONE source is open at a time (one camera owner), driven by CaptureWorker.
"""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

import cv2
import numpy as np


@dataclass
class Frame:
    bgr: np.ndarray            # uint8 HxWx3, read-only once produced
    seq: int                   # per-source sequence number
    t_capture_ms: int          # session monotonic clock when the frame was received
    source_id: str
    rotation: int = 0          # degrees clockwise as reported by the source (0 if unknown)
    meta: dict = field(default_factory=dict)


class CameraSource(Protocol):
    source_id: str
    kind: str                  # "usb_camera" | "builtin_camera" | "video_file" | "companion_stream"

    def initialize(self) -> None: ...
    def start(self) -> None: ...
    def read(self, timeout_s: float = 1.0) -> Optional[np.ndarray]: ...
    def stop(self) -> None: ...
    def cleanup(self) -> None: ...
    def capabilities(self) -> dict: ...
    def status(self) -> dict: ...


# ---------------------------------------------------------------- device discovery

def list_video_devices() -> list[dict]:
    """AVFoundation video devices in the same order OpenCV's AVFoundation backend uses.
    Each: {index, name, unique_id, kind}. Empty list if unavailable."""
    try:
        import AVFoundation as AVF
        devs = AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo)
    except Exception:
        return []
    out = []
    for i, d in enumerate(devs):
        dtype = str(d.deviceType())
        kind = "builtin_camera" if "BuiltIn" in dtype else "usb_camera"  # external / Continuity / USB phone
        out.append({"index": i, "name": str(d.localizedName()), "unique_id": str(d.uniqueID()),
                    "kind": kind, "device_type": dtype})
    return out


def resolve_device(selector: str) -> Optional[dict]:
    """selector: "" (first external, else built-in), an index "1", or part of a name ("iPhone")."""
    devs = list_video_devices()
    if not devs:
        return None
    if selector == "":
        ext = [d for d in devs if d["kind"] == "usb_camera"]
        return ext[0] if ext else devs[0]
    if selector.isdigit():
        return next((d for d in devs if d["index"] == int(selector)), None)
    return next((d for d in devs if selector.lower() in d["name"].lower()), None)


# ---------------------------------------------------------------- adapters

class AVFoundationCameraSource:
    """USB phone webcam (iPhone Continuity Camera, Camo/DroidCam, any UVC) or the built-in
    camera. Bound to a device by unique ID so an unplugged phone is never silently replaced
    by the laptop camera on reconnect."""

    def __init__(self, selector: str = "", width: int = 640, height: int = 480, fps: int = 30):
        self.selector, self.width, self.height, self.fps = selector, width, height, fps
        self.cap: Optional[cv2.VideoCapture] = None
        self.device: Optional[dict] = None
        self.source_id, self.kind = "camera:unresolved", "usb_camera"
        self._state, self._error = "IDLE", None
        self._native = (0, 0)

    def initialize(self) -> None:
        dev = resolve_device(self.selector)
        if dev is None:
            if not self.selector or self.selector.isdigit():  # pyobjc unavailable: fall back to index
                dev = {"index": int(self.selector or 0), "name": f"camera {self.selector or 0}",
                       "unique_id": "", "kind": "usb_camera"}
            else:
                raise RuntimeError(f"no camera matching '{self.selector}' (see /api/sources)")
        self.device = dev
        self.kind = dev["kind"]
        self.source_id = f"{dev['kind']}:{dev['name']}"

    def start(self) -> None:
        if self.device is None:
            self.initialize()
        cap = cv2.VideoCapture(self.device["index"], cv2.CAP_AVFOUNDATION)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not cap.isOpened():
            self._state, self._error = "ERROR", "camera not available (macOS Camera permission? device busy?)"
            raise RuntimeError(self._error)
        self.cap = cap
        self._native = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self._state, self._error = "STREAMING", None

    def still_present(self) -> bool:
        if not self.device or not self.device.get("unique_id"):
            return True
        return any(d["unique_id"] == self.device["unique_id"] for d in list_video_devices())

    def reopen(self) -> bool:
        """Reconnect only to the SAME physical device (index may have changed)."""
        self.stop()
        if not self.still_present():
            self._state = "DISCONNECTED"
            return False
        uid = self.device.get("unique_id")
        if uid:
            dev = next((d for d in list_video_devices() if d["unique_id"] == uid), None)
            if dev is None:
                return False
            self.device = dev
        try:
            self.start()
            return True
        except RuntimeError:
            self._state = "DISCONNECTED"
            return False

    def read(self, timeout_s: float = 1.0) -> Optional[np.ndarray]:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)
        return frame

    def stop(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self._state == "STREAMING":
            self._state = "STOPPED"

    cleanup = stop

    def capabilities(self) -> dict:
        return {"kind": self.kind, "device": (self.device or {}).get("name"),
                "native_resolution": list(self._native), "output_resolution": [self.width, self.height],
                "requested_fps": self.fps, "audio": False, "thermal": "unavailable", "battery": "unavailable"}

    def status(self) -> dict:
        return {"state": self._state, "error": self._error, "source_id": self.source_id}


class VideoFileSource:
    """Deterministic replay of a local file, paced at `fps`. Always labeled TEST INPUT."""

    def __init__(self, path: str, width: int = 640, height: int = 480, fps: int = 15, loop: bool = True):
        self.path, self.width, self.height, self.fps, self.loop = path, width, height, fps, loop
        self.cap: Optional[cv2.VideoCapture] = None
        self._next_t = 0.0
        self.source_id, self.kind = f"video_file:{path.rsplit('/', 1)[-1]}", "video_file"
        self._state = "IDLE"

    def initialize(self) -> None:
        pass

    def start(self) -> None:
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            self._state = "ERROR"
            raise RuntimeError(f"cannot open test video {self.path}")
        self._state = "STREAMING"

    def reopen(self) -> bool:
        return False

    def read(self, timeout_s: float = 1.0) -> Optional[np.ndarray]:
        if self.cap is None:
            return None
        now = time.monotonic()
        if now < self._next_t:
            time.sleep(self._next_t - now)
        self._next_t = time.monotonic() + 1.0 / self.fps
        ok, frame = self.cap.read()
        if not ok and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if not ok:
            return None
        return cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)

    def stop(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self._state = "STOPPED"

    cleanup = stop

    def capabilities(self) -> dict:
        return {"kind": "video_file", "output_resolution": [self.width, self.height], "fps": self.fps,
                "audio": False, "thermal": "unavailable", "battery": "unavailable"}

    def status(self) -> dict:
        return {"state": self._state, "error": None, "source_id": self.source_id}


class CompanionStreamSource:
    """Frames pushed by the iOS companion app over WebSocket (/api/ingest).

    Real path: Meta glasses -> Wearables Device Access Toolkit (MWDATCamera) -> companion
    app -> here. With the SDK's MWDATMockDevice the same app forwards mock frames. The
    origin ("meta_glasses" / "meta_mock_device" / "phone_camera") is REPORTED BY THE APP;
    this server cannot verify it and labels it as reported.
    """

    def __init__(self, width: int = 640, height: int = 480):
        self.width, self.height = width, height
        self.kind = "companion_stream"
        self.source_id = "companion:waiting"
        self._cv = threading.Condition()
        self._latest: Optional[np.ndarray] = None
        self._latest_meta: dict = {}
        self._seq = itertools.count(1)
        self.received = 0
        self.dropped = 0
        self.last_rx = 0.0
        self.device_state: dict = {}
        self._state = "WAITING_FOR_APP"

    def initialize(self) -> None:
        pass

    def start(self) -> None:
        self._state = "WAITING_FOR_APP"

    def push(self, jpeg: bytes, header: dict) -> bool:
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return False
        if img.shape[1] != self.width or img.shape[0] != self.height:
            img = cv2.resize(img, (self.width, self.height), interpolation=cv2.INTER_AREA)
        with self._cv:
            if self._latest is not None:
                self.dropped += 1  # processing hasn't taken the previous frame: drop stale
            self._latest, self._latest_meta = img, header
            self.received += 1
            self.last_rx = time.monotonic()
            origin = str(header.get("origin", "unknown"))[:40]
            self.source_id = f"companion:{origin} (reported by app)"
            self.device_state = {k: header[k] for k in ("thermal_state", "battery_level", "stream_state")
                                 if k in header}
            self._state = "STREAMING"
            self._cv.notify()
        return True

    def read(self, timeout_s: float = 1.0) -> Optional[np.ndarray]:
        with self._cv:
            if self._latest is None:
                self._cv.wait(timeout_s)
            img, self._latest = self._latest, None
        if img is None and self._state == "STREAMING" and time.monotonic() - self.last_rx > 2.0:
            self._state = "DISCONNECTED"
        return img

    def reopen(self) -> bool:
        return self._state == "STREAMING"

    def stop(self) -> None:
        self._state = "STOPPED"

    cleanup = stop

    def capabilities(self) -> dict:
        return {"kind": "companion_stream", "output_resolution": [self.width, self.height], "audio": False,
                "thermal": self.device_state.get("thermal_state", "unavailable"),
                "battery": self.device_state.get("battery_level", "unavailable")}

    def status(self) -> dict:
        return {"state": self._state, "error": None, "source_id": self.source_id,
                "received": self.received, "dropped_at_ingest": self.dropped, **self.device_state}


# ---------------------------------------------------------------- capture worker

class CaptureWorker:
    """Reads the source on its own thread and keeps only the LATEST frame.

    The processing loop takes frames at its own pace; anything it didn't get to is dropped
    (counted) instead of queuing, so latency never accumulates. Handles disconnects by
    retrying the same device every 2 s without ever substituting another camera."""

    def __init__(self, source, now_ms, on_event=lambda type_, details: None):
        self.source, self.now_ms, self.on_event = source, now_ms, on_event
        self._cv = threading.Condition()
        self._latest: Optional[Frame] = None
        self._seq = itertools.count(1)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.frames_in = 0
        self.dropped = 0
        self.connected = False
        self._t_in = []

    def start(self) -> None:
        self.source.initialize()
        self.source.start()
        self.connected = True
        self._thread = threading.Thread(target=self._loop, name="capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self.source.cleanup()

    def _loop(self) -> None:
        misses = 0
        while not self._stop.is_set():
            img = self.source.read(timeout_s=0.5)
            if img is None:
                misses += 1
                if self.connected and (misses >= 15 or self.source.status().get("state") == "DISCONNECTED"):
                    self.connected = False
                    self.on_event("CAMERA_DISCONNECTED", {"source": self.source.source_id})
                if not self.connected:
                    if getattr(self.source, "reopen", lambda: False)():
                        self.connected, misses = True, 0
                        self.on_event("CAMERA_RECONNECTED", {"source": self.source.source_id})
                    else:
                        self._stop.wait(2.0)
                continue
            misses = 0
            if not self.connected:
                self.connected = True
                self.on_event("CAMERA_RECONNECTED", {"source": self.source.source_id})
            img.setflags(write=False)
            f = Frame(img, next(self._seq), self.now_ms(), self.source.source_id)
            with self._cv:
                if self._latest is not None:
                    self.dropped += 1
                self._latest = f
                self.frames_in += 1
                self._t_in.append(time.monotonic())
                self._t_in = self._t_in[-60:]
                self._cv.notify()

    def take(self, timeout_s: float = 0.5) -> Optional[Frame]:
        with self._cv:
            if self._latest is None:
                self._cv.wait(timeout_s)
            f, self._latest = self._latest, None
            return f

    def queue_depth(self) -> int:
        return 1 if self._latest is not None else 0

    def input_fps(self) -> float:
        t = self._t_in
        return round((len(t) - 1) / (t[-1] - t[0]), 1) if len(t) > 1 and t[-1] > t[0] else 0.0


# Back-compat names
CameraSource_ = AVFoundationCameraSource
FileSource = VideoFileSource
