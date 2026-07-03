"""Generate the OrphicOS demo invoices — the flagship cross-app task's input.

Writes five real, text-based PDF invoices into C:\\OrphicDemo\\invoices\\. They are
DEMO INPUT FIXTURES for the Phase 4 task (CLAUDE.md §8), not product code and not
wired into any client/server path: OrphicOS reads them live off disk exactly like a
user's own invoices. Vendor and total live in the PDF *text* (extractable, no OCR),
and filenames are numbered so the model must open each file to learn the vendor.

Content is fixed so scripts/reset_demo.ps1 regenerates byte-comparable folders take
after take. Line items sum exactly to each Total Due (no tax) so the demo's grand
total is unambiguous and verifiable: the five totals sum to $13,474.44.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

INVOICE_DIR = Path(r"C:\OrphicDemo\invoices")

# (vendor, invoice no., date, [(description, amount), ...]) — items sum to the total.
INVOICES = [
    ("Northwind Traders", "NW-1042", "2026-06-03",
     [("Office supplies", 784.50), ("Printer paper (20 boxes)", 500.00)]),
    ("Contoso Ltd", "CT-2087", "2026-06-11",
     [("Cloud hosting (annual)", 3600.00), ("Priority support add-on", 347.00)]),
    ("Fabrikam Inc", "FB-0663", "2026-06-18",
     [("Replacement parts", 612.75), ("Shipping", 200.00)]),
    ("Adventure Works", "AW-5510", "2026-06-24",
     [("Conference sponsorship", 5000.00), ("Badge printing", 230.20)]),
    ("Wingtip Toys", "WT-3391", "2026-06-29",
     [("Promotional items", 1899.99), ("Freight", 300.00)]),
]


def _draw_invoice(path: Path, vendor: str, number: str, date: str,
                  items: list[tuple[str, float]]) -> float:
    """Render one single-page invoice PDF; return its Total Due."""
    total = round(sum(amount for _, amount in items), 2)
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    left = inch
    y = height - inch

    c.setFont("Helvetica-Bold", 22)
    c.drawString(left, y, "INVOICE")
    c.setFont("Helvetica", 11)
    c.drawRightString(width - inch, y, f"Invoice #: {number}")
    c.drawRightString(width - inch, y - 16, f"Date: {date}")

    y -= 0.6 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(left, y, vendor)
    c.setFont("Helvetica", 10)
    c.drawString(left, y - 15, "Bill To: OrphicOS Demo Co.")

    y -= 0.9 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Description")
    c.drawRightString(width - inch, y, "Amount (USD)")
    c.line(left, y - 4, width - inch, y - 4)

    c.setFont("Helvetica", 10)
    for description, amount in items:
        y -= 20
        c.drawString(left, y, description)
        c.drawRightString(width - inch, y, f"{amount:,.2f}")

    y -= 28
    c.line(left, y + 12, width - inch, y + 12)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Total Due:")
    c.drawRightString(width - inch, y, f"${total:,.2f}")

    c.showPage()
    c.save()
    return total


def main() -> None:
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    grand_total = 0.0
    for i, (vendor, number, date, items) in enumerate(INVOICES, start=1):
        path = INVOICE_DIR / f"invoice_{i}.pdf"
        total = _draw_invoice(path, vendor, number, date, items)
        grand_total += total
        print(f"  {path.name}  {vendor:<20} ${total:,.2f}")
    print(f"\n{len(INVOICES)} invoices written to {INVOICE_DIR}")
    print(f"Expected grand total: ${round(grand_total, 2):,.2f}")


if __name__ == "__main__":
    main()
