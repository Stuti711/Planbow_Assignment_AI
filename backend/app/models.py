"""Database model: one row per uploaded document."""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class DocumentStatus:
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    FAILED = "failed"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    file_path: str
    mime_type: str
    sha256: str
    status: str = DocumentStatus.UPLOADED
    doc_type: Optional[str] = None
    classification_confidence: Optional[float] = None
    classification_reasoning: Optional[str] = None
    # AI output is kept verbatim in extracted_data; human edits go to
    # corrected_data so the original is always available for comparison.
    extracted_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    corrected_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    field_confidences: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    validation_issues: Optional[list] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def effective_data(self) -> Optional[dict[str, Any]]:
        """Human corrections win over raw AI output."""
        return self.corrected_data if self.corrected_data is not None else self.extracted_data
