# Fold geometry

Two styles, clip is the default.

## clip — binder-clip stand (default)

```text
|< clip grip >|    blank strip, ~10 mm
|  name band  |    coloured, stays visible when the clip is on
|   figure    |    feet UP, head DOWN
| - - - - - - |    the ONLY fold
|   figure    |    head UP, feet DOWN
|  name band  |
|< clip grip >|

````

Fold once. Both outer ends land together at the bottom; slide a binder clip on. That's it — the clip fastens the plies and is the base.

  * `cell_w = max(art_w + 1.6, clip_floor)` where `clip_floor` is the clip width capped at 1 inch. A floor is needed: a 1" clip gripping a 7 mm ribbon holds nothing, and a 7 mm strip has no room for a name.
  * `cell_h = 2 * (art_h + clip_zone)`; fold at `cell_h / 2`.
  * Cut outline is a plain rectangle — 4 points. No notches to scissor around.
  * No score lines. One dashed fold, nothing else.
  * `clip_zone` defaults to 10 mm, not the full 12.7 mm jaw depth: at 10 mm a Medium cell is 80 mm and 3 rows still fit an A4 column; at 12.7 mm it is 88 mm and you drop to 2.

### Which clip

The clip is the footprint, so it has to match the grid square even though the paper no longer does. `sizes.clip_for()`:

| Size        | Clip                       | Footprint |
| :---------- | :------------------------- | :-------- |
| Tiny, Small | 3/4"                       | 19 mm     |
| Medium      | 1"                         | 25.4 mm   |
| Large       | 2", or two 1" side by side | 50.8 mm   |
| Huge        | three 1"                   | 76.2 mm   |
| Gargantuan  | four 1"                    | 101.6 mm  |

A 1" binder clip is 25.4 x 12.7 mm — exactly a Medium square. That coincidence is why the design works. `manifest.json` -\> `stands` carries the tally.

### Why it beats fold-out tabs

  * **No glue:** Paper holds the plies at the folded top, clip holds the bottom.
  * **Rectangular cuts:** Guillotine into strips, chop each strip. No notches.
  * **Stable:** Metal mass low down, versus creased paper. Matters at Large+.
  * **Reusable:** Unclip, store flat, clips carry to the next campaign.

**Cost, honestly:** cells are \~10% taller, so paper use is a wash (Phandelver is 7 A4 sheets either way, 69% utilisation vs 65%). You are buying assembly time and stability, not paper.

-----

# base — fold-out paper tabs

## The cut shape

One cell = one finished miniature = two printed figures.

``` text
                  aw
          |<------------>|
          +--------------+   y = 0
          |   figure     |   art_h                      upright art
          +--------------+   y = art_h                  .... internal fold
          |  base bar    |   base_h
          +--------------+   y = cell_h / 2             ---- MAIN FOLD
          |  base bar    |   base_h
          +--------------+   y = art_h + 2 * base_h     .... internal fold
          |   figure     |   art_h                      mirrored art, flipped vertically
          +--------------+   y = cell_h
          |<------------>|
                 bw

```

  * `cell_w = bw = max(grid_base, art_w + 2 * overhang)`
  * `cell_h = 2 * (art_h + base_h)`
  * Fold is always the exact centre line; `validate()` asserts this.
  * One half on its own is the "L"-figure plus base bar — hence inverted T.
  * The full cell is an I-beam, which is why `outline()` returns 12 points (or 4, when the base happens to be no wider than the art).

## Assembly

1.  Cut the solid outline.
2.  Fold once on the dashed centre line. The two figures are now back-to-back and the base bars are stacked.
3.  Fold both base bars outward on the dotted lines. You now have a figure with a foot pointing forward and a foot pointing back.
4.  Optional: glue the two plies together, and glue the feet to a coin or a scrap of cardstock. Large and Huge minis tip over without this.

## Why the back copy is flipped vertically, not rotated

Folding about a horizontal line at y = f maps (x, f + d) to (x, f - d). A vertical flip (`scale(1, -1)`) is exactly that map, so the lower figure stands upright once folded. A 180° rotation would also put the head up, but it would mirror the figure horizontally in the fold plane and shift it, so the two plies would not line up.

Seen from behind, the back ply reads left-right reversed through the paper. Every commercial paper-mini set accepts this. `-mirror-back` adds an extra `scale(-1, 1)` for a true un-reversed back view, which is worth it when the creature has an asymmetric silhouette (a shield on one arm, a single wing).

## Base dimensions: width is a fact, depth is a choice

Width must equal the battle-grid square, because that is what makes the mini occupy the correct space on a 1-inch-grid battlemap. Medium = 25.4 mm, Large = 50.8 mm, Huge = 76.2 mm.

Depth only needs to be enough to stand up, so it is `grid / 4` clamped to 4.5–9 mm per bar. A Large creature given a "correct" 50 mm deep foot would eat a quarter of the sheet for no benefit. Override per creature with `#base_depth_mm=14`.

When the artwork is wider than its grid square — a dragon's wings, a spider's legs — `base_w` grows to fit the art, because a mini that cannot physically stand is worse than one whose base slightly overhangs its square. The grid square is a floor, not a ceiling.


