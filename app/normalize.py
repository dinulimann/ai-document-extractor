"""Deterministic clean-up of what the model read.

The model copies values as printed; this module turns them into canonical
values. Dates are the main reason: "09/10/2026" means 9 October on an
Indonesian invoice and September 10 on a US one, and a language model guesses
that wrong too often. Code that looks at the document's language does not.
"""

import re
from datetime import date

from .schemas import Invoice, LineItem, RawInvoice

MONTHS = {
    # Indonesian
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7,
    "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    # English
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7, "august": 8,
    "october": 10, "december": 12,
    # Short forms
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "agu": 8, "agt": 8,
    "sep": 9, "sept": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "des": 12,
}

ID_WORDS = ("faktur", "tanggal", "kepada", "jumlah", "ppn", "tagihan", "jatuh tempo", "keterangan", "npwp")

CURRENCY = {"rp": "IDR", "idr": "IDR", "rupiah": "IDR", "$": "USD", "us$": "USD", "usd": "USD",
            "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "s$": "SGD", "sgd": "SGD"}


def is_indonesian(text: str) -> bool:
    t = text.lower()
    return sum(w in t for w in ID_WORDS) >= 2


def parse_date(raw: str, day_first: bool) -> str | None:
    """Returns YYYY-MM-DD, or None if the string is empty or not a date."""
    s = raw.strip().lower().replace(",", " ")
    if not s:
        return None

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return _iso(y, mo, d)

    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if m:
        a, b, y = map(int, m.groups())
        # An unambiguous value wins over the language hint
        if a > 12:
            day_first = True
        elif b > 12:
            day_first = False
        d, mo = (a, b) if day_first else (b, a)
        return _iso(y, mo, d)

    words = s.split()
    nums = [int(w) for w in words if w.isdigit()]
    month = next((MONTHS[w.rstrip(".")] for w in words if w.rstrip(".") in MONTHS), None)
    if month and len(nums) == 2:
        y = next(n for n in nums if n > 31)
        d = next(n for n in nums if n != y)
        return _iso(y, month, d)
    return None


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_currency(raw: str) -> str:
    s = raw.strip().lower()
    return CURRENCY.get(s, raw.strip().upper()[:3])


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v if v and v.lower() not in {"null", "none", "n/a", "-"} else None


def to_invoice(raw: RawInvoice, source_text: str) -> Invoice:
    day_first = is_indonesian(source_text)
    return Invoice(
        vendor_name=raw.vendor_name.strip(),
        vendor_tax_id=clean(raw.vendor_tax_id),
        invoice_number=raw.invoice_number.strip(),
        invoice_date=parse_date(raw.invoice_date_as_printed, day_first) or raw.invoice_date_as_printed,
        due_date=parse_date(raw.due_date_as_printed, day_first) if clean(raw.due_date_as_printed) else None,
        currency=parse_currency(raw.currency_as_printed),
        bill_to=clean(raw.bill_to),
        line_items=[LineItem(**i.model_dump()) for i in raw.line_items],
        subtotal=raw.subtotal,
        tax=raw.tax,
        total=raw.total,
    )
