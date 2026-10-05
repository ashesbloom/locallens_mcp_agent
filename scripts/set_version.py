#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2026 Mayank Pandey - LL Agent. See LICENSE.md.
"""
LocalLens Version Bumper & Release Preparation Tool (Python Edition)
======================================================================
Usage: python scripts/set_version.py <version> ["Highlight 1"] ["Highlight 2"] ...

Example:
  python scripts/set_version.py 1.0.25 "Fixed Windows process management" "Organized root hierarchy"

Actions performed:
  1. Updates version in pyproject.toml
  2. Updates MCP_VERSION in src/mcp_server/updater.py
  3. Prepends to mcp.changelog in version.json (Application GUI Release Log)
  4. Generates release_notes/release_notes_v<VERSION>.md (GitHub Release Page Release Notes)
  0. FIRST, before anything else: rewrites LICENSE.md and NOTICE.md so this
     release is licensed as exactly this version with a Change Date four years
     from today (see bump_license below). Aborts, having written nothing, if
     either file does not match the expected shape.

Deliberately NOT updated: mcp.latest in version.json. That field is what every
installed client polls, so publishing it before the release assets exist leaves
clients announcing an update they cannot download. CI sets it in the same commit
as the download URLs + checksums — see the update-version-manifest job in
.github/workflows/release.yml.
"""

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

# Highlights may be written "Fixed: …", "Added: …", "Improved: …", "Changed: …".
# The prefix drives the grouped "What Changed" section on the GitHub release page
# and is stripped everywhere else — version.json feeds the desktop UI and the
# assistant, where a bare sentence reads better than a category label.
_CATEGORY_ORDER = ["Added", "Fixed", "Improved", "Changed", "Removed"]
_CATEGORY_HEADING = {
    "Added": "### Added",
    "Fixed": "### Fixed",
    "Improved": "### Improved",
    "Changed": "### Changed",
    "Removed": "### Removed",
}
_PREFIX_RE = re.compile(r"^(Added|Fixed|Improved|Changed|Removed)\s*:\s*", re.IGNORECASE)


def split_highlight(text):
    """'Fixed: thing' -> ('Fixed', 'thing').  'thing' -> (None, 'thing')."""
    match = _PREFIX_RE.match(text)
    if not match:
        return None, text
    return match.group(1).capitalize(), text[match.end():].strip()


def build_release_sections(version, highlights):
    """
    The '{RELEASE_SECTIONS}' block: a flat Highlights list always, plus a grouped
    What Changed section when at least one highlight carries a category prefix.
    """
    pairs = [split_highlight(h) for h in highlights]

    bullets = "\n".join(f"- {text}" for _, text in pairs)
    sections = f"## ✨ Highlights\n\n{bullets}\n"

    grouped = {}
    for category, text in pairs:
        if category:
            grouped.setdefault(category, []).append(text)

    if grouped:
        blocks = []
        for category in _CATEGORY_ORDER:
            if category in grouped:
                items = "\n".join(f"- {text}" for text in grouped[category])
                blocks.append(f"{_CATEGORY_HEADING[category]}\n\n{items}")
        sections += "\n---\n\n## 🔧 What Changed\n\n" + "\n\n".join(blocks) + "\n"

    return sections + "\n---"


# ---------------------------------------------------------------------------
#  Licence Change Date — every release gets its own four years
# ---------------------------------------------------------------------------
# BSL 1.1 converts a version to Apache 2.0 on its Change Date or the fourth
# anniversary of its release, whichever comes FIRST. v1.0.1–v1.0.32 shipped with
# a Change Date of 2026-07-18 — someone typed that day's date, reading the field
# as "effective from" — so each converted within weeks of release, irrevocably.
# A fixed far-off date (2030-08-08) stopped the bleeding but gives each later
# release less than four years. So every release writes its own: today + 4 years.
# Each version is governed by the LICENSE.md it shipped with, so this never
# touches an earlier release.

_LICENSED_WORK_RE = re.compile(r"^(Licensed Work:\s+)(?:LocalLens MCP Agent|LL Agent) v\S+(?: and later)?[ \t]*$", re.M)
_CHANGE_DATE_RE = re.compile(r"^(Change Date:\s+)\d{4}-\d{2}-\d{2}[ \t]*$", re.M)
_NOTICE_DATE_RE = re.compile(r"^On \d{4}-\d{2}-\d{2}(, this version automatically becomes Apache 2\.0)", re.M)


def four_years_after(day: date) -> date:
    """Same calendar day four years on. 29 Feb lands on 28 Feb if that year has none."""
    try:
        return day.replace(year=day.year + 4)
    except ValueError:
        return day.replace(year=day.year + 4, day=28)


def bump_license(license_text: str, notice_text: str, version: str, today: date) -> tuple[str, str, str]:
    """
    Return (license_text, notice_text, change_date) rewritten for this release.

    Raises ValueError unless every line matches exactly once. A silent miss here
    would ship a release under the previous Change Date, which is the one mistake
    in this project that cannot be undone after the fact.
    """
    change_date = four_years_after(today).isoformat()
    subs = [
        ("LICENSE.md 'Licensed Work:'", _LICENSED_WORK_RE, rf"\g<1>LL Agent v{version}", "license"),
        ("LICENSE.md 'Change Date:'", _CHANGE_DATE_RE, rf"\g<1>{change_date}", "license"),
        ("NOTICE.md 'On <date>, this version…'", _NOTICE_DATE_RE, rf"On {change_date}\g<1>", "notice"),
    ]
    texts = {"license": license_text, "notice": notice_text}
    for label, pattern, replacement, key in subs:
        texts[key], count = pattern.subn(replacement, texts[key])
        if count != 1:
            raise ValueError(f"{label} line matched {count} times, expected exactly 1")
    return texts["license"], texts["notice"], change_date


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    raw_version = args[0].strip()
    version = raw_version[1:] if raw_version.startswith("v") else raw_version

    if not re.match(r"^\d+\.\d+\.\d+.*$", version):
        print(f"Error: Invalid version format \"{raw_version}\". Expected semver (e.g. 1.0.25)", file=sys.stderr)
        sys.exit(1)

    highlights = args[1:]
    if not highlights:
        highlights = [f"LL Agent v{version} release."]

    root_dir = Path(__file__).resolve().parent.parent
    month_year = datetime.now().strftime("%B %Y")

    print(f"\n🚀 Preparing Release v{version} ({month_year})\n")

    # 0. Licence first: if it cannot be rewritten, stop before touching anything.
    license_path, notice_path = root_dir / "LICENSE.md", root_dir / "NOTICE.md"
    try:
        new_license, new_notice, change_date = bump_license(
            license_path.read_text(encoding="utf-8"),
            notice_path.read_text(encoding="utf-8"),
            version,
            date.today(),
        )
    except (OSError, ValueError) as e:
        print(f" ❌ Could not set the licence Change Date: {e}", file=sys.stderr)
        print("    Nothing was written. Fix LICENSE.md / NOTICE.md and rerun.", file=sys.stderr)
        sys.exit(1)
    license_path.write_text(new_license, encoding="utf-8")
    notice_path.write_text(new_notice, encoding="utf-8")
    print(f" ✅ Updated LICENSE.md + NOTICE.md -> v{version}, Change Date {change_date}")

    # 1. Update pyproject.toml
    pyproject_path = root_dir / "pyproject.toml"
    if pyproject_path.exists():
        content = pyproject_path.read_text(encoding="utf-8")
        content = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{version}"', content, count=1)
        pyproject_path.write_text(content, encoding="utf-8")
        print(f" ✅ Updated pyproject.toml -> version = \"{version}\"")
    else:
        print(f" ⚠️ pyproject.toml not found at {pyproject_path}")

    # 2. Update src/mcp_server/updater.py
    updater_path = root_dir / "src" / "mcp_server" / "updater.py"
    if updater_path.exists():
        content = updater_path.read_text(encoding="utf-8")
        content = re.sub(r'MCP_VERSION\s*=\s*"[^"]+"', f'MCP_VERSION = "{version}"', content, count=1)
        updater_path.write_text(content, encoding="utf-8")
        print(f" ✅ Updated src/mcp_server/updater.py -> MCP_VERSION = \"{version}\"")
    else:
        print(f" ⚠️ updater.py not found at {updater_path}")

    # 3. Update version.json (Application GUI Release Log)
    version_json_path = root_dir / "version.json"
    new_changelog_entry = None
    if version_json_path.exists():
        data = json.loads(version_json_path.read_text(encoding="utf-8"))
        # mcp.latest is intentionally left alone — CI publishes it alongside the
        # download URLs and checksums. A changelog entry for a version that is
        # not yet `latest` is inert: check_for_updates() only reads highlights
        # for the version it is announcing.
        changelog = data["mcp"].get("changelog", [])
        existing_idx = next((i for i, entry in enumerate(changelog) if entry.get("version") == version), -1)
        new_changelog_entry = {
            "version": version,
            "date": month_year,
            # Prefixes are for the GitHub page's grouped section only. This list is
            # read by the desktop "What's New" panel and quoted verbatim by the
            # assistant, where a leading "Fixed:" is noise.
            "highlights": [text for _, text in (split_highlight(h) for h in highlights)],
        }

        if existing_idx != -1:
            changelog[existing_idx] = new_changelog_entry
        else:
            changelog.insert(0, new_changelog_entry)

        data["mcp"]["changelog"] = changelog
        # ensure_ascii=False, to match JSON.stringify in set_version.js — the two
        # scripts are meant to be interchangeable and were not. Without it every
        # em dash in the file is re-encoded as a \\u2014 escape, so a release that
        # adds one entry rewrites every older one too and buries the real change.
        version_json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f" ✅ Updated version.json changelog -> v{version} (mcp.latest is published by CI)")
    else:
        print(f" ⚠️ version.json not found at {version_json_path}")

    # 4. Generate release_notes/release_notes_v<VERSION>.md (GitHub Release Page Notes)
    template_path = root_dir / "release_notes" / "release_notes_template.md"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")

        if "## GitHub Release Note Template" in template:
            template = template.split("## GitHub Release Note Template", 1)[1].strip()
            if template.startswith("```markdown"):
                template = re.sub(r"^```markdown\n", "", template)
                template = re.sub(r"\n```\s*$", "", template)

        gh_release_notes = template.replace("{VERSION}", f"v{version}")

        release_sections = build_release_sections(version, highlights)

        if "{RELEASE_SECTIONS}" in gh_release_notes:
            gh_release_notes = gh_release_notes.replace("{RELEASE_SECTIONS}", release_sections, 1)
        else:
            # Template predates the placeholder — prepend rather than lose the notes.
            print(" ⚠️ {RELEASE_SECTIONS} not found in template — prepending instead")
            gh_release_notes = f"{release_sections}\n\n{gh_release_notes}"

        release_notes_filename = f"release_notes_v{version}.md"
        release_notes_dir = root_dir / "release_notes"
        release_notes_dir.mkdir(parents=True, exist_ok=True)
        release_notes_path = release_notes_dir / release_notes_filename
        # Trailing newline: the template is .strip()ped above, so without this the
        # file ends mid-line. CI appends a "---" separator to it, and markdown
        # reads "---" directly under text as a setext H2 underline — the closing
        # line of v1.0.32's notes shipped as a heading because of it.
        release_notes_path.write_text(gh_release_notes.rstrip("\n") + "\n", encoding="utf-8")
        print(f" ✅ Generated release_notes/{release_notes_filename} (GitHub Release Page Notes)")
    else:
        print(f" ⚠️ release_notes_template.md not found at {template_path}")

    print("\n───────────────────────────────────────────────────")
    print("📋 1. Application GUI Release Log (version.json):")
    if new_changelog_entry:
        print(json.dumps(new_changelog_entry, indent=2))
    print(f"\n📋 2. GitHub Release Page Notes (release_notes/release_notes_v{version}.md) generated.")
    print("───────────────────────────────────────────────────\n")
    print(f"🎉 Version {version} preparation complete!\n")


if __name__ == "__main__":
    main()
