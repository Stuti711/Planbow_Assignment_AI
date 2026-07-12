"""Invoice: schema, extraction hints, deterministic validators."""
from typing import Optional

from pydantic import BaseModel

from .base import (
    DocTypeSpec,
    check_date_order,
    check_dates_parseable,
    check_line_item_math,
    require_fields,
)


class InvoiceLineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class Invoice(BaseModel):
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    line_items: list[InvoiceLineItem] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    discount: Optional[float] = None
    total: Optional[float] = None
    payment_terms: Optional[str] = None


SPEC = DocTypeSpec(
    name="invoice",
    display_name="Invoice",
    description=(
        "A bill issued by a vendor to a customer requesting payment for goods or "
        "services already delivered. Typically has an invoice number, line items, "
        "subtotal/tax/total amounts and a due date."
    ),
    schema=Invoice,
    extraction_hints=(
        "Amounts must be plain numbers without currency symbols; put the currency "
        "code (e.g. USD, EUR, INR) in 'currency'. 'amount' on a line item is the "
        "line total (quantity x unit_price) as printed on the document."
    ),
    validators=[
        require_fields(["invoice_number", "total"]),
        require_fields(["vendor_name", "invoice_date"], severity="warning"),
        check_dates_parseable(["invoice_date", "due_date"]),
        check_date_order("invoice_date", "due_date", "Due date is before the invoice date."),
        check_line_item_math(),
    ],
)
