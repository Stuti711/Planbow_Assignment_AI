"""Document-type registry — the single extension point.

To support a new document type:
  1. Create a module in this package defining a DocTypeSpec named SPEC
     (Pydantic schema + extraction hints + validators).
  2. Add it to REGISTRY below.
Classification, extraction, validation and the review UI all derive from
this registry; nothing else changes.
"""
from .base import DocTypeSpec
from .contract import SPEC as CONTRACT
from .invoice import SPEC as INVOICE
from .purchase_order import SPEC as PURCHASE_ORDER
from .resume import SPEC as RESUME

UNKNOWN = "unknown"

REGISTRY: dict[str, DocTypeSpec] = {
    spec.name: spec for spec in (INVOICE, PURCHASE_ORDER, CONTRACT, RESUME)
}


def get_spec(doc_type: str) -> DocTypeSpec:
    if doc_type not in REGISTRY:
        raise KeyError(f"Unknown document type: {doc_type!r}")
    return REGISTRY[doc_type]
