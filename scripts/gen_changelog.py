#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2026 Mayank Pandey - LL Agent. See LICENSE.md.
"""
LL Agent CHANGELOG.md Generator
======================================================================
Usage: python scripts/gen_changelog.py

Renders version.json's `mcp.changelog[]` as a Keep a Changelog formatted
CHANGELOG.md at the repository root — the README's Updates button links to it.

version.json stays the single source of release history — this file is a
rendering of it, never an input. set_version.py calls this as its last step so
the two cannot drift.

Highlight -> section mapping reuses split_highlight() from set_version, so the
"Fixed: …" / "Added: …" / "Improved: …" / "Changed: …" prefix convention has
exactly one implementation. Highlights with no prefix (every historical entry)
land in a single "### Changed" section. Nothing is classified by guessing at
what a highlight means.

Dates: version.json stores "October 2026" — month and year, no day. Keep a
Changelog wants YYYY-MM-DD, so the day comes from the release's git tag
(`git log -1 --format=%cs v<version>`), falling back to the first of the stated
month when no tag exists. Every entry prints which source was used; a date that
resolves to neither is a hard error rather than an invented day.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from set_version import _CATEGORY_ORDER, split_highlight  # noqa: E402

# Keep a Changelog has no "Improved" section, so Improved folds into Changed.
# An unprefixed highlight is the historical shape and also reads as Changed.
_SECTION = {
    "Added": "Added",
    "Fixed": "Fixed",
    "Improved": "Changed",
    "Changed": "Changed",
    "Removed": "Removed",
    None: "Changed",
}

# set_version's order, collapsed through the mapping above, so the two scripts
# group a release's highlights in the same sequence.
_SECTION_ORDER = list(dict.fromkeys(_SECTION[c] for c in _CATEGORY_ORDER))

_HEADER = """# Changelog

All notable changes to LL Agent are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Generated from `version.json` by `scripts/gen_changelog.py` — edit that, not this.
"""


def tag_date(version, root=_ROOT):
    """YYYY-MM-DD the tag v<version> was committed, or None if there is no tag."""
    try:
        done = subprocess.run(
            ["git", "log", "-1", "--format=%cs", f"v{version}"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def month_start(month_year):
    """'July 2026' -> '2026-07-01'. None if it is not a '<Month> <Year>' string."""
    try:
        return datetime.strptime(month_year.strip(), "%B %Y").date().isoformat()
    except (AttributeError, ValueError):
        return None


def resolve_date(version, month_year, root=_ROOT):
    """
    (iso_date, source) for a release. Raises ValueError if neither the tag nor
    the stated month yields a date — a missing day is never filled in silently.
    """
    dated = tag_date(version, root)
    if dated:
        return dated, "git tag"
    dated = month_start(month_year)
    if dated:
        return dated, "month fallback — no tag"
    raise ValueError(
        f"v{version}: no git tag and date {month_year!r} is not '<Month> <Year>' — "
        "cannot resolve a YYYY-MM-DD without inventing a day"
    )


def build_changelog(entries, root=_ROOT, log=print):
    """Render changelog entries as Keep a Changelog markdown, newest release first."""
    dated = []
    for entry in entries:
        version = entry["version"]
        iso, source = resolve_date(version, entry.get("date"), root)
        log(f"v{version:<8} {iso}  ({source})")
        dated.append((iso, version, entry.get("highlights", [])))

    # Sorted rather than trusting file order: set_version prepends, but one
    # appended entry would otherwise silently publish out of order.
    dated.sort(key=lambda row: row[0], reverse=True)

    blocks = [_HEADER]
    for iso, version, highlights in dated:
        grouped = {}
        for category, text in (split_highlight(h) for h in highlights):
            grouped.setdefault(_SECTION[category], []).append(text)

        release = [f"## [{version}] - {iso}"]
        for section in _SECTION_ORDER:
            if section in grouped:
                bullets = "\n".join(f"- {text}" for text in grouped[section])
                release.append(f"### {section}\n\n{bullets}")
        blocks.append("\n\n".join(release))

    return "\n\n".join(blocks).rstrip("\n") + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    version_json_path = _ROOT / "version.json"
    data = json.loads(version_json_path.read_text(encoding="utf-8"))
    entries = data["mcp"].get("changelog", [])
    if not entries:
        print(" ⚠️ version.json has no mcp.changelog entries — nothing to generate")
        return

    print(f"\n📜 Rendering {len(entries)} release(s) from version.json\n")
    try:
        text = build_changelog(entries)
    except ValueError as e:
        print(f" ❌ {e}", file=sys.stderr)
        print("    CHANGELOG.md was not written.", file=sys.stderr)
        sys.exit(1)

    (_ROOT / "CHANGELOG.md").write_text(text, encoding="utf-8")
    print(f"\n ✅ Generated CHANGELOG.md -> {len(entries)} releases (Keep a Changelog)")


if __name__ == "__main__":
    main()
