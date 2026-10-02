#!/usr/bin/env python3
"""Create cut-out-ready art prompts from a roster using the bundled database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "paper-minis" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from roster import parse_roster  # noqa: E402


STYLE_LOCK = (
    "Painterly fantasy illustration with crisp ink outlines, readable bold "
    "silhouettes, soft top-left lighting, restrained saturated colors, and "
    "simplified detail that remains clear at miniature print size. Consistent "
    "campaign art style across every subject."
)
POSES = (
    "grounded alert stance",
    "lunging or braced combat stance",
    "casting, roaring, or advancing stance",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path, help="path to a roster text file")
    parser.add_argument("output", type=Path, help="path for the prompts JSON file")
    parser.add_argument(
        "--extra",
        type=Path,
        help="optional JSON file containing additional parsed roster entries",
    )
    args = parser.parse_args()

    roster_path = args.roster.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if not roster_path.is_file():
        parser.error(f"roster file not found: {roster_path}")

    entries = [entry.to_dict() for entry in parse_roster(roster_path.read_text(encoding="utf-8"))]
    if args.extra:
        entries.extend(json.loads(args.extra.expanduser().resolve().read_text(encoding="utf-8")))

    jobs = []
    seen = set()
    for entry in entries:
        key = entry["key"]
        if key in seen:
            continue
        seen.add(key)
        pose_count = max(1, (int(entry["count"]) + 1) // 2)
        for index in range(pose_count):
            suffix = "" if index == 0 else f"-{index + 1}"
            pose = POSES[index % len(POSES)]
            descriptor = entry.get("art") or entry["label"]
            prompt = f"""{STYLE_LOCK}
Subject: {descriptor}, a fantasy tabletop creature or fictional character.
Pose: {pose}; upright and readable, limbs and appendages contained within the silhouette.
Framing: full body, centred, entire figure inside frame, feet or lowest body edge flush with the bottom edge.
Background: fully transparent PNG with a real alpha channel; no ground, shadow, scene, vignette, or gradient.
Exclusions: no text, logo, watermark, border, frame, base, plinth, or ground shadow."""
            jobs.append({"key": key.replace(" ", "-") + suffix, "prompt": prompt})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(jobs, indent=2) + "\n", encoding="utf-8")
    print(f"{len(jobs)} prompts -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
