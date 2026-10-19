"""Web app and JSON API.

    uvicorn app.main:app --reload
"""

import csv
import hashlib
import io
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
import pdfplumber
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from . import config, db
from .extract import ExtractionError, extract_pdf, extract_text
from .schemas import Invoice, LineItem
from .validate import validate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("extractor")



@asynccontextmanager
async def lifespan(_: FastAPI):
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()
    yield


app = FastAPI(title="AI Document Extractor", version="1.0", lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def process(doc_id: int, path: Path) -> None:
    try:
        text, invoice, seconds = extract_pdf(path)
    except ExtractionError as exc:
        db.save_result(doc_id, status="failed", error=str(exc))
        return
    except Exception as exc:  # model not running, etc.
        log.exception("extraction failed for %s", path)
        db.save_result(doc_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        return
    issues = [i.model_dump() for i in validate(invoice)]
    db.save_result(doc_id, status="needs_review" if issues else "extracted", model=config.MODEL,
                   seconds=round(seconds, 2), raw_text=text, data=invoice.model_dump(), issues=issues)
    log.info("document %s: %s, %d issue(s), %.1fs", doc_id, path.name, len(issues), seconds)


# ---------- HTML pages ----------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    docs = db.list_documents()
    return templates.TemplateResponse(request, "index.html", {
        "docs": docs, "stats": db.stats(),
        "processing": any(d["status"] == "processing" for d in docs),
    })


@app.post("/upload")
async def upload(background: BackgroundTasks, files: list[UploadFile] = File(...)):
    for f in files:
        content = await f.read()
        if not content.startswith(b"%PDF"):
            continue
        sha = hashlib.sha256(content).hexdigest()
        doc_id, created = db.insert_document(f.filename or "upload.pdf", sha)
        if created:
            path = config.UPLOAD_DIR / f"{doc_id}.pdf"
            path.write_bytes(content)
            background.add_task(process, doc_id, path)
    return RedirectResponse("/", status_code=303)


@app.get("/documents/{doc_id}", response_class=HTMLResponse)
def detail(request: Request, doc_id: int):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "detail.html", {"doc": doc})


@app.post("/documents/{doc_id}")
async def review(request: Request, doc_id: int, action: str = Form("save")):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404)
    form = await request.form()
    descs = form.getlist("item_description")
    qtys = form.getlist("item_quantity")
    prices = form.getlist("item_unit_price")
    amounts = form.getlist("item_amount")

    def num(v) -> float:
        return float(str(v).replace(",", "") or 0)

    try:
        invoice = Invoice(
            vendor_name=form.get("vendor_name", ""),
            vendor_tax_id=form.get("vendor_tax_id") or None,
            invoice_number=form.get("invoice_number", ""),
            invoice_date=form.get("invoice_date", ""),
            due_date=form.get("due_date") or None,
            currency=form.get("currency", "").upper(),
            bill_to=form.get("bill_to") or None,
            line_items=[LineItem(description=d, quantity=num(q), unit_price=num(p), amount=num(a))
                        for d, q, p, a in zip(descs, qtys, prices, amounts) if str(d).strip()],
            subtotal=num(form.get("subtotal")),
            tax=num(form.get("tax")),
            total=num(form.get("total")),
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, f"Invalid input: {exc}")

    issues = [i.model_dump() for i in validate(invoice)]
    db.update_review(doc_id, invoice.model_dump(), issues, approve=(action == "approve"))
    return RedirectResponse(f"/documents/{doc_id}", status_code=303)


@app.get("/documents/{doc_id}/file")
def document_file(doc_id: int):
    path = config.UPLOAD_DIR / f"{doc_id}.pdf"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf")


@app.get("/documents/{doc_id}/page/{page_no}.png")
def document_page(doc_id: int, page_no: int):
    """First pages rendered as images, so the preview works in every browser."""
    path = config.UPLOAD_DIR / f"{doc_id}.pdf"
    if not path.exists():
        raise HTTPException(404)
    with pdfplumber.open(path) as pdf:
        if not 1 <= page_no <= len(pdf.pages):
            raise HTTPException(404)
        buf = io.BytesIO()
        pdf.pages[page_no - 1].to_image(resolution=110).original.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


@app.get("/export.csv")
def export_csv():
    cols, rows = db.export_rows()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=invoices.csv"})


# ---------- JSON API (for integrations, e.g. n8n or Zapier) ----------

@app.post("/api/extract")
async def api_extract(file: UploadFile = File(None), text: str = Form(None)):
    """Synchronous extraction. Send a PDF as `file`, or raw text as `text`.
    Nothing is stored; use the web upload for the review workflow."""
    try:
        if file is not None:
            content = await file.read()
            tmp = config.UPLOAD_DIR / f"api-{hashlib.sha256(content).hexdigest()}.pdf"
            tmp.write_bytes(content)
            try:
                _, invoice, seconds = extract_pdf(tmp)
            finally:
                tmp.unlink(missing_ok=True)
        elif text:
            invoice, seconds = extract_text(text)
        else:
            raise HTTPException(400, "Send a PDF as 'file' or plain text as 'text'.")
    except ExtractionError as exc:
        raise HTTPException(422, str(exc))
    issues = validate(invoice)
    return {
        "data": invoice.model_dump(),
        "issues": [i.model_dump() for i in issues],
        "needs_review": bool(issues),
        "model": config.MODEL,
        "seconds": round(seconds, 2),
    }


@app.get("/api/documents/{doc_id}")
def api_document(doc_id: int):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404)
    doc.pop("raw_text", None)
    return doc


@app.get("/health")
def health():
    return {"ok": True, "model": config.MODEL}
