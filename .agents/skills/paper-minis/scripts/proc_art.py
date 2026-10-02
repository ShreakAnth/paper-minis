"""Procedural fallback art: parametric creature silhouettes as SVG.

This is the "always works" art backend. It needs no network, no image model
and no licensed art pack, so a roster can be turned into a printable sheet
immediately -- and the same sheet can be reprinted later with real gen-AI art
dropped into 'art/' without touching the layout.

Contract for every art backend
------------------------------
Return `(svg_body, width, height)` in the art's own coordinate space, where:

 * the figure's feet sit exactly on 'y = height' (so it meets the base fold),
 * the silhouette is horizontally centred in `0..width`,
 * nothing is drawn outside the box (the layout engine clips nothing),
 * floating creatures include a support stem down to 'y = height'.

'seed' makes each individual of a species slightly different -- pose jitter,
so nine skeletons do not look like nine photocopies -- while staying
deterministic, so a reprint is identical.
"""

from __future__ import annotations

import math
import random

from sizes import aspect_for


def _poly(pts, fill, stroke=None, sw=1.2, extra=""):
    d = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<polygon points="{d}" fill="{fill}"{s}{extra}/>'


def _path(d, fill="none", stroke=None, sw=1.2, cap="round", extra=""):
    s = f' stroke="{stroke}" stroke-width="{sw}" stroke-linecap="{cap}" stroke-linejoin="round"' if stroke else ""
    return f'<path d="{d}" fill="{fill}"{s}{extra}/>'


def _ell(cx, cy, rx, ry, fill, stroke=None, sw=1.0, rot=0.0, extra=""):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    t = f' transform="rotate({rot:.1f} {cx:.2f} {cy:.2f})"' if rot else ""
    return f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{fill}"{s}{t}{extra}/>'


def _limb(x1, y1, x2, y2, colour, sw=5.5):
    return _path(f"M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}", stroke=colour, sw=sw)


# ---------------------------------------------------------------------------
# archetypes
# ---------------------------------------------------------------------------

def _humanoid(W, H, pal, rng, armoured=False, robed=False):
    main, dark, accent = pal
    cx = W / 2
    j = rng.uniform(-2.0, 2.0)         # stance jitter
    out = []

    if robed:
        # robe: narrow enough to read as a figure rather than a traffic cone
        hem = W * 0.30
        out.append(_path(
            f"M{cx-7.5:.2f},26 L{cx+7.5:.2f},26 L{cx+hem:.2f},{H-2:.2f} "
            f"L{cx-hem:.2f},{H-2:.2f} Z", fill=main, stroke=dark, sw=1.3))
        for k in (-0.45, 0.1, 0.55):
            out.append(_path(f"M{cx+k*hem:.2f},32 L{cx+k*hem*1.5:.2f},{H-4:.2f}",
                             stroke=dark, sw=0.8))
        # sash
        out.append(_path(f"M{cx-9:.2f},52 L{cx+9:.2f},48", stroke=accent, sw=2.2))
        # hood + shadowed face: the dome base sits below the robe's shoulder
        # line so no white sliver shows between the two shapes
        out.append(_path(f"M{cx-9.5:.2f},30 Q{cx:.2f},2 {cx+9.5:.2f},30 Z", fill=dark))
        out.append(_ell(cx + j * 0.3, 16, 5.0, 5.0, "#151210"))
        # sleeve + hand + staff
        out.append(_limb(cx - 7, 34, cx - W * 0.30, 50, main, 5.0))
        out.append(_ell(cx - W * 0.30, 51, 2.6, 2.0, accent, dark, 0.9))
        out.append(_limb(cx + 7, 34, cx + W * 0.26, 54, main, 5.0))
        out.append(_path(f"M{cx-W*0.32:.2f},16 L{cx-W*0.32:.2f},{H-2:.2f}", stroke=dark, sw=2.4))
        out.append(_ell(cx - W * 0.36, 14, 3.2, 5.0, accent, dark, 0.8))
        return out

    # legs
    out.append(_limb(cx - 4, 58, cx - 7 + j, H - 2, dark, 6.2))
    out.append(_limb(cx + 4, 58, cx + 8 - j, H - 2, dark, 6.2))
    # torso
    out.append(_poly([(cx - 11, 23), (cx + 11, 23), (cx + 8, 60), (cx - 8, 60)],
                     main, dark, 1.4))
    # arms
    out.append(_limb(cx - 10, 27, cx - W * 0.40, 48 + j, main, 5.4))
    out.append(_limb(cx + 10, 27, cx + W * 0.36, 40 - j, main, 5.4))
    # head
    out.append(_limb(cx, 20, cx, 24, dark, 4.0))
    out.append(_ell(cx, 12, 8.4, 9.2, accent, dark, 1.2))

    if armoured:
        # shield + polearm
        out.append(_ell(cx - W * 0.40, 50 - j, 8.6, 10.4, accent, dark, 1.4))
        out.append(_path(f"M{cx-W*0.40:.2f},40 L{cx-W*0.40:.2f},60", stroke=dark, sw=1.0))
        out.append(_path(f"M{cx+W*0.34:.2f},4 L{cx+W*0.38:.2f},{H-6:.2f}", stroke=dark, sw=2.4))
        out.append(_poly([(cx + W * 0.34, 0), (cx + W * 0.30, 10), (cx + W * 0.38, 9)], accent))
        # belt + pauldron
        out.append(_path(f"M{cx-9:.2f},46 L{cx+8:.2f},46", stroke=dark, sw=2.4))
        out.append(_ell(cx - 11, 25, 4.6, 3.4, dark))
        out.append(_ell(cx + 11, 25, 4.6, 3.4, dark))
    return out


def _undead_humanoid(W, H, pal, rng):
    bone, shadow, accent = pal
    cx = W / 2
    j = rng.uniform(-2.5, 2.5)
    out = [
        _limb(cx - 3, 58, cx - 7 + j, H - 2, bone, 4.4),
        _limb(cx + 3, 58, cx + 7 - j, H - 2, bone, 4.4),
        _limb(cx, 24, cx + j * 0.3, 58, bone, 5.0),
    ]
    for i, y in enumerate((30, 37, 44, 51)):
        r = 9.0 - i * 1.1
        out.append(_path(f"M{cx-r:.2f},{y} Q{cx:.2f},{y+4} {cx+r:.2f},{y}",
                         stroke=bone, sw=2.2))
    out.append(_limb(cx - 8, 27, cx - W * 0.42, 44 + j, bone, 4.0))
    out.append(_limb(cx + 8, 27, cx + W * 0.40, 52 - j, bone, 4.0))
    out.append(_path(f"M{cx+W*0.40:.2f},52 L{cx+W*0.30:.2f},20", stroke=accent, sw=2.4))
    # skull
    out.append(_ell(cx, 13, 8.0, 8.8, bone, shadow, 1.2))
    out.append(_ell(cx - 3.2, 12, 2.3, 2.6, "#14120f"))
    out.append(_ell(cx + 3.2, 12, 2.3, 2.6, "#14120f"))
    out.append(_path(f"M{cx-4:.2f},19 L{cx+4:.2f},19", stroke=shadow, sw=1.6))
    return out


def _undead_robed(W, H, pal, rng):
    main, dark, accent = pal
    cx = W / 2
    hem = []
    n = 9
    for i in range(n + 1):
        x = cx - W * 0.45 + (W * 0.90) * i / n
        hem.append((x, H - 2 - (0 if i % 2 else rng.uniform(5, 13))))
    body = [(cx - 10, 20), (cx + 10, 20)] + list(reversed(hem))
    out = [
        _path("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in body) + " Z",
              fill=main, stroke=dark, sw=1.3),
        _path(f"M{cx-12:.2f},20 Q{cx:.2f},-4 {cx+12:.2f},20 Z", fill=dark),
        _ell(cx, 13, 6.6, 7.4, "#000c12"),
        _ell(cx - 2.6, 12, 1.5, 2.0, accent),
        _ell(cx + 2.6, 12, 1.5, 2.0, accent),
        _limb(cx - 9, 28, cx - W * 0.40, 46, main, 5.0),
        _limb(cx + 9, 28, cx + W * 0.40, 40, main, 5.0),
    ]
    for sx in (-1, 1):
        bx = cx + sx * W * 0.40
        for k in (-3.5, 0, 3.5):
            out.append(_path(f"M{bx:.2f},{46 if sx<0 else 40} l{k*0.6:.2f},7", stroke=accent, sw=1.4))
    # support stem (the shade does not touch the ground; the paper must)
    out.append(_path(f"M{cx:.2f},{H-12:.2f} L{cx:.2f},{H-1:.2f}", stroke=dark, sw=3.0))
    return out


def _quadruped(W, H, pal, rng):
    main, dark, accent = pal
    j = rng.uniform(-3, 3)
    body_y = H * 0.50
    out = [
        _limb(W * 0.30, body_y + 6, W * 0.24 + j, H - 2, dark, 6.0),
        _limb(W * 0.68, body_y + 6, W * 0.76 - j, H - 2, dark, 6.0),
        _ell(W * 0.50, body_y, W * 0.30, H * 0.20, main, dark, 1.4),
        _limb(W * 0.36, body_y + 6, W * 0.33, H - 2, main, 6.6),
        _limb(W * 0.64, body_y + 6, W * 0.68, H - 2, main, 6.6),
        # tail
        _path(f"M{W*0.79:.2f},{body_y-2:.2f} Q{W*0.97:.2f},{body_y-14:.2f} "
              f"{W*0.92:.2f},{body_y+8:.2f}", stroke=main, sw=6.0),
        # neck + head
        _limb(W * 0.27, body_y - 4, W * 0.16, body_y - 16, main, 8.5),
        _ell(W * 0.13, body_y - 20, W * 0.115, H * 0.105, main, dark, 1.2),
        _poly([(W * 0.02, body_y - 18), (W * 0.15, body_y - 24), (W * 0.15, body_y - 14)], accent),
        _poly([(W * 0.15, body_y - 28), (W * 0.11, body_y - 32), (W * 0.19, body_y - 30)], dark),
        _poly([(W * 0.21, body_y - 28), (W * 0.19, body_y - 33), (W * 0.25, body_y - 29)], dark),
        _ell(W * 0.11, body_y - 22, 1.5, 1.7, "#151210"),
    ]
    return out


def _insectoid(W, H, pal, rng, winged=True):
    main, dark, accent = pal
    cx, cy = W * 0.50, H * 0.46
    out = []
    # Legs must land inside 0..W: a silhouette that walks out of its own cell
    # crosses the neighbouring mini's cut line.
    for i in range(4):
        spread = 0.09 + i * 0.075
        tip = min(spread + 0.13, 0.46)
        drop = H * (0.34 + 0.16 * math.sin(i + rng.uniform(-0.3, 0.3)))
        for sx in (-1, 1):
            kx = cx + sx * W * spread
            out.append(_path(f"M{cx:.2f},{cy:.2f} Q{kx:.2f},{cy-drop*0.35:.2f} "
                             f"{cx+sx*W*tip:.2f},{H-2:.2f}",
                             stroke=dark, sw=2.6))
    if winged:
        for sx in (-1, 1):
            out.append(_ell(cx + sx * W * 0.21, cy - H * 0.21, W * 0.19, H * 0.10,
                            "#dfe7ee", dark, 0.9, rot=sx * -24))
    out.append(_ell(cx, cy, W * 0.22, H * 0.20, main, dark, 1.4))
    out.append(_ell(cx, cy - H * 0.16, W * 0.14, H * 0.09, dark))
    for sx in (-1, 1):
        out.append(_ell(cx - W * 0.19 + sx * 0.02 * W, cy - H * 0.07, 1.6, 1.8, accent))
        out.append(_path(f"M{cx-W*0.24:.2f},{cy:.2f} L{cx-W*0.44:.2f},{cy+H*0.14:.2f}",
                         stroke=accent, sw=2.0))
    return out


def _plant(W, H, pal, rng):
    bark, dark, glow = pal
    cx = W / 2
    out = [_path(f"M{cx-6:.2f},{H-2:.2f} Q{cx-3:.2f},{H*0.5:.2f} {cx-2:.2f},{H*0.22:.2f} "
                 f"L{cx+2:.2f},{H*0.20:.2f} Q{cx+5:.2f},{H*0.55:.2f} {cx+7:.2f},{H-2:.2f} Z",
                 fill=bark, stroke=dark, sw=1.3)]
    for i in range(6):
        sx = -1 if i % 2 else 1
        y0 = H * (0.24 + 0.10 * (i // 2)) + rng.uniform(-3, 3)
        out.append(_path(f"M{cx:.2f},{y0:.2f} Q{cx+sx*W*0.28:.2f},{y0-H*0.10:.2f} "
                         f"{cx+sx*W*0.46:.2f},{y0-H*0.02:.2f}", stroke=bark, sw=2.6))
        out.append(_path(f"M{cx+sx*W*0.46:.2f},{y0-H*0.02:.2f} l{sx*4:.2f},-5", stroke=dark, sw=1.6))
    for sx in (-1, 1):
        out.append(_path(f"M{cx:.2f},{H*0.82:.2f} Q{cx+sx*W*0.26:.2f},{H*0.92:.2f} "
                         f"{cx+sx*W*0.42:.2f},{H-2:.2f}", stroke=dark, sw=2.0))
    out.append(_ell(cx - 3, H * 0.26, 1.9, 2.2, glow))
    out.append(_ell(cx + 3.5, H * 0.24, 1.9, 2.2, glow))
    return out


def _blob(W, H, pal, rng):
    main, dark, sheen = pal
    cx, cy = W / 2, H * 0.62
    pts = []
    for i in range(16):
        a = 2 * math.pi * i / 16
        r = 1.0 + 0.16 * math.sin(3 * a + rng.uniform(0, 0.6))
        x = cx + math.cos(a) * W * 0.40 * r
        y = cy + math.sin(a) * H * 0.32 * r
        pts.append((min(max(x, 1.0), W - 1.0), min(y, H - 2)))
    out = [_path("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z",
                 fill=main, stroke=dark, sw=1.4, extra=' opacity="0.95"')]
    out.append(_ell(cx - W * 0.14, cy - H * 0.12, W * 0.18, H * 0.07, sheen))
    for sx in (-1, 1):
        out.append(_path(f"M{cx+sx*W*0.30:.2f},{cy+H*0.20:.2f} q{sx*10:.2f},12 {sx*4:.2f},{H*0.16:.2f}",
                         stroke=main, sw=5.0))
    return out


def _dragon(W, H, pal, rng):
    main, dark, horn = pal
    out = [
        # far wing
        _path(f"M{W*0.52:.2f},{H*0.34:.2f} L{W*0.96:.2f},{H*0.06:.2f} "
              f"L{W*0.86:.2f},{H*0.40:.2f} L{W*0.62:.2f},{H*0.46:.2f} Z",
              fill=dark, stroke=dark, sw=1.2),
        # tail
        _path(f"M{W*0.62:.2f},{H*0.62:.2f} Q{W*0.95:.2f},{H*0.70:.2f} {W*0.88:.2f},{H-4:.2f}",
              stroke=main, sw=7.0),
        # legs
        _limb(W * 0.40, H * 0.66, W * 0.33, H - 2, dark, 7.0),
        _limb(W * 0.60, H * 0.66, W * 0.66, H - 2, main, 7.5),
        # body
        _ell(W * 0.50, H * 0.58, W * 0.21, H * 0.20, main, dark, 1.6),
        # near wing
        _path(f"M{W*0.48:.2f},{H*0.38:.2f} L{W*0.86:.2f},{H*0.04:.2f} "
              f"L{W*0.74:.2f},{H*0.42:.2f} L{W*0.38:.2f},{H*0.50:.2f} Z",
              fill=main, stroke=dark, sw=1.4),
        # neck + head
        _path(f"M{W*0.44:.2f},{H*0.46:.2f} Q{W*0.30:.2f},{H*0.26:.2f} {W*0.20:.2f},{H*0.20:.2f}",
              stroke=main, sw=9.0),
        _ell(W * 0.16, H * 0.18, W * 0.085, H * 0.065, main, dark, 1.2),
        _poly([(W * 0.08, H * 0.19), (W * 0.19, H * 0.14), (W * 0.19, H * 0.22)], main),
        _poly([(W * 0.20, H * 0.13), (W * 0.26, H * 0.04), (W * 0.24, H * 0.15)], horn),
        _ell(W * 0.14, H * 0.16, 1.7, 1.9, horn),
    ]
    for i in range(5):
        x = W * (0.40 + 0.05 * i)
        y = H * (0.44 - 0.05 * i)
        out.append(_poly([(x, y), (x + 4, y - 4), (x + 6, y)], horn))
    return out


def _floating_orb(W, H, pal, rng):
    main, dark, accent = pal
    cx, cy = W / 2, H * 0.34
    r = min(W * 0.34, H * 0.24)
    out = [_path(f"M{cx:.2f},{cy+r:.2f} L{cx:.2f},{H-1:.2f}", stroke=dark, sw=2.8)]
    for i in range(4):
        a = math.radians(200 + i * 35 + rng.uniform(-8, 8))
        out.append(_path(f"M{cx:.2f},{cy:.2f} Q{math.cos(a)*r*1.4:.2f},{math.sin(a)*r*1.4:.2f} "
                         f"{math.cos(a)*r*2.1:.2f},{math.sin(a)*r*1.6:.2f}", stroke=accent, sw=2.2))
    out.append(_ell(cx, cy, r, r * 1.04, main, dark, 1.4))
    out.append(_ell(cx, cy, r * 0.46, r * 0.46, "#0f5f2e", dark, 1.0))
    out.append(_ell(cx + r * 0.06, cy, r * 0.20, r * 0.22, "#17141a"))
    out.append(_ell(cx - r * 0.10, cy - r * 0.14, r * 0.12, r * 0.10, "#ffffff"))
    out.append(_ell(cx, H - 4, r * 0.75, 2.6, dark, extra=' opacity="0.45"'))
    return out


def _aberration(W, H, pal, rng):
    main, dark, eye = pal
    cx = W / 2
    j = rng.uniform(-2, 2)
    out = [
        _limb(cx - 4, H * 0.60, cx - 9 + j, H - 2, dark, 6.0),
        _limb(cx + 4, H * 0.60, cx + 9, H - 2, dark, 6.0),
        _path(f"M{cx-13:.2f},{H*0.30:.2f} Q{cx-22:.2f},{H*0.38:.2f} {cx-13:.2f},{H*0.38:.2f} "
              f"L{cx+9:.2f},{H*0.64:.2f} L{cx-9:.2f},{H*0.64:.2f} Z",
              fill=main, stroke=dark, sw=1.4),
        _path(f"M{cx-12:.2f},{H*0.53:.2f} Q{cx-W*0.44:.2f},{H*0.52:.2f} {cx-W*0.34:.2f},{H*0.80:.2f}",
              stroke=main, sw=6.0),
        _path(f"M{cx+12:.2f},{H*0.53:.2f} Q{cx+W*0.44:.2f},{H*0.46:.2f} {cx+W*0.36:.2f},{H*0.74:.2f}",
              stroke=main, sw=5.4),
        _ell(cx, H * 0.19, 10.5, 9.5, main, dark, 1.3),
        _ell(cx, H * 0.18, 6.4, 6.4, eye, dark, 1.0),
        _ell(cx, H * 0.14, 2.4, 3.2, "#17100f"),
    ]
    for sx in (-1, 1):
        bx = cx + sx * W * (0.34 if sx < 0 else 0.36)
        by = H * (0.80 if sx < 0 else 0.74)
        for k in (-4, 0, 4):
            out.append(_path(f"M{bx:.2f},{by:.2f} l{k*0.5:.2f},6", stroke=dark, sw=1.5))
    return out


def _beast_hybrid(W, H, pal, rng):
    fur, dark, beak = pal
    cx = W * 0.50
    out = [
        _limb(cx - 6, H * 0.70, cx - 13, H - 2, dark, 8.0),
        _limb(cx + 8, H * 0.70, cx + 15, H - 2, dark, 8.0),
        _ell(cx, H * 0.62, W * 0.26, H * 0.22, fur, dark, 1.5),
        _path(f"M{cx+W*0.24:.2f},{H*0.70:.2f} Q{W*0.16:.2f},10 {W*0.10:.2f},{H*0.18:.2f}",
              stroke=fur, sw=6.0),
        _limb(cx - 10, H * 0.46, cx - W * 0.36, H * 0.60, fur, 7.5),
        _limb(cx + 12, H * 0.46, cx + W * 0.34, H * 0.36, fur, 7.5),
        _ell(cx, H * 0.34, W * 0.19, H * 0.11, fur),    # feather ruff
        _ell(cx, H * 0.20, W * 0.155, H * 0.115, fur, dark, 1.3),
        _poly([(cx - 2, H * 0.20), (cx + 8, H * 0.235), (cx - 2, H * 0.27)], beak),
        _ell(cx - 5.5, H * 0.185, 3.2, 3.4, "#f7f1de", dark, 0.8),
        _ell(cx + 4.5, H * 0.185, 3.2, 3.4, "#f7f1de", dark, 0.8),
        _ell(cx - 5.5, H * 0.185, 1.5, 1.7, "#17130f"),
        _ell(cx + 4.5, H * 0.185, 1.5, 1.7, "#17130f"),
        _poly([(cx - 13, H * 0.13), (cx - 8, H * 0.05), (cx - 6, H * 0.14)], fur),
        _poly([(cx + 12, H * 0.13), (cx + 8, H * 0.05), (cx + 5, H * 0.14)], fur),
    ]
    for sx, bx, by in [(-1, cx - W * 0.36, H * 0.60), (1, cx + W * 0.34, H * 0.36)]:
        for k in (-4, 0, 4):
            out.append(_path(f"M{bx:.2f},{by:.2f} l{sx*5:.2f},{k*0.5+5:.2f}", stroke=beak, sw=1.8))
    return out


_BUILDERS = {
    "humanoid":         lambda W, H, p, r: _humanoid(W, H, p, r),
    "humanoid-armored": lambda W, H, p, r: _humanoid(W, H, p, r, armoured=True),
    "humanoid-robed":   lambda W, H, p, r: _humanoid(W, H, p, r, robed=True),
    "undead-humanoid":  _undead_humanoid,
    "undead-robed":     _undead_robed,
    "quadruped":        _quadruped,
    "insectoid":        _insectoid,
    "plant":            _plant,
    "blob":             _blob,
    "dragon":           _dragon,
    "floating-orb":     _floating_orb,
    "aberration":       _aberration,
    "beast-hybrid":     _beast_hybrid,
}

ARCHETYPES = sorted(_BUILDERS)


def draw(archetype: str, palette, seed: int = 0, height: float = 100.0):
    """Return (svg_body, width, height) for one individual."""
    aspect = aspect_for(archetype)
    H = height
    W = height * aspect
    rng = random.Random(f"{archetype}:{seed}")
    build = _BUILDERS.get(archetype, _BUILDERS["humanoid"])
    pal = list(palette) + ["#888888"] * 3
    body = "".join(build(W, H, pal[:3], rng))
    return body, W, H