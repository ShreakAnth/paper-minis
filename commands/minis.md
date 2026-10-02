| Field             | Details                                                 |
| :---------------- | :------------------------------------------------------ |
| **Description**   | Build printable paper miniatures from a creature roster |
| **Allowed tools** | Bash, Read, Write, Edit, Glob                           |

Build print-ready inverted-T paper miniatures for: `$ARGUMENTS`

Follow the `paper-minis` skill.

### 0\. Locate the scripts (the install path differs per host):

``` bash
MINIS=$(find "${CLAUDE_PLUGIN_ROOT:-/nonexistent}" \
  ~/.agents ~/.codex ~/.cursor ~/.gemini ~/.claude agents.cursor \
  -maxdepth 10 -type d -path "*/paper-minis/scripts" -print 2>/dev/null | head

```

### 1\. Preflight — but check yourself first. If you can generate images, do that and skip the dispatcher entirely (step 3 says how). Only if you cannot:

``` bash
python3 $MINIS/image_gen.py --check

```

If this exits non-zero, report exactly what is missing (no agent on PATH, or not signed in) and stop. Offer `--art-backend svg` only if the user asks for a silhouette proof.

### 2\. Roster. If `$ARGUMENTS` is a file path, use it. Otherwise write the list verbatim to `./minis-out/roster.txt`, one entry per line. Then check name resolution and ask the user about any `unresolved: true` entry:

``` bash
python3 $MINIS/roster.py ./minis-out/roster.txt

```

### 3\. Art. Follow the `minis-art-director` skill for the style lock, the prompts and the pose-variant rule — that skill is authoritative on all three, including when to ask the user about variants. Do not apply a threshold from memory. Write the result to `./minis-out/prompts.json`. Then run the plan step, whether or not you can draw. It links art the library already has and tells you what is genuinely missing:

``` bash
python3 $MINIS/image_gen.py ./minis-out/prompts.json --out ./minis-out --plan

```

If you have an image tool, generate exactly what it lists and save each to the filename it names. No dispatch, no second agent. Otherwise drop `--plan` and let it dispatch:

``` bash
python3 $MINIS/image_gen.py \
  ./minis-out/prompts.json --out ./minis-out

```

### 4\. Build.

``` bash
python3 $MINIS/build_minis.py \
  ./minis-out/roster.txt --out ./minis-out --title "$ARGUMENTS"

```

Exit 3 means a creature still has no real art — go back to step 3 for the creatures it names. Exit 1 means a geometry problem; report it, do not ship.

Then read `manifest.json` $\\rightarrow$ `poses`. Any creature with a non-empty `missing_poses` is printing duplicate figures where the layout expected variety: pairs share a pose, so 4 goblins want `goblin` and `goblin-2`. Either generate what it names and rebuild, or tell the user those minis will be identical. Do not leave it silent.

### 5\. Verify, then hand over. Check `manifest.json` for empty `geometry_problems` and empty `art.procedural_fallbacks`, render one sheet to PNG and actually look at it, then report minis/printed figures/sheets and give the print-and-fold instructions.
