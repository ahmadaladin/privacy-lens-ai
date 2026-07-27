"""PrivacyLens public package interface."""

from privacylens.batch import BatchResult, process_directory
from privacylens.models import BoundingBox, Detection
from privacylens.pipeline import ProcessResult, process_image
from privacylens.policy import RedactionPolicy, load_policy
from privacylens.review import ReviewPlan, load_review_plan
from privacylens.text_pipeline import TextProcessResult, process_text_file
from privacylens.text_recognition import TextDetection

__all__ = [
    "BatchResult",
    "BoundingBox",
    "Detection",
    "ProcessResult",
    "RedactionPolicy",
    "ReviewPlan",
    "TextDetection",
    "TextProcessResult",
    "process_directory",
    "process_image",
    "process_text_file",
    "load_policy",
    "load_review_plan",
]
__version__ = "0.1.0"
