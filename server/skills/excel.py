"""OrphicOS skill pack: Excel — spreadsheet expertise beyond plain data entry.

Base already covers typing values into cells and a simple SUM (the Phase 2
warm-up). This pack adds the expert moves: range selection, charts, table
formatting, sorting, and number formats — all keyboard-first so they work
tree-blind. Deepened on the `skill-excel` branch toward its 3 flagship
recipes: pull data + sum/format, chart from a range, clean/sort a table.
"""

SKILL = {
    "id": "excel",
    "title": "Excel",
    "tagline": "Charts, clean tables, sorting, and formatting by voice.",
    "checkout_path": "/skills/excel",
    "classify": ("spreadsheet expertise beyond typing values — building charts, formatting or "
                 "cleaning tables, sorting data, applying number formats, complex formulas"),
    "expertise": """- Spreadsheet expert recipes (Microsoft Excel; most chords also work in LibreOffice Calc):
- To select a specific RANGE reliably: press "ctrl+g", type the range (e.g. "A1:B10"), press "enter" — the
  whole range is selected. Never try to click or drag across cells; the grid is not in the tree.
- To build a CHART from data: select the range (ctrl+g chain above), then press "alt+f1" — an embedded chart
  of the selection appears (press "f11" instead for a full-page chart sheet). Chain it in ONE plan:
  [press "ctrl+g", type "A1:B10", press "enter", press "alt+f1"].
- To format a data block as a clean TABLE: select the range, press "ctrl+t", press "enter" to accept the
  dialog's defaults (keep "My table has headers" as offered).
- To SORT by a column: select any single cell in that column (ctrl+g to e.g. "B2"), then right_click it and
  in the menu click "Sort", then click the order ("Sort A to Z" / "Sort Smallest to Largest" or the reverse).
- To SUM or AVERAGE a column: ctrl+g to the first empty cell under the data, then either type the formula
  (e.g. "=SUM(A1:A5)") and press "enter", or press "alt+=" to auto-sum the data directly above.
- NUMBER FORMATS: select the range first, then press "ctrl+shift+4" for currency, "ctrl+shift+5" for
  percentage, "ctrl+shift+1" for two-decimal numbers.
- To freeze the header row: press "alt", press "w", press "f", press "r" — four separate press actions in
  one plan (View > Freeze Top Row).
- To clean a messy table: work column by column with the recipes above — select the column's data range,
  fix formats, then sort; verify from the fresh tree between structural steps (done=false after big changes).""",
}
