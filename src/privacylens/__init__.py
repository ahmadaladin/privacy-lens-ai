"""PrivacyLens public package interface."""

from privacylens.batch import BatchResult, process_directory
from privacylens.benchmark import (
    BenchmarkReport,
    SyntheticTextBenchmark,
    evaluate_benchmark,
    load_benchmark,
)
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
    "BenchmarkReport",
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
    "SyntheticTextBenchmark",
    "TextDetection",
    "TextProcessResult",
    "TesseractOCR",
    "evaluate_benchmark",
    "load_benchmark",
    "load_ocr_sidecar",
    "load_policy",
    "load_review_plan",
    "process_directory",
    "process_image",
    "process_text_file",
    "verify_batch_output",
]
__version__ = "0.1.0"
