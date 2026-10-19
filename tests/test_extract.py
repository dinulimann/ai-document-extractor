"""Extraction pipeline with the model mocked out, so tests run without Ollama."""

import json
from pathlib import Path

import httpx
import pytest

from app.extract import ExtractionError, extract_pdf, extract_text, pdf_to_text

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

MODEL_REPLY = {
    "vendor_name": "Toko Mitra ATK", "vendor_tax_id": "", "invoice_number": "MTK-0921",
    "invoice_date_as_printed": "21/09/2026", "due_date_as_printed": "", "currency_as_printed": "Rp",
    "bill_to": "Kantor Cabang Medan",
    "line_items": [{"description": "Kertas A4 80gsm (rim)", "quantity": 20, "unit_price": 52000, "amount": 1040000}],
    "subtotal": 1040000, "tax": 114400, "total": 1154400,
}


def client_returning(*contents: str) -> httpx.Client:
    replies = iter(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["format"]["type"] == "object"     # structured output is requested
        return httpx.Response(200, json={"message": {"content": next(replies)}})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pdf_text_keeps_columns_separate():
    text = pdf_to_text(SAMPLES / "01_sinar_kopi.pdf")
    assert "Biji kopi arabika Gayo 1 kg | 12 | Rp 185.000 | Rp 2.220.000" in text


def test_reply_is_normalised():
    _, inv, _ = extract_pdf(SAMPLES / "03_mitra_atk.pdf", client_returning(json.dumps(MODEL_REPLY)))
    assert inv.invoice_date == "2026-09-21"
    assert inv.currency == "IDR"
    assert inv.vendor_tax_id is None and inv.due_date is None


def test_invalid_reply_is_retried_once():
    inv, _ = extract_text("FAKTUR ...", client_returning("not json", json.dumps(MODEL_REPLY)))
    assert inv.invoice_number == "MTK-0921"


def test_gives_up_after_two_bad_replies():
    with pytest.raises(ExtractionError):
        extract_text("FAKTUR ...", client_returning("{}", "{}"))
