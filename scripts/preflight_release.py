#!/usr/bin/env python3
"""
LocalLens Release Preflight
===========================
Usage: python scripts/preflight_release.py <version>

Gates a release on the mistakes this project has actually made. Exits 0 when
every check passes, 1 otherwise. Prints one line per check, so a failure says
which invariant broke rather than "preflight failed".

Run it AFTER scripts/set_version.py and BEFORE `git tag`.

Checks
------
1. No junk in the working tree (build output, venvs, user licence data, .DS_Store)
2. Version agreement — pyproject.toml == updater.MCP_VERSION == changelog[0]
3. version.json `mcp.latest` still holds the PREVIOUS version  ← inverted on purpose
4. Release notes exist, fully substituted, and free of the dead domain
5. Test suite green
6. Tag v<version> does not already exist (locally or on the remote)

Why check 3 is inverted
-----------------------
`mcp.latest` is what every installed client polls. Publishing it in the release
commit announces a version whose assets do not exist yet: for the length of the
build (plus up to 24h of client-side manifest cache) `downloads` still holds the
PREVIOUS release's url+sha. That pair is self-consistent, so the checksum
verifies and the tray silently reinstalls the old build. CI's
update-version-manifest job owns this field and sets it together with the
download URLs. A bumped mcp.latest in a release commit is a regression, so this
script fails on it.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEAD_DOMAIN = "locallens.app"

# Paths that must never reach a commit. .gitignore covers today's known cases;
# this is the backstop for a new one, and for an `git add -f` slip.
JUNK_PATTERNS = [
    re.compile(p) for p in (
        r"(^|/)venv/", r"(^|/)\.venv/", r"(^|/)dist/", r"(^|/)build/",
        r"(^|/)\.eggs/", r"\.egg-info/", r"(^|/)__pycache__/",
        r"\.DS_Store$", r"\.dmg$", r"\.pyc$",
        r"(^|/)test_env.*\.py$",
        r"(^|/)for dev/", r"(^|/)for LLM's/", r"(^|/)\.-\.-/",
        # User runtime data — a leaked licence or API token is not recoverable
        # by deleting it later; the value is in the history for good.
        r"mcp_license\.json$", r"local_api_token\.txt$", r"port\.txt$",
        r"mcp_onboarded\.json$", r"^\.env$", r"(^|/)\.env\.",
    )
]

_results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    _results.append((ok, name, detail))
    return ok


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def read_pyproject_version() -> str | None:
    match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def read_mcp_version() -> str | None:
    match = re.search(
        r'^MCP_VERSION\s*=\s*"([^"]+)"',
        (ROOT / "src" / "mcp_server" / "updater.py").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def check_working_tree() -> None:
    porcelain = git("status", "--porcelain", "--untracked-files=all")
    lines = [line for line in porcelain.splitlines() if line.strip()]

    junk = [
        line for line in lines
        if any(pattern.search(line[3:]) for pattern in JUNK_PATTERNS)
    ]
    check(
        not junk,
        "working tree carries no junk",
        "remove or ignore:\n      " + "\n      ".join(junk) if junk else "",
    )

    # Not a failure — untracked files are how new work arrives. But a release is
    # the wrong moment to discover one by accident, so they are surfaced.
    untracked = [line[3:] for line in lines if line.startswith("??")]
    if untracked:
        print(f"  ℹ️  {len(untracked)} untracked file(s) — confirm each belongs in this release:")
        for path in untracked:
            print(f"        {path}")


def check_versions(version: str) -> None:
    pyproject = read_pyproject_version()
    mcp = read_mcp_version()
    data = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    changelog = data["mcp"].get("changelog", [])
    newest = changelog[0].get("version") if changelog else None
    latest = data["mcp"].get("latest")

    check(
        pyproject == version == mcp == newest,
        f"version is {version} everywhere",
        f"pyproject={pyproject} updater.MCP_VERSION={mcp} changelog[0]={newest}",
    )
    check(
        latest != version,
        f"version.json mcp.latest ({latest}) is NOT yet {version}",
        "CI's update-version-manifest job owns mcp.latest and publishes it with "
        "the download URLs. Bumping it here announces a build that does not exist "
        "yet, and clients reinstall the previous release.",
    )
    check(
        bool(changelog and changelog[0].get("highlights")),
        "changelog entry has highlights",
        "the desktop What's New panel and the assistant both read this list",
    )


def check_release_notes(version: str) -> None:
    notes = ROOT / "release_notes" / f"release_notes_v{version}.md"
    if not check(notes.exists(), f"release_notes_v{version}.md exists",
                 "run scripts/set_version.py first"):
        return

    body = notes.read_text(encoding="utf-8")
    leftovers = re.findall(r"\{[A-Z_]+\}", body)
    check(not leftovers, "no unreplaced template placeholders",
          f"found {sorted(set(leftovers))}")

    # Links, not mentions. Release notes may legitimately name the dead domain to
    # tell users it is no longer ours; what must never ship is a clickable one.
    dead_links = re.findall(rf"https?://{re.escape(DEAD_DOMAIN)}\S*", body)
    check(not dead_links, f"no links to {DEAD_DOMAIN}",
          f"that domain lapsed and now serves Whistle Enterprise: {sorted(set(dead_links))}")
    check(f"v{version}" in body, f"notes reference v{version}")


def check_tests() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    summary = (proc.stdout.strip().splitlines() or ["no output"])[-1]
    check(proc.returncode == 0, "test suite green", summary)


def check_tag_free(version: str) -> None:
    tag = f"v{version}"
    local = git("tag", "--list", tag)
    remote = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}")
    check(
        not local and not remote,
        f"tag {tag} is unused",
        f"local={local or '-'} remote={'yes' if remote else '-'}",
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    version = sys.argv[1].lstrip("v")
    if not re.match(r"^\d+\.\d+\.\d+", version):
        print(f"Error: expected semver, got {sys.argv[1]!r}", file=sys.stderr)
        return 2

    print(f"\n🔍 Release preflight for v{version}\n")

    check_working_tree()
    check_versions(version)
    check_release_notes(version)
    check_tests()
    check_tag_free(version)

    print()
    failed = 0
    for ok, name, detail in _results:
        print(f"  {'✅' if ok else '❌'} {name}")
        if detail and not ok:
            print(f"      {detail}")
        failed += not ok

    if failed:
        print(f"\n🛑 {failed} check(s) failed — do not tag.\n")
        return 1

    print(f"\n🎉 Clear to release v{version}.")
    print(f"   git tag v{version} && git push origin main v{version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
