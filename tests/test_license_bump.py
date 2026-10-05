"""
Tests for the licence Change Date bump in scripts/set_version.py.

v1.0.1–v1.0.32 shipped with a BSL Change Date that had already arrived (someone
typed that day's date into the field) and are Apache 2.0 for good because of it.
Every release now writes its own Change Date, today + 4 years. These pin that the
rewrite hits the real LICENSE.md/NOTICE.md and refuses to half-work.

Run with:
    python -m pytest tests/test_license_bump.py -v
"""

import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from set_version import bump_license, four_years_after  # noqa: E402

LICENSE = (_ROOT / "LICENSE.md").read_text(encoding="utf-8")
NOTICE = (_ROOT / "NOTICE.md").read_text(encoding="utf-8")


def test_four_years_after_keeps_the_calendar_day():
    assert four_years_after(date(2026, 10, 1)) == date(2030, 10, 1)
    assert four_years_after(date(2028, 2, 29)) == date(2032, 2, 29)
    # 2100 is not a leap year — 29 Feb falls back to 28 Feb rather than crashing.
    assert four_years_after(date(2096, 2, 29)) == date(2100, 2, 28)


def test_bump_rewrites_the_real_files():
    lic, notice, change = bump_license(LICENSE, NOTICE, "1.2.0", date(2026, 10, 1))
    assert change == "2030-10-01"
    assert "Licensed Work:        LL Agent v1.2.0\n" in lic
    assert "Change Date:          2030-10-01\n" in lic
    assert "On 2030-10-01, this version automatically becomes Apache 2.0" in notice
    # Nothing else in either file moves — the rest is legal text.
    assert len(lic.splitlines()) == len(LICENSE.splitlines())
    assert len(notice.splitlines()) == len(NOTICE.splitlines())


def test_bump_is_repeatable():
    # Re-running set_version (a typo fix, a second highlight) must still work on
    # its own output, which says "v1.2.0" rather than "v1.0.34 and later".
    lic, notice, _ = bump_license(LICENSE, NOTICE, "1.2.0", date(2026, 10, 1))
    lic2, notice2, change = bump_license(lic, notice, "1.2.1", date(2026, 11, 5))
    assert "LL Agent v1.2.1\n" in lic2 and "2030-11-05" in lic2
    assert change == "2030-11-05" and "On 2030-11-05," in notice2


def test_bump_renames_a_licence_still_under_the_old_product_name():
    # Every LICENSE.md released before v1.1.3 says "LocalLens MCP Agent"; the
    # product is LL Agent now, and the next bump must carry the new name.
    old = LICENSE.replace("Licensed Work:        LL Agent v1.0.34 and later",
                          "Licensed Work:        LocalLens MCP Agent v1.0.34 and later")
    assert "LocalLens MCP Agent v1.0.34" in old
    lic, _, _ = bump_license(old, NOTICE, "1.2.0", date(2026, 10, 1))
    assert "Licensed Work:        LL Agent v1.2.0\n" in lic


@pytest.mark.parametrize("broken", ["LICENSE", "NOTICE"])
def test_bump_refuses_a_file_it_cannot_match(broken):
    lic = LICENSE.replace("Change Date:", "Change date:") if broken == "LICENSE" else LICENSE
    notice = NOTICE.replace("this version automatically", "it") if broken == "NOTICE" else NOTICE
    with pytest.raises(ValueError, match="expected exactly 1"):
        bump_license(lic, notice, "1.2.0", date(2026, 10, 1))


def test_preflight_accepts_what_set_version_writes(tmp_path, monkeypatch):
    # The release gate and the bump script must agree on the Licensed Work name,
    # or every release after a rename is refused at "LICENSE.md licenses exactly".
    import preflight_release
    lic, notice, _ = bump_license(LICENSE, NOTICE, "1.2.0", date.today())
    (tmp_path / "LICENSE.md").write_text(lic, encoding="utf-8")
    (tmp_path / "NOTICE.md").write_text(notice, encoding="utf-8")
    monkeypatch.setattr(preflight_release, "ROOT", tmp_path)
    monkeypatch.setattr(preflight_release, "_results", [])
    preflight_release.check_license("1.2.0")
    failed = [(name, detail) for ok, name, detail in preflight_release._results if not ok]
    assert not failed
