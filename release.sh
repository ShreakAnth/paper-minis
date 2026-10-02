#!/usr/bin/env bash
# release.sh -- cut a version. Trunk + tags: one 'main', one tag per release.
#
#   ./release.sh 0.7.3          bump, verify, commit, tag (does NOT push)
#   ./release.sh 0.7.3 --push   ...and push main + the tag
#   ./release.sh --check        verify only, touch nothing
#
# Nothing reaches the remote unless you pass --push.

set -eue pipefail
cd "$(dirname "$0")"

PLUGIN=.claude-plugin/plugin.json
VERSION="${1:-}"
PUSH=no
[[ "${2:-}" == "--push" ]] && PUSH=yes

verify() {
  echo "== verify =="
  python3 - <<'PY'
import glob, json, os, py_compile, re, sys
m = json.load(open('.claude-plugin/plugin.json'))
assert re.fullmatch(r'[a-z0-9-]+', m['name']), f"bad name: {m['name']}"
assert re.fullmatch(r'\d+\.\d+\.\d+', m['version']), f"bad version: {m['version']}"
for d in os.listdir('skills'):
    p = f'skills/{d}/SKILL.md'
    assert os.path.isfile(p), f"missing {p}"
n = 0
for f in glob.glob('skills/*/scripts/*.py'):
    py_compile.compile(f, doraise=True); n += 1
print(f"  plugin.json ok  v{m['version']}")
print(f"  skills: {', '.join(sorted(os.listdir('skills')))}")
print(f"  commands: {', '.join(sorted(os.listdir('commands')))}")
print(f"  {n} scripts compile")
mk = json.load(open('.claude-plugin/marketplace.json'))
assert any(p['name'] == m['name'] for p in mk['plugins']), "marketplace.json missing this plugin"
print(f"  marketplace.json lists {m['name']}")

# One manifest per host, and they must agree. A stale version in a manifest
# nobody on this machine reads is exactly the kind of drift that ships.
for path, check in (
    ('.cursor-plugin/marketplace.json',
     lambda d: any(p['name'] == m['name'] for p in d['plugins'])),
    ('gemini-extension.json',
     lambda d: d['name'] == m['name'] and d['version'] == m['version']),
):
    assert os.path.isfile(path), f"missing {path}"
    d = json.load(open(path))
    assert check(d), f"{path} disagrees with plugin.json"
    print(f"  {path} ok")
PY

  echo "== dispatch test (fake agent, no network, no real CLI) =="
  python3 tests/test_dispatch.py | tail -1

  echo "== keying test (background goes, highlights stay) =="
  python3 tests/test_keying.py | tail -1

  echo "== smoke build (procedural art, no network, no agent) =="
  tmp=$(mktemp -d)
  python3 skills/paper-minis/scripts/build_minis.py examples/phandelver.roster.txt       --out "$tmp" --art-backend svg --title "release check" --no-pdf | tail -1
  python3 - "$tmp" <<'PY'
import json, sys
m = json.load(open(f"{sys.argv[1]}/manifest.json"))
assert not m['geometry_problems'], m['geometry_problems']
assert m['totals']['minis'] == 113, m['totals']
print(f"  {m['totals']['minis']} minis, {m['totals']['sheets']} sheets, geometry clean")
PY
  rm -rf "$tmp"

  # Real people must never be committed. .gitignore covers it; this catches a
  # -f override or a stray paste into a tracked file.
  echo "== privacy check =="
  if git ls-files 2>/dev/null | grep -qE '(^|/)cast\.json$|(^|/)art/'; then
    echo "  REFUSING: a cast file or art/ folder is tracked" >&2; exit 1
  fi
  echo "  no cast files or art/ tracked"
}

if [[ "$VERSION" == "--check" ]] && { verify; echo "OK (nothing changed)"; exit 0; }

if [[ -z "$VERSION" ]]; then
  echo "usage: ./release.sh X.Y.Z [--push] | ./release.sh --check" >&2; exit 2
fi
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] ; then echo "not semver: $VERSION" >&2; exit 2; }

git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo -- see README 'Sharing'" >&2; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo "working tree dirty: commit or stash first" >&2; exit 2; }
git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null && { echo "tag v$VERSION exists" >&2; exit 2; }

grep -q "^## $VERSION" CHANGELOG.md || {
  echo "CHANGELOG.md has no '## $VERSION' section -- write it first" >&2; exit 2;
}

python3 - "$VERSION" <<'PY'
import json, sys
from pathlib import Path
# Every manifest that carries a version gets bumped here. plugin.json is still
# the source of truth; the others must not be left to drift, and verify()
# refuses the release if they have.
for path in ('.claude-plugin/plugin.json', 'gemini-extension.json'):
    p = Path(path)
    if not p.is_file():
        continue
    m = json.loads(p.read_text())
    m['version'] = sys.argv[1]
    p.write_text(json.dumps(m, indent=2) + "
")
    print(f"bumped {path} -> {sys.argv[1]}")
PY

verify

git add -A
git commit -m "Release $VERSION"
git tag -a "v$VERSION" -m "$(sed -e "/^## $VERSION\$/ , /^## /p" CHANGELOG.md | sed '1d;$d')"
echo "committed and tagged v$VERSION"

if [[ "$PUSH" == "yes" ]]; then
  git push origin main
  git push origin "v$VERSION"
  echo "pushed main and v$VERSION"
else
  echo
  echo "Not pushed. When you're ready:"
  echo "  git push origin main && git push origin v$VERSION"
fi
