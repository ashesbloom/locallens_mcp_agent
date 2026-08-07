#!/usr/bin/env python3
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
from datetime import datetime
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
        highlights = [f"LocalLens MCP Agent v{version} release."]

    root_dir = Path(__file__).resolve().parent.parent
    month_year = datetime.now().strftime("%B %Y")

    print(f"\n🚀 Preparing Release v{version} ({month_year})\n")

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
