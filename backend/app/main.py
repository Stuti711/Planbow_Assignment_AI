"""REST API — upload, review workflow, and the downstream integration surface."""
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from . import ingest, pipeline
from .db import get_session, init_db
from .doctypes.registry import REGISTRY, get_spec
from .models import Document, DocumentStatus, utcnow


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI Document Processing Platform",
    description="Upload business documents; AI classifies and extracts structured "
                "data; deterministic rules validate it; humans review and correct; "
                "approved results are exposed as structured JSON.",
    lifespan=lifespan,
)


class CorrectionPayload(BaseModel):
    data: dict


class ClassifyPayload(BaseModel):
    doc_type: str


def _doc_or_404(session: Session, doc_id: int) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _detail(doc: Document) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "mime_type": doc.mime_type,
        "sha256": doc.sha256,
        "status": doc.status,
        "doc_type": doc.doc_type,
        "classification_confidence": doc.classification_confidence,
        "classification_reasoning": doc.classification_reasoning,
        "extracted_data": doc.extracted_data,
        "corrected_data": doc.corrected_data,
        "field_confidences": doc.field_confidences,
        "validation_issues": doc.validation_issues,
        "error": doc.error,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


@app.get("/doctypes")
def list_doctypes() -> list[dict]:
    return [{"name": s.name, "display_name": s.display_name} for s in REGISTRY.values()]


@app.post("/documents", status_code=201)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        path, sha256, mime = ingest.save_upload(file.filename or "upload", data)
    except ingest.UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc))

    doc = Document(
        filename=file.filename or "upload",
        file_path=path,
        mime_type=mime,
        sha256=sha256,
        status=DocumentStatus.PROCESSING,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    background_tasks.add_task(pipeline.process_document, doc.id)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@app.get("/documents")
def list_documents(session: Session = Depends(get_session)) -> list[dict]:
    docs = session.exec(select(Document).order_by(Document.uploaded_at.desc())).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "status": d.status,
            "doc_type": d.doc_type,
            "classification_confidence": d.classification_confidence,
            "uploaded_at": d.uploaded_at.isoformat(),
            "has_validation_errors": any(
                i.get("severity") == "error" for i in (d.validation_issues or [])
            ),
        }
        for d in docs
    ]


@app.get("/documents/{doc_id}")
def get_document(doc_id: int, session: Session = Depends(get_session)) -> dict:
    return _detail(_doc_or_404(session, doc_id))


@app.patch("/documents/{doc_id}/data")
def correct_document(
    doc_id: int,
    payload: CorrectionPayload,
    session: Session = Depends(get_session),
) -> dict:
    doc = _doc_or_404(session, doc_id)
    if doc.doc_type not in REGISTRY:
        raise HTTPException(
            status_code=409,
            detail="Document has no known type yet; classify it first via POST /classify.",
        )
    spec = get_spec(doc.doc_type)
    try:
        normalized = spec.schema.model_validate(payload.data).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Data does not match the "
                            f"{spec.display_name} schema: {exc.errors()}")

    doc.corrected_data = normalized
    doc.validation_issues = [i.model_dump() for i in spec.validate(normalized)]
    if doc.status == DocumentStatus.APPROVED:
        doc.status = DocumentStatus.NEEDS_REVIEW  # edits re-open review
    doc.updated_at = utcnow()
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return _detail(doc)


@app.post("/documents/{doc_id}/classify")
def classify_document(
    doc_id: int,
    payload: ClassifyPayload,
    session: Session = Depends(get_session),
) -> dict:
    doc = _doc_or_404(session, doc_id)
    if payload.doc_type not in REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown doc_type '{payload.doc_type}'. Valid: {sorted(REGISTRY)}",
        )
    try:
        pipeline.reclassify_document(doc, payload.doc_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Re-extraction failed: {exc}")
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return _detail(doc)


@app.post("/documents/{doc_id}/approve")
def approve_document(doc_id: int, session: Session = Depends(get_session)) -> dict:
    doc = _doc_or_404(session, doc_id)
    if doc.doc_type not in REGISTRY:
        raise HTTPException(status_code=409, detail="Cannot approve: document type is unknown.")
    data = doc.effective_data()
    if data is None:
        raise HTTPException(status_code=409, detail="Cannot approve: no extracted data.")

    # Approval gate is deterministic: re-validate whatever data is current.
    issues = [i.model_dump() for i in get_spec(doc.doc_type).validate(data)]
    doc.validation_issues = issues
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        doc.updated_at = utcnow()
        session.add(doc)
        session.commit()
        raise HTTPException(
            status_code=409,
            detail={"message": "Cannot approve while validation errors remain.",
                    "issues": errors},
        )

    doc.status = DocumentStatus.APPROVED
    doc.updated_at = utcnow()
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return _detail(doc)


@app.post("/documents/{doc_id}/retry")
def retry_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    doc = _doc_or_404(session, doc_id)
    doc.status = DocumentStatus.PROCESSING
    doc.error = None
    doc.updated_at = utcnow()
    session.add(doc)
    session.commit()
    background_tasks.add_task(pipeline.process_document, doc.id)
    return {"id": doc.id, "status": doc.status}


@app.get("/documents/{doc_id}/result")
def get_result(doc_id: int, session: Session = Depends(get_session)) -> dict:
    """Final structured output for downstream systems.

    Human corrections take precedence over raw AI output. Downstream
    consumers should filter on approved=true (or poll GET /documents for
    status=approved) to take only human-verified data.
    """
    doc = _doc_or_404(session, doc_id)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "approved": doc.status == DocumentStatus.APPROVED,
        "data": doc.effective_data(),
        "was_corrected": doc.corrected_data is not None,
        "classification_confidence": doc.classification_confidence,
        "field_confidences": doc.field_confidences,
        "validation_issues": doc.validation_issues,
        "sha256": doc.sha256,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }
