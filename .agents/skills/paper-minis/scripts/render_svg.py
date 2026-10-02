"""Page model -> SVG, in real millimetres.

The SVG is authored in a viewBox of '0 0 <page_w> <page_h>' with
'width'/'height' in mm, so one user unit is exactly one millimetre. Nothing
downstream rescales: what the ruler says in the file is what comes out of the
printer, provided the printer is told to print at 100%.

Line semantics match the legend printed on every sheet:
  solid    cut
  dashed   fold (the single centre fold)
  dotted   internal fold -- base style only; clip style emits none
"""

from __future__ import annotations

from xml.sax.saxutils import escape

FONT = '"DejaVu Sans", Helvetica, Arial, sans-serif'
CUT = "#141414"
FOLD = "#7a7a7a"
SCORE = "#a8a8a8"
INK = "#2b2b2b"

CSS = f"""
  .cut   {{ fill:none; stroke:{CUT}; stroke-width:0.25; }}
  .fold  {{ fill:none; stroke:{FOLD}; stroke-width:0.25; stroke-dasharray:2.2 1.4; }}
  .score {{ fill:none; stroke:{SCORE}; stroke-width:0.22; stroke-dasharray:0.6 1.0; }}
  .crop  {{ fill:none; stroke:{CUT}; stroke-width:0.2; }}
  .lbl   {{ font-family:{FONT}; font-weight:600; }}
  .meta  {{ font-family:{FONT}; fill:{INK}; }}
  .dim   {{ font-family:{FONT}; fill:#6b6b6b; }}
"""

# Mean glyph advance as a fraction of font size for semibold DejaVu Sans at
# mixed case. Measured empirically against rendered output: erring high is
# correct because the failure mode of erring low is a label crossing the cut
# line into the neighbouring mini.
_AVG_GLYPH = 0.64


def _fit_label(text: str, avail_mm: float, max_pt: float, min_pt: float = 1.30):
    """Shrink, then truncate. A label that runs into the neighbouring mini is
    worse than a label that is slightly small, and both are better than one
    that silently overlaps the cut line."""
    fs = max_pt
    while fs > min_pt and len(text) * _AVG_GLYPH * fs > avail_mm:
        fs -= 0.05
    max_chars = max(3, int(avail_mm / (_AVG_GLYPH * fs)))
    if len(text) > max_chars:
        text = text[:max_chars - 1].rstrip() + "…"
    return text, fs


def _on_band(hex_colour: str) -> str:
    """Readable label colour for a given band. A player character picks its own
    base colour, and a pale one (white plate, bone, saffron) makes white text
    vanish -- so the text follows the band rather than the band following the
    text."""
    try:
        h = hex_colour.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return "#ffffff"
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#17161e" if lum > 0.55 else "#ffffff"


def _art_group(cell, y_top: float, flip: bool, mirror_back: bool,
               clip_id: str | None = None):
    """One copy of the art, its top edge at 'y_top', optionally flipped."""
    art = cell.art
    x0 = (cell.cell_w - cell.art_w) / 2.0

    if art.kind == "raster":
        body = (f'<image x="{x0:.3f}" y="0" width="{cell.art_w:.3f}" '
                f'height="{cell.art_h:.3f}" preserveAspectRatio="none" '
                f'xlink:href="{art.payload}" href="{art.payload}"/>')
    else:
        vw = art.view_w or 100.0 * max(art.aspect, 0.08)
        vh = art.view_h or 100.0
        body = (f'<g transform="translate({x0:.3f},0) '
                f'scale({cell.art_w/vw:.5f},{cell.art_h/vh:.5f})">{art.payload}</g>')

    if flip and mirror_back:
        body = (f'<g transform="translate({cell.cell_w:.3f},0) scale(-1,1)">'
                f'{body}</g>')

    if clip_id:
        # clip in the art's own (possibly flipped) frame
        body = f'<g clip-path="url(#{clip_id})">{body}</g>'

    if flip:
        # place the box then invert y about its own top edge
        return (f'<g transform="translate(0,{y_top + cell.art_h:.3f}) scale(1,-1)">'
                f'<g transform="translate(0,{-y_top:.3f})">{body}</g></g>')
    return f'<g transform="translate(0,{y_top:.3f})">{body}</g>'


def _cell_svg(cell, cfg):
    pal = getattr(cell, "palette", None) or ["#555555", "#333333", "#eeeeee"]
    band = pal[0]
    pts = " ".join(f"{x:.3f},{y:.3f}" for x, y in cell.outline())
    w = cell.cell_w

    cid = f"ab{cell.page}_{cell.row}_{int(round(cell.x * 10))}_{int(round(cell.y * 10))}"
    x0 = (w - cell.art_w) / 2.0
    g = [f'<g transform="translate({cell.x:.3f},{cell.y:.3f})">']

    for i, (ay, flip) in enumerate(cell.art_boxes()):
        g.append(f'<clipPath id="{cid}_{i}"><rect x="{x0:.3f}" y="{ay:.3f}" '
                 f'width="{cell.art_w:.3f}" height="{cell.art_h:.3f}"/></clipPath>')

    for by, bh in cell.bands():
        g.append(f'<rect x="0" y="{by:.3f}" width="{w:.3f}" height="{bh:.3f}" '
                 f'fill="{band}" fill-opacity="0.92"/>')

    for i, (ay, flip) in enumerate(cell.art_boxes()):
        g.append(_art_group(cell, ay, flip, cfg.mirror_back, f"{cid}_{i}"))

    if cfg.labels:
        tag, fs = _fit_label(
            cell.label + (f" ({cell.index})" if cell.group_total > 1 else ""),
            w - 2.0, max_pt=min(2.4, cell.band_h * 0.58))
        tag = escape(tag)
        ink = _on_band(band)
        for y_base, pivot, rot in cell.labels():
            spin = (f' transform="rotate(180 {w/2:.3f} {pivot:.3f})"'
                    if rot else '')
            g.append(f'<text class="lbl" x="{w/2:.3f}" y="{y_base:.3f}" '
                     f'fill="{ink}" font-size="{fs:.2f}" '
                     f'text-anchor="middle"{spin}>{tag}</text>')

    for sy in cell.score_ys():
        g.append(f'<path class="score" d="M0,{sy:.3f} L{w:.3f},{sy:.3f}"/>')

    g.append(f'<polygon class="cut" points="{pts}"/>')
    g.append('</g>')
    return "".join(g)


def _row_guides(page, cfg):
    """Cut and fold lines extended across the whole sheet.

    Cells in a row share a height, so a row has exactly one top edge, one
    bottom edge and one fold line -- and running them the full width lets you
    lay a ruler across the page and crease or guillotine a whole strip in one
    pass. Vertical cuts cannot do this: cell widths differ between rows, so a
    full-height vertical would slice through a neighbouring row's minis.
    """
    out = []
    for row in page.rows:
        if not row.cells:
            continue
        c = row.cells[0]
        for y, cls in ((c.y, "cut"),
                       (c.y + c.cell_h, "cut"),
                       (c.y + c.fold_y, "fold")):
            out.append(f'<path class="{cls}" d="M0,{y:.3f} L{cfg.page_w:.3f},{y:.3f}"/>')
    return "".join(out)


def _chrome(cfg, page_no, total_pages, title, subtitle=""):
    W, H, m = cfg.page_w, cfg.page_h, cfg.margin_mm
    out = []

    for x, y in ((m, m), (W - m, m), (m, H - m), (W - m, H - m)):
        dx = 4 if x < W / 2 else -4
        dy = 4 if y < H / 2 else -4
        out.append(f'<path class="crop" d="M{x:.2f},{y:.2f} l{dx},0 M{x:.2f},{y:.2f} l0,{dy}"/>')

    out.append(f'<text class="meta" x="{m:.2f}" y="{m+4.2:.2f}" font-size="4" '
               f'font-weight="700">{escape(title)}</text>')
    if subtitle:
        out.append(f'<text class="dim" x="{m:.2f}" y="{m+8.4:.2f}" font-size="2.6">'
                   f'{escape(subtitle)}</text>')
    out.append(f'<text class="meta" x="{W-m:.2f}" y="{m+4.2:.2f}" font-size="3.2" '
               f'text-anchor="end">Sheet {page_no} of {total_pages}</text>')

    # legend
    lx, ly = W - m - 58, m - 8.6
    out.append(f'<path class="cut" d="M{lx:.2f},{ly:.2f} l7,0"/>')
    out.append(f'<text class="dim" x="{lx+8.4:.2f}" y="{ly+0.9:.2f}" font-size="2.3">cut</text>')
    out.append(f'<path class="fold" d="M{lx+17:.2f},{ly:.2f} l7,0"/>')
    out.append(f'<text class="dim" x="{lx+25.4:.2f}" y="{ly+0.9:.2f}" font-size="2.3">fold</text>')
    out.append(f'<path class="score" d="M{lx+36:.2f},{ly:.2f} l7,0"/>')
    out.append(f'<text class="dim" x="{lx+44.4:.2f}" y="{ly+0.9:.2f}" font-size="2.3">base score</text>')

    # scale-check ruler: the single most useful thing on a print-to-scale sheet
    by = H - m - 4.0
    out.append(f'<path class="cut" d="M{m:.2f},{by:.2f} l50,0"/>')
    for i in range(6):
        x = m + i * 10
        out.append(f'<path class="cut" d="M{x:.2f},{by:.2f} l0,{-2.4 if i%5==0 else -1.4}"/>')
    out.append(f'<text class="dim" x="{m+52:.2f}" y="{by:.2f}" font-size="2.5">'
               f"this bar must measure 50 mm &#8212; print at 100% / Actual Size, "
               f'never &#8220;Fit to page&#8221;</text>')

    return "".join(out)


def render_page(page, cfg, total_pages, title, subtitle=""):
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{cfg.page_w}mm" height="{cfg.page_h}mm" '
        f'viewBox="0 0 {cfg.page_w} {cfg.page_h}">',
        f'<style>{CSS}</style>',
        f'<rect x="0" y="0" width="{cfg.page_w}" height="{cfg.page_h}" fill="#ffffff"/>',
        _chrome(cfg, page.index, total_pages, title, subtitle),
    ]
    body.append(_row_guides(page, cfg))
    for row in page.rows:
        for cell in row.cells:
            body.append(_cell_svg(cell, cfg))
    body.append('</svg>')
    return "\n".join(body)
