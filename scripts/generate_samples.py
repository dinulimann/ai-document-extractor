"""Generates fictional invoice PDFs plus the expected extraction for each.

Layouts, languages, number formats and date formats differ on purpose, so the
extractor cannot rely on a fixed template. One invoice has a wrong printed
total, which validation must flag.

    python scripts/generate_samples.py
"""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

OUT = Path(__file__).resolve().parent.parent / "samples"
styles = getSampleStyleSheet()

MONTHS_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
             "Agustus", "September", "Oktober", "November", "Desember"]


def fmt_idr(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def fmt_usd(x: float) -> str:
    return f"{x:,.2f}"


INVOICES = [
    dict(file="01_sinar_kopi.pdf", layout="classic", lang="id", currency="IDR",
         vendor="CV Sinar Kopi Nusantara", tax_id="01.234.567.8-901.000",
         number="INV/2026/09/0147", date=(2026, 9, 3), due=(2026, 10, 3),
         bill_to="PT Contoh Logistik Abadi",
         items=[("Biji kopi arabika Gayo 1 kg", 12, 185000), ("Biji kopi robusta Lampung 1 kg", 8, 120000),
                ("Gula aren cair 1 L", 5, 45000)], tax_rate=0.11),
    dict(file="02_bright_cloud.pdf", layout="modern", lang="en", currency="USD",
         vendor="Bright Cloud Hosting LLC", tax_id=None,
         number="BCH-88213", date=(2026, 8, 31), due=(2026, 9, 15),
         bill_to="Example Studio Ltd",
         items=[("VPS 4 vCPU / 8 GB (monthly)", 3, 48.0), ("Managed PostgreSQL 50 GB", 1, 65.0),
                ("Object storage 500 GB", 1, 11.5), ("Support plan - Business", 1, 99.0)], tax_rate=0.0),
    dict(file="03_mitra_atk.pdf", layout="compact", lang="id", currency="IDR",
         vendor="Toko Mitra ATK", tax_id=None,
         number="MTK-0921", date=(2026, 9, 21), due=None,
         bill_to="Kantor Cabang Medan",
         items=[("Kertas A4 80gsm (rim)", 20, 52000), ("Tinta printer hitam", 6, 95000),
                ("Map plastik", 50, 3500), ("Pulpen gel 0.5", 24, 4500), ("Stapler besar", 2, 78000)],
         tax_rate=0.11),
    dict(file="04_pixel_forge.pdf", layout="classic", lang="en", currency="USD",
         vendor="Pixel Forge Design Co.", tax_id="EIN 12-3456789",
         number="PF-2026-031", date=(2026, 9, 10), due=(2026, 10, 10),
         bill_to="Sample Retail Inc.",
         items=[("Logo redesign", 1, 1200.0), ("Brand guideline document", 1, 800.0),
                ("Social media templates (set of 10)", 2, 150.0)], tax_rate=0.08),
    dict(file="05_jaya_teknik.pdf", layout="modern", lang="id", currency="IDR",
         vendor="PT Jaya Teknik Mandiri", tax_id="02.987.654.3-210.000",
         number="JTM/INV/IX/2026/055", date=(2026, 9, 15), due=(2026, 9, 30),
         bill_to="PT Contoh Logistik Abadi",
         items=[("Servis AC split 2 PK", 4, 175000), ("Freon R32 (per kg)", 3, 250000),
                ("Pipa tembaga 1/4 + 3/8 (per m)", 10, 85000)], tax_rate=0.11),
    # Printed total is wrong on purpose: validation must catch it.
    dict(file="06_wrong_total.pdf", layout="compact", lang="en", currency="USD",
         vendor="Northwind Office Supply", tax_id=None,
         number="NW-77120", date=(2026, 9, 2), due=(2026, 10, 2),
         bill_to="Example Studio Ltd",
         items=[("Ergonomic chair", 2, 219.0), ("Standing desk frame", 1, 340.0)], tax_rate=0.0,
         printed_total=878.0),
]


def date_text(d, lang, layout):
    y, m, day = d
    if lang == "id":
        return f"{day} {MONTHS_ID[m - 1]} {y}" if layout != "compact" else f"{day:02d}/{m:02d}/{y}"
    return f"{y}-{m:02d}-{day:02d}" if layout == "modern" else f"{m:02d}/{day:02d}/{y}"


def build(inv: dict) -> dict:
    money = fmt_idr if inv["currency"] == "IDR" else fmt_usd
    sym = "Rp" if inv["currency"] == "IDR" else "$"
    id_ = inv["lang"] == "id"
    items = [dict(description=d, quantity=q, unit_price=p, amount=round(q * p, 2)) for d, q, p in inv["items"]]
    subtotal = round(sum(i["amount"] for i in items), 2)
    tax = round(subtotal * inv["tax_rate"], 0 if inv["currency"] == "IDR" else 2)
    total = round(subtotal + tax, 2)
    printed_total = inv.get("printed_total", total)

    L = {
        "title": "FAKTUR" if id_ else "INVOICE",
        "no": "No. Faktur" if id_ else "Invoice No.",
        "date": "Tanggal" if id_ else "Date",
        "due": "Jatuh Tempo" if id_ else "Due Date",
        "to": "Kepada" if id_ else "Bill To",
        "desc": "Keterangan" if id_ else "Description",
        "qty": "Jml" if id_ else "Qty",
        "price": "Harga Satuan" if id_ else "Unit Price",
        "amount": "Jumlah" if id_ else "Amount",
        "sub": "Subtotal",
        "tax": "PPN 11%" if id_ else f"Tax {inv['tax_rate'] * 100:.0f}%",
        "total": "Total Tagihan" if id_ else "Total Due",
        "npwp": "NPWP" if id_ else "Tax ID",
    }

    story = []
    head = f"<b>{inv['vendor']}</b>"
    if inv["tax_id"]:
        head += f"<br/>{L['npwp']}: {inv['tax_id']}"
    if inv["layout"] == "modern":
        story.append(Paragraph(f"<font size=22><b>{L['title']}</b></font>", styles["Title"]))
        story.append(Paragraph(head, styles["Normal"]))
    else:
        story.append(Paragraph(head, styles["Heading2"]))
        story.append(Paragraph(f"<b>{L['title']}</b>", styles["Heading1"]))
    story.append(Spacer(1, 4 * mm))

    meta = [[L["no"], inv["number"]], [L["date"], date_text(inv["date"], inv["lang"], inv["layout"])]]
    if inv["due"]:
        meta.append([L["due"], date_text(inv["due"], inv["lang"], inv["layout"])])
    meta.append([L["to"], inv["bill_to"]])
    story.append(Table(meta, colWidths=[35 * mm, 100 * mm], hAlign="LEFT"))
    story.append(Spacer(1, 6 * mm))

    rows = [[L["desc"], L["qty"], L["price"], L["amount"]]]
    rows += [[i["description"], str(i["quantity"]), f"{sym} {money(i['unit_price'])}", f"{sym} {money(i['amount'])}"]
             for i in items]
    rows.append(["", "", L["sub"], f"{sym} {money(subtotal)}"])
    if inv["tax_rate"]:
        rows.append(["", "", L["tax"], f"{sym} {money(tax)}"])
    rows.append(["", "", L["total"], f"{sym} {money(printed_total)}"])
    t = Table(rows, colWidths=[85 * mm, 15 * mm, 35 * mm, 35 * mm])
    style = [("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
             ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold")]
    if inv["layout"] == "classic":
        style += [("GRID", (0, 0), (-1, len(items)), 0.5, colors.grey)]
    elif inv["layout"] == "modern":
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("LINEBELOW", (0, len(items)), (-1, len(items)), 0.8, colors.black)]
    t.setStyle(TableStyle(style))
    story.append(t)

    SimpleDocTemplate(str(OUT / inv["file"]), pagesize=A4, title=inv["number"]).build(story)

    y, m, d = inv["date"]
    expected = dict(
        vendor_name=inv["vendor"], vendor_tax_id=inv["tax_id"], invoice_number=inv["number"],
        invoice_date=f"{y}-{m:02d}-{d:02d}",
        due_date=f"{inv['due'][0]}-{inv['due'][1]:02d}-{inv['due'][2]:02d}" if inv["due"] else None,
        currency=inv["currency"], bill_to=inv["bill_to"], line_items=items,
        subtotal=subtotal, tax=tax, total=printed_total,
    )
    return expected


def main() -> None:
    OUT.mkdir(exist_ok=True)
    truth = {inv["file"]: build(inv) for inv in INVOICES}
    (OUT / "expected.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False))
    print(f"wrote {len(truth)} invoices to {OUT}")


if __name__ == "__main__":
    main()
