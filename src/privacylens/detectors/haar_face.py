"""Lightweight local face-detection baseline."""

from __future__ import annotations

import cv2
import numpy as np

from privacylens.models import BoundingBox, Detection


class HaarFaceDetector:
    """Detect frontal faces with OpenCV's bundled Haar cascade.

    This detector is fast and dependency-light, but it is only a baseline. It
    can miss rotated, occluded, small, or profile faces.
    """

    def __init__(self, min_size: tuple[int, int] = (30, 30)) -> None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():
            raise RuntimeError("OpenCV face cascade could not be loaded")
        self._min_size = min_size

    def detect(self, image: np.ndarray) -> list[Detection]:
        if image.ndim not in (2, 3):
            raise ValueError("image must be a grayscale or BGR array")

        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=self._min_size,
        )
        return [
            Detection(
                kind="face",
                box=BoundingBox(int(x), int(y), int(x + width), int(y + height)),
                # OpenCV's Haar cascade does not provide a calibrated probability.
                score=None,
            )
            for x, y, width, height in faces
        ]
