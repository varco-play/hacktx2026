"""Live encoders written during capture (no offline re-render).

Protected writer only ever receives FrameResult.protected_bgr. The diagnostic
original writer is created only when ENABLE_DIAGNOSTIC_ORIGINAL=true.
"""
from __future__ import annotations

import secrets
import threading
from fractions import Fraction
from pathlib import Path
from typing import Optional

import av
import numpy as np


class VideoWriter:
    def __init__(self, path: Path, width: int, height: int, fps: int = 15):
        self.path = path
        self.container = av.open(str(path), mode="w")
        self.stream = self.container.add_stream("libx264", rate=fps)
        self.stream.width, self.stream.height = width, height
        self.stream.pix_fmt = "yuv420p"
        self.stream.time_base = Fraction(1, 1000)
        # Encoder must also count in ms: camera may deliver 30 fps while rate=15,
        # and 1/15 s codec ticks would give two frames the same DTS (EINVAL 22).
        self.stream.codec_context.time_base = Fraction(1, 1000)
        self.stream.options = {"preset": "ultrafast", "crf": "23"}
        self.last_pts = -1
        self.frames = 0

    def write(self, bgr: np.ndarray, t_ms: int) -> None:
        pts = max(int(t_ms), self.last_pts + 1)  # strictly increasing
        frame = av.VideoFrame.from_ndarray(bgr, format="bgr24")
        frame.pts, frame.time_base = pts, Fraction(1, 1000)
        for packet in self.stream.encode(frame):
            self.container.mux(packet)
        self.last_pts = pts
        self.frames += 1

    def close(self) -> None:
        for packet in self.stream.encode():
            self.container.mux(packet)
        self.container.close()


class PairedRecorder:
    """One recording = protected (+ optional diagnostic original), same timestamps."""

    def __init__(self, out_dir: Path, width: int, height: int, fps: int,
                 diagnostic_original: bool, t0_ms: int):
        out_dir.mkdir(parents=True, exist_ok=True)
        self.recording_id = "rec_" + secrets.token_hex(6)
        self.t0_ms = t0_ms
        self.protected = VideoWriter(out_dir / f"{self.recording_id}_protected.mp4", width, height, fps)
        self.original: Optional[VideoWriter] = None
        if diagnostic_original:
            self.original = VideoWriter(out_dir / f"{self.recording_id}_original_DIAGNOSTIC.mp4",
                                        width, height, fps)
        self.lock = threading.Lock()
        self.closed = False
        self.error: Optional[str] = None

    def write(self, source_bgr: np.ndarray, protected_bgr: np.ndarray, t_ms: int) -> None:
        with self.lock:
            if self.closed:
                return
            rel = t_ms - self.t0_ms
            try:
                self.protected.write(protected_bgr, rel)
                if self.original is not None:
                    self.original.write(source_bgr, rel)
            except Exception as exc:  # disk/encoder failure: stop, do not pretend
                self.error = f"{type(exc).__name__}: {exc}"
                self._close_locked()

    def close(self) -> dict:
        with self.lock:
            self._close_locked()
            return self.info()

    def _close_locked(self) -> None:
        if self.closed:
            return
        self.closed = True
        for w in (self.protected, self.original):
            if w is not None:
                try:
                    w.close()
                except Exception as exc:
                    self.error = self.error or f"close failed: {exc}"

    def info(self) -> dict:
        return {
            "recording_id": self.recording_id,
            "closed": self.closed,
            "frames": self.protected.frames,
            "has_diagnostic_original": self.original is not None,
            "error": self.error,
        }


def probe(path: Path) -> dict:
    """Open an encoded file and count decodable frames (proves playability)."""
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        n = 0
        last = None
        for fr in c.decode(s):
            n += 1
            last = fr
        dur = float(last.pts * last.time_base) if last is not None and last.pts is not None else 0.0
        return {"frames": n, "width": s.codec_context.width, "height": s.codec_context.height,
                "duration_s": round(dur, 2), "codec": s.codec_context.name}
