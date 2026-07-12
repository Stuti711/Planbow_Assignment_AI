"""Contract: schema, extraction hints, deterministic validators."""
from typing import Optional

from pydantic import BaseModel

from .base import (
    DocTypeSpec,
    ValidationIssue,
    check_date_order,
    check_dates_parseable,
    issue,
    require_fields,
)


class ContractParty(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None  # e.g. "Client", "Service Provider", "Employer"


class Contract(BaseModel):
    title: Optional[str] = None
    contract_type: Optional[str] = None  # e.g. "Service Agreement", "NDA", "Employment"
    parties: list[ContractParty] = []
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    term_description: Optional[str] = None
    governing_law: Optional[str] = None
    contract_value: Optional[float] = None
    currency: Optional[str] = None
    payment_terms: Optional[str] = None
    termination_clause_summary: Optional[str] = None
    auto_renewal: Optional[bool] = None


def _check_parties(data: dict) -> list[ValidationIssue]:
    parties = data.get("parties") or []
    named = [p for p in parties if isinstance(p, dict) and p.get("name")]
    if len(named) < 2:
        return [issue("parties", "min_parties", "warning",
                      f"Only {len(named)} named part{'y' if len(named) == 1 else 'ies'} found; "
                      "contracts normally have at least two.")]
    return []


SPEC = DocTypeSpec(
    name="contract",
    display_name="Contract",
    description=(
        "A legal agreement between two or more parties defining obligations, "
        "terms, duration and conditions (service agreements, NDAs, employment "
        "contracts, leases, etc.)."
    ),
    schema=Contract,
    extraction_hints=(
        "List every named party with its role in the agreement. "
        "'effective_date' is when the contract takes effect; 'end_date' is when "
        "it expires (null for indefinite terms). Summarize the termination "
        "clause in one or two sentences if present."
    ),
    validators=[
        require_fields(["title"], severity="warning"),
        _check_parties,
        check_dates_parseable(["effective_date", "end_date"]),
        check_date_order("effective_date", "end_date", "End date is before the effective date."),
    ],
)
