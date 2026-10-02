#!/usr/bin/env python3
"""build_minis.py -- roster in, print-ready paper-miniature sheets out.

python3 build_minis.py ROSTER.txt --out ./out --title "Phandelver"

Stages (each one inspectable, each one skippable):

  1 parse      roster text           -> entries          (roster.py)
  2 scale      size category         -> mm               (sizes.py)
  3 art        entry + individual    -> Art              (art_provider.py)
  4 cell       art + mm              -> inverted-T       (layout.py)
  5 pack       cells                 -> rows -> pages    (layout.py)
  6 render     pages                 -> SVG              (render_svg.py)
  7 render     pages                 -> PDF              (render_pdf.py, native)

Counting, stated explicitly because it is the thing people get wrong:
`7 Goblins` produces 7 cells and 14 printed images -- each cell carries the
upright figure and its vertically-mirrored twin, which fold back-to-back into
one standing mini.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import art_provider        # noqa: E402
import layout              # noqa: E402
import render_pdf          # noqa: E402
import render_svg          # noqa: E402
import sizes               # noqa: E402
import to_pdf              # noqa: E402
from roster import CreatureDB, parse_roster  # noqa: E402


def _poses(cells):
    """Which pose files each creature actually wants, and which are missing.

    Pairs share a pose, so a creature with N minis needs ceil(N/2) images:
    `<key>`, `<key>-2`, `<key>-3`... This is what the art director generates
    from, and what tells the user a set is only half-posed.
    """
    want, have = {}, {}
    for c in cells:
        pose = art_provider.pose_for(c.index, c.poses)
        want[c.key] = max(want.get(c.key, 0), pose)
        if c.art.kind != "procedural":
            have.setdefault(c.key, set()).add(pose)

    out = {}
    for key, n in sorted(want.items()):
        got = have.get(key, set())
        missing = [p for p in range(1, n + 1) if p not in got]
        out[key] = {
            "minis": sum(1 for c in cells if c.key == key),
            "poses_needed": n,
            "missing_poses": [key if p == 1 else f"{key}-{p}" for p in missing],
        }
    return out


def _stands(cells, fold_style):
    """What the user has to go buy. Running out of clips mid-session is the
    failure mode, so the count is reported, never left to be guessed."""
    if fold_style != "clip":
        return {"style": "base", "note": "fold-out paper tabs; needs glue"}
    tally, one_inch = {}, 0
    for c in cells:
        desc, mm, n = sizes.clip_for(c.size)
        tally[desc] = tally.get(desc, 0) + 1
        one_inch += n
    return {
        "style": "clip",
        "by_clip": tally,
        "total_clips": sum(tally.values()),
        "equivalent_1inch_clips": one_inch,
        "note": "fold once, clip the blank strip at the bottom, no glue",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate printable D&D paper miniatures.")
    ap.add_argument("roster", nargs="?", help="roster text file ('-' for stdin)")
    ap.add_argument("--out", default="./minis-out")
    ap.add_argument("--title", default=None,
                    help="campaign or encounter name. NO DEFAULT on purpose: a "
                         "'sheet with an invented title looks finished when it "
                         "is not. Ask the user; never infer one from a "
                         "filename.'")
    ap.add_argument("--paper", default="a4", choices=sorted(layout.PAPERS))
    ap.add_argument("--scale", default="heroic", choices=["heroic", "true", "token"])
    ap.add_argument("--token-mm", type=float, default=28.0)
    ap.add_argument("--fold-style", default="clip", choices=["clip", "base"],
                    help="clip (default): fold at the heads, stand it in a "
                         "binder clip -- no glue, rectangular cuts. "
                         "base: original fold-out paper tabs.")
    ap.add_argument("--size-by", default="width",
                    choices=["width", "area", "height"],
                    help="width (default): every creature in a size class "
                         "prints at its grid-square width; height follows the "
                         "art. area: equal printed area. height: the original "
                         "fixed-height behaviour.")
    ap.add_argument("--clip-zone-mm", type=float, default=10.0,
                    help="grip strip per half. 10 keeps 3 Medium rows on A4; "
                         "12.7 (full jaw depth) drops it to 2.")
    ap.add_argument("--art-backend", default="genai",
                    choices=["auto", "genai", "folder", "svg"],
                    help="default 'genai': every mini must have real art on disk")
    ap.add_argument("--allow-procedural", action="store_true",
                    help="permit the silhouette fallback for creatures with no art "
                         "(implied by --art-backend svg/auto)")
    ap.add_argument("--art-dir", default=None, help="your own art pack")
    ap.add_argument("--library", default=None,
                    help="durable cross-campaign art library "
                         "(default ~/.dnd-paper-minis/art). Art generated "
                         "once is reused by every later roster.")
    ap.add_argument("--style", default="default",
                    help="library namespace; reuse is only safe within one "
                         "'style lock'")
    ap.add_argument("--creatures-extra", default=None, help="sidecar creatures.local.json")
    ap.add_argument("--margin-mm", type=float, default=8.0)
    ap.add_argument("--gutter-x-mm", type=float, default=0.0)
    ap.add_argument("--gutter-y-mm", type=float, default=1.5)
    ap.add_argument("--mirror-back", action="store_true",
                    help="un-reverse the back ply (true back view instead of a mirror)")
    ap.add_argument("--no-labels", action="store_true")
    ap.add_argument("--strip-bg", action="store_true",
                    help="key out a uniform background on supplied raster art. "
                         "Only needed for art with no alpha channel, and art "
                         "with one is keyed automatically without this flag -- "
                         "so you rarely want it. Passing it against already-"
                         "transparent art does nothing but cost time, and is "
                         "now skipped with a warning rather than obeyed.")
    ap.add_argument("--art-dpi", type=int, default=0, metavar="DPI",
                    help="resample art to this resolution at its printed "
                         "size, so file size follows the print rather than "
                         "whatever the image model produced. 0 (default) "
                         "leaves art untouched. A 32-image Phandelver set "
                         "measures ~71 MB untouched, 27 MB at 640, 18 MB at "
                         "512 and 11 MB at 400. Print shops call 300 dpi "
                         "photographic quality, so 400 is generous and "
                         "emailable. Never upscales.")
    ap.add_argument("--statblock", action="store_true",
                    help="parse input as a monster stat-block instead of a roster list")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--explain", action="store_true", help="print the scale table and exit")
    args = ap.parse_args(argv)

    if args.explain:
        print(json.dumps(sizes.table_as_rows(args.scale), indent=2))
        print("archetypes:", ", ".join(__import__("proc_art").ARCHETYPES))
        return 0
    if not args.roster:
        ap.error("roster is required (or use --explain)")

    text = sys.stdin.read() if args.roster == "-" else Path(args.roster).read_text()
    db = CreatureDB(extra=Path(args.creatures_extra) if args.creatures_extra else None)
    entries = parse_roster(text, db, is_statblock=args.statblock)
    if not entries:
        print("no roster entries parsed", file=sys.stderr)
        return 2

    out = Path(args.out)
    (out / "art").mkdir(parents=True, exist_ok=True)

    cfg = layout.SheetConfig(
        paper=args.paper, margin_mm=args.margin_mm,
        gutter_x_mm=args.gutter_x_mm, gutter_y_mm=args.gutter_y_mm,
        scale_mode=args.scale, token_mm=args.token_mm,
        fold_style=args.fold_style, clip_zone_mm=args.clip_zone_mm,
        size_by=args.size_by,
        mirror_back=args.mirror_back, labels=not args.no_labels,
    )

    cells, warnings = [], []
    for e in entries:
        if e.unresolved:
            warnings.append(f"unrecognised creature '{e.label}' -> defaulted to "
                            f"medium/humanoid (add it to creatures.local.json or "
                            f"append '# size=large archetype=dragon')")
        for i in range(1, e.count + 1):
            art = art_provider.get_art(e, i, out_dir=out, art_dir=args.art_dir,
                                       backend=args.art_backend, strip_bg=args.strip_bg,
                                       library=args.library, style=args.style,
                                       art_dpi=args.art_dpi)
            cell = layout.make_cell(e, i, art, cfg)
            cells.extend([cell])
            warnings.extend([f"{e.label}#{i}: {w}" for w in cell.warnings])

    # Real art is mandatory under the default 'genai' backend. Fail loudly and
    # early rather than shipping a sheet whose art is silently a silhouette --
    # that is the failure the user only notices after cutting out 113 minis.
    strict = args.art_backend == "genai" and not args.allow_procedural
    # 'art_provider.art_key' and not 'c.key': the roster slug is
    # space-separated and the art file is hyphenated, so reporting the raw slug
    # named a file the loader would never read.
    missing = sorted({art_provider.art_key(c.key)
                      for c in cells if c.art.kind == "procedural"})
    if strict and missing:
        art_dir = out / "art"
        print(f"\nART NEEDED for {len(missing)} creature(s). Nothing written.",
              file=sys.stderr)
        print("\nDraw these yourself and save each one exactly here, "
              "transparent background:", file=sys.stderr)
        # Quoted, because 'slug' keys are space-separated by design ("frost
        # giant", not "frost-giant") and an unquoted path with spaces is
        # routinely saved to the wrong filename -- which lands right back here.
        for k in missing:
            print(f'  "{art_dir / (k + ".png")}"', file=sys.stderr)
        print("\nThen re-run this command. Nothing else is needed -- the "
              "layout engine reads\nthese files off disk.", file=sys.stderr)
        print("\nIf you have an image generator, that is the whole job. It may "
              "be a DEFERRED\ntool missing from your visible list until you "
              "search for it, or a skill rather\nthan a tool -- search "
              "'image', 'imagegen', 'draw' before concluding you cannot.\n"
              "The minis-art-director skill says where to look, and\n"
              f"  image_gen.py prompts.json --out {out} --plan\n"
              "reuses everything the library already owns and prints the rest "
              "with its filename.", file=sys.stderr)
        print("\nOnly if nothing here can draw: image_gen.py dispatches an "
              "installed CLI agent\n('--list-tools' to see what is available). "
              "That path is billed per image and has\nbroken on MDM approval "
              "policy and sandbox permissions before -- if it fails, say so "
              "and\nask. A dispatch failure is not a reason to lower the "
              "output.", file=sys.stderr)
        print("\n--allow-procedural and --art-backend svg replace the figures "
              "with blank\nsilhouettes. They are for someone who ASKED for "
              "silhouettes. Do not reach for\nthem to get past this message: "
              "the sheet looks finished and the user finds out\nafter cutting "
              "out every mini.", file=sys.stderr)
        return 3

    rows = layout.build_rows(cells, cfg)
    pages = layout.paginate(rows, cfg)
    problems = layout.validate(pages, cfg)

    if not args.title:
        warnings.append("no --title given: the sheet header shows only the "
                        "summary line. Ask what this set is called and re-run.")
    subtitle = (f"{len(cells)} minis * {2*len(cells)} printed figures * "
                f"{args.scale} scale * {args.paper.upper()}")
    svgs = []
    for page in pages:
        svg = render_svg.render_page(page, cfg, len(pages), args.title or "",
                                     subtitle)
        p = out / f"sheet-{page.index:02d}.svg"
        p.write_text(svg)
        svgs.append(p)

    # PDF: draw it natively with ReportLab (pure Python, no libcairo) and only
    # fall back to converting the SVGs if ReportLab is missing. The old order
    # meant a machine without Homebrew's cairo got no PDF at all.
    pdf, page_pdfs, notes = (None, [], [])
    if not args.no_pdf:
        if render_pdf.available():
            pdf = render_pdf.render(pages, cfg, out / "minis.pdf",
                                    args.title or "", subtitle)
            gaps = render_pdf.unsupported()
            if gaps:
                notes.append("PDF renderer skipped unsupported art primitives: "
                             + ", ".join(sorted(gaps))
                             + " (the SVG sheets are unaffected)")
        else:
            # Degrading silently here is what makes an agent go and write its
            # own HTML/Chrome renderer, which then gets the fold geometry
            # wrong. Fail with the one-line fix instead.
            pdf, page_pdfs, notes2 = to_pdf.convert(svgs, out / "minis.pdf")
            notes += notes2
            if not pdf:
                print("\nSheets written, but no PDF: reportlab is not installed.\n"
                      "    pip install reportlab\n"
                      "\nThen re-run this command. reportlab is pure Python -- no "
                      "compiler, no Chrome, no Homebrew, no libcairo.\n"
                      "DO NOT write a replacement renderer: the fold geometry "
                      "lives in layout.py and re-implementing it silently breaks "
                      "the mirrored copy.\n"
                      f"The SVGs in {out} are already correct and print fine "
                      "from a browser at 100% if you need them today.",
                      file=sys.stderr)
                return 4

    manifest = {
        "title": args.title,
        "poses": _poses(cells),
        "paper": args.paper,
        "scale_mode": args.scale,
        "totals": {
            "roster_entries": len(entries),
            "minis": len(cells),
            "printed_figures": 2 * len(cells),
            "sheets": len(pages),
            "sheet_utilisation": round(layout.utilisation(pages, cfg), 3),
        },
        "art": {
            "backend": args.art_backend,
            "strict": strict,
            "procedural_fallbacks": missing,
            "sources": sorted({c.art.provenance.split(":")[0] for c in cells}),
            "library": str(art_provider.library_dir(args.library, args.style)),
        },
        "stands": _stands(cells, args.fold_style),
        "size_table_mm": sizes.table_as_rows(args.scale),
        "entries": [e.to_dict() for e in entries],
        "minis": [
            {
                "label": c.label, "key": c.key, "index": c.index, "size": c.size,
                "figure_mm": round(c.art_h, 2), "base_mm": round(c.base_w, 2),
                "base_depth_mm": round(2 * c.base_h, 2),
                "cell_mm": [round(c.cell_w, 2), round(c.cell_h, 2)],
                "page": c.page, "row": c.row,
                "xy_mm": [round(c.x, 2), round(c.y, 2)],
                "art": c.art.provenance,
            }
            for p in pages for r in p.rows for c in r.cells
        ],
        "outputs": {
            "svg": [str(p.name) for p in svgs],
            "pdf": pdf.name if pdf else None,
            "page_pdfs": [p.name for p in page_pdfs],
        },
        "warnings": warnings + notes,
        "geometry_problems": problems,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    t = manifest["totals"]
    print(f"{t['minis']} minis / {t['printed_figures']} printed figures "
          f"on {t['sheets']} {args.paper.upper()} sheet(s) "
          f"({t['sheet_utilisation']*100:.0f}% of printable area used)")
    if pdf:
        print(f"pdf: {pdf}")
    st = manifest["stands"]
    if st.get("style") == "clip":
        print("clips needed: " + ", ".join(f"{n} x {d}" for d, n in st["by_clip"].items())
              + f" ({st['equivalent_1inch_clips']} one-inch clips if you only have those)")
    for w in warnings + notes:
        print(f" ! {w}")
    for p in problems:
        print(f" GEOMETRY: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
