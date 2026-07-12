"""Processing pipeline: classify (AI) -> extract (AI) -> validate (deterministic).

Runs in a FastAPI background task after upload; also reused when a reviewer
manually re-classifies a document or retries a failed one.
"""
import logging

from sqlmodel import Session

from . import ingest
from .ai.classifier import classify
from .ai.extractor import extract
from .db import engine
from .doctypes.registry import REGISTRY, get_spec
from .models import Document, DocumentStatus, utcnow

logger = logging.getLogger(__name__)


def extract_and_validate(doc_type: str, content, mime_type: str) -> tuple[dict, dict, list[dict]]:
    """AI extraction followed by deterministic validation for one doc type."""
    spec = get_spec(doc_type)
    data, confidences = extract(content, mime_type, spec)
    issues = [i.model_dump() for i in spec.validate(data)]
    return data, confidences, issues


def process_document(doc_id: int) -> None:
    """Full pipeline for a freshly uploaded document (background task)."""
    with Session(engine) as session:
        doc = session.get(Document, doc_id)
        if doc is None:
            return
        doc.status = DocumentStatus.PROCESSING
        doc.error = None
        doc.updated_at = utcnow()
        session.add(doc)
        session.commit()

        try:
            content = ingest.load_content(doc.file_path, doc.mime_type)

            doc_type, confidence, reasoning = classify(content, doc.mime_type)
            doc.doc_type = doc_type
            doc.classification_confidence = confidence
            doc.classification_reasoning = reasoning

            if doc_type in REGISTRY:
                # Extract even at low confidence — the reviewer can re-classify;
                # having a draft extraction beats having nothing to review.
                data, confidences, issues = extract_and_validate(doc_type, content, doc.mime_type)
                doc.extracted_data = data
                doc.field_confidences = confidences
                doc.validation_issues = issues
            else:
                # Unknown type: nothing to extract; reviewer must pick a type.
                doc.extracted_data = None
                doc.field_confidences = None
                doc.validation_issues = None

            doc.status = DocumentStatus.NEEDS_REVIEW
        except Exception as exc:  # any failure lands in a reviewable state
            logger.exception("Pipeline failed for document %s", doc_id)
            doc.status = DocumentStatus.FAILED
            doc.error = f"{type(exc).__name__}: {exc}"

        doc.updated_at = utcnow()
        session.add(doc)
        session.commit()


def reclassify_document(doc: Document, doc_type: str) -> None:
    """Reviewer manually set the type: re-run extraction + validation.

    Mutates `doc` in place; caller commits. Used both for correcting a wrong
    classification and for typing documents that came back 'unknown'.
    """
    content = ingest.load_content(doc.file_path, doc.mime_type)
    data, confidences, issues = extract_and_validate(doc_type, content, doc.mime_type)
    doc.doc_type = doc_type
    doc.classification_confidence = 1.0
    doc.classification_reasoning = "Manually classified by reviewer."
    doc.extracted_data = data
    doc.field_confidences = confidences
    doc.validation_issues = issues
    doc.corrected_data = None  # corrections for the old type no longer apply
    doc.status = DocumentStatus.NEEDS_REVIEW
    doc.error = None
    doc.updated_at = utcnow()
