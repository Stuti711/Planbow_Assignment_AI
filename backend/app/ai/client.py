"""Thin wrapper around the google-genai client.

All model calls go through generate_structured(): document content in,
schema-validated Pydantic instance out. temperature=0 for repeatability.
"""
import re
import threading
import time
from typing import Union

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from ..config import settings

_client: genai.Client | None = None
_client_lock = threading.Lock()
# Documents process concurrently in FastAPI's threadpool; cap in-flight model
# calls so a burst of uploads doesn't trip per-minute rate limits.
_inflight = threading.BoundedSemaphore(3)

RETRYABLE_CODES = {429, 500, 503}
MAX_ATTEMPTS = 3
MAX_BACKOFF_SECONDS = 60.0

_RETRY_HINT = re.compile(r"retry in ([\d.]+)\s*s|retryDelay[':\s]+([\d.]+)s", re.IGNORECASE)


def _backoff_seconds(exc: errors.APIError, attempt: int) -> float:
    """Rate limits come with a server-suggested delay ("Please retry in 36s");
    honoring it matters on free-tier keys with small per-minute quotas."""
    if exc.code == 429:
        match = _RETRY_HINT.search(str(exc))
        if match:
            suggested = float(match.group(1) or match.group(2))
            return min(MAX_BACKOFF_SECONDS, suggested + 1.0)
        return 35.0
    return float(2 ** attempt)


def get_client() -> genai.Client:
    # Thread-safe lazy singleton: concurrent pipelines must never race the
    # creation — an orphaned client being garbage-collected can close the
    # shared transport out from under in-flight requests.
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not settings.gemini_api_key:
                    raise RuntimeError(
                        "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
                    )
                _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def generate_structured(
    content: tuple[str, Union[bytes, str]],
    mime_type: str,
    prompt: str,
    schema: type[BaseModel],
) -> BaseModel:
    """Send document content + prompt, get a validated instance of `schema`.

    `content` is ("binary", bytes) for PDF/images (native multimodal input)
    or ("text", str) for text extracted from DOCX/TXT.
    """
    kind, payload = content
    if kind == "binary":
        doc_part = types.Part.from_bytes(data=payload, mime_type=mime_type)
    else:
        doc_part = f"--- DOCUMENT CONTENT ---\n{payload}\n--- END DOCUMENT ---"

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0,
    )

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with _inflight:
                response = get_client().models.generate_content(
                    model=settings.gemini_model,
                    contents=[doc_part, prompt],
                    config=config,
                )
            parsed = response.parsed
            if isinstance(parsed, schema):
                return parsed
            # Fallback: the SDK failed to parse — validate the raw JSON text.
            return schema.model_validate_json(response.text)
        except errors.APIError as exc:
            if exc.code in RETRYABLE_CODES and attempt < MAX_ATTEMPTS - 1:
                last_error = exc
                time.sleep(_backoff_seconds(exc, attempt))
                continue
            raise
    raise RuntimeError(f"Gemini call failed after {MAX_ATTEMPTS} attempts: {last_error}")
