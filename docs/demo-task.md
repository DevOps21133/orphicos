# OrphicOS Flagship Demo — Invoices → Spreadsheet → Summary

The Phase 4 money demo: one spoken/typed command that reads several PDFs, moves
their key figures into a spreadsheet, sums them, and writes a plain-language
summary in Notepad. It exercises the whole product — file system, PDF viewer,
spreadsheet, and Notepad — in a single hands-free run across four apps.

## Setup

`scripts\reset_demo.ps1` wipes and regenerates `C:\OrphicDemo\invoices\` with five
fixed PDF invoices (`demo\make_invoices.py`). Run it before every take so each
recording starts from an identical folder.

## The canonical command (say it or type it verbatim)

> Go through the PDFs in C:\OrphicDemo\invoices, put each vendor and total into a
> new spreadsheet, sum the column, then write a short summary in Notepad.

(The build spec's wording says "a new Excel sheet." This machine has **LibreOffice
Calc, not Excel**, so the client's app-alias fallback opens Calc automatically when
the brain asks for Excel — the command still works either way. Saying "spreadsheet"
avoids the brand entirely.)

## Expected result (for verifying a run — do NOT read this to the model)

The five invoices and their totals:

| Invoice        | Vendor            | Total       |
|----------------|-------------------|-------------|
| invoice_1.pdf  | Northwind Traders | $1,284.50   |
| invoice_2.pdf  | Contoso Ltd       | $3,947.00   |
| invoice_3.pdf  | Fabrikam Inc      | $812.75     |
| invoice_4.pdf  | Adventure Works   | $5,230.20   |
| invoice_5.pdf  | Wingtip Toys      | $2,199.99   |
| **Sum**        |                   | **$13,474.44** |

A run is correct when the spreadsheet holds all five vendors with their matching
totals, the column sum reads **$13,474.44**, and the Notepad summary states that
total (and ideally the invoice count and the largest vendor, Adventure Works).

## Why this is the hard demo

Each invoice must be opened and *read* — the vendor and total are text inside the
PDF, not in the filename. Tree-first perception reads the PDF viewer where it can;
the vision fallback (active-window crop) covers viewers that render to a canvas.
Then the data crosses into a spreadsheet, gets summed, and is narrated in Notepad:
four apps, one command, no hands.
