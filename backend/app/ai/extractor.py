"""Structured field extraction (AI step 2).

The extraction schema is the document type's Pydantic model, enforced by
Gemini structured outputs — the response is guaranteed to match the schema.
The model also self-reports a confidence per top-level field, which the
review UI uses to flag uncertain values.
"""
from functools import lru_cache
from typing import Union

from pydantic import BaseModel, Field, create_model

from ..doctypes.base import DocTypeSpec


class FieldConfidence(BaseModel):
    field: str = Field(description="Top-level field name from 'data'")
    confidence: float = Field(ge=0.0, le=1.0)


@lru_cache(maxsize=None)
def _wrapper_schema(spec_name: str) -> type[BaseModel]:
    from ..doctypes.registry import get_spec

    spec = get_spec(spec_name)
    return create_model(
        f"{spec.schema.__name__}Extraction",
        data=(spec.schema, ...),
        field_confidences=(list[FieldConfidence], ...),
        __base__=BaseModel,
    )


def _build_prompt(spec: DocTypeSpec) -> str:
    return (
        f"Extract structured data from the attached document, which is a "
        f"{spec.display_name}.\n\n"
        f"{spec.extraction_hints}\n\n"
        "Rules:\n"
        "- Use null for any field whose value is not present in the document. "
        "Never guess or fabricate a value.\n"
        "- Format dates as YYYY-MM-DD whenever the full date is known.\n"
        "- Numbers must be plain numbers (no currency symbols or thousands separators).\n"
        "- Copy every value exactly as it appears in the document, character for "
        "character. Do NOT repair typos, malformed emails or URLs, or unusual "
        "formatting — downstream validation must see the document's real content. "
        "For example, if an email is printed as 'x[at]y.com', return 'x[at]y.com', "
        "not 'x@y.com'.\n\n"
        "Also return field_confidences: one entry for each top-level field of 'data', "
        "with a confidence from 0.0 to 1.0 that the extracted value is correct. Use 1.0 "
        "when the value is clearly printed, lower when it is inferred, ambiguous, "
        "partially illegible, or missing."
    )


def extract(
    content: tuple[str, Union[bytes, str]],
    mime_type: str,
    spec: DocTypeSpec,
) -> tuple[dict, dict[str, float]]:
    """Returns (extracted data dict, {field: confidence})."""
    from .client import generate_structured

    result = generate_structured(content, mime_type, _build_prompt(spec), _wrapper_schema(spec.name))
    data = result.data.model_dump()
    confidences = {fc.field: fc.confidence for fc in result.field_confidences}
    return data, confidences
