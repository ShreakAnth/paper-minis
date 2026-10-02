"""Art provider adapter: one interface, three backends, deterministic fallback.

Design rule: **this script never calls an image model.** Claude does that, in
the 'minis-art-director' skill, and writes the results to `<out>/art/`. The
layout engine only ever reads files off disk. Consequences worth keeping:

 * the build is reproducible and unit-testable with no network,
 * a sheet can be regenerated years later from the same 'art/' folder,
 * swapping in better art is a re-run, not a re-design,
 * and if art is missing the build still produces a usable sheet.

Resolution order per creature (first hit wins):

 1. `<out>/art/<key>.{png,webp,svg}`    -- art for this specific run
 2. `<library>/<style>/<key>.{...}`      -- the durable cross-campaign library
 3. `<art_dir>/<key>.{png,webp,svg}`     -- your own art pack / commissioned art
 4. procedural silhouette from proc_art -- always available

The **library** is the answer to "why am I regenerating goblins again?".
Generated art is written once to '~/.dnd-paper-minis/art/<style>/' and found
from there by every later roster, in any output folder, forever. A goblin is
generated on the first campaign that needs one and never again. The `<style>`
segment exists because reuse is only coherent within one style lock -- mixing a
goblin drawn in the inked style into a module-art set is exactly the
incoherence the art director works to avoid.

Pose variants come in **pairs**: minis 1 and 2 share `<key>`, minis 3 and 4
share `<key>-2`, 5 and 6 share `<key>-3`. A mob then has visible variety at
half the generation cost of one image per mini, and nobody at the table
notices that two of the nine skeletons match. A missing variant falls back to
`<key>`, so a half-generated set still builds.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import proc_art
import sizes

RASTER = (".png", ".webp", ".jpg", ".jpeg")
VECTOR = (".svg",)
EXTS = RASTER + VECTOR


@dataclass
class Art:
    kind: str           # "raster" | "vector" | "procedural"
    aspect: float       # width / height of the trimmed artwork
    payload: str        # data URI (raster), or inline SVG body (vector/procedural)
    provenance: str     # where it came from, for the manifest
    view_w: float = 0.0
    view_h: float = 0.0
    warnings: tuple = ()


def pose_for(index: int, mode: str = "pairs") -> int:
    """1-based mini number -> 1-based pose number.

    "pairs" (default) minis 1-2 share pose 1, 3-4 share pose 2, and so on.
    "single" every mini uses the one image. Set per creature with
             '# poses=single' when a mob does not need the variety and you
             would rather not pay for the extra generations.
    """
    if mode in ("single", "1", "one"):
        return 1
    return (index + 1) // 2


def _find(dirs, key: str, variant: int):
    stems = []
    if variant > 1:
        stems.append(f"{key}-{variant}")
    stems.append(key)
    for d in dirs:
        if not d:
            continue
        d = Path(d)
        if not d.is_dir():
            continue
        for stem in stems:
            for ext in EXTS:
                p = d / f"{stem}{ext}"
                if p.is_file():
                    return p
    return None


def _key_out(img, bg, tol: int) -> None:
    """Make the background transparent, in place. Background means *reachable
    from the edge* -- not merely the same colour.

    This used to knock out every pixel within tolerance of the background
    colour anywhere in the image, which is fine for magenta and quietly
    destructive for anything else. On white-backed art at tol 28 it ate the
    creature's own highlights: a giant spider came out speckled through its
    legs and abdomen, bugbears lost the pale edges of their fur and straps.
    The pixels were never background; they just matched it.

    Connectivity is the property that actually distinguishes the two. A white
    highlight inside a spider touches nothing outside the spider, so a fill
    seeded from the border cannot reach it, whatever its colour. That makes
    the fix independent of what the image model chose to put behind the
    creature -- which matters most for library art generated before the
    prompt asked for magenta, since that art is reused forever.

    Implemented as one flood fill rather than a per-pixel loop in Python: the
    colour test becomes a mask, the mask gets a one-pixel frame so every
    edge-touching region is connected to the corner, and a single fill from
    that corner marks the lot.
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    r0, g0, b0 = bg
    r, g, b, _ = img.split()

    def near(channel, value):
        return channel.point(
            lambda p, v=value: 255 if abs(p - v) < tol else 0, mode="1")

    mask = ImageChops.logical_and(
        ImageChops.logical_and(near(r, r0), near(g, g0)),
        near(b, b0)).convert("L")

    is_chroma = (
        (r0 > 200 and g0 < 50 and b0 > 200) or  # Magenta
        (r0 < 50 and g0 > 200 and b0 < 50) or  # Green
        (r0 < 50 and g0 < 50 and b0 > 200)     # Blue
    )

    if is_chroma:
        # For pure chroma screens (magenta, green, blue), key out ALL matching pixels including interior loops/holes
        alpha = img.getchannel("A")
        alpha.paste(0, (0, 0), mask)
        alpha = alpha.filter(ImageFilter.MinFilter(3))
        img.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.6)))
    else:
        # The frame is the trick: without it a background region touching only,
        # say, the left edge would need its own seed. With it, everything that
        # reaches any edge reaches (0, 0).
        framed = Image.new("L", (img.width + 2, img.height + 2), 255)
        framed.paste(mask, (1, 1))
        ImageDraw.floodfill(framed, (0, 0), 128, thresh=0)
        reachable = framed.crop((1, 1, img.width + 1, img.height + 1))

        alpha = img.getchannel("A")
        # 128 marks background; everything else keeps whatever alpha it had.
        alpha.paste(0, (0, 0), reachable.point(
            lambda p: 255 if p == 128 else 0, mode="1"))
        # Erode 1px so the anti-aliased fringe ring goes with it, then soften so
        # the cut edge is not jagged. Imperceptible at 25 mm.
        alpha = alpha.filter(ImageFilter.MinFilter(3))
        img.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.6)))


def _resample(img, max_px: int, warnings: list):
    """Shrink art to the resolution it will actually be printed at.

    Generated art arrives at whatever the image model felt like -- 4096x6144
    is common -- and gets printed 25 mm wide. That is roughly 4000 dpi, which
    no printer can render and every byte of which lands in the PDF: a
    Phandelver set came out at 114 MB, far past what anyone can email.

    Resolution is chosen from the printed size, not a fixed pixel count, so a
    Gargantuan creature at 101.6 mm keeps four times the pixels of a Medium at
    25.4 mm and both end up at the same dpi. Measured on a 32-image set:
    ~1030 dpi (native) 71 MB, 640 dpi 27 MB, 512 dpi 18 MB, 400 dpi 11 MB.
    Print shops call 300 dpi photographic quality, so 400 is still generous.

    Never upscales: art smaller than the target is left alone.
    """
    if not max_px or img.width <= max_px:
        return img
    from PIL import Image
    h = max(1, round(img.height * max_px / img.width))
    warnings.append(f"resampled {img.width}x{img.height} -> {max_px}x{h} "
                    f"for the printed size")
    return img.resize((max_px, h), Image.LANCZOS)


def _figure_blocks(img, gap_frac: float = 0.05, min_frac: float = 0.06) -> int:
    """How many separate figures this trimmed image appears to contain.

    Counts runs of columns that carry any opaque pixel, separated by empty
    gaps. Three characters side by side leave two clear vertical corridors
    between them; one creature, however wide, is a single run.

    Deliberately not an aspect-ratio test. A trimmed humanoid is taller than
    wide and a three-up composite is much wider than tall, so aspect looks
    like it would work -- but a dragon with spread wings or a gargantuan
    tentacled thing is legitimately wider than tall, and those are exactly the
    creatures whose art is most expensive to redraw. Measured on stand-ins:
    a 3-up composite gives 3 runs on both a flat and a gradient background,
    an upright humanoid gives 1, and a winged dragon 641 px wide also gives 1.

    Returned as a count rather than a verdict, and raised as a warning rather
    than an error: a creature with a detached familiar or a swarm on one base
    is a real thing, and the person can see the picture.
    """
    import numpy as np

    a = np.asarray(img.getchannel("A"))
    if a.size == 0:
        return 0
    cols = (a > 40).any(axis=0)
    runs, cur = [], 0
    for c in cols:
        if c:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    # Ignore slivers: a stray speck or a trailing wisp is not a figure.
    return sum(1 for r in runs if r > min_frac * len(cols))


def _trim_and_encode(path: Path, strip_bg: bool, max_px: int = 0):
    """Trim transparent (or keyed-out) margins so feet land on the fold line."""
    from PIL import Image

    warnings = []
    img = Image.open(path).convert("RGBA")

    opaque = img.getchannel("A").getextrema()[0] == 255
    if strip_bg and not opaque:
        # Art that already carries a real alpha channel needs no keying, and
        # keying it anyway is pure cost: the flag used to force the work
        # regardless, so a run over already-transparent art spent minutes
        # re-deriving a mask it was about to throw away. Skip, and say so --
        # silently ignoring a flag the user passed is its own bug.
        warnings.append("--strip-bg ignored: this art already has a real "
                        "alpha channel, so there is no background to key")

    if opaque:
        # No usable alpha. Key the background out. Image models often ignore
        # "transparent background", so the art director asks for a flat pure
        # chroma screen (magenta, green, or blue).
        corners = [img.getpixel(p)[:3] for p in
                   ((0, 0), (img.width - 1, 0), (0, img.height - 1),
                    (img.width - 1, img.height - 1))]
        
        is_magenta = all(r > 170 and g < 90 and b > 170 for r, g, b in corners)
        is_green = all(r < 90 and g > 170 and b < 90 for r, g, b in corners)
        is_blue = all(r < 90 and g < 90 and b > 170 for r, g, b in corners)

        if is_magenta:
            r0, g0, b0, tol = 255, 0, 255, 90
        elif is_green:
            r0, g0, b0, tol = 0, 255, 0, 90
        elif is_blue:
            r0, g0, b0, tol = 0, 0, 255, 90
        else:
            r0, g0, b0 = (sum(c[i] for c in corners) // 4 for i in range(3))
            tol = 28

        spread = max(abs(c[i] - v) for c in corners
                     for i, v in enumerate((r0, g0, b0)))
        if is_magenta or is_green or is_blue or spread <= 18:
            _key_out(img, (r0, g0, b0), tol)
        else:
            warnings.append("opaque background could not be keyed out; ask for "
                            "a flat pure-magenta background and re-run")

    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    else:
        warnings.append("image is fully transparent")

    n = _figure_blocks(img)
    if n > 1:
        warnings.append(
            f"this file looks like {n} figures side by side, not one. The "
            f"layout gives each art file a single {25.4:.1f} mm cell, so a "
            f"group shot is squeezed to the width of one mini. Generate one "
            f"creature per image, one file per key -- and do not crop a party "
            f"illustration into pieces: the figures are drawn to look good "
            f"together, not to a common height, so cropped pieces print at "
            f"inconsistent scale")

    # After the crop, so the target applies to the creature rather than to
    # whatever margin the generator left around it.
    img = _resample(img, max_px, warnings)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return uri, img.width / img.height, warnings


DEFAULT_LIBRARY = Path.home() / ".dnd-paper-minis" / "art"


def library_dir(library=None, style: str = "default") -> Path:
    return Path(library or DEFAULT_LIBRARY).expanduser() / style


def art_key(roster_key: str) -> str:
    """Filename stem this creature's art must use.

    'roster._slug' is space-separated on purpose -- it is a *matching* slug, so
    "Goblins" and "goblin" resolve to one entry. Art filenames are hyphenated
    instead, because a path with spaces gets mangled on every route that
    touches a shell.

    The conversion lives here and nowhere else. It used to be an inline
    '.replace(" ", "-")' in 'get_art', while 'build_minis.py' reported missing
    art straight from 'Cell.key' -- so the "art needed" message named
    'durkarad monk.png' and the loader then looked for 'durkarad-monk.png'.
    Drawing exactly the file the tool asked for still failed the build.
    """
    return roster_key.replace(" ", "-")


def get_art(entry, index: int, *, out_dir: Path, art_dir=None,
            backend: str = "auto", strip_bg: bool = False,
            library=None, style: str = "default", art_dpi: int = 0) -> Art:
    """'entry' is a roster.Entry; 'index' is the 1-based individual number."""
    key = art_key(entry.key)
    # Printed width of this size class decides the pixel budget, so every
    # creature lands at the same dpi regardless of how big it prints.
    max_px = round(sizes.base_width_mm(entry.size) / 25.4 * art_dpi) if art_dpi else 0
    ai_dir = Path(out_dir) / "art"
    lib_dir = library_dir(library, style)

    if backend in ("auto", "genai", "folder"):
        search = []
        if backend in ("auto", "genai"):
            search += [ai_dir, lib_dir]
        if backend in ("auto", "folder"):
            search.append(art_dir)
        found = _find(search, key,
                      pose_for(index, (entry.overrides or {}).get("poses", "pairs")))
        if found:
            if found.suffix.lower() in VECTOR:
                body = found.read_text()
                return Art("vector", _svg_aspect(body), body,
                           f"vector:{found.name}")
            uri, aspect, warns = _trim_and_encode(found, strip_bg, max_px)
            return Art("raster", aspect, uri, f"raster:{found.name}",
                       warnings=tuple(warns))

    if backend in ("genai", "folder"):
        # explicit backend but nothing on disk -> say so loudly, then fall back
        body, w, h = proc_art.draw(entry.archetype, entry.palette, seed=index)
        return Art("procedural", w / h, body,
                   f"procedural:{entry.archetype} (MISSING {key})",
                   w, h, warnings=(f"no art file found for '{key}' in {backend} backend",))

    body, w, h = proc_art.draw(entry.archetype, entry.palette, seed=index)
    return Art("procedural", w / h, body, f"procedural:{entry.archetype}", w, h)


def _svg_aspect(body: str) -> float:
    import re
    m = re.search(r'viewBox\s*=\s*"([-\d.\s]+)"', body)
    if m:
        nums = [float(v) for v in m.group(1).split()]
        if len(nums) == 4 and nums[3]:
            return nums[2] / nums[3]
    return 0.6
