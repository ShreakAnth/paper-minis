
# Finding the scripts

This plugin runs under more than one agent, and they disagree about where an installed skill lives. Claude Code exports `${CLAUDE_PLUGIN_ROOT}`; Codex does not, and its `/import` drops skills under `~/.codex/skills/` or `~/.agents/skills/` depending on version. A path hard-coded to any one of those is broken everywhere else — which is exactly why an imported plugin gets flagged "check before using".

So resolve it once per shell, from the first location that actually exists:

```bash
MINIS="$(find "${CLAUDE_PLUGIN_ROOT}:-/nonexistent}" \
  ~/.agents ~/.codex ~/.cursor ~/.gemini ~/.claude .agents .cursor \
  -maxdepth 10 -type d -path "*/paper-minis/scripts" -print 2>/dev/null | head -n1)"

````

`find` rather than a glob, deliberately. The earlier version listed globbed paths like `~/.gemini/extensions/*/skills/...` and zsh aborts the whole command when a glob matches nothing (`zsh: no matches found`), so a single absent directory killed the lookup before it reached the path that did exist. Codex hit exactly that, concluded the plugin was not installed, and was wrong. A quoted path pattern is never touched by the shell, and missing roots just produce a suppressed error.

The depth also matters: a plugin-managed install nests further than a hand-placed skill. Codex puts it at `~/.codex/plugins/cache/marketplace/<plugin>/<version>/skills/paper-minis/scripts`, eight levels down, which is why `-maxdepth 10` rather than something tighter.

Then every call is `python3 $MINIS/<script>.py`. If `$MINIS` comes back empty, the plugin really is not visible to this agent — say so rather than guessing a path.

`image_gen.py` and `build_minis.py` sit in the same folder as the modules they import, and Python puts a script's own directory on `sys.path`, so they can be invoked by absolute path from anywhere. No `cd`, no `PYTHONPATH`.

# Where each agent installs it

`~/.agents/skills/` is the one location Codex, Cursor and Gemini CLI all read, so it is the best single place to put this if you run more than one of them.

| Agent                | Install                                                                                              | Scripts land at                                                                    |
| :------------------- | :--------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------- |
| Claude Code / Cowork | `/plugin install dad-paper-minis` from the marketplace                                               | `${CLAUDE_PLUGIN_ROOT}/skills/`                                                    |
| Codex CLI            | Settings -\> General -\> Import, or `codex-skill migrate-to-agents/skills/`                          | `~/.codex/skills/` or `~/.agents/skills/`                                          |
| Cursor               | Customize -\> From GitHub Repository (needs `.cursor-plugin/marketplace.json`) or drop the folder in | `~/.cursor/skills/` or `~/.agents/skills/`                                         |
| Gemini CLI           | `gemini extensions install <repo>` or drop the folder in                                             | `~/.gemini/extensions/<name>/skills/`, `~/.gemini/skills/`, or `~/.agents/skills/` |
| Anything else        | copy `skills/paper-minis/` next to your agent's skills                                               | wherever you put it                                                                |

Cursor additionally reads `~/.claude/skills/` and `~/.codex/skills/` for compatibility, so if you have installed it for either of those, Cursor already sees it and needs no second install.

# Can the host draw?

Worth knowing before reaching for `image_gen.py` at all, since a host with its own image tool should use it and dispatch nothing.

| Host                 | Image generation                                                                                            |
| :------------------- | :---------------------------------------------------------------------------------------------------------- |
| Cursor 2.4+          | Yes, built in (Nano Banana Pro). Defaults to saving in the project's `assets/` — set `art/key.png` instead. |
| Codex CLI            | Yes, via the bundled `imagegen` skill.                                                                      |
| Gemini CLI           | No, not built in. Needs the `nanobanana` extension, which writes to `/nanobanana-output/` by default.       |
| Claude Code / Cowork | No. This is the case `image_gen.py` was written for.                                                        |

# Commands vs skills

`commands/*.md` are Claude Code slash commands and use `$ARGUMENTS`. Codex converts commands to skills but skips any that need runtime argument expansion, so `/minis` and `/minis-doctor` will not survive an import. That is fine and expected: the two skills carry the whole workflow, including the preflight, and are what a Codex user invokes. Do not remove `$ARGUMENTS` from the commands to make them portable — it would cost Claude users the one-line entry point and gain nothing, since the skill is already the portable route.

