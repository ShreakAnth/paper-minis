# Paper Minis

## Description
Generate print-ready paper miniatures from a list of creatures or characters. Use when the user asks for paper minis, printable miniatures, paper standees, fold-over minis, cardstock minis, a mini sheet for an encounter or campaign, or says things like "make me 7 goblins and 3 wolves I can print", "turn this monster list into printable minis", "I need minis for tonight's session", or pastes a roster of D&D creatures with counts. Also use when the user wants to rescale, repack, or reprint an existing mini set.

Build printable "Inverted-T" fold-over paper miniatures from a roster. Drive the pipeline in `scripts/`; do not hand-write SVG or HTML layout — the geometry is already exact and validated there.

## Non-negotiables
* **Counts double.** `7 Goblins` = 7 minis = 14 printed figures. Each cell holds the upright figure and its vertically-mirrored twin, which fold back-to-back into one standee. State both numbers to the user.
* **True to scale.** Base width equals the creature's battle-grid square (Medium = 1 in / 25.4 mm, Large = 2 in, Huge = 3 in). Never eyeball sizes.
* **Straight cut lines.** Rows have uniform height so the sheet can be guillotined into strips. Never switch to free 2D bin packing.
* **Binder-clip stands by default.** `--fold-style clip`: one fold, rectangular cuts, no glue, and a binder clip is the base. `--fold-style base` is the older fold-out-paper-tab design and needs glue.
* **A4 by default.** Never assume Letter.
* **Never invent a campaign name.** `--title` has no default. If the user has not said what the set is called, ask — do not infer it from a roster filename, a creature list, or the adventure it looks like. A sheet with a guessed title looks finished when it is not. The build warns when no title was given; treat that warning as a question you failed to ask.
* **Never write a renderer.** The PDF comes from `render_pdf.py` (ReportLab, pure Python — no Chrome, no libcairo, no Homebrew). If it exits 4, the fix is `pip install reportlab` and nothing else. Do not build an HTML/Chrome print path, do not hand-write SVG: the fold geometry lives in `layout.py` and re-implementing it silently loses the mirrored copy.
* **Print at 100%.** Every sheet carries a 50 mm verification bar. Tell the user to print at Actual Size and never "Fit to page", or the scale is a lie.
* **YOU draw the art if you can generate an image at all.** `art_provider.py` never calls an image model by design — it only reads files off disk, so the art step is yours: save one image per creature to `<out>/art/<key>.png`, `<key>` verbatim, transparent background. Run `image_gen.py <out>/prompts.json --out <out> --plan` first even when drawing natively: it links what the reuse library already owns and prints every outstanding prompt with the exact filename to save it as. Nothing else is needed.
  * Search before concluding you cannot draw. An image generator may be a deferred tool absent from your visible list until you search for it, or a skill rather than a tool. The `minis-art-director` skill says where to look. Dispatching a second agent to reach a capability you already have is the most common failure here.
* `image_gen.py` dispatch is for hosts that cannot draw. It spawns a CLI agent as a subprocess with its own auth, context and per-job config home, billed per image. It is refused outright inside the agent it would dispatch, and it is the fragile path — MDM approval policy, sandbox write permissions and the user's global instruction file have each broken it before. Do not reach for it to do something you can do yourself.
* A failed art step is an error, never a downgrade to silhouettes. The build exits 3 and names every creature still missing art. That is art owed, not a build failure to route around. Never pass `--allow-procedural` or `--art-backend svg` to get past it unless the user asked for silhouettes: it ships a sheet whose figures are blank shapes, and the user finds out after cutting out the minis. Report what failed, say which creatures have no art, and ask. A dispatch that fails is a fact to relay, not a reason to lower the output.

## Workflow

### 0. Locate the scripts
The install path differs per agent — Claude Code exports `${CLAUDE_PLUGIN_ROOT}`, Codex puts imported skills under `~/.codex/skills/` or `~/.agents/skills/`. Resolve it once, then use `$MINIS` throughout:

```bash
MINIS=$(find "${CLAUDE_PLUGIN_ROOT:-/nonexistent}" \
  ~/.agents ~/.codex ~/.cursor ~/.gemini ~/.claude .agents .cursor \
  -maxdepth 10 -type d -path "*/paper-minis/scripts" -print 2>/dev/null | head -1)
```

Empty means the plugin is not visible to this agent — say so, do not guess. Details in `references/paths.md`.

### 1. Get the roster
Accept whatever the user pasted. Write it verbatim to `<out>/roster.txt`. Do not reformat counts or rename creatures. Supported shapes are in `references/roster-format.md`.

### 2. Resolve names, then confirm only the failures
```bash
python3 $MINIS/roster.py <out>/roster.txt
```

Report any entry with `"unresolved": true`. For each, ask the user for the size category and body type, then record it as a trailing override on that roster line (`# size=large archetype=dragon`) or in `<out>/creatures.local.json`. Never silently print an unknown creature as a generic human.

Named NPCs keep their own label. `1 Nezznar the Black Spider (Drow)` prints "Nezznar the Black Spider" using drow-mage stats.

### 3. Choose the art backend
Ask the user once, then remember the choice for the session:

| Backend | When | What happens |
|---|---|---|
| `genai` | some CLI agent that can draw is installed and logged in | Invoke the `minis-art-director` skill, which writes prompts and runs `image_gen.py` to dispatch it. One image per unique creature at `<out>/art/<key>.<ext>`; pose variants at `<key>-2`, `<key>-3`. |
| `folder` | user owns or licensed an art pack | Point `--art-dir` at it; filenames must match creature keys. |
| `svg` | no image route, or the user wants a fast proof | Procedural silhouettes, colour-coded, always works, no network. |
| `auto` | mixed | run folder, then the shared library, then `--art-dir`, then procedural. Missing art never blocks the build. |

#### Draw it yourself if you can. Only shell out if you cannot. In order:
1. **Native.** If you have an image-generation tool, use it. Generate each prompt and save it as `<out>/art/<key>.png`, `key` verbatim, transparent background. The build reads art off disk and never calls a model, so nothing else in the workflow changes. This is the fastest and cheapest path by a wide margin — no second agent, no second auth, no second context.
2. **Dispatch another agent.** Only when you have no image tool. `image_gen.py` drives `codex`, `claude`, `gemini`, `opencode` or `cursor-agent`, and `--cmd 'whatever {prompt}'` handles anything else. `--tool auto` picks the first one installed that you are not already running inside.
3. `svg`. No image route at all — procedural silhouettes, always works.

```bash
python3 $MINIS/image_gen.py --list-tools  # what is installed, what auto pick sees
python3 $MINIS/image_gen.py --check       # full preflight, add --probe for actual api ping
```

`image_gen.py` refuses to dispatch the agent if it is already running inside and prints the native-first instructions instead, so step 1 is enforced rather than merely recommended. If nothing is usable, build with `svg` and say so — a printable sheet today beats a perfect sheet never.

Never generate creature art inline in the conversation and never paste image data into the layout scripts. Art lands on disk as files; the build reads files.

### 4. Build
```bash
python3 $MINIS/build_minis.py \
  <out>/roster.txt --out <out> --title "<campaign or encounter name>"
```

Do not pass `--paper`. A4 is the default and is what to print on. Only override when the user names a size: `a3`, `a2`, `letter`, `legal`. Never assume Letter.

Pose variety is paired: minis 1–2 share an image, 3–4 share the next. The build picks variants up automatically; `# poses=single` on a roster line opts a creature out. See `minis-art-director` before generating any.

Useful flags: `--scale true|token`, `--art-dir DIR`, `--strip-bg` (key out an opaque background on supplied art), `--mirror-back` (un-reversed back view), `--no-labels`, `--explain` (dump the size table and exit). Full geometry rationale in `references/geometry.md`, size numbers in `references/size-scale.md`.

### 5. Verify before handing over
The build writes `manifest.json`. Check it and do not present the sheets until both are clean:
* `geometry_problems` is empty (overlap, margin overflow, fold asymmetry)
* `warnings` is empty, or every warning has been explained to the user

Then render one sheet to PNG and actually look at it:
```bash
python3 -c "import pymupdf; pymupdf.open('<out>/minis.pdf')[0].get_pixmap(dpi=150).save('<out>/page1.png')"
```

Confirm: art sits inside its cut outline, feet meet the base bar, the mirrored half is a vertical flip (not a rotation), labels stay inside their cell.

### 6. Present
Share `minis.pdf` (or the SVGs if no converter was available), then give the assembly line in this order, because people skip it and waste a sheet:
> Print at 100% / Actual Size — check the 50 mm bar with a ruler. Cut along the solid lines (straight cuts only — the sheet guillotines into strips, then each strip chops into minis). Fold each one once on the dashed centre line, so the two figures come back-to-back with the heads at the fold. Slide a binder clip onto the blank strip at the bottom — that's the stand. No glue.

Then the clip count, taken from the manifest: 1" clips for Medium, 3/4" for Small and Tiny, 2" (or two 1") for Large and up. Say the total, because running out mid-session is the failure mode.

If the user asked for `--fold-style base` instead: fold once on the dashed line, then fold both base bars outward on the dotted lines, and glue the halves.

Report: minis, printed figures, sheets, and every creature whose art came from the procedural fallback so the user knows what to upgrade.