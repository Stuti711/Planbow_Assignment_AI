"""Purchase order: schema, extraction hints, deterministic validators."""
from typing import Optional

from pydantic import BaseModel

from .base import (
    DocTypeSpec,
    check_date_order,
    check_dates_parseable,
    check_line_item_math,
    require_fields,
)


class POLineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class PurchaseOrder(BaseModel):
    po_number: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_address: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_address: Optional[str] = None
    order_date: Optional[str] = None
    delivery_date: Optional[str] = None
    currency: Optional[str] = None
    line_items: list[POLineItem] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    discount: Optional[float] = None
    total: Optional[float] = None
    shipping_terms: Optional[str] = None


SPEC = DocTypeSpec(
    name="purchase_order",
    display_name="Purchase Order",
    description=(
        "A document issued by a buyer to a supplier to order goods or services, "
        "specifying items, quantities and agreed prices, before delivery. "
        "Typically has a PO number, buyer/supplier details and a delivery date."
    ),
    schema=PurchaseOrder,
    extraction_hints=(
        "Amounts must be plain numbers without currency symbols; put the currency "
        "code in 'currency'. The buyer is the party placing the order; the "
        "supplier is the party fulfilling it."
    ),
    validators=[
        require_fields(["po_number", "total"]),
        require_fields(["buyer_name", "supplier_name"], severity="warning"),
        check_dates_parseable(["order_date", "delivery_date"]),
        check_date_order("order_date", "delivery_date", "Delivery date is before the order date."),
        check_line_item_math(),
    ],
)
