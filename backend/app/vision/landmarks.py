"""MediaPipe face + hand landmarks -> per-frame evidence signals (not identity).

faces: [{"c": (x, y), "mouth": lip gap / eye distance, "eyes_closed": min(blinkL, blinkR)}]
hands: [{"c": palm center, "pts": [(x, y)*21], "peace": bool}]
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

UPPER_INNER, LOWER_INNER = 13, 14
EYE_L, EYE_R = 33, 263
WRIST = 0
PALM = (0, 5, 9, 13, 17)


def _angle(a, b, c) -> float:
    """Angle at b in degrees."""
    v1, v2 = a - b, c - b
    cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6))
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def is_peace(pts: np.ndarray) -> bool:
    """V sign: index + middle straight and spread, ring + pinky clearly bent (thumb ignored).

    Strict on purpose: curled fingers touching a face must not count (seen in real footage).
    pts: (21, 2) pixel landmarks.
    """
    palm = float(np.linalg.norm(pts[9] - pts[0])) + 1e-6
    straight = lambda m, p, d, t: _angle(pts[m], pts[p], pts[t]) > 155 and _angle(pts[p], pts[d], pts[t]) > 150
    bent = lambda m, p, t: _angle(pts[m], pts[p], pts[t]) < 120
    if not (straight(5, 6, 7, 8) and straight(9, 10, 11, 12)):
        return False
    if not (bent(13, 14, 16) and bent(17, 18, 20)):
        return False
    if min(np.linalg.norm(pts[8] - pts[5]), np.linalg.norm(pts[12] - pts[9])) < 0.75 * palm:
        return False  # raised fingers must be long relative to the palm
    v1, v2 = pts[8] - pts[5], pts[12] - pts[9]
    spread = _angle(pts[5] + v1, pts[5], pts[5] + v2)
    return spread >= 10.0


class Signals:
    def __init__(self, models_dir: str | Path, max_faces: int = 4, max_hands: int = 4, hands_every: int = 2):
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        self._mp = mp
        d = Path(models_dir)
        self.face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(d / "face_landmarker.task")),
            running_mode=vision.RunningMode.VIDEO, num_faces=max_faces, output_face_blendshapes=True,
            min_face_detection_confidence=0.4, min_tracking_confidence=0.4))
        self.hand = None
        if (d / "hand_landmarker.task").is_file():
            self.hand = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=str(d / "hand_landmarker.task")),
                running_mode=vision.RunningMode.VIDEO, num_hands=max_hands,
                min_hand_detection_confidence=0.5, min_tracking_confidence=0.5))
        self.hands_every = hands_every
        self._n = 0
        self._last_ts = -1
        self._last_hands: list = []

    def __call__(self, bgr: np.ndarray, t_ms: int) -> dict:
        ts = max(int(t_ms), self._last_ts + 1)  # VIDEO mode needs strictly increasing timestamps
        self._last_ts = ts
        h, w = bgr.shape[:2]
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        faces = []
        fr = self.face.detect_for_video(img, ts)
        for i, lms in enumerate(fr.face_landmarks):
            pt = lambda k: np.array([lms[k].x * w, lms[k].y * h])
            eye = np.linalg.norm(pt(EYE_L) - pt(EYE_R))
            if eye < 5:
                continue
            bs = {b.category_name: b.score for b in fr.face_blendshapes[i]} if fr.face_blendshapes else {}
            c = (pt(EYE_L) + pt(EYE_R) + pt(UPPER_INNER)) / 3
            faces.append({"c": (float(c[0]), float(c[1])),
                          "mouth": float(np.linalg.norm(pt(UPPER_INNER) - pt(LOWER_INNER)) / eye),
                          "eyes_closed": float(min(bs.get("eyeBlinkLeft", 0.0), bs.get("eyeBlinkRight", 0.0)))})
        self._n += 1
        if self.hand is not None and self._n % self.hands_every == 0:
            hands = []
            for lms in self.hand.detect_for_video(img, ts).hand_landmarks:
                pts = np.array([[p.x * w, p.y * h] for p in lms], dtype=np.float32)
                c = pts[list(PALM)].mean(axis=0)
                hands.append({"c": (float(c[0]), float(c[1])), "pts": pts, "peace": is_peace(pts)})
            self._last_hands = hands
        return {"faces": faces, "hands": self._last_hands}
