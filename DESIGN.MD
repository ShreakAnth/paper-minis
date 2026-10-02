# Design notes — dnd-paper-minis
Brainstorm and decision log. Written so a future session (or another AI) can pick this up without re-deriving anything.

# 1. The problem, stated precisely
"Turn a list of creatures into printable minis" hides five separate problems that want separate solutions:
1. **Naming** — `1 Sildar Hallwinter (Human Warrior)` has to become a stat lookup while keeping "Sildar Hallwinter" as the printed label.
2. **Scale** — a goblin, a human and a young dragon are not the same size, and the mini has to stand in the right grid square.
3. **Art** — 30 unique creatures need 30 coherent images that are cut-out-ready.
4. **Geometry** — the inverted-T fold, mirrored correctly, with cut/fold/score lines that mean the right thing.
5. **Packing** — ~113 minis onto as few sheets as possible without making the cutting horrible.

Conflating art with layout is the trap. The art problem is fuzzy, slow, expensive and needs a model. The layout problem is exact, fast, free and needs arithmetic. Keeping them apart is the central design decision.

# 2. Architecture

```

roster text
|
v
roster.py                 parse counts, resolve names, apply overrides
|
v
entries \[(label, key, count, size, archetype, palette, art)\]
|                           
v                            
sizes.py                      art\_provider.py
size category -\>              per individual: art/ -\> art-dir -\> procedural
figure\_mm + base\_mm
|
v
cells     inverted-T geometry, one per mini
|
v
layout.py                 bucket by height -\> rows -\> first-fit pages -\> validate
|
v
pages
|
v
render\_svg.py             real-millimetre SVG, cut/fold/score, labels, ruler
|
v
sheet-NN.svg
|
v
to\_pdf.py                 cairosvg per-page PDF -\> pypdf merge
|
v
minis.pdf + manifest.json

``` 

Every stage is a separate module with a plain-data boundary, so any one of them can be swapped without touching the others. Concretely: better art is a new file in `art/`, a different paper size is a flag, a new fold style is one function in `layout.Cell.outline()`.

The key rule: the script never calls a model.
Claude generates art (in the art-director skill) and writes PNGs to `<out>/art/`. `build_minis.py` only ever reads files off disk.

Why this is the right boundary:
* the build is reproducible and unit-testable with no network
* a sheet can be regenerated years later from the same `art/` folder
* upgrading art is a re-run, not a redesign
* a missing image degrades to a silhouette instead of failing the build
* generation, the slow and possibly billed step, is never repeated by accident

# 3. Decision log

| Decision | Chosen | Rejected, and why |
|---|---|---|
| Art source | adapter with gen-AI primary + procedural fallback | gen-AI only (plugin is useless until an endpoint exists); folder only (you source 30 images by hand); procedural only (not illustrated art) |
| Render | Python -> SVG (mm) -> PDF | HTML/CSS print (browser scaling silently breaks true-to-scale); LaTeX/TikZ (heavy toolchain, slow iteration for image-heavy sheets); direct ReportLab (no inspectable intermediate) |
| Packing | uniform row heights, first-fit decreasing | free 2D bin packing — saves ~3% paper, produces a staircase of offset cut lines. Paper is cheap, scissors time decreasing is not |
| Mirror | vertical flip (`scale(1, -1)`) | 180° rotation — also puts the head up, but mirrors in the fold plane and shifts the figure, so plies misalign |
| Base depth | `grid / 4`, clamped 4.5–9 mm | full grid square — a Large mini would eat a quarter of a sheet for a foot it does not need |
| Base width | `max(grid_square, art_width)` | strict grid square — a dragon's wings would make it physically unable to stand |
| Plural handling | test multiple candidate forms | one rule — `zombies` -> `zomby` would have mislabelled twelve minis |
| Unknown creature | warn, default medium/humanoid, keep building | hard fail — one typo should not kill a 113-mini build |

Things that turned out to matter more than expected:
* **The 50 mm verification bar.** Printer drivers default to "Fit to page", which rescales by a few percent and makes every size claim on the sheet false. One printed ruler makes the whole scale system trustworthy.
* **Clipping art to its cell.** During development the procedural spider's legs walked across the neighbouring mini's cut line. A per-cell clip path makes "nothing leaves the box" a guarantee for every backend, including art the user supplies.
* **Label auto-fit.** "Gundren Rockseeker" does not fit in 25.4 mm at a readable size. Shrink-then-truncate, with the glyph-width estimate erring high, because a label crossing a cut line is worse than a small label.

# 4. Skill split
Two skills, split along the lines of what kind of judgement is needed:
* `paper-minis` — procedural judgement. Runs the pipeline, reports counts, chases down unresolved names, validates, presents. Owns the non-negotiables (counts double, true to scale, straight cuts, print at 100%).
* `minis-art-director` — aesthetic judgement. Owns the style lock and the six hard constraints that make art cut-out-ready. This is where a model's creativity is wanted and where it must be fenced in.

Each skill's `SKILL.md` stays lean; detail lives in `references/` and loads only when needed.

# 5. Verified against the real roster
Full Phandelver list, 34 entries -> 113 minis -> 226 printed figures -> 7 A4 sheets, 65% of printable area used, `geometry_problems: []`, zero unresolved names.
* Generated A4 PDF measures 595.28 x 841.89 pt = 210.0 x 297.0 mm exactly.
* Letter + heroic: 6 sheets, 72% utilisation.
* `--scale true` and `--scale token` both build clean.
* Edge cases (unknown creature, 5 Kobolds x3 double count, override comment, stdin roster) warn and build rather than crash.
* A rendered sheet was inspected visually: I-beam outline, fold dashed at the centre, score dotted at the base, mirrored half is a true vertical flip, art inside its outline, labels inside their cells.

# 6. Open questions
1. **Fold style.** Implemented: shared base bar, ⊥ per half. The reference sheet may instead use fold-at-the-feet with side tabs. `outline()` plus two score lines is the only place this lives — say the word and it becomes a `--fold-style` flag.
2. **Back view.** Default back ply is left-right reversed (industry standard). `--mirror-back` gives a true back view. Which do you want as default?
3. **Pose variety.** Settled, and the open question caused a bug. The rule is: pairs share a pose, so N minis want `ceil(N/2)` images, and the art director asks the user once at 3 or more. The "count > 5" floated here leaked into the `/minis` command, where it overrode the skill — four goblins printed identical because nothing asked. One threshold, stated in `minis-art-director/SKILL.md` only, everything else defers to it.
4. **Sheet grouping.** Everything is mixed for density. Alternative: one sheet per encounter or per creature type, so you print only what tonight needs.

# 7. Roadmap — further skills worth adding

| Skill | Why |
|---|---|
| `minis-encounter-import` | paste an adventure's encounter table or a statblock URL -> roster, so step 1 disappears |
| `minis-party` | the PCs, from character sheets, with per-player base colours and character cards |
| `minis-terrain` | fold-up doors, chests, braziers, campfires — same geometry, different content |
| `minis-tokens` | flat top-down tokens from the same art, for when you want a battlemap not standees |
| `minis-reprint` | "reprint just the goblins at Large for the boss fight" from an existing manifest |
| `minis-art-pack` | build a reusable local art library across campaigns, so creature art is generated once |

`minis-reprint` is the highest-value next one: the manifest already records every mini's size, art source and placement, so reprinting a subset is a query plus a re-pack, not a rebuild.

# 8. The art backend: Codex CLI imagegen (settled 2026-09-22)
The resolved route is Codex CLI's bundled `imagegen` skill.

### What works
`codex` -> "generate an image of..." -> Read `SKILL.md` (`imagegen` skill) -> file saved to `~/.codex/generated_images/<run-id>/<exec-id>.<ext>`. Verified 2026-09-22 with zero configuration: 37 s, `gpt-5.6-luna` at low reasoning effort. Auth is Codex's own OAuth (`codex login`) against the ChatGPT Enterprise entitlement.

Driven here by `scripts/image_gen.py` (named `codex_art.py` until 0.9.0, when it stopped being Codex-specific; the compatibility shim was removed in 0.9.7):
* `--tool codex|claude|gemini|opencode|cursor-agent`, or `--cmd 'x {prompt}'` for an agent with no backend entry. `auto` picks the first one installed that we are not already running inside
* `--mode cpair` -> `run-role.sh --tool <agent> imagegen "<prompt>"`, so the cpair imagegen role's own instructions and effort setting apply
* `--mode exec` -> the agent's own non-interactive invocation
* `--mode auto` (default) -> cpair if `run-role.sh` is found, else exec
* harvests the printed path, falling back to the newest new file under the `generated-images` directory, then copies to `art/<key>.<ext>`
* skips existing files unless `--force`; failures degrade to procedural art

Two rules make the harvest safe, both learned the hard way:
* the provenance guard lives inside the harvest, so a path outside the job home is skipped and the scan continues. As a post-filter it rejected the printed cwd copy and discarded the genuine file sitting one directory down
* a backend whose config-dir env var is unverified gets no isolated home, and therefore no newest-file fallback. A wrong home is worse than none: it confines the harvest to a directory the tool never writes to and throws away every job

### Why this validated the architecture rather than changing it
The plugin was already built so the layout engine reads art off disk and the build script never calls a model. That decision was made for reproducibility — but it is what made this swap a subprocess plus a file copy instead of a redesign. Two gateway routes died and one new one appeared, and `layout.py`, `render_svg.py`, `sizes.py` and `roster.py` were untouched.

It also settles something structural: Claude cannot draw these creatures. Anthropic ships no image-generation model, so a plugin running under Claude must either shell out or fall back. Both paths are now explicit in the art-director skill, so a future session does not waste a turn trying to render creature art as SVG and calling it generated art.

That statement is about Claude, not about the plugin, and 0.9.0 makes the difference matter. The plugin now runs under four hosts, and two of them draw natively — so "shell out" is the fallback, not the design. The order is: the host draws if it can, otherwise dispatch an installed agent, otherwise procedural silhouettes. `image_gen.py` enforces the first step by refusing to spawn the agent it is already running inside.

### Routes ruled out, and why

| Route | Status |
|---|---|
| Host draws natively | **BEST** — Cursor 2.4+ (Nano Banana Pro, defaults to `assets/`), Codex (`imagegen`). No dispatch, no second auth. |
| Codex CLI `imagegen` skill | **WORKS** — best for scripted/agent use. Verified 2026-09-22 |
| Gemini CLI | Only with the nanobanana extension; no built-in image generation. |
| ChatGPT Enterprise UI (`go/chatgpt`) | Works, but manual; fine for one-offs, not for 30 creatures. |
| Claude Code | Impossible — no image-generation model exists. This is the case the dispatcher was written for. |
| Custom image-stack route | Ruled out, two hard blockers. See below. |
| Vertex Imagen + local SDK | Blocked on a project ADM role. |
| MCP Image-Gen Service | Not in the Non-HRZ MCP hub as of 2026-09-22. |

### Why the custom image-stack route failed, recorded so nobody re-litigates it:
1. The project-specific model registry accepts only a fixed set of model IDs, so arbitrary image-model names cannot be addressed at all.
2. Adding a custom component is not a UI paste: it requires a forked upstream stack, a custom image build, MLOps image registration, a new orchestration path, and a separate runtime allowlist update. The ported component set is text/data only, and even the image-input node is blocked in the v3 port.

Full evidence with page IDs: `~/.second-brain/notes/global/custom_image_stack_imagen_feasibility_verified_facts.md` and `~/.second-brain/notes/global/codex_imagegen_skill_verified_facts.md`.

# Real art is mandatory (v0.3.0, broadened in 0.9.0)
`--art-backend` now defaults to `genai` and the build exits 3 if any creature lacks real art on disk, naming the creatures. The reasoning: the old default silently substituted a silhouette, and that is a failure you discover after cutting out 113 minis, not before. Failing at second zero is cheaper than failing at minute forty.

Cost of the choice, stated honestly: in 0.3.0 this meant a hard dependency on a second CLI and an OpenAI entitlement, producing nothing at all when Codex was down or logged out. 0.9.0 narrows that considerably — any of five agents will do, and a host that draws natively needs none of them — but the shape of the risk is unchanged: something must be able to generate an image. Mitigations:
* `image_gen.py --list-tools` answers "can anything draw here" without running anything; `--check` preflights binary, login and output dir in ~2 s, and `--probe` does one real end-to-end image
* two documented escape hatches: `--art-backend svg` (all procedural) and `--allow-procedural` (real art where it exists, silhouettes elsewhere)
* `manifest.json` records `art.backend`, `art.strict`, `art.sources` and `art.procedural_fallbacks`, so a sheet can always be audited after the fact

### Open dependency
The cpair `imagegen` role is not yet committed — tracked in `~/.second-brain/tasks/global/2026-09-22-cpair-codex-imagegen-role.md` (`ROLE_IMAGEGEN: codex`, `ROLE_EFFORT_IMAGEGEN: low`, plus an agent file). Until it lands, `image_gen.py --mode exec` works on any machine with one of the supported agents installed and logged in. This plugin is that role's first real consumer.

