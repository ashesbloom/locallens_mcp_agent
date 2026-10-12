"""
Tests for the CHANGELOG.md generator in scripts/gen_changelog.py.

The README's Updates button links to CHANGELOG.md, but release history lives in
version.json under mcp.changelog. These pin the two things that can go wrong in
between: a highlight landing in the wrong Keep a Changelog section, and a date
gaining a day nobody wrote down.

Nothing here hardcodes the newest version or the release count — the sister
project had tests that did, and every release broke them. Values are looked up
from version.json instead.

Run with:
    python -m pytest tests/test_gen_changelog.py -v
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from gen_changelog import build_changelog, month_start, resolve_date, tag_date  # noqa: E402

RELEASE_RE = re.compile(r"^## \[(\d+\.\d+\.\d+[^\]]*)\] - (\d{4}-\d{2}-\d{2})$", re.M)

CHANGELOG_ENTRIES = json.loads(
    (_ROOT / "version.json").read_text(encoding="utf-8")
)["mcp"]["changelog"]


def render(entries):
    """build_changelog with the per-entry date log silenced."""
    return build_changelog(entries, log=lambda *a, **k: None)


def entry(version="9.9.9", date="July 2026", highlights=()):
    return {"version": version, "date": date, "highlights": list(highlights)}


def sections_of(markdown):
    """['Added', 'Fixed', …] in the order the rendered release lists them."""
    return re.findall(r"^### (\w+)$", markdown, re.M)


# ── Prefix -> section mapping ───────────────────────────────────────────────

@pytest.mark.parametrize("prefix,section", [
    ("Fixed", "Fixed"),
    ("Added", "Added"),
    ("Improved", "Changed"),
    ("Changed", "Changed"),
])
def test_prefix_maps_to_its_keep_a_changelog_section(prefix, section):
    out = render([entry(highlights=[f"{prefix}: the thing"])])
    assert sections_of(out) == [section]
    # The prefix itself is stripped — the bullet is the bare sentence.
    assert f"### {section}\n\n- the thing" in out
    assert f"{prefix}:" not in out


def test_improved_and_changed_share_one_changed_section():
    out = render([entry(highlights=["Improved: faster", "Changed: renamed"])])
    assert sections_of(out) == ["Changed"]
    assert "- faster" in out and "- renamed" in out


def test_unprefixed_highlights_all_land_in_one_changed_section():
    out = render([entry(highlights=["first thing", "second thing", "third thing"])])
    assert sections_of(out) == ["Changed"]
    assert "### Changed\n\n- first thing\n- second thing\n- third thing" in out


def test_mixed_prefixes_split_into_their_own_sections():
    out = render([entry(highlights=[
        "Added: a tool", "Fixed: a crash", "Improved: speed", "unlabelled note",
    ])])
    assert sorted(sections_of(out)) == ["Added", "Changed", "Fixed"]
    assert len(sections_of(out)) == 3  # no section emitted twice


# ── Date resolution ─────────────────────────────────────────────────────────

def test_month_start_takes_the_first_of_the_month():
    assert month_start("July 2026") == "2026-07-01"
    assert month_start("October 2026") == "2026-10-01"
    assert month_start("not a month") is None


def test_date_comes_from_the_git_tag_when_one_exists():
    # Any released version with a tag will do — look one up rather than naming it.
    tagged = next(
        (e for e in CHANGELOG_ENTRIES if tag_date(e["version"])), None
    )
    if tagged is None:
        pytest.skip("no release tags available (shallow clone?)")

    iso, source = resolve_date(tagged["version"], tagged["date"])
    assert source == "git tag"
    assert iso == tag_date(tagged["version"])
    # The tag date must still sit inside the month version.json claims.
    assert iso[:7] == month_start(tagged["date"])[:7]


def test_date_falls_back_to_the_first_of_the_month_without_a_tag():
    iso, source = resolve_date("0.0.0-never-tagged", "July 2026")
    assert iso == "2026-07-01"
    assert "month fallback" in source


def test_an_unresolvable_date_fails_loudly_rather_than_inventing_a_day():
    with pytest.raises(ValueError):
        resolve_date("0.0.0-never-tagged", "sometime last summer")
    with pytest.raises(ValueError):
        resolve_date("0.0.0-never-tagged", None)


# ── Whole-document shape ────────────────────────────────────────────────────

def test_releases_are_ordered_newest_first():
    out = render([
        entry(version="0.0.1-a", date="July 2026"),
        entry(version="0.0.2-b", date="October 2026"),
        entry(version="0.0.3-c", date="August 2026"),
    ])
    assert [v for v, _ in RELEASE_RE.findall(out)] == ["0.0.2-b", "0.0.3-c", "0.0.1-a"]


def test_real_changelog_is_ordered_newest_first():
    dates = [d for _, d in RELEASE_RE.findall(render(CHANGELOG_ENTRIES))]
    assert dates == sorted(dates, reverse=True)


def test_every_version_in_version_json_appears_exactly_once():
    found = [v for v, _ in RELEASE_RE.findall(render(CHANGELOG_ENTRIES))]
    expected = [e["version"] for e in CHANGELOG_ENTRIES]
    assert sorted(found) == sorted(expected)
    assert len(found) == len(set(found))


def test_every_release_heading_parses_as_a_real_date():
    out = render(CHANGELOG_ENTRIES)
    headings = RELEASE_RE.findall(out)
    assert headings, "no release headings rendered"
    for version, iso in headings:
        datetime.strptime(iso, "%Y-%m-%d")  # raises if the day was faked badly

    # Every '## [' line matched the expected shape — none slipped through loose.
    assert len(headings) == out.count("\n## [")


def test_document_opens_with_a_keep_a_changelog_header():
    out = render(CHANGELOG_ENTRIES)
    assert out.startswith("# Changelog")
    assert "keepachangelog.com" in out
    assert out.endswith("\n")


def test_committed_changelog_matches_what_the_generator_produces():
    """CHANGELOG.md is generated — a hand edit, or a stale file, shows up here."""
    committed = _ROOT / "CHANGELOG.md"
    if not committed.exists():
        pytest.skip("CHANGELOG.md not generated yet")
    assert committed.read_text(encoding="utf-8") == render(CHANGELOG_ENTRIES)


# ── set_version.js -> gen_changelog.py wiring ───────────────────────────────
# scripts/set_version.js is interchangeable with set_version.py, so it has to
# regenerate CHANGELOG.md too or a release
# done through the JS path publishes a changelog stuck a version behind.
# It shells out to the Python generator rather than reimplementing the
# rendering — these assert the wiring is really there, by content, because the
# repo has no JS test runner and adding one is not worth it.

SET_VERSION_JS = (_ROOT / "scripts" / "set_version.js").read_text(encoding="utf-8")

# Comment lines stripped, so a bare mention in a comment cannot satisfy any of
# these — the generator has to be named in executable code.
SET_VERSION_JS_CODE = "\n".join(
    line for line in SET_VERSION_JS.splitlines()
    if not line.lstrip().startswith("//")
)


def test_set_version_js_references_the_generator_in_real_code():
    assert "gen_changelog.py" in SET_VERSION_JS_CODE
    # The path is built from the repo root, not the cwd, so a release run from
    # another directory still finds it.
    assert re.search(
        r"path\.join\(\s*rootDir\s*,\s*'scripts'\s*,\s*'gen_changelog\.py'\s*\)",
        SET_VERSION_JS_CODE,
    )


def test_set_version_js_runs_the_generator_as_a_child_process():
    assert "execFileSync" in SET_VERSION_JS_CODE
    assert re.search(
        r"require\(\s*'node:child_process'\s*\)", SET_VERSION_JS_CODE
    ), "execFileSync must be imported from node:child_process"

    # The execFileSync call has to actually pass the generator's path, not just
    # exist somewhere in the file alongside an unrelated mention.
    call = re.search(r"execFileSync\((?P<args>[^;]*?)\);", SET_VERSION_JS_CODE, re.S)
    assert call, "no execFileSync(...) call found"
    assert "genChangelogPath" in call.group("args")
    # stdio inherited, so the per-entry date-source lines reach the operator.
    assert "stdio: 'inherit'" in call.group("args")


def test_set_version_js_propagates_a_generator_failure():
    """A failed generator must exit non-zero, never warn and carry on."""
    # Anchored on the call, not the `{ execFileSync } = require(...)` import at
    # the top of the file — otherwise this measures the licence step's try/catch.
    start = re.search(r"execFileSync\(", SET_VERSION_JS_CODE).start()
    block = SET_VERSION_JS_CODE[start:]
    catch = block.index("catch")
    exit_call = block.index("process.exit(1)")
    assert catch < exit_call, "process.exit(1) must sit inside the catch path"
    # Nothing between the two turns the failure into a mere warning.
    assert "console.warn" not in block[catch:exit_call]
