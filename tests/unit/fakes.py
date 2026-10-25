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
    raw[4:10] = (x + 0.3 * size, y + 0.4 * size, x + 0.7 * size, y + 0.4 * size, x + 0.5 * size, y + 0.6 * size)
    d = Detection(box=(float(x), float(y), float(size), float(size)), score=score, raw=raw)
    d.who = who
    return d


class Script:
    def __init__(self):
        self.frame = []
        self.fail = False
        self.sig = {"faces": [], "hands": []}
        self.bad_feature_for = set()  # who -> return an off-identity feature (bad pose/blur)
        self.rng = np.random.default_rng(11)  # per-script: tests don't depend on run order

    def signals(self, bgr, t_ms):
        return self.sig

    def detect(self, bgr):
        if self.fail:
            raise RuntimeError("detector exploded")
        return list(self.frame)

    def feature(self, bgr, det):
        if det.who in self.bad_feature_for:
            v = self.rng.normal(size=(1, 128)).astype(np.float32)
            return v / np.linalg.norm(v)
        noise = self.rng.normal(scale=0.02, size=(1, 128)).astype(np.float32)
        f = IDS[det.who] + noise
        return f / np.linalg.norm(f)


def packet(i, session="s_test"):
    img = np.full((H, W, 3), 128, np.uint8)
    img[:, :, 0] = (np.arange(W) % 256).astype(np.uint8)[None, :]  # textured so blur changes pixels
    img.setflags(write=False)
    return FramePacket(session, i, i * 66, img)


def face_sig(x, y, size=100, eyes_closed=0.0, mouth=0.03):
    return {"c": (x + size / 2, y + size * 0.45), "mouth": mouth, "eyes_closed": eyes_closed}


def hand(cx, cy, peace=False, pts=None):
    if pts is None:
        pts = np.array([[cx + dx, cy + dy] for dx, dy in zip(range(-10, 11), range(-10, 11))], np.float32)
    return {"c": (cx, cy), "pts": pts, "peace": peace}


def hand_over_eyes(x, y, size=100):
    """21 points spread across the eye band of a face box (both halves)."""
    xs = np.linspace(x + 5, x + size - 5, 21)
    pts = np.stack([xs, np.full(21, y + 0.35 * size)], axis=1).astype(np.float32)
    return {"c": (x + size / 2, y + 0.35 * size), "pts": pts, "peace": False}
