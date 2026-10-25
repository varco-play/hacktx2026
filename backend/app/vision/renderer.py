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


def obscure(roi: np.ndarray) -> np.ndarray:
    """Irreversible frosted blur: ~12x downscale destroys facial detail, then smooth upscale."""
    h, w = roi.shape[:2]
    small = cv2.resize(roi, (max(2, w // 12), max(2, h // 12)), interpolation=cv2.INTER_AREA)
    up = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(up, (0, 0), sigmaX=max(2.0, w / 18))


def oval_mask(w: int, h: int) -> np.ndarray:
    """Float mask 0..1: solid ellipse filling the box, feathered only at its outer rim.
    The face box sits at ~0.5 of the ellipse radius after padding, so the soft edge never
    reaches facial features."""
    m = np.zeros((h, w), np.uint8)
    cv2.ellipse(m, (w // 2, h // 2), (max(1, int(w * 0.48)), max(1, int(h * 0.48))), 0, 0, 360, 255, -1)
    m = cv2.GaussianBlur(m, (0, 0), sigmaX=max(1.5, min(w, h) * 0.035))
    return (m.astype(np.float32) / 255.0)[..., None]


def blur_oval(img: np.ndarray, box) -> None:
    """The ellipse is built on the UNCLIPPED padded box, then cropped to the frame, so a face
    at the image border is still fully inside the oval (clipping first would shrink it)."""
    H, W = img.shape[:2]
    x, y, w, h = box
    pad = 0.45
    ux0, uy0 = int(x - w * pad), int(y - h * pad * 1.2)
    ux1, uy1 = int(x + w + w * pad), int(y + h + h * pad)
    x0, y0, x1, y1 = max(0, ux0), max(0, uy0), min(W, ux1), min(H, uy1)
    if x1 <= x0 or y1 <= y0:
        return
    full = oval_mask(ux1 - ux0, uy1 - uy0)
    a = full[y0 - uy0:y1 - uy0, x0 - ux0:x1 - ux0]
    roi = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = (obscure(roi).astype(np.float32) * a + roi.astype(np.float32) * (1 - a)).astype(np.uint8)


def render_protected(src: np.ndarray, regions: list) -> np.ndarray:
    """regions: list of (x, y, w, h) boxes to obscure with an oval blur. Never mutates `src`."""
    out = src.copy()
    for box in regions:
        blur_oval(out, box)
    return out


def full_shield(shape, label: str = "PROTECTED OUTPUT PAUSED") -> np.ndarray:
    """Slate that contains no source pixels at all."""
    out = np.full(shape, SHIELD_COLOR, dtype=np.uint8)
    cv2.putText(out, label, (20, shape[0] // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (220, 220, 220), 2, cv2.LINE_AA)
    return out
