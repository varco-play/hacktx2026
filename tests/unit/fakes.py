"""Deterministic fake detector/features so engine privacy logic is testable without a camera."""
import numpy as np
from backend.app.vision.detector import Detection
from shared.contracts import FramePacket

rng = np.random.default_rng(7)
IDS = {k: (lambda v: v / np.linalg.norm(v))(rng.normal(size=(1, 128)).astype(np.float32)) for k in "ABCD"}
W, H = 640, 480


def face(who, x, y, size=100, score=0.95):
    raw = np.zeros(15, dtype=np.float32)
    raw[:4] = (x, y, size, size); raw[-1] = score
    d = Detection(box=(float(x), float(y), float(size), float(size)), score=score, raw=raw)
    d.who = who
    return d


class Script:
    def __init__(self):
        self.frame = []
        self.fail = False

    def detect(self, bgr):
        if self.fail:
            raise RuntimeError("detector exploded")
        return list(self.frame)

    def feature(self, bgr, det):
        noise = rng.normal(scale=0.02, size=(1, 128)).astype(np.float32)
        f = IDS[det.who] + noise
        return f / np.linalg.norm(f)


def packet(i, session="s_test"):
    img = np.full((H, W, 3), 128, np.uint8)
    img[:, :, 0] = (np.arange(W) % 256).astype(np.uint8)[None, :]  # textured so blur changes pixels
    img.setflags(write=False)
    return FramePacket(session, i, i * 66, img)
