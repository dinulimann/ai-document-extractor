from app.schemas import Invoice, LineItem
from app.validate import validate


def invoice(**overrides) -> Invoice:
    base = dict(
        vendor_name="Vendor", invoice_number="INV-1", invoice_date="2026-09-01", due_date="2026-09-30",
        currency="IDR", line_items=[LineItem(description="A", quantity=2, unit_price=100, amount=200),
                                    LineItem(description="B", quantity=1, unit_price=50, amount=50)],
        subtotal=250, tax=27.5, total=277.5,
    )
    return Invoice(**{**base, **overrides})


def fields(issues):
    return [i.field for i in issues]


def test_valid_invoice_has_no_issues():
    assert validate(invoice()) == []


def test_wrong_line_amount():
    items = [LineItem(description="A", quantity=12, unit_price=100, amount=200)]
    assert "line_items[1]" in fields(validate(invoice(line_items=items, subtotal=200, tax=0, total=200)))


def test_subtotal_and_total_mismatch():
    assert fields(validate(invoice(subtotal=300, total=327.5))) == ["subtotal"]
    assert fields(validate(invoice(total=999))) == ["total"]


def test_rounding_within_tolerance_is_ok():
    assert validate(invoice(total=278)) == []


def test_dates():
    assert fields(validate(invoice(invoice_date="09/10/2026"))) == ["invoice_date"]
    assert fields(validate(invoice(due_date="2026-08-01"))) == ["due_date"]


def test_missing_values():
    got = fields(validate(invoice(vendor_name=" ", line_items=[], subtotal=0, tax=0, total=0)))
    assert got == ["vendor_name", "line_items"]
