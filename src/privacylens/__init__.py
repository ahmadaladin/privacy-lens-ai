"""PrivacyLens public package interface."""

from privacylens.batch import BatchResult, process_directory
from privacylens.gate import GateReport, verify_batch_output
from privacylens.models import BoundingBox, Detection
from privacylens.ocr import (
    OCRExtraction,
    OCRObservation,
    OCRSidecar,
    load_ocr_sidecar,
)
from privacylens.pipeline import ProcessResult, process_image
from privacylens.policy import RedactionPolicy, load_policy
from privacylens.review import ReviewPlan, load_review_plan
from privacylens.risk_summary import DatasetRiskSummary
from privacylens.tesseract_ocr import TesseractOCR
from privacylens.text_pipeline import TextProcessResult, process_text_file
from privacylens.text_recognition import TextDetection

__all__ = [
    "BatchResult",
    "BoundingBox",
    "Detection",
    "DatasetRiskSummary",
    "GateReport",
    "OCRExtraction",
    "OCRObservation",
    "OCRSidecar",
    "ProcessResult",
    "RedactionPolicy",
    "ReviewPlan",
    "TextDetection",
    "TextProcessResult",
    "TesseractOCR",
    "load_ocr_sidecar",
    "process_directory",
    "process_image",
    "process_text_file",
    "verify_batch_output",
    "load_policy",
    "load_review_plan",
]
__version__ = "0.1.0"
