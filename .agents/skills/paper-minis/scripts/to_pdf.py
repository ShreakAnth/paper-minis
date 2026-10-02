"""SVG -> PDF, preserving real millimetres.

`cairosvg` is the primary path because it honours the mm units declared on the
root `<svg>` element, so a 50 mm ruler in the SVG is 50 mm in the PDF. The
per-page PDFs are then merged. Every step degrades gracefully: if no converter
is installed the SVGs are still written and still printable from a browser
(at 100%), so a missing dependency never costs you the sheet.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def available():
    try:
        import cairosvg  # noqa: F401
        return 'cairosvg'
    except Exception:
        pass
    for exe in ("rsvg-convert", "inkscape", "chromium", "google-chrome"):
        if shutil.which(exe):
            return exe
    return None


def _one(svg_path: Path, pdf_path: Path) -> bool:
    try:
        import cairosvg
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        return True
    except Exception:
        pass
    if shutil.which("rsvg-convert"):
        r = subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(pdf_path), str(svg_path)],
                           capture_output=True)
        return r.returncode == 0
    if shutil.which("inkscape"):
        r = subprocess.run(["inkscape", str(svg_path), "--export-type=pdf",
                           "--export-filename=" + str(pdf_path)], capture_output=True)
        return r.returncode == 0
    return False


def _merge(pdfs, out: Path) -> bool:
    try:
        from pypdf import PdfWriter
    except Exception:
        try:
            from PyPDF2 import PdfWriter  # type: ignore
        except Exception:
            return False
    w = PdfWriter()
    for p in pdfs:
        w.append(str(p))
    with open(out, "wb") as fh:
        w.write(fh)
    return True


def convert(svg_paths, out_pdf: Path, keep_pages=True):
    """Returns (merged_pdf_or_None, per_page_pdfs, notes)."""
    out_pdf = Path(out_pdf)
    notes = []
    if not available():
        notes.append("no SVG->PDF converter found; SVGs written only "
                     "(print from a browser at 100%)")
        return None, [], notes

    pages = []
    for svg in svg_paths:
        svg = Path(svg)
        pdf = svg.with_suffix(".pdf")
        if _one(svg, pdf):
            pages.append(pdf)
        else:
            notes.append(f"failed to convert {svg.name}")

    merged = None
    if pages and _merge(pages, out_pdf):
        merged = out_pdf
        if not keep_pages:
            for p in pages:
                p.unlink(missing_ok=True)
            pages = []
    elif pages:
        notes.append("pypdf not installed: per-page PDFs kept unmerged "
                     "(pip install pypdf to get one file)")

    return merged, pages, notes