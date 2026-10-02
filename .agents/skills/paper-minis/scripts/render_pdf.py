"""Page model -> PDF, natively, with no native libraries.

Why this exists
----------------
'cairosvg' is a binding to libcairo, a C library. On macOS that means
'brew install cairo' plus a 'DYLD_FALLBACK_LIBRARY_PATH' dance, and the failure
mode is an import-time "cannot load library 'libcairo.so.2'" long after the
sheets have already been generated. A printable plugin should not hinge on a
Homebrew formula.

ReportLab is pure Python -- 'pip install reportlab', no compiler, no dylib --
so this module draws the same page model straight to PDF. It is the primary
PDF path; 'to_pdf.py' (SVG -> PDF via cairosvg/rsvg/inkscape) is the fallback
for environments that have a converter but not ReportLab.

Both renderers consume 'layout.Page' objects, so the SVG and the PDF are two
views of one model rather than a conversion chain. Millimetres are exact in
both: ReportLab works in points, and 1 mm is 72/25.4 pt by definition.

Coordinates
------------
The layout model is top-left origin, y increasing downward. PDF is bottom-left,
y increasing upward. '_y()' does the flip. Text is drawn in unflipped space so
glyphs are not mirrored; art groups use an explicit transform instead.

Vector art
----------
Procedural silhouettes are SVG fragments. Rather than shell out to a renderer,
this module reads the small primitive vocabulary 'proc_art' actually emits --
'polygon', 'ellipse', 'path' with M/L/Q/Z (absolute and relative) -- and
replays it onto the canvas. Quadratic segments become cubics, which is exact,
not an approximation. Anything outside that vocabulary is skipped rather than
guessed at, and 'unsupported()' reports it so the gap is visible.
"""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MM = 72.0 / 25.4            # points per millimetre, by definition
_SKIPPED: set[str] = set()

# One ImageReader per distinct image, not per figure drawn.
#
# This used to base64-decode the payload and build a fresh ImageReader inside
# the draw call, which happens once per *printed figure*. A roster of 113
# minis prints 226 figures from about 35 distinct images, so every image was
# decoded roughly six times over, and `mask="auto"` rebuilt its soft mask each
# time -- ReportLab's slow path for anything with an alpha channel. On
# 4096x6144 art that is what stalled PDF generation outright.
#
# The duplication also reaches the output: ReportLab keys its embedded-image
# cache on the ImageReader object, so a new one each time meant 226 copies of
# the art in the file instead of 35. That is where a 114 MB PDF came from.
#
# Keyed on the payload string, so two creatures that genuinely share an image
# also share the embed. Cleared per document by 'reset_caches()' -- a long-
# lived process rendering several rosters must not accumulate every image it
# has ever seen.
_READERS: dict[str, object] = {}


def reset_caches() -> None:
    # Only the readers. '_SKIPPED' has always accumulated for the life of the
    # process and 'unsupported()' is read after 'render()' returns; clearing
    # it here would be an unrelated behaviour change.
    _READERS.clear()


def _reader(payload: str):
    """Decoded ImageReader for a data URI, or None if it will not decode."""
    hit = _READERS.get(payload)
    if hit is not None:
        return hit
    from reportlab.lib.utils import ImageReader
    try:
        raw = base64.b64decode(payload.split(",", 1)[1])
        reader = ImageReader(io.BytesIO(raw))
    except Exception as exc:
        _SKIPPED.add(f"raster decode ({exc})")
        return None
    _READERS[payload] = reader
    return reader


_NUM = re.compile(r"(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")
_CMD = re.compile(r"([MmLlHhVvQqCcZz])")


def unsupported() -> set[str]:
    return set(_SKIPPED)


def available() -> str | None:
    try:
        import reportlab  # noqa: F401
        return "reportlab"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# tiny SVG primitive replayer
# ---------------------------------------------------------------------------

def _colour(value):
    """SVG paint -> reportlab colour, or None for 'none'."""
    from reportlab.lib import colors
    if not value or value in ("none", "transparent"):
        return None
    try:
        return colors.HexColor(value) if value.startswith("#") else colors.toColor(value)
    except Exception:
        return None


def _quad_to_cubic(p0, p1, p2):
    """Exact quadratic -> cubic Bezier promotion."""
    c1 = (p0[0] + 2 / 3 * (p1[0] - p0[0]), p0[1] + 2 / 3 * (p1[1] - p0[1]))
    c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]), p2[1] + 2 / 3 * (p1[1] - p2[1]))
    return c1, c2


def _replay_path(c, d: str):
    """Build a reportlab path from an SVG 'd' attribute. Returns the path."""
    p = c.beginPath()
    tokens, i = _CMD.split(d), 0
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = None
    parts = [t for t in tokens if t.strip()]
    while i < len(parts):
        tok = parts[i]
        if _CMD.fullmatch(tok):
            cmd = tok
            i += 1
            if cmd in ("Z", "z"):
                p.close()
                cur = start
                continue
            nums = [float(n) for n in _NUM.findall(parts[i])] if i < len(parts) else []
            i += 1
        else:
            nums = [float(n) for n in _NUM.findall(tok)]
            i += 1
        if cmd is None:
            continue
        rel = cmd.islower()
        k = 0
        while k < len(nums):
            if cmd in ("M", "m"):
                if k + 2 > len(nums):
                    break
                x, y = nums[k], nums[k + 1]
                cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
                p.moveTo(*cur)
                start = cur
                k += 2
                cmd = 'l' if rel else 'L'    # implicit lineto after moveto
            elif cmd in ("L", "l"):
                if k + 2 > len(nums):
                    break
                x, y = nums[k], nums[k + 1]
                cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
                p.lineTo(*cur)
                k += 2
            elif cmd in ("H", "h"):
                x = nums[k]
                cur = (cur[0] + x, cur[1]) if rel else (x, cur[1])
                p.lineTo(*cur)
                k += 1
            elif cmd in ("V", "v"):
                y = nums[k]
                cur = (cur[0], cur[1] + y) if rel else (cur[0], y)
                p.lineTo(*cur)
                k += 1
            elif cmd in ("Q", "q"):
                if k + 4 > len(nums):
                    break
                cx, cy, x, y = nums[k:k + 4]
                ctrl = (cur[0] + cx, cur[1] + cy) if rel else (cx, cy)
                end = (cur[0] + x, cur[1] + y) if rel else (x, y)
                c1, c2 = _quad_to_cubic(cur, ctrl, end)
                p.curveTo(c1[0], c1[1], c2[0], c2[1], end[0], end[1])
                cur = end
                k += 4
            elif cmd in ("C", "c"):
                if k + 6 > len(nums):
                    break
                a, b, cc, dd, x, y = nums[k:k + 6]
                if rel:
                    c1 = (cur[0] + a, cur[1] + b)
                    c2 = (cur[0] + cc, cur[1] + dd)
                    end = (cur[0] + x, cur[1] + y)
                else:
                    c1, c2, end = (a, b), (cc, dd), (x, y)
                p.curveTo(c1[0], c1[1], c2[0], c2[1], end[0], end[1])
                cur = end
                k += 6
            else:
                _SKIPPED.add(f"path command {cmd}")
                break
    return p


def _draw_svg_fragment(c, body: str):
    """Replay a 'proc_art'-style SVG fragment onto the current canvas state."""
    try:
        root = ET.fromstring(f'<g xmlns="http://www.w3.org/2000/svg">{body}</g>')
    except ET.ParseError as exc:
        _SKIPPED.add(f"unparseable fragment ({exc})")
        return

    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "g":
            continue
        fill = _colour(el.get("fill"))
        stroke = _colour(el.get("stroke"))
        sw = float(el.get("stroke-width", 1.0) or 1.0)
        opacity = el.get("opacity")

        c.saveState()
        if opacity:
            try:
                c.setFillAlpha(float(opacity))
                c.setStrokeAlpha(float(opacity))
            except ValueError:
                pass
        rot = el.get("transform", "")
        m = re.match(r"rotate\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)", rot)
        if m:
            ang, rx, ry = (float(g) for g in m.groups())
            c.translate(rx, ry)
            c.rotate(ang)
            c.translate(-rx, -ry)
        elif rot:
            _SKIPPED.add(f"transform {rot[:24]}")

        if fill:
            c.setFillColor(fill)
        if stroke:
            c.setStrokeColor(stroke)
            c.setLineWidth(sw)
            c.setLineCap(1)
            c.setLineJoin(1)

        if tag == "polygon":
            pts = [float(n) for n in _NUM.findall(el.get("points", ""))]
            if len(pts) >= 6:
                p = c.beginPath()
                p.moveTo(pts[0], pts[1])
                for j in range(2, len(pts) - 1, 2):
                    p.lineTo(pts[j], pts[j + 1])
                p.close()
                c.drawPath(p, stroke=bool(stroke), fill=bool(fill))
        elif tag == "ellipse":
            cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
            rx, ry = float(el.get("rx", 0)), float(el.get("ry", 0))
            c.ellipse(cx - rx, cy - ry, cx + rx, cy + ry,
                      stroke=bool(stroke), fill=bool(fill))
        elif tag == "rect":
            c.rect(float(el.get("x", 0)), float(el.get("y", 0)),
                   float(el.get("width", 0)), float(el.get("height", 0)),
                   stroke=bool(stroke), fill=bool(fill))
        elif tag == "path":
            p = _replay_path(c, el.get("d", ""))
            c.drawPath(p, stroke=bool(stroke), fill=bool(fill))
        elif tag in ("text", "image", "clipPath", "style", "defs"):
            pass        # chrome and clipping are handled by the caller
        else:
            _SKIPPED.add(tag)
        c.restoreState()


# ---------------------------------------------------------------------------
# sheet rendering
# ---------------------------------------------------------------------------

class _Sheet:
    def __init__(self, canvas, cfg):
        self.c = canvas
        self.cfg = cfg

    def y(self, y_mm: float) -> float:
        return (self.cfg.page_h - y_mm) * MM

    def x(self, x_mm: float) -> float:
        return x_mm * MM

    # -- line styles matching the SVG legend ---------------------------------
    def _style(self, kind: str):
        c = self.c
        if kind == "cut":
            c.setStrokeColorRGB(0.08, 0.08, 0.08)
            c.setLineWidth(0.25 * MM)
            c.setDash()
        elif kind == "fold":
            c.setStrokeColorRGB(0.48, 0.48, 0.48)
            c.setLineWidth(0.25 * MM)
            c.setDash(2.2 * MM, 1.4 * MM)
        elif kind == "score":
            c.setStrokeColorRGB(0.66, 0.66, 0.66)
            c.setLineWidth(0.22 * MM)
            c.setDash(0.6 * MM, 1.0 * MM)

    def line(self, x1, y1, x2, y2, kind="cut"):
        self.c.saveState()
        self._style(kind)
        self.c.line(self.x(x1), self.y(y1), self.x(x2), self.y(y2))
        self.c.restoreState()

    def text(self, x_mm, y_mm, s, size_mm, anchor="start",
             rgb=(0.17, 0.17, 0.17), bold=False, rotate=0, pivot_y_mm=None):
        """pivot_y_mm is the point rotation happens about, matching the SVG's
        'rotate(180 cx cy)'. Without it the PDF rotates about the baseline
        instead, which drops the flipped label ~1.5 mm and the cell edge
        slices it -- the two renderers must agree or the PDF lies."""
        c = self.c
        c.saveState()
        c.setFillColorRGB(*rgb)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size_mm * MM)
        pivot = y_mm if pivot_y_mm is None else pivot_y_mm
        dy = 0.0
        c.translate(self.x(x_mm), self.y(pivot))
        if rotate:
            c.rotate(rotate)
            dy = -(y_mm - pivot) * MM
        elif pivot_y_mm is not None:
            dy = -(y_mm - pivot) * MM
        if anchor == "middle":
            c.drawCentredString(0, dy, s)
        elif anchor == "end":
            c.drawRightString(0, dy, s)
        else:
            c.drawString(0, dy, s)
        c.restoreState()

    # -- one cell ------------------------------------------------------------
    def cell(self, cell, mirror_back: bool, labels: bool):
        import render_svg
        c = self.c
        w = cell.cell_w
        band = (getattr(cell, "palette", None) or ["#555555"])[0]

        col = _colour(band)
        if col:
            for by, bh in cell.bands():
                c.saveState()
                c.setFillColor(col)
                c.setFillAlpha(0.92)
                c.rect(self.x(cell.x), self.y(cell.y + by + bh),
                       w * MM, bh * MM, stroke=0, fill=1)
                c.restoreState()

        for ay, flip in cell.art_boxes():
            self._art(cell, ay, flip, mirror_back)

        if labels:
            tag, fs = render_svg._fit_label(
                cell.label + (f" ({cell.index})" if cell.group_total > 1 else ""),
                w - 2.0, max_pt=min(2.4, cell.band_h * 0.58))
            ink = render_svg._on_band(band)
            rgb = (0.09, 0.036, 0.18) if ink != "#ffffff" else (1, 1, 1)
            for y_base, pivot, rot in cell.labels():
                self.text(cell.x + w / 2, cell.y + y_base, tag, fs, "middle",
                          rgb, bold=True,
                          rotate=180 if rot else 0,
                          pivot_y_mm=cell.y + pivot)

        for sy in cell.score_ys():
            self.line(cell.x, cell.y + sy, cell.x + w, cell.y + sy, "score")

        pts = cell.outline()
        c.saveState()
        self._style("cut")
        p = c.beginPath()
        p.moveTo(self.x(cell.x + pts[0][0]), self.y(cell.y + pts[0][1]))
        for px, py in pts[1:]:
            p.lineTo(self.x(cell.x + px), self.y(cell.y + py))
        p.close()
        c.drawPath(p, stroke=1, fill=0)
        c.restoreState()

    def _art(self, cell, y_off: float, flip: bool, mirror_back: bool):
        art = cell.art
        c = self.c
        x0 = cell.x + (cell.cell_w - cell.art_w) / 2
        y_top = cell.y + y_off
        w_pt, h_pt = cell.art_w * MM, cell.art_h * MM

        c.saveState()
        p = c.beginPath()
        p.rect(self.x(x0), self.y(y_top + cell.art_h), w_pt, h_pt)
        c.clipPath(p, stroke=0, fill=0)

        if art.kind == "raster":
            img = _reader(art.payload)
            if img is None:
                c.restoreState()
                return
            c.saveState()
            if flip:
                c.translate(self.x(x0), self.y(y_top))
                c.scale(1, -1)
                if mirror_back:
                    c.translate(w_pt, 0)
                    c.scale(-1, 1)
                c.drawImage(img, 0, 0, w_pt, h_pt, mask="auto")
            else:
                c.drawImage(img, self.x(x0), self.y(y_top + cell.art_h),
                            w_pt, h_pt, mask="auto")
            c.restoreState()
        else:
            vw = art.view_w or 100.0 * max(art.aspect, 0.08)
            vh = art.view_h or 100.0
            c.saveState()
            c.translate(self.x(x0), self.y(y_top))
            c.scale(w_pt / vw, -h_pt / vh)
            if flip:
                c.translate(0, vh)
                c.scale(1, -1)
                if mirror_back:
                    c.translate(vw, 0)
                    c.scale(-1, 1)
            _draw_svg_fragment(c, art.payload)
            c.restoreState()
        c.restoreState()

    def row_guides(self, page):
        """Cut and fold lines across the whole sheet -- see render_svg for why
        only the horizontals can do this."""
        for row in page.rows:
            if not row.cells:
                continue
            c = row.cells[0]
            for y, kind in ((c.y, "cut"),
                            (c.y + c.cell_h, "cut"),
                            (c.y + c.fold_y, "fold")):
                self.line(0, y, self.cfg.page_w, y, kind)

    # -- page chrome ---------------------------------------------------------
    def chrome(self, page_no, total, title, subtitle=""):
        cfg, m = self.cfg, self.cfg.margin_mm
        W, H = cfg.page_w, cfg.page_h

        for cx, cy in ((m, m), (W - m, m), (m, H - m), (W - m, H - m)):
            dx = 4 if cx < W / 2 else -4
            dy = 4 if cy < H / 2 else -4
            self.line(cx, cy, cx + dx, cy, "cut")
            self.line(cx, cy, cx, cy + dy, "cut")

        self.text(m, m - 4.2, title, 4.0, bold=True)
        if subtitle:
            self.text(m, m - 8.4, subtitle, 2.6, rgb=(0.42, 0.42, 0.42))
        self.text(W - m, m - 4.2, f"Sheet {page_no} of {total}", 3.2, "end")

        lx, ly = W - m - 58, m - 8.6
        for dx, kind, label in ((0, "cut", "cut"), (17, "fold", "fold"),
                                (34, "score", "base score")):
            self.line(lx + dx, ly, lx + dx + 7, ly, kind)
            self.text(lx + dx + 8.4, ly - 0.9, label, 2.3, rgb=(0.42, 0.42, 0.42))

        by = H - m - 4.0
        self.line(m, by, m + 50, by, "cut")
        for i in range(6):
            x = m + i * 10
            self.line(x, by, x, by - (2.4 if i % 5 == 0 else 1.4), "cut")
        self.text(m + 52, by, "this bar must measure 50 mm - print at 100% / "
                  '"Actual Size, never "Fit to page""', 2.5,
                  rgb=(0.42, 0.42, 0.42))


def render(pages, cfg, out_pdf: Path, title: str, subtitle: str = ""):
    """Write every page to one PDF. Returns the path."""
    from reportlab.pdfgen import canvas as rl_canvas

    out_pdf = Path(out_pdf)
    # Per document, not per process: the reader cache is keyed on image
    # payloads, and holding one roster's decoded art while rendering the next
    # would grow without bound in a long-lived process.
    reset_caches()
    c = rl_canvas.Canvas(str(out_pdf), pagesize=(cfg.page_w * MM, cfg.page_h * MM))
    c.setTitle(title)
    for page in pages:
        sheet = _Sheet(c, cfg)
        sheet.chrome(page.index, len(pages), title, subtitle)
        sheet.row_guides(page)
        for row in page.rows:
            for cell in row.cells:
                sheet.cell(cell, cfg.mirror_back, cfg.labels)
        c.showPage()
    c.save()
    return out_pdf
