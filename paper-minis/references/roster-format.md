Here is the complete **`roster-format.md`** content compiled from your attached files:


# Roster format

Designed so a list pasted out of an adventure module works unedited.

## Accepted line shapes

```text
7 Goblins                             count leads
* 3 Wolves                            bullets are stripped
- 1 Sildar Hallwinter (Human Warrior) parenthetical = stat hint
Skeletons x9                          count trails
Zombie: 12                            colon form
Owlbear                               no count = 1
# a comment line                      ignored

````

## The parenthetical is a stat hint, not the name

`1 Nezznar the Black Spider (Drow)` prints "Nezznar the Black Spider" and resolves stats from `drow`. This is the whole reason named NPCs work: the label is what appears on the mini, the hint is what the database looks up.

**Lookup order:** `label` → `parenthetical hint` → `the raw line including the parenthetical`. First hit wins.

## Name resolution

1.  **Normalise:** lowercase, strip accents and punctuation.
2.  **Generate plural candidates and try each:** `zombies` → `zombie`, `wolves` → `wolf`, `bodies` → `body`. Multiple candidate forms are tested rather than one guessing rule, because `zombies` → `zomby` is exactly the near-miss that would mislabel twelve minis.
3.  **Exact key**, then alias, then fuzzy match at 0.86 similarity.
4.  **Unmatched:** default to `medium` / `humanoid`, flag `unresolved: true`, and keep building. Never fail a 130-mini build over one typo.

> Always report unresolved entries to the user and get the size class before printing. A silent generic human standing in for a dragon is worse than an error.

## Overrides

Trailing `# comment`, `key=value`, space separated:

| Key             | Effect                                                        |
| :-------------- | :------------------------------------------------------------ |
| `size`          | `tiny` / `small` / `medium` / `large` / `huge` / `gargantuan` |
| `archetype`     | body type for procedural art and prompt skeleton              |
| `height_mm`     | exact figure height, bypasses the scale mode                  |
| `base_mm`       | exact base width                                              |
| `base_depth_mm` | total footprint depth (both bars)                             |
| `art`           | replacement art descriptor for the prompt                     |
| `poses`         | `pairs` (default) or `single` — see below                     |

### Examples

``` text
12 Zombies                       # archetype=undead-humanoid
1 Venomfang (Young Green Dragon) # size=huge height_mm=80

```

## Pose variety

Minis of the same creature share art in pairs: 1–2 use `<key>`, 3–4 use `<key>-2`, 5–6 use `<key>-3`. A creature with N minis wants `ceil(N/2)` images. Missing variants fall back to `<key>`, so a half-generated set still builds.

`# poses=single` makes every mini of that creature use the one image:

``` text
9 Skeletons                   # paired poses (default)
12 Zombies   # poses=single   # one image for all twelve

```

`manifest.json` → `poses` reports `minis`, `poses_needed`, and `missing_poses` per creature.

## Archetypes

`humanoid`, `humanoid-armored`, `humanoid-robed`, `undead-humanoid`, `undead-robed`, `quadruped`, `insectoid`, `plant`, `blob`, `dragon`, `floating-orb`, `aberration`, `beast-hybrid`.

Archetype drives two things: the procedural silhouette, and the skeleton of the gen-AI prompt. It does not affect geometry except through the assumed aspect ratio.

## Inspecting a parse

``` bash
python3 scripts/roster.py myroster.txt

```

Prints normalised JSON: `label`, `resolved key`, `count`, `size`, `archetype`, `palette`, `art descriptor`, `unresolved`, and the `original line`. Diff this against the roster before a big print run.



