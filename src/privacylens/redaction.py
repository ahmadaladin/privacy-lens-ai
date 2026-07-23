"""Pixel transformations used to hide detected regions."""

from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np

from privacylens.models import Detection

REDACTION_STYLES = {"blur", "pixelate", "solid"}


def redact_regions(
    image: np.ndarray,
    detections: Iterable[Detection],
    *,
    style: str = "blur",
) -> np.ndarray:
    """Return a copy with every detection redacted."""

    if image.ndim not in (2, 3):
        raise ValueError("image must be a grayscale or BGR array")
    if style not in REDACTION_STYLES:
        raise ValueError(f"unsupported redaction style: {style}")

    result = image.copy()
    height, width = result.shape[:2]

    for detection in detections:
        box = detection.box.clipped(width, height)
        if box.is_empty:
            continue

        region = result[box.y1 : box.y2, box.x1 : box.x2]
        if style == "solid":
            region[...] = 0
        elif style == "pixelate":
            _pixelate(region)
        else:
            _blur(region)

    return result


def _blur(region: np.ndarray) -> None:
    smallest_side = min(region.shape[:2])
    kernel = max(3, smallest_side // 3)
    if kernel % 2 == 0:
        kernel += 1
    region[...] = cv2.GaussianBlur(region, (kernel, kernel), 0)


def _pixelate(region: np.ndarray) -> None:
    height, width = region.shape[:2]
    small_width = max(1, width // 10)
    small_height = max(1, height // 10)
    reduced = cv2.resize(region, (small_width, small_height), interpolation=cv2.INTER_LINEAR)
    region[...] = cv2.resize(reduced, (width, height), interpolation=cv2.INTER_NEAREST)

