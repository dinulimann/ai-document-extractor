from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class RawInvoice(BaseModel):
    """What the model is asked for: values copied as printed.

    Every field is a required string (empty when absent) rather than nullable;
    small models tend to answer null for nullable fields they could have read.
    Dates and currency stay raw and are normalised in code (normalize.py).
    """
    vendor_name: str
    vendor_tax_id: str = Field(description="Value after the NPWP / Tax ID / EIN label, empty string if none")
    invoice_number: str
    invoice_date_as_printed: str = Field(description="Exactly as printed, e.g. '09/10/2026' or '3 September 2026'")
    due_date_as_printed: str = Field(description="Exactly as printed, empty string if none")
    currency_as_printed: str = Field(description="Symbol or code as printed, e.g. 'Rp', '$', 'USD'")
    bill_to: str = Field(description="Name after the Bill To / Kepada label, empty string if none")
    line_items: list[LineItem]
    subtotal: float
    tax: float = Field(description="0 if there is no tax line")
    total: float = Field(description="The final total exactly as printed, even if it looks wrong")


class Invoice(BaseModel):
    """Canonical invoice stored in the database and returned by the API."""
    vendor_name: str
    vendor_tax_id: str | None = None
    invoice_number: str
    invoice_date: str = Field(description="YYYY-MM-DD")
    due_date: str | None = None
    currency: str = Field(description="ISO 4217 code")
    bill_to: str | None = None
    line_items: list[LineItem]
    subtotal: float
    tax: float
    total: float


class Issue(BaseModel):
    field: str
    message: str
