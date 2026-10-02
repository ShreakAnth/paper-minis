#!/usr/bin/env python3
"""image_gen.py -- fill <out>/art/ by dispatching a CLI agent that can draw.

Why this exists
----------------
The agent hosting this plugin may have no image-generation model of its own,
so it cannot draw its own creatures. Another CLI agent on the same machine
usually can. The contract needed is small enough to be worth nothing more than
a subprocess and a file copy: "draw this, write it to disk, print the path".
The build script already reads art off disk and never calls a model, so this
slots in without an architecture change.

The tool is therefore a parameter, not a name baked into the module. '--tool
codex|claude|gemini', or '--cmd "anything {prompt}"' for an agent with no
backend entry. 'auto' picks the first one installed that you are not already
running inside.

Codex is the verified route: 'codex' -> "generate an image of ..." ->
'Read SKILL.md (imagegen skill)' -> file saved under
'$CODEX_HOME/generated_images/<run-id>/<exec-id>.<ext>'. Authenticate with
the CLI's normal login flow before dispatching.

If the agent running this script *is* the agent it would dispatch, it stops
and says so: nesting buys a second context, a second auth and a second sandbox
to reach a tool the caller already has. '--allow-nested' overrides.

Four things 'codex exec' needs, and all four are handled here so no shell
wrapper is required:

 * **stdin must be closed.** 'subprocess.run' inherits the parent's stdin by
   default; Codex then waits on it and the call hangs until the timeout,
   which looks exactly like "the model is slow". Every invocation below uses
   'stdin=DEVNULL'.
 * **--skip-git-repo-check.** 'codex exec' refuses to run in a directory
   that is not a trusted git repo. Output folders usually are not, so the
   flag is passed by default ('--no-skip-git-check' to opt out).
 * **The user's agent instructions must not override this image task.** Each
   dispatch gets a single-purpose instruction file for generating and saving
   the requested image; the user's original file is left untouched.
 * **MCP servers must be off.** An image job needs none of them, their tool
   lists cost tens of thousands of tokens per dispatch, and a server that
   cannot hand-shake non-interactively gives the model something to stop on.
   '-c mcp_servers={}' by default; '--keep-mcp' to opt out.

Reasoning effort defaults to 'low', which is verified sufficient for imagegen
and materially faster.

Usage
-----
  python3 image_gen.py --check --probe                       # preflight, one real image
  python3 image_gen.py prompts.json --out ./minis-out
  python3 image_gen.py prompts.json --out ./minis-out --verbose

'prompts.json' is what the minis-art-director skill produces:

  [{"key": "goblin", "prompt": "<style lock> ... goblin ..."}, ...]

Reuse
-----
Generated art is written to a durable library at '~/.dnd-paper-minis/art/<style>/'
and symlinked into the run folder. Anything already in the library -- or in
this run's 'art/' -- is skipped. So a goblin is generated on the first campaign
that needs one and never again, in any output folder. '--style' namespaces the
library because reuse is only coherent within one style lock; '--no-library'
opts out entirely; '--force' regenerates regardless.

Every failed dispatch leaves its full agent transcript at
'<out>/.minis-work/logs/<key>.log'.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

IMAGE_EXTS = (".png", ".webp", ".jpg", ".jpeg")

# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
# The plugin needs one thing from a CLI agent: "draw this, write it to disk,
# tell me where". Any agent that can do that is a usable backend, so the tool
# is a parameter rather than a name baked into the module. Codex is the
# verified default because it ships an 'imagegen' skill; Claude and Gemini are
# wired the same way and work as soon as their host has an image route.
#
# Per backend:
#   bin           default executable
#   home_env      env var for an isolated per-job config dir, or None
#   home_default  where that dir normally lives, used to seed the isolated copy
#   gen_subdir    where the tool writes images inside its home
#   agents_file   the instruction file to neutralise for a job (see _JOB_AGENTS)
#   noshare       entries never symlinked into a job home: anything written
#                 during a run, because sharing those is what makes two
#                 concurrent jobs collide
#   argv          builds the command line
#   self_env      set by the tool in its own subprocesses; if we see it and it
#                 matches the backend, we are already running inside that agent
#   system_skills True if the tool keeps built-ins under skills/.system
BACKENDS: dict[str, dict] = {}


def _codex_argv(cfg, prompt):
    argv = [cfg["tool_bin"]]
    if cfg["effort"]:
        argv += ["-c", f"model_reasoning_effort={cfg['effort']}"]
    if cfg["no_mcp"]:
        # An art dispatch needs no MCP server, and carrying them is actively
        # harmful: every server's tool list is prepended to the context (18-27k
        # tokens in one observed run, before a single pixel), and a server that
        # cannot complete its handshake non-interactively gives the model
        # something to fail on. Belt to _JOB_AGENTS' braces -- that removes the
        # instruction to call them, this removes the servers themselves.
        argv += ["-c", "mcp_servers={}"]
    argv += ["exec"]
    if cfg["skip_git_check"]:
        argv += ["--skip-git-repo-check"]
    return argv + list(cfg["extra_args"]) + [prompt]


def _claude_argv(cfg, prompt):
    argv = [cfg["tool_bin"], "-p"]
    if cfg["no_mcp"]:
        argv += ["--strict-mcp-config"]     # ignore every configured server
    return argv + list(cfg["extra_args"]) + [prompt]


def _gemini_argv(cfg, prompt):
    # No auto-approve flag is baked in here. Headless Gemini may need one to
    # write files ('--extra-arg --yolo'), but that auto-approves *every* tool
    # call, which is the user's call to make and not a default this script
    # should choose for them. --check says so when it finds gemini.
    return [cfg["tool_bin"], "-p"] + list(cfg["extra_args"]) + [prompt]


def _opencode_argv(cfg, prompt):
    return [cfg["tool_bin"], "run"] + list(cfg["extra_args"]) + [prompt]


def _cursor_argv(cfg, prompt):
    # '--force' is not optional: without it headless Cursor will not write
    # files, so the run "succeeds" having produced nothing. '--output-format
    # text' keeps the final response plain so the printed path is greppable.
    return ([cfg["tool_bin"], "-p", "--output-format", "text", "--force"]
            + list(cfg["extra_args"]) + [prompt])


BACKENDS["codex"] = dict(
    bin="codex", home_env="CODEX_HOME", home_default="~/.codex",
    gen_subdir="generated_images", agents_file="AGENTS.md",
    noshare={"generated_images", "sessions", "log", "logs", "history.jsonl",
             "tmp", "cache", "AGENTS.md", "skills"},
    argv=_codex_argv, self_env="CODEX_HOME", system_skills=True,
    login_hint="codex login", auth_file="auth.json",
)

BACKENDS["claude"] = dict(
    bin="claude", home_env="CLAUDE_CONFIG_DIR", home_default="~/.claude",
    gen_subdir="generated_images", agents_file="CLAUDE.md",
    noshare={"generated_images", "projects", "sessions", "logs", "todos",
             "statsig", "shell-snapshots", "tmp", "cache", "CLAUDE.md"},
    argv=_claude_argv, self_env="CLAUDECODE", system_skills=False,
    login_hint="claude login", auth_file="credentials.json",
)

# Gemini deliberately has 'home_env=None'. The env var that relocates its
# config is not something this script has verified, and guessing it is worse
# than leaving isolation off: a wrong home_env would point the harvest at a
# directory Gemini never writes to, so every job would be confined out and
# discarded -- which is precisely the bug 0.8.1 fixed. No isolation means
# printed-path-only harvesting, which is correct rather than merely cautious.
#
# Gemini CLI also has no built-in image generation: that is the 'nanobanana'
# extension ('gemini extensions install'), which writes to ./nanobanana-output/
# unless told otherwise. Without it this backend has no image route at all.
BACKENDS["gemini"] = dict(
    bin="gemini", home_env=None, home_default="~/.gemini",
    gen_subdir="generated_images", agents_file="GEMINI.md", noshare=set(),
    argv=_gemini_argv, self_env="GEMINI_CLI", system_skills=False,
    login_hint="gemini auth login (and 'gemini extensions install "
               "https://github.com/gemini-cli-extensions/nanobanana' for "
               "image generation)",
    auth_file="oauth_creds.json",
)

# Unverified backends. 'home_env=None' says "this script does not know how to
# give this tool an isolated config dir", and that is load-bearing, not a TODO:
# without isolation there is no private output directory to confine a harvest
# to, so these backends accept *only* the path the agent prints and never fall
# back to scanning. A tool that does not print a path fails loudly instead of
# risking one job's image being saved under another creature's name. See
# _harvest's 'allow_scan'.
BACKENDS["opencode"] = dict(
    bin="opencode", home_env=None, home_default="~/.config/opencode",
    gen_subdir="generated_images", agents_file="AGENTS.md", noshare=set(),
    argv=_opencode_argv, self_env="OPENCODE", system_skills=False,
    login_hint="opencode auth login", auth_file="auth.json",
)

BACKENDS["cursor-agent"] = dict(
    bin="cursor-agent", home_env=None, home_default="~/.cursor",
    gen_subdir="generated_images", agents_file="AGENTS.md", noshare=set(),
    argv=_cursor_argv, self_env="CURSOR_AGENT", system_skills=False,
    login_hint="cursor-agent login", auth_file="auth.json",
)

# Tried in this order by '--tool auto', best-supported first.
#
# 'cursor-agent' is the Cursor *CLI*, which is a separate install from the
# Cursor IDE -- having the IDE does not put it on PATH. That distinction
# matters more than it looks: since 2.4 the Cursor agent generates images
# natively, so inside the IDE this script has nothing to offer and should not
# be reached for at all. It is a host, not a backend. See _HOSTS_THAT_DRAW.
TOOL_ORDER = ["codex", "claude", "gemini", "opencode", "cursor-agent"]

# Agents known to have their own image generation. If one of these is reading
# this, it should draw the set itself; dispatching anything is strictly worse.
# Absence from this list means "unknown", not "cannot" -- the instruction in
# the skill is to check your own tools first regardless.
_HOSTS_THAT_DRAW = {
    "cursor-agent": "Cursor 2.4+ generates images natively (Nano Banana Pro). "
                    "Note it saves to the project's assets/ folder by default "
                    "-- write to <out>/art/<key>.png instead.",
    "codex": "Codex ships an 'imagegen' skill that writes a file and prints "
             "its path.",
}


def cursor_ide_present() -> bool:
    """Is the Cursor IDE installed, regardless of the CLI?

    Only a hint -- '~/.cursor' surviving an uninstall would make it a false
    positive -- but a useful one, because a user who has the IDE and not the
    CLI is being told the wrong thing if we just say "cursor-agent not found".
    """
    return (Path.home() / ".cursor").is_dir()


# Written into each job home in place of the user's instruction file so the
# non-interactive image task has clear, task-specific directions. The user's
# original file remains untouched.
_JOB_AGENTS = """\
# Image generation job

This is a single-purpose, non-interactive image-generation dispatch.

Generate the requested image, save it to disk, and print its absolute path as
the last line of output. Nothing else is in scope.

"""

_print_lock = threading.Lock()


def _say(*parts, err=False):
    with _print_lock:
        print(*parts, file=sys.stderr if err else sys.stdout, flush=True)


# Appended to every prompt so the result path is easy to harvest.
TAIL = (
    "\n\nOperational requirements: save the generated image to disk and print "
    "its absolute file path as the very last line of your output, with no "
    "surrounding prose. Do not include any text, watermark, logo or signature "
    "in the image itself."
)

# Appended on top of TAIL unless --full-detail. A roster is routinely 40+
# dispatches, so anything paid per image is paid forty times.
#
# This is not a quality compromise: a mini is printed 22-30 mm tall, where fine
# detail is invisible at best and mud at worst. The style lock already says
# "bold simplified forms readable at thumbnail size" -- this says the same thing
# to the image model, and asks it not to deliberate about it first.
_LITE = (
    " Work in one pass: do not iterate, refine, critique or regenerate, and do "
    "not open the file to inspect it afterwards. Keep the illustration simple "
    "-- flat colour, few shapes, minimal fine detail and texture -- which is "
    "what prints legibly at 25 mm anyway. A modest resolution is correct; do "
    "not upscale."
)


def _tool_home(be: dict) -> Path:
    """The backend's real config dir -- what a job home is seeded from."""
    env = be.get("home_env")
    if env and os.environ.get(env):
        return Path(os.environ[env])
    return Path(be["home_default"]).expanduser()


def running_inside(be: dict) -> bool:
    """Are we already executing inside this backend's own agent?

    Dispatching 'codex exec' from a script that Codex itself is running works,
    but it is a whole second agent -- its own context, its own auth, its own
    sandbox and approval rules -- paid per image to reach a tool the outer
    agent already has. The caller is better off drawing the image directly, so
    say so and stop rather than quietly costing them twice.
    """
    env = be.get("self_env")
    return bool(env and os.environ.get(env))


def _inside_advice(tool: str, be: dict, art: Path, todo) -> str:
    keys = ", ".join(j["key"] for j in todo[:6]) + ("..." if len(todo) > 6 else "")
    others = [t for t in installed_tools() if t != tool]
    alt = (f"If you cannot, dispatch a different installed agent: --tool "
           f"'{'|'.join(others)}'.\n" if others else
           "No other agent is installed, so the alternative is\n"
           "  build_minis.py --art-backend svg for procedural silhouettes.\n")
    return (
        f"\nThis script is already running inside {tool}, so it will not start "
        f"a second {tool} to draw for it.\n\n"
        f"Draw them yourself -- that is the cheapest path and the reason this "
        f"check exists.\nRe-run with --plan first: it links anything the "
        f"library already has into\n{art} and prints only the prompts still "
        f"outstanding, with the exact filename\neach must be saved as. Skip "
        f"that step and you will redraw art you already own\n({keys}).\n\n"
        f"Transparent background, no text or watermark, one creature per file.\n"
        f"Then re-run build_minis.py, which reads art off disk and calls no "
        f"model.\n\n" + alt +
        f"--allow-nested overrides this check if you really want a second "
        f"{tool}.\n"
    )


def installed_tools(explicit_bin: str | None = None) -> list[str]:
    return [t for t in TOOL_ORDER
            if shutil.which(explicit_bin or BACKENDS[t]["bin"])]


def host_agent() -> str | None:
    """Which known agent, if any, is running this script right now."""
    for t in TOOL_ORDER:
        if running_inside(BACKENDS[t]):
            return t
    return None


def _pick_tool(explicit_bin: str | None) -> str:
    """Choose a backend: installed, and not the agent we are already inside.

    Note the order of preference the caller should apply, of which this
    function is only the last step:

      1. If the agent reading this plugin can draw, it should draw. Nothing
         here is needed and nothing should be spawned.
      2. Otherwise dispatch some *other* installed agent that can.

    So 'auto' deliberately skips the agent we are inside. Asked to draw from
    inside Codex it reaches for Claude, Gemini, opencode or cursor-agent before
    considering a second Codex; only if there is no alternative does it fall
    back and let the nesting check explain the cheaper option.
    """
    usable = installed_tools(explicit_bin)
    for t in usable:
        if not running_inside(BACKENDS[t]):
            return t
    return usable[0] if usable else "codex"


def _snapshot(gen_dir: Path) -> set[Path]:
    if not gen_dir.is_dir():
        return set()
    return {p for p in gen_dir.rglob("*") if p.suffix.lower() in IMAGE_EXTS}


_PATH_RE = re.compile(
    r"""(?:file://)?((?:[A-Za-z]:[\\/]|/)[^\s*"'<>()]+\.(?:png|webp|jpe?g))""",
    re.IGNORECASE)


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _harvest(stdout: str, gen_dir: Path, before: set[Path],
             started: float, confine: Path | None = None,
             allow_scan: bool = True) -> Path | None:
    """Prefer the path Codex printed; fall back to the newest new file.

    'confine' is the provenance guard. With a per-job home, the only legitimate
    result lives under that home's 'generated_images'; a path anywhere else
    means we picked up a file this dispatch did not create, which is the bug
    that once put goblin art in 'human-commoner-2.png'.

    The guard has to live *inside* harvesting, not after it. It used to be a
    post-filter: '_harvest' returned the printed path, the caller checked it,
    rejected it, and set 'src = None' -- never reconsidering. That threw away
    real work. Codex, told to "save the image to disk and print its absolute
    path", does both: the built-in tool writes
    '$CODEX_HOME/generated_images/<session>/exec-<id>.png' and Codex *also*
    copies it into the cwd under a friendly name, then prints the copy. The
    printed path is outside the home, so it was rejected -- while the genuine
    file sat unexamined in 'generated_images/' one directory down. Two of four
    jobs in one run rendered correctly and had their art discarded this way.

    Skipping a confined-out path and continuing costs nothing and finds it.

    'allow_scan=False' drops the mtime fallback entirely, for backends this
    script cannot give a private output directory to. Without isolation the
    newest-file heuristic can reach another job's image, and mislabelled art is
    worse than missing art -- it gets copied into the durable library and every
    later roster inherits it. Those backends must print a path or fail.
    """
    for m in reversed(_PATH_RE.findall(stdout or "")):
        p = Path(m)
        if not p.is_file():
            continue
        if confine is not None and not _under(p, confine):
            continue            # <- skip and keep looking, do NOT give up
        return p
    if not allow_scan:
        return None
    fresh = [p for p in _snapshot(gen_dir) - before
             if p.stat().st_mtime >= started - 2]
    if fresh:
        return max(fresh, key=lambda p: p.stat().st_mtime)
    return None


def _build_cmd(cfg, prompt: str) -> list[str]:
    """Build argv for one direct CLI dispatch."""
    if cfg["cmd_template"]:
        # Escape hatch for a tool with no backend entry: a template with
        # {prompt} somewhere in it, e.g.
        #   --cmd 'my-agent run --quiet --prompt {prompt}'
        return [a.replace("{prompt}", prompt) for a in cfg["cmd_template"]]
    return cfg["backend"]["argv"](cfg, prompt)


def _run(cfg, prompt: str, timeout: int, job_home: Path | None = None):
    """One dispatch. stdin is always closed -- see the module docstring."""
    env = os.environ.copy()
    home_env = cfg["backend"].get("home_env")
    if job_home and home_env:
        env[home_env] = str(job_home)
    return subprocess.run(
        _build_cmd(cfg, prompt),
        capture_output=True, text=True, timeout=timeout,
        stdin=subprocess.DEVNULL,       # <- without this, the agent hangs
        cwd=str(cfg["workdir"]),
        env=env,
    )


def _worker_home(base: Path, name: str, real_home: Path, be: dict) -> Path:
    """An isolated config home for ONE DISPATCH.

    Jobs must not share 'generated_images'. The primary harvest reads the path
    Codex prints, which is collision-proof, but the fallback takes the newest
    new file in the tree -- so any sharing lets one job harvest another job's
    image and save it under the wrong creature.

    This used to be per *worker slot*, computed as 'i % jobs' at submit time.
    That was wrong: ThreadPoolExecutor does not pin task i to thread i % jobs,
    so when a thread freed early a later job with the same slot number started
    while the earlier one was still running, and the two shared a home. The
    result was art cross-contamination that then got copied into the durable
    library and persisted across every later run. Keying the home off the job
    itself removes the possibility rather than narrowing it.

    Auth and config are symlinked in, so the tool's own login is still done
    once in the real home and nothing is copied. The instruction file
    ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md' -- whichever this backend reads) is
    the exception: the user's own is deliberately left out and a
    single-purpose one is written instead. See '_JOB_AGENTS'.
    """
    # Sanitised name for readability, hash suffix for correctness: keys that
    # differ only in separators ("a/b" vs "a-b") must not land in one folder,
    # because that is the sharing this whole function exists to prevent.
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name)[:40].strip("-") or "job"
    home = base / f"{safe}-{hashlib.sha1(name.encode()).hexdigest()[:8]}"
    home.mkdir(parents=True, exist_ok=True)
    (home / be["gen_subdir"]).mkdir(exist_ok=True)
    if real_home.is_dir():
        for entry in real_home.iterdir():
            if entry.name in be["noshare"]:
                continue
            link = home / entry.name
            if link.exists() or link.is_symlink():
                continue
            try:
                link.symlink_to(entry)
            except OSError:
                pass    # a missing convenience link is not worth failing over
    # Written last, and unconditionally: the instruction file is excluded from
    # the symlink loop above, so this is the only one the dispatch will see.
    (home / be["agents_file"]).write_text(_JOB_AGENTS)
    if be.get("system_skills"):
        _link_skills(home, real_home)
    return home


def _link_skills(home: Path, real_home: Path) -> None:
    """Expose the built-in skills only, not the user's personal catalogue.

    Every skill's description is loaded into context at startup -- Codex says so
    out loud when the catalogue is big: 'Skill descriptions were shortened to
    fit the skills context budget.' A roster of forty creatures pays that on
    forty dispatches, for skills an image job will never call.

    'imagegen' lives under 'skills/.system/', so linking that one subdirectory
    keeps the route this script depends on and drops the rest. If the layout
    differs (older Codex, or a user who put skills elsewhere), fall back to
    linking the whole directory rather than breaking imagegen to save tokens.
    """
    src = real_home / "skills"
    if not src.is_dir():
        return
    dest = home / "skills"
    if dest.exists() or dest.is_symlink():
        return
    system = src / ".system"
    try:
        if system.is_dir():
            dest.mkdir(exist_ok=True)
            (dest / ".system").symlink_to(system)
        else:
            dest.symlink_to(src)
    except OSError:
        pass


_mcp_fallback_lock = threading.Lock()


def _mcp_override_rejected(proc) -> bool:
    """Did this Codex build refuse '-c mcp_servers={}'?

    '-c' takes a TOML value and an empty inline table is the documented way to
    clear one, but '-c' parsing has shifted between Codex releases and this
    script has to work on whatever the user happens to have installed. Pinning
    a version is not an option; noticing the refusal is cheap.
    """
    if getattr(proc, "returncode", 0) == 0:
        return False
    text = ((getattr(proc, "stderr", "") or "")
            + (getattr(proc, "stdout", "") or "")).lower()
    if "mcp_servers" not in text:
        return False
    return any(s in text for s in ("invalid", "error", "unexpected", "expected",
                                   "failed to parse", "could not parse"))


def _disable_mcp_override(cfg) -> bool:
    """Drop the override for the rest of the run. Returns True if we just did."""
    with _mcp_fallback_lock:
        if not cfg["no_mcp"]:
            return False
        cfg["no_mcp"] = False
        _say("  note: this Codex build rejected '-c mcp_servers={}'; retrying "
             "with MCP servers enabled for the rest of the run. If dispatches "
             "then return exit 0 with no image, suspect an MCP server that "
             "cannot complete its handshake non-interactively.", err=True)
        return True


def _dispatch(cfg, prompt: str, timeout: int, home: Path | None):
    """One dispatch, with a single no-cost retry if the MCP override is refused."""
    proc = _run(cfg, prompt, timeout, job_home=home)
    if cfg["no_mcp"] and _mcp_override_rejected(proc):
        if _disable_mcp_override(cfg):
            proc = _run(cfg, prompt, timeout, job_home=home)
    return proc


def _log_failure(log_dir: Path, key: str, argv, proc, elapsed) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{key}.log"
    rc = getattr(proc, "returncode", "n/a")
    path.write_text(
        f"argv       : {argv}\n"
        f"elapsed    : {elapsed:.1f}s\n"
        f"exit code: {rc}\n"
        f"--- stdout ---\n{getattr(proc, 'stdout', '') or ''}\n"
        f"--- stderr ---\n{getattr(proc, 'stderr', '') or ''}\n"
    )
    return path


def _tail(text: str, n: int = 6) -> list[str]:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return lines[-n:]


def doctor(cfg, args) -> int:
    """Preflight. Fail in two seconds rather than after thirty generations."""
    problems, notes = [], []
    be, tool = cfg["backend"], cfg["tool"]
    real_home = _tool_home(be)
    gen_dir = cfg["gen_dir"]
    binary = shutil.which(cfg["tool_bin"])

    print("dnd-paper-minis art preflight")
    host = host_agent()
    if host:
        # The cheapest image is the one you draw yourself. Say this before any
        # of the dispatch plumbing, because if it applies none of the rest
        # matters.
        print(f"\n  NATIVE FIRST: this is running inside {host}. If {host} can "
              f"generate\n  images itself, do that and write them to "
              f"<out>/art/<key>.png -- do not\n  dispatch anything. Everything "
              f"below is the fallback for hosts that cannot.\n")
    found = installed_tools()
    print(f"  agents installed : {', '.join(found) or 'none found'}"
          + (f" (inside: {host})" if host else ""))
    print(f"  tool             : {tool}")
    print(f"  mode             : {cfg['mode']}")
    print(f"  binary           : {binary or 'NOT FOUND'} ({cfg['tool_bin']})")
    if not binary and not cfg["cmd_template"]:
        problems.append(f"{cfg['tool_bin']} is not on PATH. Install it, then "
                        f"run '{be['login_hint']}'.")

    if running_inside(be):
        problems.append(
            f"already running inside {tool} (${be['self_env']} is set). "
            f"Generate the images directly instead of dispatching a second "
            f"agent, or pick another --tool. --allow-nested overrides this.")

    auth = real_home / be["auth_file"]
    print(f"  auth             : {'present' if auth.is_file() else 'NOT FOUND'} ({auth})")
    if binary and not auth.is_file():
        problems.append(f"{tool} does not look signed in. Run '{be['login_hint']}'.")

    print(f"  images land in   : {cfg['homes_dir']}/<key>/{be['gen_subdir']} "
          f"(per job; your {gen_dir} is left alone)")
    print(f"  workdir          : {cfg['workdir']}")
    print(f"  your {be['agents_file']:<13}: "
          f"{'replaced per job' if (real_home / be['agents_file']).is_file() else 'none found'} "
          f"(art jobs get a single-purpose one)")
    print(f"  MCP servers      : {'disabled for art jobs' if cfg['no_mcp'] else 'ENABLED (--keep-mcp)'}")
    if not be.get("home_env"):
        notes.append(f"{tool} gets no isolated config dir here, so jobs cannot "
                     f"be confined to a private output folder. Harvest accepts "
                     f"only the path {tool} prints -- no newest-file guess. "
                     f"Prefer --jobs 1 with this backend.")
    if tool == "gemini":
        notes.append("Gemini CLI has no built-in image generation -- install "
                     "the nanobanana extension. Headless runs may also need "
                     "--extra-arg --yolo to be allowed to write files; that "
                     "auto-approves every tool call, so it is opt-in.")
    print(f"  argv             : {_build_cmd(cfg, '<prompt>')}")

    if binary and not problems and args.probe:
        print(f"  probe            : generating one throwaway image "
              f"(timeout {args.probe_timeout}s)...", flush=True)
        # The probe runs through the same isolated home as a real dispatch --
        # otherwise it validates a route the build will never take, and a
        # preflight that passes while every real job fails is worse than none.
        probe_home = _worker_home(cfg["homes_dir"], "_probe", real_home, be)
        gen_dir = probe_home / be["gen_subdir"]
        probe_prompt = "generate a plain grey 64x64 test square" + cfg["tail"]
        before, started = _snapshot(gen_dir), time.time()
        argv = _build_cmd(cfg, probe_prompt)
        try:
            proc = _dispatch(cfg, probe_prompt, args.probe_timeout, probe_home)
            elapsed = time.time() - started
            hit = _harvest(proc.stdout + "\n" + proc.stderr, gen_dir, before,
                           started, confine=gen_dir)
            if hit:
                print(f"  probe            : OK -> {hit} ({elapsed:.0f}s)")
            else:
                log = _log_failure(cfg["log_dir"], "_probe", argv, proc, elapsed)
                problems.append(
                    f"probe ran ({elapsed:.0f}s (exit {proc.returncode}) but produced "
                    f"no image. Transcript: {log}")
                for l in _tail(proc.stderr or proc.stdout):
                    problems.append(f"    [{tool}]: {l[:200]}")
        except subprocess.TimeoutExpired:
            problems.append(
                f"probe timed out after {args.probe_timeout}s. If this persists, run "
                f"the argv above by hand -- {tool} may be waiting on an approval "
                f"prompt this script cannot answer.")

    for n in notes:
        print(f"  note: {n}")
    if problems:
        print("\nNOT READY:")
        for p in problems:
            print(f"  {p}")
        print("\nTo build anyway with procedural silhouettes instead of real art:\n"
              "  build_minis.py ROSTER --art-backend svg")
        return 1
    print(f"\nREADY: {tool} is usable for creature art.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("prompts", nargs="?", help="prompts.json from minis-art-director")
    ap.add_argument("--out", help="roster output folder")
    ap.add_argument("--check", action="store_true",
                    help="preflight only: is the image route usable here?")
    ap.add_argument("--probe", action="store_true",
                    help="with --check, actually generate one throwaway image")
    ap.add_argument("--probe-timeout", type=int, default=150)
    ap.add_argument("--tool", default="auto",
                    choices=["auto"] + sorted(BACKENDS),
                    help="which CLI agent draws the images. 'auto' picks the "
                         "first one on PATH that you are not already running "
                         "inside. Codex is the verified route (it ships an "
                         "'imagegen' skill); the others work wherever their host "
                         "has an image tool.")
    ap.add_argument("--tool-bin", "--codex-bin", dest="tool_bin", default=None,
                    help="override the executable for --tool")
    ap.add_argument("--cmd", default=None, metavar="TEMPLATE",
                    help="dispatch an agent with no backend entry, as a shell-"
                         "style template containing {prompt}, e.g. "
                         "--cmd 'my-agent run --quiet {prompt}'. It must write "
                         "an image and print its absolute path.")
    ap.add_argument("--list-tools", action="store_true",
                    help="list which agents are installed, which one 'auto' "
                         "would pick, and whether we are inside one")
    ap.add_argument("--allow-nested", action="store_true",
                    help="dispatch the target agent even when already running "
                         "inside it. OFF by default: that is a second agent "
                         "with its own context and auth, paid per image, to "
                         "reach a tool the outer one already has.")
    ap.add_argument("--effort", default="low",
                    help="reasoning effort where the backend supports it; "
                         "'low' is verified sufficient for image sort. Empty "
                         "string to leave unset.")
    ap.add_argument("--no-skip-git-check", action="store_true",
                    help="do not pass --skip-git-repo-check (it is on by default "
                         "because output folders are rarely git repos)")
    ap.add_argument("--full-detail", action="store_true",
                    help="drop the brevity clause appended to every prompt. By "
                         "default each dispatch is told to work in one pass and "
                         "keep the illustration simple, because a 40-creature "
                         "roster pays for deliberation and fine detail forty "
                         "times over and neither survives printing at 25 mm.")
    ap.add_argument("--keep-mcp", action="store_true",
                    help="leave your MCP servers enabled for art dispatches. "
                         "OFF by default: an image job needs none of them, "
                         "their tool lists cost tens of thousands of tokens per "
                         "dispatch, and one that cannot hand-shake "
                         "non-interactively gives the model something to stop "
                         "on. Pass this only if your imagegen route genuinely "
                         "depends on an MCP server.")
    ap.add_argument("--extra-arg", action="append", default=[], metavar="ARG",
                    help="repeatable, passed through to the agent's command line")
    ap.add_argument("--workdir", default=None,
                    help="cwd for the subprocess (default: the out folder)")
    ap.add_argument("--library", default=None,
                    help="durable art library (default ~/.dnd-paper-minis/art). Generated art is written here AND copied into <out>/art, so the next campaign reuses it instead of regenerating.")
    ap.add_argument("--style", default="default",
                    help="library namespace; keep one per style lock")
    ap.add_argument("--no-library", action="store_true",
                    help="do not read or write the shared library")
    ap.add_argument("--gen-dir", default=None,
                    help="where your real agent writes images, shown by --check. "
                         "Dispatches do not use it: each one harvests from its "
                         "own isolated home under .minis-work/agent-homes/.")
    ap.add_argument("--timeout", type=int, default=300,
                    help="per image; a verified run took 37s at low effort")
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("-j", "--jobs", type=int, default=4,
                    help="images to generate concurrently (default 4). Each "
                         "worker gets an isolated CODEX_HOME so generated-image "
                         "dirs cannot collide. Raise it until you hit rate "
                         "limits; --jobs 1 is the old serial behaviour.")
    ap.add_argument("--stagger", type=float, default=2.0,
                    help="seconds between starting each worker, to avoid a "
                         "thundering herd against the API")
    ap.add_argument("--only", default="",
                    help="comma-separated keys to (re)generate, e.g. "
                         "'goblin,skeleton-3'. Combine with --force to repair "
                         "specific images without touching the rest of the set "
                         "or the library.")
    ap.add_argument("--purge", action="store_true",
                    help="with --only: delete those keys from the run folder "
                         "AND the shared library first. Use when an image is "
                         "wrong, not merely missing -- otherwise the bad file "
                         "in the library keeps winning.")
    ap.add_argument("--limit", type=int, default=0,
                    help="generate at most N images this run, for a quick "
                         "look before committing to the whole set")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verbose", action="store_true",
                    help="echo the argv and Codex's output for every dispatch")
    ap.add_argument("--plan", action="store_true",
                    help="for a host that draws its own images: link anything "
                         "the library already has into <out>/art, then print "
                         "the prompts still outstanding and the exact file "
                         "each one must be saved as. Dispatches nothing. Run "
                         "this before drawing natively, or you will regenerate "
                         "art you already own.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.list_tools:
        host = host_agent()
        found = installed_tools()
        if host:
            print(f"running inside: {host}")
            print(f"  -> if {host} can generate images itself, do that and "
                  f"save to <out>/art/<key>.png. Nothing below is needed.\n")
        for t in TOOL_ORDER:
            be = BACKENDS[t]
            where = shutil.which(be["bin"])
            flags = []
            if t == host:
                flags.append("running inside")
            if not be.get("home_env"):
                flags.append("no isolation; must print its path")
            print(f"  {t:13} {'installed ' if where else 'not found '}"
                  f"({where or be['bin']})"
                  + (f" [{', '.join(flags)}]" if flags else ""))
        if not shutil.which("cursor-agent") and cursor_ide_present():
            # "cursor-agent not found" is a misleading thing to leave a Cursor
            # user with: the IDE is a separate install from the CLI, and the
            # IDE agent can already draw. Nothing needs installing.
            print("\n  Cursor IDE looks installed (the CLI is a separate "
                  "install).\n  Inside Cursor you do not need this script at "
                  "all -- the agent generates\n  images itself. Save them to "
                  "<out>/art/<key>.png, not the default assets/.")
        print(f"\nauto would pick: {_pick_tool(None) if found else 'nothing usable'}")
        if host and host in _HOSTS_THAT_DRAW:
            print(f"...but you are inside {host}: {_HOSTS_THAT_DRAW[host]}")
        return 0

    out = Path(args.out) if args.out else Path.cwd()
    tool = args.tool if args.tool != "auto" else _pick_tool(args.tool_bin)
    be = BACKENDS[tool]

    cfg = {
        "tool": tool,
        "backend": be,
        "mode": "exec",
        "tool_bin": args.tool_bin or be["bin"],
        "cmd_template": shlex.split(args.cmd) if args.cmd else None,
        "effort": args.effort.strip(),
        "skip_git_check": not args.no_skip_git_check,
        "no_mcp": not args.keep_mcp,
        "tail": TAIL if args.full_detail else TAIL + _LITE,
        "extra_args": args.extra_arg,
        "gen_dir": Path(args.gen_dir) if args.gen_dir
                   else _tool_home(be) / be["gen_subdir"],
        "workdir": Path(args.workdir) if args.workdir else out,
        # Scratch lives outside art/. art/ is the folder the user is told to
        # keep and reuse across reprints; it should contain art and nothing else.
        "log_dir": out / ".minis-work" / "logs",
        "homes_dir": out / ".minis-work" / "agent-homes",
    }
    cfg["workdir"].mkdir(parents=True, exist_ok=True)

    if args.check:
        return doctor(cfg, args)
    if not args.prompts:
        ap.error("pass prompts.json, or use --check for the preflight")
    if not args.out:
        print(f"no --out given; using {out}")

    jobs = json.loads(Path(args.prompts).read_text())
    art = out / "art"
    art.mkdir(parents=True, exist_ok=True)

    # The library is why a goblin is generated once ever, not once per campaign.
    lib = None
    if not args.no_library:
        import art_provider
        lib = art_provider.library_dir(args.library, args.style)
        lib.mkdir(parents=True, exist_ok=True)

    def have(key: str):
        """Return an existing file for 'key', from the run folder or library."""
        for d in (art, lib):
            if not d:
                continue
            for e in IMAGE_EXTS + (".svg",):
                f = d / f"{key}{e}"
                if f.is_file():
                    return f
        return None

    only = {k.strip() for k in args.only.split(",") if k.strip()}
    if only:
        unknown = only - {j["key"] for j in jobs}
        if unknown:
            print(f"--only names keys not in {args.prompts}: "
                  f"{', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        jobs = [j for j in jobs if j["key"] in only]

    if args.purge:
        if not only:
            print("--purge requires --only", file=sys.stderr)
            return 2
        for j in jobs:
            for d in (art, lib):
                if not d:
                    continue
                for e in IMAGE_EXTS + (".svg",):
                    f = d / f"{j['key']}{e}"
                    if f.exists() or f.is_symlink():
                        f.unlink()
                        print(f"  purged {f}")

    reused = []
    todo = []
    for j in jobs:
        hit = None if args.force else have(j["key"])
        if hit is None:
            todo.append(j)
            continue
        # Found it. If it only exists in the library, link it into this run.
        local = art / hit.name
        if not local.exists():
            try:
                local.symlink_to(hit)
            except OSError:
                shutil.copy2(hit, local)
        reused.append(j["key"])
    if reused:
        print(f"reusing {len(reused)} from the library: "
              + ", ".join(reused[:8])
              + (f" (+{len(reused)-8} more)" if len(reused) > 8 else ""))
    capped = len(todo)

    if args.limit and len(todo) > args.limit:
        todo = todo[: args.limit]

    args.jobs = max(1, min(args.jobs, len(todo) or 1))

    if not args.plan:
        # All of this describes the dispatch. Under --plan there is no
        # dispatch: the reader is an agent about to draw the images itself,
        # and telling it which binary it would otherwise have shelled out to
        # is noise at best and a suggestion to go do that at worst.
        print(f"tool={tool} mode=exec"
              f" bin={shutil.which(cfg['tool_bin']) or cfg['tool_bin']}"
              f" effort={cfg['effort'] or 'default'}")
        print(f"gen-dir={cfg['homes_dir']}/<key>/{be['gen_subdir']} "
              f"workdir={cfg['workdir']}")
        print(f"per-job home: single-purpose {be['agents_file']}, "
              f"MCP {'off' if cfg['no_mcp'] else 'ON (--keep-mcp)'}")
        print(f"argv={_build_cmd(cfg, '<prompt>')}")
        print(f"{len(jobs)} prompts, {len(todo)} to generate, "
              f"{len(jobs)-capped} already on disk"
              + (f" (this run limited to {len(todo)})" if args.limit and
                 len(todo) < capped else ""))
        if todo:
            print(f"jobs={args.jobs}"
                  + (f" -> roughly {len(todo)/args.jobs*1.6:.0f} min at ~95s each"
                     if args.jobs > 1 else
                     f" (serial) -> roughly {len(todo)*1.6:.0f} min at ~95s each"))

    if args.plan:
        # For an agent that will draw the images itself.
        #
        # Library reuse lives in this script, so a host that skips the script
        # skips the reuse -- and redraws art it already owns. That was a real
        # bug: a native run regenerated creatures that were sitting in the
        # library. --plan runs everything up to the dispatch (library hits are
        # linked into <out>/art above) and then prints exactly what is left,
        # so drawing directly costs no more generations than dispatching would.
        print(f"\n{len(todo)} image(s) to draw. ({len(reused)} already on disk "
              f"and linked into {art} -- do not redraw those.\n")
        for j in todo:
            print(f"--- {art}/{j['key']}.png")
            print(j["prompt"])
            print()
        if not todo:
            print("Nothing to draw. Go straight to build_minis.py.")
        return 0

    if args.dry_run:
        for j in todo:
            print(f"  would dispatch {j['key']}: {j['prompt'][:100]}...")
        return 0

    # The nesting guard sits after --dry-run, so you can still inspect what
    # would run from inside the agent, and before any dispatch, no nobody pays
    # for a second agent before being told there was a cheaper way.
    if todo and not args.allow_nested and running_inside(be):
        print(_inside_advice(tool, be, art, todo), file=sys.stderr)
        return 3

    if not cfg["cmd_template"] and not shutil.which(cfg["tool_bin"]):
        print(f"{cfg['tool_bin']} is not on PATH. Install {tool} and run "
              f"'{be['login_hint']}', or pick another --tool. "
              f"The build will fall back to procedural art.", file=sys.stderr)
        return 2

    homes_base = cfg["homes_dir"]
    done = [0]
    count_lock = threading.Lock()

    def one(job):
        key = job["key"]
        destination = (art / f"{key}.png").resolve()
        prompt = (
            f"{job['prompt']}\n\nSave the generated image exactly to "
            f'"{destination}". Print that absolute path as the last line.'
            + cfg["tail"]
        )
        # One home per dispatch, always -- including --jobs 1. It used to be
        # built only for jobs > 1, because its original job was collision
        # avoidance and a serial run cannot collide. It now also carries the
        # job-scoped instruction file, and a serial run needs that just as
        # much: with no home it reads the user's real one and can talk itself
        # out of generating anything.
        #
        # Backends with no home_env get neither, so they also get no scan
        # fallback and no confinement -- see _harvest's allow_scan.
        #
        # '--cmd' is in that category whatever backend was selected. A custom
        # command has no relationship to the chosen agent's config home, so
        # confining its output to that home rejects every image it produces --
        # the same failure as an unverified home_env, and it made the escape
        # hatch useless. Caught by tests/test_dispatch.py, which drives
        # exactly this path.
        if be.get("home_env") and not cfg["cmd_template"]:
            home = _worker_home(homes_base, key, _tool_home(be), be)
            gen_dir, confine, allow_scan = home / be["gen_subdir"], None, True
            confine = gen_dir
        else:
            home, gen_dir = None, cfg["workdir"]
            confine, allow_scan = None, False

        for attempt in range(args.retries + 1):
            before, started = _snapshot(gen_dir), time.time()
            argv_used = _build_cmd(cfg, prompt)
            if args.verbose:
                _say(f"  {key} -> {argv_used[:-1]} <prompt ({len(prompt)} chars)>")
            try:
                proc = _dispatch(cfg, prompt, args.timeout, home)
            except subprocess.TimeoutExpired:
                if attempt == args.retries:
                    _say(f"  FAIL {key}: timed out after {args.timeout}s. Run the "
                         f"argv above by hand to see what Codex is waiting on.",
                         err=True)
                    return key, False
                continue
            except (OSError, RuntimeError) as exc:
                _say(f"  FAIL {key}: {exc}", err=True)
                return key, False

            elapsed = time.time() - started
            # Provenance is enforced inside _harvest (see its docstring), so a
            # path outside the job home is skipped over rather than promoted
            # and then thrown away along with the real file.
            src = _harvest(proc.stdout + "\n" + proc.stderr, gen_dir,
                           before, started, confine=confine,
                           allow_scan=allow_scan)

            if src:
                ext = src.suffix.lower()
                dest = art / f"{key}{ext}"
                if lib:
                    keep = lib / f"{key}{ext}"
                    shutil.copy2(src, keep)
                    try:
                        if dest.exists() or dest.is_symlink():
                            dest.unlink()
                        dest.symlink_to(keep)
                    except OSError:
                        shutil.copy2(keep, dest)
                else:
                    shutil.copy2(src, dest)
                with count_lock:
                    done[0] += 1
                    n = done[0]
                _say(f"  [{n}/{len(todo)}] ok  {dest.name}  "
                     f"({(dest.stat().st_size//1024)} KB) ({elapsed:.0f}s)")
                return key, True

            if attempt == args.retries:
                log = _log_failure(cfg["log_dir"], key, argv_used, proc, elapsed)
                _say(f"  FAIL {key}: exit {proc.returncode}, no image after "
                     f"{elapsed:.0f}s. Transcript: {log}", err=True)
                for l in _tail(proc.stderr or proc.stdout):
                    _say(f"    [{tool}]: {l[:200]}", err=True)
                return key, False

        return key, False

    ok, failed = 0, []
    t0 = time.time()

    if args.jobs <= 1:
        for j in todo:
            key, good = one(j)
            ok += good
            if not good:
                failed.append(key)
    else:
        with futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            pending = []
            for i, j in enumerate(todo):
                if i < args.jobs and args.stagger:
                    # Ease into the rate limit rather than firing N at once.
                    time.sleep(args.stagger if i else 0)
                pending.append(pool.submit(one, j))
            for fut in futures.as_completed(pending):
                key, good = fut.result()
                ok += good
                if not good:
                    failed.append(key)

    mins = (time.time() - t0) / 60
    print(f"\n{ok} generated, {len(failed)} failed in {mins:.1f} min"
          + (f" across {args.jobs} workers" if args.jobs > 1 else ""))
    if failed:
        print("these have no art yet: " + ", ".join(sorted(failed)))
        print(f"transcripts in {cfg['log_dir']}")
        print("re-running this command retries only the failures "
              "(existing files are skipped)")
    if homes_base.is_dir():
        print(f"per-job homes kept at {homes_base} (delete when done; "
              f"auth/config are symlinks, not copies -- AGENTS.md is not)")
    if lib:
        n = len([p for p in lib.iterdir() if p.suffix.lower() in IMAGE_EXTS])
        print(f"library now holds {n} images at {lib} -- later rosters reuse these")
    print(f"now re-run build_minis.py to pick up {art}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
