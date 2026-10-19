"""PDF -> text -> structured invoice, using a local model through Ollama."""

import json
import logging
import re
import time
from pathlib import Path

import httpx
import pdfplumber
from pydantic import ValidationError

from . import config
from .normalize import to_invoice
from .schemas import Invoice, RawInvoice

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You read invoices and copy their values into JSON that matches the schema.

Rules:
- Copy every text value exactly as printed. Do not translate, reformat or guess.
- Dates and currency: copy them as printed (e.g. "09/10/2026", "3 September 2026", "Rp", "$").
- vendor_tax_id: the value printed after a label such as NPWP, Tax ID or EIN.
- bill_to: the name printed after a label such as Bill To or Kepada.
- Line items: read each row as description, quantity, unit price, amount. The quantity is the
  separate number column between the description and the unit price; numbers inside the
  description (like "1 kg" or "0.5") belong to the description.
- Amounts: plain numbers. Indonesian invoices use dots for thousands: "Rp 1.250.000" is 1250000.
- total: the final total exactly as printed, even if it does not add up.
- Use an empty string for text that is not on the document. Never invent values."""


class ExtractionError(Exception):
    pass


def pdf_to_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        # layout=True keeps column spacing, so "Gayo 1 kg    12" stays two columns
        pages = (page.extract_text(layout=True) or "" for page in pdf.pages)
        lines = (line.strip() for page in pages for line in page.splitlines())
        # ...but runs of spaces cost tokens; a short separator keeps the columns
        text = "\n".join(re.sub(r" {2,}", " | ", line) for line in lines if line)
    if not text:
        raise ExtractionError("No text layer found. This looks like a scanned PDF; add OCR first.")
    return text


def call_llm(text: str, client: httpx.Client | None = None) -> dict:
    payload = {
        "model": config.MODEL,
        "stream": False,
        "format": RawInvoice.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Invoice text:\n\n{text}"},
        ],
    }
    own = client is None
    client = client or httpx.Client(timeout=300)
    try:
        resp = client.post(f"{config.OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return json.loads(resp.json()["message"]["content"])
    finally:
        if own:
            client.close()


def extract_text(text: str, client: httpx.Client | None = None, attempts: int = 2) -> tuple[Invoice, float]:
    """Returns the parsed invoice and the model time in seconds."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        try:
            raw = RawInvoice.model_validate(call_llm(text, client))
            return to_invoice(raw, text), time.monotonic() - t0
        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            log.warning("attempt %d: model output did not match schema: %s", attempt, exc)
            last_error = exc
    raise ExtractionError(f"Model output did not match the schema: {last_error}")


def extract_pdf(path: Path, client: httpx.Client | None = None) -> tuple[str, Invoice, float]:
    text = pdf_to_text(path)
    invoice, seconds = extract_text(text, client)
    return text, invoice, seconds
