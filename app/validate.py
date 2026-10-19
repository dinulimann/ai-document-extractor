"""Business checks on an extracted invoice.

The model is good at reading documents but it is not an accountant, and the
document itself can be wrong. Anything that fails here goes to a human.
"""

from datetime import date

from . import config
from .schemas import Invoice, Issue


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= config.AMOUNT_TOLERANCE


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate(inv: Invoice) -> list[Issue]:
    issues: list[Issue] = []

    for field in ("vendor_name", "invoice_number", "currency"):
        if not getattr(inv, field).strip():
            issues.append(Issue(field=field, message="Missing"))

    inv_date = _parse_date(inv.invoice_date)
    if inv_date is None:
        issues.append(Issue(field="invoice_date", message=f"Not a valid date: {inv.invoice_date!r}"))
    if inv.due_date is not None:
        due = _parse_date(inv.due_date)
        if due is None:
            issues.append(Issue(field="due_date", message=f"Not a valid date: {inv.due_date!r}"))
        elif inv_date and due < inv_date:
            issues.append(Issue(field="due_date", message="Due date is before the invoice date"))

    if not inv.line_items:
        issues.append(Issue(field="line_items", message="No line items found"))

    for n, item in enumerate(inv.line_items, 1):
        expected = item.quantity * item.unit_price
        if not _close(expected, item.amount):
            issues.append(Issue(
                field=f"line_items[{n}]",
                message=f"{item.quantity:g} × {item.unit_price:,.2f} = {expected:,.2f}, but amount is {item.amount:,.2f}",
            ))

    lines_sum = sum(i.amount for i in inv.line_items)
    if inv.line_items and not _close(lines_sum, inv.subtotal):
        issues.append(Issue(field="subtotal",
                            message=f"Line items add up to {lines_sum:,.2f}, subtotal says {inv.subtotal:,.2f}"))

    if not _close(inv.subtotal + inv.tax, inv.total):
        issues.append(Issue(field="total",
                            message=f"Subtotal + tax = {inv.subtotal + inv.tax:,.2f}, total says {inv.total:,.2f}"))

    return issues
