**Description** Check that paper-minis can generate art and render PDFs on this machine

**Allowed tools** Bash

Run the paper-minis preflight and report plainly what is and is not ready.

```bash
MINIS="$(find "${CLAUDE_PLUGIN_ROOT:-/nonexistent}" \
  -/.agents -/.codex -/.cursor -/.gemini -/.claude .agents .cursor \
  -maxdepth 10 -type d -path "**/paper-minis/scripts" -print 2>/dev/null | head -n 1)"
python3 $MINIS/image_gen.py --list-tools
python3 $MINIS/image_gen.py --check $ARGUMENTS

````

`--list-tools` is the cheap one: which agents are installed, which the dispatcher would pick, and whether we are already inside one that can draw. Pass `--probe` to `--check` to actually generate one throwaway image end-to-end (\~40s) rather than only checking that a binary and login exist.

If you can generate images, none of this matters — say so plainly and report art as ready, because the workflow writes files directly in that case.

Then check the render chain:

``` bash
python3 <<'PY'
import importlib
for m, why in (("reportlab", "PDF output (primary, pure Python)"),
               ("PIL", "measuring and trimming supplied raster art")):
    try:
        importlib.import_module(m); print(f"  {m:10s} ok       - {why}")
    except ImportError:
        print(f"  {m:10s} MISSING  - {why}")
PY

```

Also report how much art is already banked, so a wait estimate is honest:

``` bash
ls -1 ~/.dnd-paper-minis/art/*/* 2>/dev/null | wc -l

```

Report as three lines: art (can anything draw here, and by which route), render (can it produce a PDF, or SVG only), verdict.

If `reportlab` is missing the fix is `pip install reportlab` — pure Python, no compiler, no native library. Do not suggest `brew install cairo`: PDFs are drawn natively from the page model and `cairosvg` is only a fallback. With neither installed the sheets are still printable as SVG from a browser at 100%.

 

