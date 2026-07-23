"""Detector interface shared by vision and OCR detectors."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from privacylens.models import Detection


class Detector(Protocol):
    """Anything that locates sensitive regions in an image."""

    def detect(self, image: np.ndarray) -> list[Detection]:
        """Return sensitive regions found in a BGR image."""
        ...

