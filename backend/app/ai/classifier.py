"""Document type classification (AI step 1).

The allowed-type enum is generated from the registry, so adding a new
document type automatically extends classification.
"""
import enum
from typing import Union

from pydantic import BaseModel, Field, create_model

from ..doctypes.registry import REGISTRY, UNKNOWN

# Dynamic enum of registry keys + "unknown" — constrains the model's output.
DocTypeEnum = enum.Enum("DocTypeEnum", {key: key for key in [*REGISTRY, UNKNOWN]})

ClassificationResult = create_model(
    "ClassificationResult",
    doc_type=(DocTypeEnum, ...),
    confidence=(float, Field(ge=0.0, le=1.0, description="Certainty that doc_type is correct")),
    reasoning=(str, Field(description="One-sentence justification")),
    __base__=BaseModel,
)


def _build_prompt() -> str:
    type_lines = "\n".join(
        f"- {spec.name}: {spec.description}" for spec in REGISTRY.values()
    )
    return (
        "You are a document classification system.\n"
        "Classify the attached document as exactly one of these types:\n\n"
        f"{type_lines}\n"
        f"- {UNKNOWN}: the document does not clearly match any type above.\n\n"
        "Report your confidence from 0.0 to 1.0 that the chosen type is correct, "
        "and one sentence of reasoning. If you are genuinely unsure between types, "
        f"prefer '{UNKNOWN}' with low confidence over guessing."
    )


def classify(content: tuple[str, Union[bytes, str]], mime_type: str) -> tuple[str, float, str]:
    """Returns (doc_type, confidence, reasoning)."""
    from .client import generate_structured

    result = generate_structured(content, mime_type, _build_prompt(), ClassificationResult)
    doc_type = result.doc_type.value
    if doc_type not in REGISTRY:  # deterministic guard: anything unexpected -> unknown
        doc_type = UNKNOWN
    return doc_type, float(result.confidence), result.reasoning
