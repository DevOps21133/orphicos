"""Read a document's text straight from disk — a third perception mode (Rule 5).

Opening a file in a GUI viewer is how a *human* reads it; the client can read the
bytes. For a text-bearing PDF (or a plain-text file) this returns the exact content
instantly — no viewer to launch, no file-association picker, no browser first-run
onboarding to fight, and none of the vision model's guessing at a downscaled page.
It is both faster (the product's #1 concern) and more reliable than screenshotting.

Scanned / image-only PDFs carry no extractable text; those return NO_TEXT_MARKER so
the caller can fall back to opening a viewer + the cropped-screenshot vision path.
Perception only: no LLM, no network — the extracted text stays behind the client wall
until the loop sends it to the brain as an action result, subject to zero-retention.
"""
from __future__ import annotations

from pathlib import Path

# Returned when a PDF has no extractable text (scanned/photographed pages). It tells
# the brain to fall back to the viewer + screenshot path for THIS file specifically.
NO_TEXT_MARKER = ("[no extractable text — this looks like a scanned/image PDF; "
                  "open it in a viewer with open_path and read it from a screenshot]")

# Cap on returned text so one huge document cannot blow up the decision payload
# (the loop also bounds how much of an action result it forwards to the brain).
_MAX_CHARS = 6000

# Plain-text document types we can read directly (no parsing library needed).
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".log", ".json", ".xml",
                  ".ini", ".tsv", ".yml", ".yaml", ".py"}


def read_document_text(path: Path) -> str:
    """Extract a document's text. Raises ValueError for an unsupported file type."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix in _TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(
            f"cannot read '{suffix or '(no extension)'}' as text — read_document handles "
            "PDFs and plain-text files; open other types with open_path instead")
    text = text.strip()
    if not text:
        return NO_TEXT_MARKER
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS].rstrip() + "\n…[truncated]"
    return text


def _read_pdf(path: Path) -> str:
    # Imported lazily so pypdf is only loaded when a PDF is actually read.
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)
