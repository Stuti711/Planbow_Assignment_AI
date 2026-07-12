"""DocTypeSpec: everything the system needs to know about one document type.

Adding a new document type = one module defining a DocTypeSpec + one
registry entry. Classification, extraction, validation and the review UI
all derive from the spec.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional

from pydantic import BaseModel

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
# Loose: digits, spaces, dashes, parentheses, optional leading +, 7-15 digits total.
PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")

DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
    "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y/%m/%d",
)


class ValidationIssue(BaseModel):
    field: str
    rule: str
    severity: str  # "error" | "warning"
    message: str


# A validator takes the extracted data dict and returns issues found.
Validator = Callable[[dict], list[ValidationIssue]]


@dataclass
class DocTypeSpec:
    name: str                      # registry key, e.g. "invoice"
    display_name: str              # e.g. "Invoice"
    description: str               # used in the classification prompt
    schema: type[BaseModel]        # extraction schema (Pydantic)
    extraction_hints: str          # type-specific guidance for the extraction prompt
    validators: list[Validator] = field(default_factory=list)

    def validate(self, data: dict) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for validator in self.validators:
            issues.extend(validator(data))
        return issues


# ---------------------------------------------------------------------------
# Shared deterministic helpers used by per-type validators
# ---------------------------------------------------------------------------

def parse_date(value: Optional[str]) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def issue(field_name: str, rule: str, severity: str, message: str) -> ValidationIssue:
    return ValidationIssue(field=field_name, rule=rule, severity=severity, message=message)


def require_fields(fields: list[str], severity: str = "error") -> Validator:
    def _validator(data: dict) -> list[ValidationIssue]:
        out = []
        for name in fields:
            value = data.get(name)
            if value is None or (isinstance(value, (str, list)) and not value):
                out.append(issue(name, "required", severity, f"'{name}' is missing."))
        return out
    return _validator


def check_dates_parseable(fields: list[str]) -> Validator:
    def _validator(data: dict) -> list[ValidationIssue]:
        out = []
        for name in fields:
            value = data.get(name)
            if value and parse_date(value) is None:
                out.append(issue(name, "date_format", "warning",
                                 f"'{name}' value '{value}' is not a recognizable date."))
        return out
    return _validator


def check_date_order(earlier: str, later: str, message: str) -> Validator:
    def _validator(data: dict) -> list[ValidationIssue]:
        d1, d2 = parse_date(data.get(earlier)), parse_date(data.get(later))
        if d1 and d2 and d2 < d1:
            return [issue(later, "date_order", "error", message)]
        return []
    return _validator


def check_email(field_name: str) -> Validator:
    def _validator(data: dict) -> list[ValidationIssue]:
        value = data.get(field_name)
        if value and not EMAIL_RE.match(str(value).strip()):
            return [issue(field_name, "email_format", "warning",
                          f"'{value}' does not look like a valid email address.")]
        return []
    return _validator


def check_phone(field_name: str) -> Validator:
    def _validator(data: dict) -> list[ValidationIssue]:
        value = data.get(field_name)
        if value and not PHONE_RE.match(str(value).strip()):
            return [issue(field_name, "phone_format", "warning",
                          f"'{value}' does not look like a valid phone number.")]
        return []
    return _validator


def check_line_item_math(tolerance: float = 0.02) -> Validator:
    """Line-item amounts should sum to the subtotal, and
    subtotal + tax - discount should equal the total (within tolerance)."""
    def _validator(data: dict) -> list[ValidationIssue]:
        out = []
        items = data.get("line_items") or []
        amounts = [i.get("amount") for i in items if isinstance(i, dict)]
        subtotal, tax = data.get("subtotal"), data.get("tax")
        discount, total = data.get("discount"), data.get("total")

        if amounts and all(isinstance(a, (int, float)) for a in amounts) and isinstance(subtotal, (int, float)):
            items_sum = sum(amounts)
            if abs(items_sum - subtotal) > tolerance:
                out.append(issue("subtotal", "line_items_sum", "error",
                                 f"Line items sum to {items_sum:.2f} but subtotal is {subtotal:.2f}."))

        if isinstance(subtotal, (int, float)) and isinstance(total, (int, float)):
            expected = subtotal + (tax or 0) - (discount or 0)
            if abs(expected - total) > tolerance:
                out.append(issue("total", "totals_math", "error",
                                 f"subtotal + tax - discount = {expected:.2f} but total is {total:.2f}."))
        return out
    return _validator
