"""Roster text -> normalised creature entries.

Accepts the way people actually write encounter lists:

  7 Goblins
  * 3 Wolves
  - 1 Sildar Hallwinter (Human Warrior)
  Skeletons x9
  Zombie: 12
  1 Venomfang (Young Green Dragon)  # size=large scale=heroic

Rules
-----
* Count may lead ("7 Goblins"), trail ("Goblins x7", "Goblin: 7") or be absent
  (implies 1).
* A trailing parenthetical is a *stat hint*: the label stays as written (so a
  named NPC keeps their name on the sheet) but lookup uses the hint.
* '# key=value' trailing comments override anything: size, archetype, scale,
  height_mm, base_mm, art, palette.
* Unresolved names do NOT fail the build. They fall back to medium/humanoid
  and are flagged so the user can correct them in one pass.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path

DATA = Path(__file__).parent / "data" / "creatures.json"

_LINE = re.compile(
    r"""^\s*[-*]?\s*
        (?:(?P<pre>\d+)\s+[*x]?\s*)?
        (?P<name>.+?)
        (?:\s*[*x]\s*(?P<post>\d+))?
        (?:\s*:\s*(?P<colon>\d+))?
        \s*$""",
    re.VERBOSE | re.IGNORECASE,
)
_PAREN = re.compile(r"\s*\(([^)]+)\)\s*$")
_OVERRIDE = re.compile(r"(\w+)\s*=\s*([^\s,]+)")
_GENDER = re.compile(r"\b\s*(male|female|man|woman)\b\s*", re.IGNORECASE)
_GENDER_WORD = {"male": "male", "man": "male", "female": "female", "woman": "female"}


@dataclass
class Entry:
    label: str                     # what gets printed on the mini
    key: str                       # creature-database key (+ '-male'/'-female')
    count: int
    size: str
    archetype: str
    palette: list
    art: str                       # short art descriptor, seeds the AI prompt
    unresolved: bool = False
    gender: str = ""               # "male"/"female" when the roster says so
    overrides: dict = field(default_factory=dict)
    source_line: str = ""

    def to_dict(self):
        return asdict(self)


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _candidates(slug: str):
    """Every plausible singular of 'slug', cheapest first.

    English plurals are not worth guessing with one rule -- "zombies" -> "zomby"
    is exactly the kind of near-miss that silently mislabels nine minis. So
    generate all the plausible forms and let the database decide which is real.
    """
    words = slug.split()
    if not words:
        return [slug]
    head, last = words[:-1], words[-1]
    forms = [last]
    if last.endswith("s") and not last.endswith("ss"):
        forms.append(last[:-1])             # zombies -> zombie
    if last.endswith("es") and len(last) > 3:
        forms.append(last[:-2])             # boxes -> box
    if last.endswith("ies") and len(last) > 4:
        forms.append(last[:-3] + "y")       # bodies -> body
    if last.endswith("ves") and len(last) > 4:
        forms.append(last[:-3] + "f")       # wolves -> wolf
        forms.append(last[:-3] + "fe")      # knives -> knife
    seen, out = set(), []
    for f in forms:
        cand = " ".join(head + [f]) if f else " ".join(head)
        if cand and cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


class CreatureDB:
    def __init__(self, path: Path = DATA, extra: Path | None = None):
        raw = json.loads(path.read_text()) if path.is_file() else {"creatures": {}, "aliases": {}}
        self.creatures = {_slug(k): v | {"key": k} for k, v in raw["creatures"].items()}
        self.aliases = {_slug(k): _slug(v) for k, v in raw.get("aliases", {}).items()}
        if extra and extra.exists():
            more = json.loads(extra.read_text())
            for k, v in more.get("creatures", {}).items():
                self.creatures[_slug(k)] = v | {"key": k}
            for k, v in more.get("aliases", {}).items():
                self.aliases[_slug(k)] = _slug(v)

    def lookup(self, name: str):
        """Return (record, matched_how) or (None, None)."""
        cands = _candidates(_slug(name))
        for candidate in cands:
            if candidate in self.creatures:
                return self.creatures[candidate], "exact"
            if candidate in self.aliases:
                target = self.aliases[candidate]
                if target in self.creatures:
                    return self.creatures[target], "alias"
        pool = list(self.creatures) + list(self.aliases)
        for candidate in cands:
            hit = difflib.get_close_matches(candidate, pool, n=1, cutoff=0.86)
            if hit:
                target = self.aliases.get(hit[0], hit[0])
                if target in self.creatures:
                    return self.creatures[target], "fuzzy"
        return None, None


def parse_line(line: str, db: CreatureDB) -> Entry | None:
    raw = line.rstrip("\n")
    if not raw.strip() or raw.lstrip().startswith(("#", "//")):
        return None

    overrides = {}
    body, _, comment = raw.partition("#")
    if comment:
        overrides = {k.lower(): v for k, v in _OVERRIDE.findall(comment)}

    m = _LINE.match(body)
    if not m:
        return None
    count = int(m.group("pre") or m.group("post") or m.group("colon") or 1)
    label = m.group("name").strip().rstrip(":").strip()
    if not label:
        return None

    hint = None
    pm = _PAREN.search(label)
    if pm:
        hint = pm.group(1).strip()
        label_clean = _PAREN.sub("", label).strip()
    else:
        label_clean = label

    # "Female Drow" and "Male Drow" must not collapse onto one art file, so a
    # stated sex becomes part of the art key and of the prompt. The creature
    # record (size, archetype, palette) still comes from the base name.
    gender = ""
    gm = _GENDER.search(label_clean)
    if gm:
        gender = _GENDER_WORD[gm.group(1).lower()]
        stripped = _GENDER.sub("", label_clean).strip()
        if db.lookup(stripped)[0] is not None:
            label_clean = stripped
    gender = _GENDER_WORD.get(overrides.get("gender", "").lower(), gender)

    rec, how = db.lookup(label_clean)
    if rec is None and hint:
        rec, how = db.lookup(hint)
    if rec is None:
        rec, how = db.lookup(label)

    unresolved = rec is None
    if rec is None:
        rec = {
            "key": _slug(label_clean) or "unknown",
            "size": "medium",
            "archetype": "humanoid",
            "palette": ["#7a7a7a", "#3d3d3d", "#b5b5b5"],
            "art": label_clean,
        }

    palette = rec["palette"]
    if "palette" in overrides:
        # # palette=#6b7b84,#33403f,#b5762f -- how a player character gets its
        # own base-band colour, so it is findable on a crowded table.
        cols = [c if c.startswith("#") else f"#{c}"
                for c in overrides["palette"].split(",") if c.strip()]
        if cols:
            palette = (cols + palette[len(cols):])[:3] if len(cols) < 3 else cols[:3]

    # An entry that carries explicit size AND archetype is fully specified, so
    # the database never needed to resolve it. Warning about it is noise --
    # that is the normal shape of a player-character roster line.
    fully_specified = "size" in overrides and "archetype" in overrides

    base_art = overrides.get("art", rec.get("art", label_clean))
    entry = Entry(
        label=label_clean or label,
        key=f"{rec['key']}-{gender}" if gender else rec["key"],
        gender=gender,
        count=count,
        size=overrides.get("size", rec["size"]),
        archetype=overrides.get("archetype", rec["archetype"]),
        palette=palette,
        art=f"{gender} {base_art}" if gender else base_art,
        unresolved=unresolved and not fully_specified,
        overrides=overrides,
        source_line=raw.strip(),
    )
    return entry


def parse_roster(text: str, db: CreatureDB | None = None) -> list[Entry]:
    db = db or CreatureDB()
    out = []
    for line in text.splitlines():
        entry = parse_line(line, db)
        if entry:
            out.append(entry)
    return out


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
    entries = parse_roster(src)
    print(json.dumps([e.to_dict() for e in entries], indent=2))
