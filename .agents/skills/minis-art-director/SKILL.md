
---
description: Produce consistent, cut-out-ready creature art for paper miniatures. Use when generating or regenerating art for a mini set, when the user says the minis look inconsistent or "like different art styles", when art needs to be redone at a different style or palette, or when a creature has no art yet. Also use when the user asks for pose variants so a mob of identical monsters looks less repetitive.
---

# Minis Art Director

Generate one image per creature that drops straight into the paper-minis layout with no manual cleanup. The layout engine reads files off disk, so the job here is: produce correct files in `<out>/art/`, then stop.

# Who draws

If you can generate an image, you draw. The whole dispatch apparatus below exists only for hosts that cannot, and dispatching to reach a capability you already have is the most common way this skill goes wrong.

Look properly before concluding you cannot. Do not decide from the tool list in front of you, and do not rely on any claim about which hosts can draw — including one in this file, which would go stale the moment a host gained the capability. Check all three places it can live:

1. **Deferred tools.** Many hosts load tools on demand, so an image generator that exists is not in your visible list until you search for it. Search by capability, not brand: `image`, `imagegen`, `image generation`, `draw`, `picture`.
2. **Skills.** On some hosts image generation arrives as a skill rather than a tool. Check the available-skills list for an `imagegen` or `image-generation` entry and invoke it.
3. **Your own built-in ability,** if you have one that needs no tool call.

Only after all three come back empty are you a host that cannot draw. Say so explicitly in your report — "no image tool, skill, or deferred tool found after searching" — so the user can see it was checked rather than assumed.

Drawing natively still goes through the plan step, because the reuse library lives in the script and skipping it means regenerating art you already own:

```bash
python3 $MINIS/image_gen.py <out>/prompts.json --out <out> --plan

````

That links every library hit into `<out>/art/` and prints only the prompts still outstanding, each with the exact filename to save it as. Generate those, transparent background, then go to `build_minis.py`. Nothing else is needed.

What you must not do either way: render creature art as SVG, canvas or ASCII and pass it off as generated art. That is the procedural fallback's job and it is already better at it.

# Dispatching, when you cannot draw

Write prompts to a JSON file, dispatch, harvest:

``` bash
A=$MINIS/image_gen.py
python3 $A <out>/prompts.json --out <out>            # 4 workers by default
python3 $A <out>/prompts.json --out <out> --limit 3  # look before committing
python3 $A <out>/prompts.json --out <out> --jobs 8   # faster, match rate lim
python3 $A <out>/prompts.json --out <out> --dry-run

```

Always parallelise, and always sanity-check a few first. One image takes \~95 s, so a 50-creature set is 80 minutes serial and about 20 at `--jobs 4`. Each worker gets an isolated `CODEX_HOME` (auth and config symlinked in) so generated-image directories cannot collide — do not hand-roll this with shell loops, and do not set `--jobs 1` unless you are debugging.

Run `--limit 3` first and look at the results. Fixing the style lock after three images costs five minutes; after fifty it costs an hour.

When using Codex CLI, dispatches through `codex exec`. Images land in `~/.codex/generated_images/<run-id>/` and are copied to `<out>/art/<key>.<ext>`. Sign in with `codex login` first. Existing files are skipped unless `--force`.

The current supported path is the host's image tool or the Codex CLI `imagegen` skill. `scripts/fetch_art.py` remains for a generic HTTP image endpoint if one ever appears — it is not the current path.

# The hard constraints

Paper-mini art has requirements that ordinary character art does not. Violating any of these produces a mini that is unusable, so put every one of them in every prompt:

1.  **Full body, feet at the very bottom edge of the frame.** The feet meet the base fold line. A cropped or floating figure cannot stand.
2.  **Transparent background.** No scene, no ground, no cast shadow, no vignette, no gradient backdrop. A shadow on the ground becomes a grey smear on the base.
3.  **Straight-on or slight three-quarter view, upright, centred.** Not a dutch angle, not from above, not lying down.
4.  **No text, no border, no frame, no watermark, no base or plinth drawn in.** The base is printed by the layout engine.
5.  **Silhouette readable at 22–30 mm tall.** This is the constraint people forget. Fine filigree, thin whiskers and small props vanish. Ask for bold shapes, strong value contrast, chunky readable weapons.
6.  **Limbs inside the bounding box.** Wings folded or half-spread, tails curled in. Anything that leaves the frame gets clipped at the cut line.

# Style lock

Generate one style-lock block per set, before any creature, and paste it verbatim into every prompt in that set. Cohesion across the sheet matters more than any single image being beautiful — mismatched styles are what make a home-made set look home-made.

Write the style lock as 4–6 clauses covering: rendering technique, line treatment, lighting direction, saturation, and level of detail. Full worked examples and three ready-made house styles are in `references/style-lock.md`.

Do not vary the style lock between creatures in a set. Do not let a creature's own description (a "glowing" flameskull, a "shadowy" wraith) override lighting direction — express it in the creature clause instead.

# Per-creature prompt assembly

Compose in this fixed order so the constraints always win over flourish:

``` 
<style lock>
Subject: <creature descriptor from creatures.json "art" field, expanded>
Pose: <one specific readable action>
Framing: full body, standing, feet flush with the bottom edge of the image, centred, entire figure inside frame, no cropping
Background: fully transparent, no ground, no shadow, no scene
Exclusions: no text, no logo, no frame, no base, no plinth, no ground shadow

```

# Generate as little as possible

Every image costs \~95 s and an API call. Two rules keep a set cheap:

Ask before generating variants, then generate them in pairs. When a creature has 3 or more minis, ask the user whether they want pose variety for it. Ask once, covering every such creature in the set, with the cost:

> 14 of your creatures have 3+ minis. Pose variety means 47 images instead of 14 — about 13 minutes at `--jobs 8` rather than 6. Want it, and for all of them or just some?

If yes, pairs share a pose: minis 1–2 use `<key>`, 3–4 use `<key>-2`, 5–6 use `<key>-3`. A creature with N minis therefore needs ceil(N/2) images. That gives a mob visible variety at half the cost of one image per mini, and nobody at the table notices that two of nine skeletons match.

Record the answer on the roster line so a re-run does not re-ask and the roster stays self-describing:

``` 
9 Skeletons
12 Zombies          # (nothing) -> paired poses, the default
                    # poses=single -> one image for all twelve

```

`manifest.json` -\> `poses` tells you exactly what to generate: `poses_needed` and `missing_poses` per creature. Build `prompts.json` from that rather than counting by hand. Never generate what the library already has. `image_gen.py` checks `~/.dnd-paper-minis/art/<style>/` before dispatching and reports what it reused, so a goblin is generated on the first campaign that needs one and never again. Build `prompts.json` for every unique creature in the roster and let the script decide what is actually missing — do not pre-filter, and do not pass `--force` unless the user wants art replaced.

Check what is already banked before promising a wait time:

``` bash
ls ~/.dnd-paper-minis/art/default/

```

For pose variants, change only the `Pose` clause. Variants differ in stance, not in style or palette.

# Naming and delivery

`image_gen.py` handles the file naming from the `key` in `prompts.json`, so build `prompts.json` with the creature key from `creatures.json`, spaces replaced by hyphens:

``` json
[
  {
    "key": "goblin",
    "prompt": "<style lock>\nSubject: ..."
  },
  {
    "key": "goblin-2",
    "prompt": "<same lock, different Pose clause>"
  },
  {
    "key": "young-green-dragon",
    "prompt": "..."
  },
  {
    "key": "ravi-the-unshaken",
    "prompt": "..."
  }
]

```

The resulting files:

``` 
<out>/art/goblin.png              used for every goblin with no variant
<out>/art/goblin-2.png            used for goblin #2
<out>/art/goblin-3.png            used for goblin #3
<out>/art/young-green-dragon.png

```

Ask for a transparent PNG. Image models frequently ignore that and return an opaque background, so put the fallback in the prompt, not in a script you write afterwards:

``` 
Background: fully transparent PNG with a real alpha channel. If transparency is not possible, use a flat pure magenta #FF00FF background with no gradient, no shadow and no magenta anywhere on the creature itself.

```

Then build with `--strip-bg`. The plugin keys magenta out, erodes the alpha by 1 px to drop the anti-aliased fringe, and softens the edge — automatically, for every image. Do not hand-roll a background remover; if the keyer needs changing, change `art_provider._trim_and_encode` so the next run inherits it.

# After generating

1.  Re-run `build_minis.py` so the new art is picked up.
2.  Render one sheet to PNG and look at it. Check feet-on-fold-line, no clipped limbs, silhouette still readable at print size.
3.  Report which creatures now have real art and which are still on the procedural fallback.

If Codex CLI is not installed or not logged in, say so plainly, build with the procedural backend, and tell the user the set can be upgraded later by dropping files into `art/` — the layout does not change and the sheets stay printable in the meantime.

