# Paper Minis

Turn a creature roster into print-ready paper miniatures.

```text
7 Goblins
3 Wolves
1 Ogre
```

The build creates printable SVG sheets, a PDF, and a JSON manifest. Each mini
prints as two mirrored figures that fold back-to-back. Cut out each rectangle,
fold on the marked line, and attach a binder clip to the blank strip to make a
stand. Print at **Actual Size / 100%** and check the sheet's 50 mm scale bar.

## What is included

- **`paper-minis/`** — roster parser, size and layout engine, renderers, and
  build scripts.
- **`paper-minis/SKILL.md`** — instructions for running and validating builds.
- **`minis-art-director/`** — art style and prompt guidance.
- **`commands/`** — `/minis` and `/minis-doctor` command instructions.
- **`vscode-paper-minis/`** — a VS Code extension development scaffold with
  roster input and optional Gemini prompt-to-roster conversion.

There are two skills in this checkout: `paper-minis` and
`minis-art-director`. Roster lines support creature names, counts, stat hints,
and the documented `key=value` overrides.

## Requirements

- Python 3.10 or newer
- `reportlab` for PDF output
- `pillow` for raster-art processing

Install the Python dependencies:

```powershell
python -m pip install reportlab pillow
```

## Build a roster

Save the roster as `roster.txt`, then run from the repository root:

```powershell
python .\paper-minis\scripts\build_minis.py .\roster.txt --out .\minis-out --title "Tonight's Encounter"
```

The output directory contains `minis.pdf`, one or more `sheet-NN.svg` files,
and `manifest.json`.

By default, the build expects real art files. Put one transparent image per
creature under `<out>\art\`, named from its creature key (for example
`goblin.png`). For a layout smoke test with built-in procedural silhouettes:

```powershell
python .\paper-minis\scripts\build_minis.py .\roster.txt --out .\minis-out --title "Smoke Test" --art-backend svg
```

See [roster-format](paper-minis/references/roster-format.md) for accepted
roster syntax and overrides, [size-scale](paper-minis/references/size-scale.md)
for scale options, and [geometry](paper-minis/references/geometry.md) for
folding and assembly.

## Art workflow

The build reads art from disk; it does not call an image model. See
[minis-art-director](minis-art-director/SKILL.md) for the image requirements,
style lock, and art-generation workflow. Existing art can be supplied with
`--art-dir`; `--art-backend svg` selects procedural artwork.

## VS Code development scaffold

The VS Code extension source is in `vscode-paper-minis/`. To compile it:

```powershell
Set-Location .\vscode-paper-minis
npm install
npm run compile
```

Open that folder in VS Code and launch it in an Extension Development Host
using **Run and Debug**. The Gemini API key is configured through the
`paperMinis.geminiApiKey` setting; it is used only for turning natural-language
requests into roster text. Gemini API access is optional; a roster can be
pasted directly. The root `gemini-extension.json` is draft metadata, not a
separate verified Gemini CLI installation package.
