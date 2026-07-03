"""Unit tests for client.perceive.documents.read_document_text.

The PDFs here are built with reportlab purely as TEST FIXTURES (CLAUDE.md Rule 14) —
the code under test is read_document_text, the genuine client document reader.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from client.perceive.documents import NO_TEXT_MARKER, read_document_text


def _pdf_with_text(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, text)
    c.showPage()
    c.save()


def _pdf_no_text(path: Path) -> None:
    # A page with only a drawn shape and no text ops — mimics a scanned/image PDF.
    c = canvas.Canvas(str(path))
    c.rect(72, 700, 200, 50)
    c.showPage()
    c.save()


class ReadDocumentTextTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_reads_pdf_text(self) -> None:
        p = self.dir / "inv.pdf"
        _pdf_with_text(p, "Vendor Northwind Total Due 1,284.50")
        out = read_document_text(p)
        self.assertIn("Northwind", out)
        self.assertIn("1,284.50", out)

    def test_reads_plain_text_file(self) -> None:
        p = self.dir / "note.txt"
        p.write_text("hello from a text file", encoding="utf-8")
        self.assertEqual(read_document_text(p), "hello from a text file")

    def test_scanned_pdf_returns_marker(self) -> None:
        p = self.dir / "scan.pdf"
        _pdf_no_text(p)
        self.assertEqual(read_document_text(p), NO_TEXT_MARKER)

    def test_empty_text_file_returns_marker(self) -> None:
        p = self.dir / "blank.txt"
        p.write_text("   \n\t ", encoding="utf-8")  # only whitespace
        self.assertEqual(read_document_text(p), NO_TEXT_MARKER)

    def test_unsupported_type_raises_valueerror(self) -> None:
        p = self.dir / "pic.png"
        p.write_bytes(b"\x89PNG")
        with self.assertRaises(ValueError):
            read_document_text(p)

    def test_long_text_is_truncated(self) -> None:
        p = self.dir / "big.txt"
        p.write_text("x" * 10_000, encoding="utf-8")
        out = read_document_text(p)
        self.assertTrue(out.endswith("[truncated]"))
        self.assertLess(len(out), 6_100)  # capped near _MAX_CHARS, not the full 10k


if __name__ == "__main__":
    unittest.main()
