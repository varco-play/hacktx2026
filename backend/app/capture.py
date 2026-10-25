"""The ONE camera owner. Nothing else in the app may open the camera."""
from __future__ import annotations

import threading
import time
from typing import Optional

import cv2
import numpy as np


class CameraSource:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480, fps: int = 15):
        self.index, self.width, self.height, self.fps = index, width, height, fps
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> None:
        cap = cv2.VideoCapture(self.index, cv2.CAP_AVFOUNDATION)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not cap.isOpened():
            raise RuntimeError("camera not available (check macOS Camera permission for this app)")
        self.cap = cap

    def read(self) -> Optional[np.ndarray]:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok:
            return None
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))
        return frame

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class FileSource:
    """Replays a local video file as if it were the camera (labeled TEST INPUT)."""

    def __init__(self, path: str, width: int = 640, height: int = 480, fps: int = 15, loop: bool = True):
        self.path, self.width, self.height, self.fps, self.loop = path, width, height, fps, loop
        self.cap: Optional[cv2.VideoCapture] = None
        self._next_t = 0.0

    def open(self) -> None:
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open test video {self.path}")

    def read(self) -> Optional[np.ndarray]:
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
        return cv2.resize(frame, (self.width, self.height))

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
