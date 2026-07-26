"""PrivacyLens public package interface."""

from privacylens.batch import BatchResult, process_directory
from privacylens.models import BoundingBox, Detection
from privacylens.pipeline import ProcessResult, process_image
from privacylens.policy import RedactionPolicy, load_policy
from privacylens.text_pipeline import TextProcessResult, process_text_file
from privacylens.text_recognition import TextDetection

__all__ = [
    "BatchResult",
    "BoundingBox",
    "Detection",
    "ProcessResult",
    "RedactionPolicy",
    "TextDetection",
    "TextProcessResult",
    "process_directory",
    "process_image",
    "process_text_file",
    "load_policy",
]
__version__ = "0.1.0"
