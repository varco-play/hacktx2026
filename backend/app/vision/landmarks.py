"""MediaPipe Face Landmarker -> per-face mouth openness (lip-motion evidence, not identity)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

UPPER_INNER, LOWER_INNER = 13, 14
EYE_L, EYE_R = 33, 263


class MouthTracker:
    def __init__(self, models_dir: str | Path, max_faces: int = 4):
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        self._mp = mp
        opts = vision.FaceLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(Path(models_dir) / "face_landmarker.task")),
            running_mode=vision.RunningMode.VIDEO, num_faces=max_faces,
            min_face_detection_confidence=0.4, min_tracking_confidence=0.4)
        self.landmarker = vision.FaceLandmarker.create_from_options(opts)
        self._last_ts = -1

    def __call__(self, bgr: np.ndarray, t_ms: int) -> list[tuple[float, float, float]]:
        """Returns [(center_x, center_y, openness)] in pixel coords; openness is lip gap / eye distance."""
        ts = max(int(t_ms), self._last_ts + 1)  # VIDEO mode needs strictly increasing timestamps
        self._last_ts = ts
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        res = self.landmarker.detect_for_video(
            self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb), ts)
        h, w = bgr.shape[:2]
        out = []
        for lms in res.face_landmarks:
            pt = lambda i: np.array([lms[i].x * w, lms[i].y * h])
            eye = np.linalg.norm(pt(EYE_L) - pt(EYE_R))
            if eye < 5:
                continue
            gap = np.linalg.norm(pt(UPPER_INNER) - pt(LOWER_INNER))
            c = (pt(EYE_L) + pt(EYE_R) + pt(UPPER_INNER)) / 3
            out.append((float(c[0]), float(c[1]), float(gap / eye)))
        return out
