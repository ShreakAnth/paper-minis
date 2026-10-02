"""Cell geometry and sheet packing.

Two fold styles
---------------
**clip** (default) -- binder-clip stand. Feet point outward, heads meet at the
fold, and a binder clip on the bottom is both the fastening and the base:

      |< clip grip >|           y = 0       blank strip
      |   name band |           y = clip_h  coloured, stays visible
      |    figure   |  art_h    feet up, head down
      |-------------|           y = cell_h/2 <- dashed: the ONLY fold
      |    figure   |  art_h    head up, feet down
      |   name band |
      |< clip grip >|           y = cell_h

  Fold once. Both outer ends land together at the bottom; clip them. Done --
  no glue, no scoring, and the cut outline is a plain rectangle.

  Why it beats fold-out tabs: the paper holds the plies at the folded top and
  the clip holds them at the bottom, so nothing needs gluing. The clip's mass
  sits low, which is far more stable than creased paper, especially for Large
  and up. And it comes apart for flat storage, with the clips reused.

  The clip is the footprint, so the paper no longer has to equal the grid
  square -- but 'sizes.clip_for()' says which clip does: a 1 inch binder clip
  is 25.4 x 12.7 mm, exactly a Medium square. Large wants 2 inches, i.e. two
  1 inch clips side by side.

**base** -- the original. Cut shape per half is figure + base bar ("_"), the
halves share the bar, so the whole cell is an I-beam:

             _
      |   figure   |  art_h     head up, feet down
      |------------|            y = art_h      <- dotted: internal fold
      |  base bar  |  base_h
      |============|            y = cell_h/2   <- dashed: main fold
      |  base bar  |  base_h
      |------------|            y = cell_h-art_h <- dotted: internal fold
      |   figure   |  art_h     mirrored
             -                  y = cell_h

  Fold on the centre line, then fold both base bars outward on the dotted
  lines. Footprint = base_w wide by 2 x base_h deep, taken from the grid
  square. Needs glue to stop the heads flapping.

Why the mirrored half is flipped *vertically* and not rotated: folding about a
horizontal line maps (x, fold+d) -> (x, fold-d). A vertical flip is exactly
that map. A 180 degree rotation would also put the head up, but it mirrors in
the fold plane and shifts the figure, so the plies would not line up. (The back
ply then reads left-right reversed through the paper, as in every commercial
set; 'mirror_back=True' gives a true back view.)

Packing
-------
Shelf packing with uniform row heights, NOT free 2D bin packing. Free packing
saves a few percent of paper and produces a jagged staircase of cut lines that
is miserable with scissors. Uniform rows give full-width straight cuts: you
guillotine the sheet into strips, then chop each strip into minis.

Cells are bucketed by cell height (which is a function of size class only), so
every Medium creature shares rows, every Large creature shares rows, and each
creature's individuals stay contiguous within its bucket.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sizes import base_width_mm, figure_height_mm

# Reference silhouette for area normalisation: an armoured humanoid. Chosen so
# that Medium creatures keep the dimensions they already had.
REF_ASPECT = 0.62
MIN_H_RATIO = 0.55
MAX_H_RATIO = 1.35

PAPERS = {
    "a4":     (210.0, 297.0),       # default
    "a3":     (297.0, 420.0),
    "a2":     (420.0, 594.0),
    "letter": (215.9, 279.4),
    "legal":  (215.9, 355.6),
}


@dataclass
class Cell:
    label: str
    key: str
    size: str
    index: int                          # 1-based individual number within its creature group
    group_total: int
    art_h: float
    art_w: float
    base_w: float
    base_h: float
    art: object                         # art_provider.Art
    poses: str = "pairs"                # "pairs" | "single" -- see art_provider.pose_for
    box_w: float = 0.0                  # width the CELL reserves for art; 0 = use art_w
    box_h: float = 0.0                  # height the CELL reserves for art; 0 = use art_h
    fold_style: str = "clip"            # "clip" (binder-clip stand) | "base" (fold-out tabs)
    clip_h: float = 10.0                # clip grip zone per half, clip style only
    min_w: float = 25.4                 # clip style: narrowest the paper may be
    palette: list = field(default_factory=lambda: ["#555555", "#333333", "#eeeeee"])
    x: float = 0.0                      # placed top-left on the page, mm
    y: float = 0.0
    page: int = 0
    row: int = 0
    warnings: list = field(default_factory=list)

    @property
    def clip(self) -> bool:
        return self.fold_style == "clip"

    @property
    def cell_w(self) -> float:
        # Clip style: the clip is the footprint, so the paper no longer has to
        # match the grid square -- which is what turns the cut outline into a
        # rectangle. But it still needs a floor: a 1 inch clip gripping a 7 mm
        # ribbon holds nothing, and a 7 mm strip has no room for a name.
        if self.clip:
            # One frame per size class. The art floats inside it -- a wide pose
            # fills the width, a tall one fills the height -- but the cut
            # rectangle is identical for every creature of this size, so the
            # sheet guillotines both ways.
            return max((self.box_w or self.art_w) + 1.6, self.min_w)
        return self.base_w

    @property
    def reserved_h(self) -> float:
        """Vertical space the cell gives the art. Shrink-to-fit makes art_h
        vary per creature, but every cell in a size class must stay the same
        height or rows stop bucketing and the full-width cuts are lost. So the
        cell reserves the class box and a short creature simply has air above
        it."""
        return self.box_h or self.art_h

    @property
    def cell_h(self) -> float:
        pad = self.clip_h if self.clip else self.base_h
        return 2.0 * (self.reserved_h + pad)

    @property
    def fold_y(self) -> float:
        return self.cell_h / 2.0

    @property
    def band_h(self) -> float:
        """Coloured name band. Clip style puts it at the inner edge of the grip
        zone, so it stays readable when the clip is pushed on ~8 mm."""
        return min(4.0, self.clip_h * 0.45) if self.clip else self.base_h

    def art_boxes(self):
        """[(y_top, flip)] for the two copies, cell-local mm.

        Clip style: feet point OUTWARD to the clip, heads meet at the fold, so
        the top half is the flipped one -- the opposite of base style.

        Feet always sit against the band; the slack goes above the head.
        """
        if self.clip:
            return [(self.clip_h, True),
                    (self.cell_h - self.clip_h - self.art_h, False)]
        return [(self.reserved_h - self.art_h, False),
                (self.cell_h - self.reserved_h, True)]

    def bands(self):
        """[(y, h)] coloured rectangles, cell-local mm."""
        if self.clip:
            b = self.band_h
            return [(self.clip_h - b, b), (self.cell_h - self.clip_h, b)]
        return [(self.art_h, 2 * self.base_h)]

    def score_ys(self):
        """Dotted internal folds. Clip style has none -- one fold, that's it."""
        if self.clip:
            return []
        return [self.art_h, self.art_h + 2 * self.base_h]

    def labels(self):
        """[(y_baseline, pivot_y, rotate)] aligned 1:1 with art_boxes().

        **A label rotates exactly when the art in its own half rotates.** Get
        this wrong and the figure reads upright while its own name is upside
        down -- which is what happens if you reason about the sheet instead of
        the finished mini. Whichever way you turn the folded standee, the face
        you are looking at should have its feet down, its head up, and its name
        the right way round.
        """
        boxes, bands = self.art_boxes(), self.bands()
        if self.clip:
            return [(by + bh * 0.72, by + bh / 2.0, flip)
                    for (_, flip), (by, bh) in zip(boxes, bands)]
        # base style shares one bar between the halves; each half labels it
        # from its own side.
        a, b = self.art_h, self.base_h
        return [(a + b * 0.5, a + b, boxes[0][1]),
                (a + b * 0.5, a + b, boxes[1][1])]

    def outline(self):
        """Cut path, cell-local. Rectangle for clip style; I-beam for base."""
        w, h = self.cell_w, self.cell_h
        if self.clip:
            return [(0, 0), (w, 0), (w, h), (0, h)]
        cx = w / 2.0
        aw, bw = self.art_w, self.base_w
        a, b = self.art_h, self.base_h
        if abs(bw - aw) < 0.05:
            return [(0, 0), (bw, 0), (bw, h), (0, h)]
        return [
            (cx - aw / 2, 0), (cx + aw / 2, 0),
            (cx + aw / 2, a), (cx + bw / 2, a),
            (cx + bw / 2, a + 2 * b), (cx + aw / 2, a + 2 * b),
            (cx + aw / 2, h), (cx - aw / 2, h),
            (cx - aw / 2, a + 2 * b), (cx - bw / 2, a + 2 * b),
            (cx - bw / 2, a), (cx - aw / 2, a),
        ]


@dataclass
class Row:
    height: float
    cells: list
    y: float = 0.0
    page: int = 0

    @property
    def width(self):
        return sum(c.cell_w for c in self.cells)


@dataclass
class Page:
    index: int
    rows: list = field(default_factory=list)
    used_h: float = 0.0


@dataclass
class SheetConfig:
    paper: str = "a4"
    margin_mm: float = 8.0
    gutter_x_mm: float = 0.0            # 0 = shared cut lines (tightest)
    gutter_y_mm: float = 1.5            # a hair of daylight between strips
    scale_mode: str = "heroic"
    token_mm: float = 28.0
    # "clip" binder-clip stand: fold at the heads, clip the feet and end. No glue,
    # rectangular cuts, and the clip is the footprint so the paper need
    # not be grid-square wide.
    # "base" original fold-out paper tabs. Needs glue; cuts have notches.
    fold_style: str = "clip"
    clip_zone_mm: float = 10.0
    # "width" (default) SHRINK TO FIT one box per size class: the battle-grid
    #   square wide by the class height band tall. Every creature is
    #   scaled down to fit that box preserving aspect, never scaled up.
    #   So a size class has one consistent footprint, nothing exceeds
    #   the class above it, and a creature added tomorrow needs no new
    #   numbers -- the box comes from the size table.
    # "area" same printed area per size class, both dimensions floating.
    #   Needs a reference aspect constant, which is a tuning knob that
    #   goes stale as new creatures arrive.
    # "height" the original: fixed height, uncontrolled width. Same-class
    #   creatures varied over 2x in width and two poses of ONE creature
    #   printed at visibly different sizes.
    size_by: str = "width"
    # Base *width* must equal the battle-grid square, because that is what makes
    # the mini occupy the right space on a battlemap. Base *depth* only has to
    # be enough for the folded-out foot to stand, so it is clamped: a Large
    # creature does not need a 50 mm deep foot, and giving it one wastes a
    # quarter of the sheet.
    min_base_h_mm: float = 4.5
    max_base_h_mm: float = 9.0
    base_overhang_mm: float = 0.8       # how far the base bar sticks past the art
    header_mm: float = 11.0
    footer_mm: float = 9.0
    mirror_back: bool = False
    labels: bool = True

    @property
    def page_w(self):
        return PAPERS[self.paper.lower()][0]

    @property
    def page_h(self):
        return PAPERS[self.paper.lower()][1]

    @property
    def printable_w(self):
        return self.page_w - 2 * self.margin_mm

    @property
    def printable_h(self):
        return self.page_h - 2 * self.margin_mm - self.header_mm - self.footer_mm

    @property
    def origin(self):
        return self.margin_mm, self.margin_mm + self.header_mm


def make_cell(entry, index: int, art, cfg: SheetConfig) -> Cell:
    ov = entry.overrides or {}
    size_key = entry.size
    art_h = float(ov["height_mm"]) if "height_mm" in ov else \
        figure_height_mm(entry.size, cfg.scale_mode, cfg.token_mm)
    grid_base = float(ov["base_mm"]) if "base_mm" in ov else base_width_mm(entry.size)

    aspect = max(art.aspect, 0.08)
    warnings = list(art.warnings)
    box_h = box_w_res = 0.0
    if cfg.size_by == "width" and "height_mm" not in ov:
        # Pin the drawing to its grid square; let height follow the art's
        # proportions -- but bounded to this size class, or a narrow creature
        # ends up taller than the class above it. When the bound bites, width
        # gives way rather than the figure being distorted.
        # SHRINK TO FIT a box that is the same for every creature in this
        # size class: the grid square wide, the class height band tall.
        # Scale down to fit, never up -- so nothing ever exceeds its class,
        # and a Large can no longer print taller than a Huge.
        # Frame = the grid square by the class height. Using the class height
        # rather than the top of the band keeps cells tight (a roomier frame
        # just prints air above short creatures and costs sheets), and it
        # guarantees no class can reach the one above it.
        box_h, box_w = art_h, grid_base
        art_h = min(box_w / aspect, box_h)      # contain, preserving aspect
        box_w_res = box_w                       # frame is the class box
        if art_h * aspect < box_w - 0.05:
            warnings.append(
                f"height-limited by the {size_key} box (({box_w:.1f} * "
                f"{box_h:.1f} mm): this pose is tall and narrow, so it is "
                f"{art_h * aspect:.1f} mm wide rather than the full square")
    elif cfg.size_by == "area" and "height_mm" not in ov:
        # Anchor on the reference humanoid so Medium figures are unchanged:
        # a 0.62-aspect figure at the class height defines the class's area.
        # Then art_h = sqrt(area / aspect), art_w = aspect * art_h.
        target_area = (art_h ** 2) * REF_ASPECT
        scaled_h = math.sqrt(target_area / aspect)
        # Clamp so an extreme aspect cannot produce a stubby or absurd figure.
        art_h = max(MIN_H_RATIO * art_h, min(MAX_H_RATIO * art_h, scaled_h))
    art_w = art_h * aspect

    clip_h = float(ov.get("clip_zone_mm", cfg.clip_zone_mm))
    # Floor the paper width at the clip it will sit in, capped at 1 inch: wider
    # creatures already exceed it, and a Large mini does not need 2 inches of
    # paper when two 1 inch clips carry it.
    from sizes import clip_for
    min_w = min(clip_for(size_key)[1], 25.4)
    if "base_depth_mm" in ov:
        base_h = float(ov["base_depth_mm"]) / 2.0
    else:
        base_h = min(cfg.max_base_h_mm, max(cfg.min_base_h_mm, grid_base / 4.0))
    base_w = max(grid_base, art_w + 2 * cfg.base_overhang_mm)

    width_now = max(art_w + 1.6, min_w) if cfg.fold_style == "clip" else base_w
    # A single cell must fit the printable width. Wide silhouettes (dragons,
    # spiders) can otherwise blow past it; shrink the art rather than fail.
    if width_now > cfg.printable_w:
        shrink = (cfg.printable_w - 2 * cfg.base_overhang_mm) / art_w
        art_h *= shrink
        art_w *= shrink
        base_w = max(grid_base, art_w + 2 * cfg.base_overhang_mm)
        warnings.append(f"art shrunk x{shrink:.2f} to fit the page width")

    return Cell(label=entry.label, key=entry.key, size=entry.size, index=index,
                group_total=entry.count, art_h=art_h, art_w=art_w,
                base_w=base_w, base_h=base_h, art=art,
                poses=ov.get("poses", "pairs"), box_w=box_w_res, box_h=box_h,
                fold_style=cfg.fold_style, clip_h=clip_h, min_w=min_w,
                palette=list(entry.palette), warnings=warnings)


def build_rows(cells, cfg: SheetConfig):
    """Bucket by cell height, then fill rows left to right."""
    buckets = {}
    for c in cells:
        buckets.setdefault(round(c.cell_h, 1), []).append(c)

    rows = []
    for h in sorted(buckets, reverse=True):     # tallest strips first
        current, used = [], 0.0
        for c in buckets[h]:
            step = c.cell_w + (cfg.gutter_x_mm if current else 0.0)
            if current and used + step > cfg.printable_w + 1e-6:
                rows.append(Row(height=h, cells=current))
                current, used = [c], c.cell_w
            else:
                current.append(c)
                used += step
        if current:
            rows.append(Row(height=h, cells=current))
    return rows


def paginate(rows, cfg: SheetConfig):
    """First-fit rows onto pages; short leftover rows backfill earlier pages."""
    pages: list[Page] = []
    for row in rows:
        placed = False
        for page in pages:
            need = row.height + (cfg.gutter_y_mm if page.rows else 0.0)
            if page.used_h + need <= cfg.printable_h + 1e-6:
                row.y = page.used_h + (cfg.gutter_y_mm if page.rows else 0.0)
                page.used_h = row.y + row.height
                row.page = page.index
                page.rows.append(row)
                placed = True
                break
        if not placed:
            page = Page(index=len(pages) + 1)
            row.y = 0.0
            row.page = page.index
            page.used_h = row.height
            page.rows.append(row)
            pages.append(page)

    ox, oy = cfg.origin
    for page in pages:
        for ri, row in enumerate(page.rows):
            x = ox
            for c in row.cells:
                c.x, c.y = x, oy + row.y
                c.page, c.row = page.index, ri
                x += c.cell_w + cfg.gutter_x_mm
    return pages


def validate(pages, cfg: SheetConfig):
    """Geometry assertions. Returns a list of problems (empty == good)."""
    problems = []
    for page in pages:
        boxes = []
        for row in page.rows:
            for c in row.cells:
                if c.x < cfg.margin_mm - 1e-6 or c.y < cfg.margin_mm - 1e-6:
                    problems.append(f"P{page.index} {c.label}#{c.index}: starts inside the margin")
                if c.x + c.cell_w > cfg.page_w - cfg.margin_mm + 1e-6:
                    problems.append(f"P{page.index} {c.label}#{c.index}: overflows right margin")
                if c.y + c.cell_h > cfg.page_h - cfg.margin_mm - cfg.footer_mm + 1e-6:
                    problems.append(f"P{page.index} {c.label}#{c.index}: overflows bottom margin")
                if abs(c.fold_y - c.cell_h / 2) > 1e-6:
                    problems.append(f"P{page.index} {c.label}#{c.index}: fold line is not the centre line")
                if c.art_h > c.reserved_h + 1e-6:
                    problems.append(f"P{page.index} {c.label}#{c.index}: art taller than the "
                                    f"cell reserves ({c.art_h:.1f}) > ({c.reserved_h:.1f})")
                if c.art_w > c.cell_w + 1e-6:
                    problems.append(f"P{page.index} {c.label}#{c.index}: art wider than the cell "
                                    f"({c.art_w:.1f}) > ({c.cell_w:.1f})")
                for y, flip in c.art_boxes():
                    if y < -1e-6 or y + c.art_h > c.cell_h + 1e-6:
                        problems.append(f"P{page.index} {c.label}#{c.index}: art box outside the cell")
                boxes.append((c.x, c.y, c.cell_w, c.cell_h, f"{c.label}#{c.index}"))
        for i in range(len(boxes)):
            ax, ay, aw, ah, an = boxes[i]
            for j in range(i + 1, len(boxes)):
                bx, by, bw, bh, bn = boxes[j]
                if ax < bx + bw - 1e-6 and bx < ax + aw - 1e-6 and \
                   ay < by + bh - 1e-6 and by < ay + ah - 1e-6:
                    problems.append(f"P{page.index}: {an} overlaps {bn}")
    return problems


def utilisation(pages, cfg: SheetConfig):
    ink = sum(c.cell_w * c.cell_h for p in pages for r in p.rows for c in r.cells)
    avail = len(pages) * cfg.printable_w * cfg.printable_h
    return (ink / avail) if avail else 0.0
