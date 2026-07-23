"""PrivacyLens public package interface."""

from privacylens.models import BoundingBox, Detection
from privacylens.pipeline import ProcessResult, process_image

__all__ = ["BoundingBox", "Detection", "ProcessResult", "process_image"]
__version__ = "0.1.0"

