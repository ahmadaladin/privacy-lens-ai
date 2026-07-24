"""PrivacyLens public package interface."""

from privacylens.batch import BatchResult, process_directory
from privacylens.models import BoundingBox, Detection
from privacylens.pipeline import ProcessResult, process_image

__all__ = [
    "BatchResult",
    "BoundingBox",
    "Detection",
    "ProcessResult",
    "process_directory",
    "process_image",
]
__version__ = "0.1.0"
