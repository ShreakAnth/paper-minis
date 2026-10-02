"""Shared creature dimensions, scale modes, and binder-clip sizing."""

from __future__ import annotations

from typing import Any


# Battle-grid widths in millimetres. Tiny creatures occupy half a 1-inch
# square; the other categories use their standard grid footprint.
_BASE_WIDTH_MM = {
    "tiny": 12.7,
    "small": 25.4,
    "medium": 25.4,
    "large": 50.8,
    "huge": 76.2,
    "gargantuan": 101.6,
}

# Typical figure heights used by heroic scale and by the linear true scale.
_HEROIC_HEIGHT_MM = {
    "tiny": 14.0,
    "small": 22.0,
    "medium": 30.0,
    "large": 50.0,
    "huge": 72.0,
    "gargantuan": 95.0,
}
_TRUE_HEIGHT_FT = {
    "tiny": 1.5,
    "small": 4.0,
    "medium": 6.0,
    "large": 10.0,
    "huge": 15.0,
    "gargantuan": 20.0,
}
_MM_PER_FOOT = 28.0 / 6.0

# Estimated width/height ratios for unmeasured art. Supplied transparent art
# uses its measured aspect ratio instead.
ARCHETYPE_ASPECT = {
    "humanoid": 0.62,
    "humanoid-armored": 0.62,
    "undead-humanoid": 0.62,
    "quadruped": 1.35,
    "beast": 1.05,
    "dragon": 1.35,
    "serpentine": 0.58,
    "insectoid": 0.9,
    "spider": 1.35,
    "ooze": 1.0,
    "floating": 0.8,
    "plant": 0.8,
    "giant": 0.72,
    "default": 0.62,
}


def _size_key(size: str) -> str:
    key = size.strip().lower()
    if key not in _BASE_WIDTH_MM:
        raise ValueError(f"Unknown creature size {size!r}; expected one of {', '.join(_BASE_WIDTH_MM)}")
    return key


def base_width_mm(size: str) -> float:
    """Return the battle-grid footprint width for a creature size."""
    return _BASE_WIDTH_MM[_size_key(size)]


def figure_height_mm(size: str, mode: str = "heroic", token_mm: float = 28.0) -> float:
    """Return figure height for heroic, linear true, or uniform token scale."""
    key = _size_key(size)
    if mode == "heroic":
        return _HEROIC_HEIGHT_MM[key]
    if mode == "true":
        return _TRUE_HEIGHT_FT[key] * _MM_PER_FOOT
    if mode == "token":
        if token_mm <= 0:
            raise ValueError("token_mm must be greater than zero")
        return float(token_mm)
    raise ValueError(f"Unknown scale mode {mode!r}; expected heroic, true, or token")


def aspect_for(archetype: str) -> float:
    """Return the expected width/height ratio for a procedural body type."""
    key = archetype.strip().lower()
    return ARCHETYPE_ASPECT.get(key, ARCHETYPE_ASPECT["default"])


def clip_for(size: str) -> tuple[str, float, int]:
    """Return (clip description, footprint width in mm, 1-inch clip count)."""
    key = _size_key(size)
    if key in ("tiny", "small"):
        return '3/4"', 19.0, 1
    count = round(_BASE_WIDTH_MM[key] / 25.4)
    if count == 1:
        return '1"', 25.4, 1
    return f'{count}"', _BASE_WIDTH_MM[key], count


def table_as_rows(mode: str = "heroic", token_mm: float = 28.0) -> list[dict[str, Any]]:
    """Return size dimensions in the JSON-friendly row shape used in reports."""
    rows = []
    for size, width in _BASE_WIDTH_MM.items():
        rows.append({
            "size": size,
            "base_width_mm": width,
            "base_depth_mm": min(9.0, max(4.5, width / 4.0)),
            "figure_height_mm": figure_height_mm(size, mode, token_mm),
            "scale": mode,
        })
    return rows
