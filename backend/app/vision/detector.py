"""YuNet face detection + SFace features (local, session-only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"


@dataclass
class Detection:
    box: tuple  # (x, y, w, h) floats
    score: float
    raw: np.ndarray  # YuNet row (15 values + score) needed for alignCrop


class FaceModels:
    def __init__(self, models_dir: str | Path, score_threshold: float = 0.7):
        d = Path(models_dir)
        for f in (YUNET, SFACE):
            if not (d / f).is_file():
                raise FileNotFoundError(f"missing model {d / f}; run scripts/fetch_models.sh")
        self.detector = cv2.FaceDetectorYN.create(str(d / YUNET), "", (320, 320),
                                                  score_threshold, 0.3, 20)
        self.recognizer = cv2.FaceRecognizerSF.create(str(d / SFACE), "")
        self._size = None

    def detect(self, bgr: np.ndarray) -> list[Detection]:
        h, w = bgr.shape[:2]
        if self._size != (w, h):
            self.detector.setInputSize((w, h))
            self._size = (w, h)
        _, faces = self.detector.detect(bgr)
        if faces is None:
            return []
        return [Detection(box=tuple(float(v) for v in f[:4]), score=float(f[-1]), raw=f)
                for f in faces]

    def feature(self, bgr: np.ndarray, det: Detection) -> np.ndarray:
        aligned = self.recognizer.alignCrop(bgr, det.raw)
        f = self.recognizer.feature(aligned).astype(np.float32)
        return f / (np.linalg.norm(f) + 1e-9)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a.ravel(), b.ravel()))
