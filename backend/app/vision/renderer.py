"""Writes protection into real pixels of a COPY of the source frame."""
from __future__ import annotations

import cv2
import numpy as np

SHIELD_COLOR = (40, 40, 40)


def pad_box(box, frame_shape, pad: float = 0.45):
    """Expand (x, y, w, h) to cover head/hair; clip to frame. Returns ints."""
    x, y, w, h = box
    H, W = frame_shape[:2]
    px, py = w * pad, h * pad
    x0 = int(max(0, x - px))
    y0 = int(max(0, y - py * 1.2))  # more room above for hair
    x1 = int(min(W, x + w + px))
    y1 = int(min(H, y + h + py))
    return x0, y0, x1, y1


def pixelate_region(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    roi = img[y0:y1, x0:x1]
    if roi.size == 0:
        return
    h, w = roi.shape[:2]
    small = cv2.resize(roi, (max(1, w // 16), max(1, h // 16)), interpolation=cv2.INTER_LINEAR)
    blocky = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    img[y0:y1, x0:x1] = cv2.GaussianBlur(blocky, (0, 0), sigmaX=max(2, w / 20))


def render_protected(src: np.ndarray, regions: list) -> np.ndarray:
    """regions: list of (x, y, w, h) boxes to obscure. Never mutates `src`."""
    out = src.copy()
    for box in regions:
        x0, y0, x1, y1 = pad_box(box, out.shape)
        pixelate_region(out, x0, y0, x1, y1)
    return out


def full_shield(shape, label: str = "PROTECTED OUTPUT PAUSED") -> np.ndarray:
    """Slate that contains no source pixels at all."""
    out = np.full(shape, SHIELD_COLOR, dtype=np.uint8)
    cv2.putText(out, label, (20, shape[0] // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (220, 220, 220), 2, cv2.LINE_AA)
    return out
