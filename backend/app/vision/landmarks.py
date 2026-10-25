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
    # Live-tested MVP thresholds (2/2 real peace signs detected, 0 false releases on replays).
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


class _Landmarkers:
    """MediaPipe face + hand landmarkers owned by ONE worker thread."""

    def __init__(self, models_dir: Path, max_faces: int, max_hands: int):
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        self._mp = mp
        self.face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(models_dir / "face_landmarker.task")),
            running_mode=vision.RunningMode.VIDEO, num_faces=max_faces, output_face_blendshapes=True,
            min_face_detection_confidence=0.4, min_tracking_confidence=0.4))
        self.hand = None
        if (models_dir / "hand_landmarker.task").is_file():
            self.hand = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=str(models_dir / "hand_landmarker.task")),
                running_mode=vision.RunningMode.VIDEO, num_hands=max_hands,
                min_hand_detection_confidence=0.5, min_tracking_confidence=0.5))
        self.pose = None
        import os
        # Pose links each hand to its own body (who made the gesture). On by default.
        if os.getenv("POSE_TRACKING", "on").lower() in ("1", "on", "true") and \
                (models_dir / "pose_landmarker_lite.task").is_file():
            self.pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=str(models_dir / "pose_landmarker_lite.task")),
                running_mode=vision.RunningMode.VIDEO, num_poses=max_faces,
                min_pose_detection_confidence=0.5, min_tracking_confidence=0.5))
        self.last_ts = -1


HEAD_POINTS = range(0, 11)   # nose, eyes, ears, mouth corners (visible even in profile)
SHOULDERS = (11, 12)
WRISTS = (15, 16)
BODY_POINTS = range(0, 25)   # head, shoulders, arms, hands, hips


def body_box(pts: np.ndarray, vis: np.ndarray) -> tuple | None:
    """Bounding box of the visible upper body (for showing whose hands are whose)."""
    p = np.array([pts[i] for i in BODY_POINTS if vis[i] > 0.5])
    if len(p) < 4:
        return None
    x0, y0 = p.min(axis=0)
    x1, y1 = p.max(axis=0)
    return (float(x0), float(y0), float(x1 - x0), float(y1 - y0))


def head_box(pts: np.ndarray, vis: np.ndarray) -> tuple | None:
    """Head box from pose keypoints; works for profile / back-of-head where face detectors fail."""
    head = [pts[i] for i in HEAD_POINTS if vis[i] > 0.5]
    if len(head) < 2:
        return None
    head = np.array(head)
    cx, cy = head.mean(axis=0)
    span = float(max(np.ptp(head[:, 0]), np.ptp(head[:, 1])))
    if vis[SHOULDERS[0]] > 0.5 and vis[SHOULDERS[1]] > 0.5:
        span = max(span, 0.45 * float(np.linalg.norm(pts[SHOULDERS[0]] - pts[SHOULDERS[1]])))
    size = max(span * 1.5, 30.0)
    return (float(cx - size / 2), float(cy - size * 0.55), size, size * 1.1)


class Signals:
    """Landmark evidence with a time budget so MediaPipe can never freeze the vision loop.

    Detection runs on a dedicated worker thread. If a frame exceeds `budget_ms` the
    caller gets no evidence for that frame (gestures/lips pause; blur decisions are
    unaffected). If the worker stays stuck for `restart_ms`, it is abandoned and a
    fresh worker with new landmarkers takes over. (Observed once: an intermittent
    MediaPipe stall under heavy CPU load, 2026-10-25.)
    """

    def __init__(self, models_dir: str | Path, max_faces: int = 4, max_hands: int = 4, hands_every: int = 2,
                 budget_ms: int = 120, restart_ms: int = 2000):
        from concurrent.futures import ThreadPoolExecutor
        self._Executor = ThreadPoolExecutor
        self.models_dir, self.max_faces, self.max_hands = Path(models_dir), max_faces, max_hands
        self.hands_every, self.budget_ms, self.restart_ms = hands_every, budget_ms, restart_ms
        self._n = 0
        self._last_hands: list = []
        self._last_heads: list = []
        self.timeouts = 0
        self.restarts = 0
        self._start_worker()
        self._lm = self._pool.submit(_Landmarkers, self.models_dir, max_faces, max_hands).result()
        self._pending = None
        self._pending_since = 0.0

    def _start_worker(self) -> None:
        self._pool = self._Executor(max_workers=1, thread_name_prefix="landmarks")

    supports_heavy = True  # engine may ask for face-only frames

    def __call__(self, bgr: np.ndarray, t_ms: int, heavy: bool = True) -> dict:
        """Face landmarks (lips, eyes) on EVERY call — they are the cheap part and lip timing
        needs density for "who spoke". Hands/pose (heavier) only when heavy=True, alternating."""
        import time as _t
        from concurrent.futures import TimeoutError as _Timeout
        now = _t.monotonic()
        cached = {"faces": [], "hands": self._last_hands, "heads": self._last_heads, "stalled": True}
        if self._pending is not None and not self._pending.done():
            if (now - self._pending_since) * 1000 > self.restart_ms:
                self._pool.shutdown(wait=False, cancel_futures=True)  # abandon the stuck worker
                self._start_worker()
                self._lm = self._pool.submit(_Landmarkers, self.models_dir, self.max_faces, self.max_hands).result()
                self._pending = None
                self.restarts += 1
            return cached
        do_hands = do_pose = False
        if heavy:
            self._n += 1
            do_hands = self._n % self.hands_every == 0
            do_pose = not do_hands
        fut = self._pool.submit(self._detect, self._lm, bgr, int(t_ms), do_hands, do_pose)
        try:
            faces, hands, heads = fut.result(timeout=self.budget_ms / 1000)
        except _Timeout:
            self.timeouts += 1
            self._pending, self._pending_since = fut, now
            return cached
        self._pending = None
        if hands is not None:
            self._last_hands = hands
        if heads is not None:
            self._last_heads = heads
        return {"faces": faces, "hands": self._last_hands, "heads": self._last_heads}

    @staticmethod
    def _detect(lm: _Landmarkers, bgr: np.ndarray, t_ms: int, do_hands: bool, do_pose: bool = None):
        ts = max(t_ms, lm.last_ts + 1)  # VIDEO mode needs strictly increasing timestamps
        lm.last_ts = ts
        h, w = bgr.shape[:2]
        img = lm._mp.Image(image_format=lm._mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        faces = []
        fr = lm.face.detect_for_video(img, ts)
        for i, lms in enumerate(fr.face_landmarks):
            pt = lambda k: np.array([lms[k].x * w, lms[k].y * h])
            eye = np.linalg.norm(pt(EYE_L) - pt(EYE_R))
            if eye < 5:
                continue
            bs = {b.category_name: b.score for b in fr.face_blendshapes[i]} if fr.face_blendshapes else {}
            c = (pt(EYE_L) + pt(EYE_R) + pt(UPPER_INNER)) / 3
            faces.append({"c": (float(c[0]), float(c[1])),
                          "mouth": float(np.linalg.norm(pt(UPPER_INNER) - pt(LOWER_INNER)) / eye),
                          "eyes_closed": float(min(bs.get("eyeBlinkLeft", 0.0), bs.get("eyeBlinkRight", 0.0))),
                          "look_down": float(min(bs.get("eyeLookDownLeft", 0.0), bs.get("eyeLookDownRight", 0.0)))})
        hands = heads = None
        if do_pose is None:
            do_pose = not do_hands
        if lm.pose is not None and do_pose:
            heads = []  # one entry per detected BODY (pose): head box, body box, nose, wrists
            for pl in lm.pose.detect_for_video(img, ts).pose_landmarks:
                pts = np.array([[p.x * w, p.y * h] for p in pl], dtype=np.float32)
                vis = np.array([getattr(p, "visibility", 1.0) or 0.0 for p in pl], dtype=np.float32)
                b = head_box(pts, vis)
                if b is None:
                    continue
                heads.append({"box": b, "body": body_box(pts, vis),
                              "nose": tuple(map(float, pts[0])) if vis[0] > 0.5 else None,
                              "wrists": [tuple(map(float, pts[i])) for i in WRISTS if vis[i] > 0.3],
                              "shoulder_w": float(np.linalg.norm(pts[11] - pts[12])) if min(vis[11], vis[12]) > 0.5 else None})
        if lm.hand is not None and do_hands:
            hands = []
            for hl in lm.hand.detect_for_video(img, ts).hand_landmarks:
                pts = np.array([[p.x * w, p.y * h] for p in hl], dtype=np.float32)
                c = pts[list(PALM)].mean(axis=0)
                hands.append({"c": (float(c[0]), float(c[1])), "pts": pts, "peace": is_peace(pts)})
        return faces, hands, heads
