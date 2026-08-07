"""
Guards for the "why is it telling me to run pip / why does it search the web"
round of fixes.

Two independent bugs shared one symptom — the assistant handing the user advice
that could not work:

  1. _is_bundled(): Claude Desktop launches the packaged connector as
       dist/LocalLens Agent.app/Contents/MacOS/python -m mcp_server.main
     which never runs py2app's __boot__.py, so sys.frozen stayed False and every
     bundle user was told to `pip install --upgrade locallens-mcp`.

  2. The website nag: the pricing URL was the primary call to action and was
     repeated to established users. It is now secondary and onboarding-scoped.

Run: python -m pytest tests/test_bundle_and_pricing.py -v
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_server import license as lic
from mcp_server.updater import _is_bundled


# ── 1. Bundle detection ─────────────────────────────────────────────────────

_BUNDLE_EXE = "/Users/x/Git/locallens_mcp_agent/dist/LocalLens Agent.app/Contents/MacOS/python"


def test_bundle_detected_without_sys_frozen():
    """The exact reported bug: inside a .app, launched as `python -m`."""
    with mock.patch.object(sys, "executable", _BUNDLE_EXE):
        assert not getattr(sys, "frozen", False), "precondition: sys.frozen unset"
        assert _is_bundled() is True, (
            "a user inside LocalLens Agent.app was classified as a pip install and "
            "told to run `pip install --upgrade locallens-mcp`, which cannot work."
        )


def test_pyinstaller_still_detected():
    """sys.frozen remains sufficient on its own (Windows/PyInstaller)."""
    with mock.patch.object(sys, "executable", "/usr/bin/python3"), \
         mock.patch.object(sys, "frozen", True, create=True):
        assert _is_bundled() is True


def test_dev_checkout_is_not_bundled():
    """A source checkout must keep the pip path — otherwise devs lose their upgrade."""
    with mock.patch.object(sys, "executable", "/Users/x/proj/venv/bin/python"):
        assert _is_bundled() is False


# ── 2. The website is a suggestion, not a source or a nag ───────────────────

def _with_onboarded_at(tmp_path, stamp):
    """Point the licence dir at tmp_path holding an mcp_onboarded.json marker."""
    if stamp is not None:
        (tmp_path / "mcp_onboarded.json").write_text(
            json.dumps({"onboarded": True, "onboarded_at": stamp}), encoding="utf-8"
        )
    return mock.patch.object(lic, "_get_license_dir", return_value=tmp_path)


def test_new_user_gets_the_suggestion(tmp_path):
    recent = (datetime.now() - timedelta(days=2)).isoformat()
    with _with_onboarded_at(tmp_path, recent):
        assert lic.is_new_user() is True
        assert lic.PRICING_URL in lic.pro_upgrade_message()


def test_established_user_is_not_nagged(tmp_path):
    """The user's complaint: stop recommending the site over and over."""
    old = (datetime.now() - timedelta(days=90)).isoformat()
    with _with_onboarded_at(tmp_path, old):
        assert lic.is_new_user() is False
        msg = lic.pro_upgrade_message()
        assert lic.PRICING_URL not in msg, (
            "someone who has used LocalLens for months should not be pointed at the "
            "marketing site every time they touch a Pro feature."
        )
        assert "tray menu" in msg.lower(), "the in-app route must remain"


def test_never_missing_marker_counts_as_new(tmp_path):
    with _with_onboarded_at(tmp_path, None):
        assert lic.is_new_user() is True


def test_upsell_leads_with_the_app_not_the_website(tmp_path):
    """Website is secondary: the in-app route must come first in the string."""
    recent = (datetime.now() - timedelta(days=1)).isoformat()
    with _with_onboarded_at(tmp_path, recent):
        msg = lic.pro_upgrade_message()
        assert msg.index("tray menu") < msg.index(lic.PRICING_URL), (
            "the pricing URL is ahead of the in-app route — the website was asked to "
            "be the secondary option, not the primary one."
        )


def test_upsell_never_quotes_a_price(tmp_path):
    """No price exists in this repo; asserting one is the bug being fixed."""
    recent = (datetime.now() - timedelta(days=1)).isoformat()
    with _with_onboarded_at(tmp_path, recent):
        msg = lic.pro_upgrade_message()
    for token in ("$", "€", "£", "₹", "USD", "INR"):
        assert token not in msg, f"upsell quotes a price ({token!r}); link out instead"


# ── 3. Sort by People is FREE ───────────────────────────────────────────────
#
# The marketing copy said Pro for months while the code never gated it. Asked
# "is sort by people available on Free?", the assistant read the copy and told
# the user no — right after telling them deactivating Pro had disabled it.
# It had not: People sort runs through start_sorting, which has no @require_pro.
#
# Guarded in both directions: the enforcement must stay open, and the prose must
# stop claiming otherwise.

_SRC = Path(__file__).resolve().parents[1] / "src"


def test_sorting_module_gates_nothing():
    """start_sorting lives here; a @require_pro landing in this file is the bug."""
    source = (_SRC / "mcp_server" / "tools" / "actions.py").read_text(encoding="utf-8")
    # Decorator USE only — a line whose first token is @require_pro. Prose mentioning
    # the decorator (including the note in that file explaining why it is absent)
    # must not trip this.
    applied = re.findall(r"^\s*@require_pro\b", source, re.MULTILINE)
    assert not applied, (
        "a tool in actions.py is now Pro-gated. start_sorting handles People sorting "
        "and must stay free — only batch enrolment (pro_tools.add_face_enroll) is Pro."
    )


def _help_pro_topic(is_pro: bool):
    import asyncio
    from mcp.server.fastmcp import FastMCP
    from mcp_server.tools.status import register_status

    app = FastMCP("t")
    register_status(app)
    info = {"activated": is_pro, "tier": "pro" if is_pro else "free"}
    with mock.patch("mcp_server.tools.status.get_license_info", return_value=info):
        result = asyncio.run(app.call_tool("locallens_help", {"topic": "pro"}))
    return json.dumps(result[1] if isinstance(result, tuple) else result)


def test_free_tier_lists_people_sort():
    payload = _help_pro_topic(is_pro=False)
    assert "Sort by People" in payload, (
        "the Free tier list omits Sort by People, so the assistant tells free users "
        "it is locked when it actually works."
    )


def test_pro_pitch_does_not_sell_people_sort():
    """Selling something already free is what produced the wrong answer."""
    payload = _help_pro_topic(is_pro=False)
    marker = '"feature": "\\ud83d\\udc64 Sort by People"'
    assert marker not in payload and '"feature": "👤 Sort by People"' not in payload, (
        "Sort by People is still listed as a Pro showcase feature; it is free."
    )
