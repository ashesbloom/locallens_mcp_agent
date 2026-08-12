"""
Guards for the free-preview gate.

There is no store yet — Lemon Squeezy declined the merchant application pending a
live site and a real user base — so `FREE_PREVIEW` opens every Pro tool to
everyone until a purchase is actually possible.

The subtle part is *where* the flag lives. It would have been one line shorter to
put it inside `is_pro_active()` and be done, and that would have been wrong twice
over:

  1. `get_license_info()` and `get_license_status` report the user's real license
     state. If `is_pro_active()` started answering "yes" for everyone, the tray
     and the assistant would tell people they own a Pro license they never bought.
  2. The subscription expiry enforcement in `tests/test_license_expiry.py` is only
     meaningful while `is_pro_active()` still computes the honest answer. Short-
     circuiting it would leave nine tests passing against dead code, and the
     revenue hole they close would quietly reopen the day the flag flipped back.

So the flag lives in `pro_features_unlocked()` — "may this tool run" — which is a
different question from `is_pro_active()` — "does this machine hold a valid paid
license". These tests pin that separation.

Run: python -m pytest tests/test_free_preview.py -v
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_server import license as lic


def _expired_cache(tmp_path):
    """A cache holding a subscription that lapsed well past the offline grace."""
    path = tmp_path / "mcp_license.json"
    expired = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%S.000000Z"
    )
    path.write_text(
        json.dumps(
            {
                "license_key": "TEST-KEY",
                "activated_at": datetime.now().isoformat(),
                "machine_id": lic._get_machine_id(),
                "tier": "pro",
                "expires_at": expired,
            }
        ),
        encoding="utf-8",
    )
    return mock.patch.object(lic, "_license_path", lambda: path)


def _no_cache(tmp_path):
    """Point the module at a path that does not exist — a brand-new Free user."""
    return mock.patch.object(lic, "_license_path", lambda: tmp_path / "absent.json")


# ── The gate ────────────────────────────────────────────────────────────────

def test_pro_tool_runs_without_a_license_during_free_preview(tmp_path):
    @lic.require_pro
    async def some_pro_tool():
        return {"ran": True}

    with _no_cache(tmp_path), mock.patch.object(lic, "FREE_PREVIEW", True):
        assert asyncio.run(some_pro_tool()) == {"ran": True}


def test_pro_tool_is_gated_again_for_a_post_launch_user(tmp_path):
    """
    Re-gating takes all three: the preview off, a cutoff set, and an install after
    it. Turning FREE_PREVIEW off alone is deliberately NOT enough — with no cutoff
    set, no paid launch has happened and nobody can have arrived late, so the gate
    stays open (see test_no_cutoff_set_means_nobody_has_arrived_late). That is the
    fail-open the grandfathering promise requires.
    """
    @lic.require_pro
    async def some_pro_tool():
        return {"ran": True}

    with _no_cache(tmp_path), \
         _onboarded(tmp_path, "2027-03-01T12:00:00"), \
         mock.patch.object(lic, "FREE_PREVIEW", False), \
         mock.patch.object(lic, "_PREVIEW_CUTOFF", _CUTOFF):
        result = asyncio.run(some_pro_tool())

    assert result["error"] == "pro_required", (
        "a post-launch user with no license got a Pro tool — the gate never closes "
        "and there is no paid tier"
    )


# ── The separation ──────────────────────────────────────────────────────────

def test_free_preview_does_not_forge_a_license(tmp_path):
    """
    `is_pro_active()` answers "does this machine hold a valid paid license" and
    must keep saying no during the preview, or every licence-reporting surface
    starts lying.
    """
    with _no_cache(tmp_path), mock.patch.object(lic, "FREE_PREVIEW", True):
        assert lic.is_pro_active() is False
        assert lic.get_license_info()["activated"] is False
        assert lic.get_license_info()["tier"] == "free"


def test_free_preview_does_not_disable_expiry_enforcement(tmp_path):
    """
    The expiry logic must still compute the honest answer while the gate is open,
    otherwise test_license_expiry.py is passing against code nothing reaches.
    """
    with _expired_cache(tmp_path), mock.patch.object(lic, "FREE_PREVIEW", True):
        assert lic.is_pro_active() is False
        assert lic.pro_features_unlocked() is True


# ── Grandfathering ──────────────────────────────────────────────────────────
#
# The promise (docs/PRICING.md): nobody who used LocalLens during the free preview
# ever pays. It survives `FREE_PREVIEW` being switched off, which is exactly when
# it can break silently — so every case below runs with the preview already off.

def _onboarded(tmp_path, stamp):
    """Point the license dir at tmp_path, optionally holding an install marker."""
    if stamp is not None:
        (tmp_path / "mcp_onboarded.json").write_text(
            json.dumps({"onboarded": True, "onboarded_at": stamp}), encoding="utf-8"
        )
    return mock.patch.object(lic, "_get_license_dir", return_value=tmp_path)


_CUTOFF = "2026-12-01T00:00:00Z"


def test_preview_user_keeps_pro_after_the_preview_ends(tmp_path):
    """The whole promise, in one assertion."""
    before = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with _onboarded(tmp_path, before), \
         mock.patch.object(lic, "FREE_PREVIEW", False), \
         mock.patch.object(lic, "_PREVIEW_CUTOFF", _CUTOFF):
        assert lic.pro_features_unlocked() is True, (
            "a free-preview user lost Pro when the preview ended — this is the "
            "grandfathering promise in docs/PRICING.md being broken"
        )


def test_user_who_arrived_after_launch_is_gated(tmp_path):
    """Otherwise the cutoff grants Pro to everyone and there is no paid tier."""
    after = "2027-03-01T12:00:00"
    with _onboarded(tmp_path, after), \
         mock.patch.object(lic, "FREE_PREVIEW", False), \
         mock.patch.object(lic, "_PREVIEW_CUTOFF", _CUTOFF):
        assert lic.pro_features_unlocked() is False


def test_missing_marker_is_treated_as_eligible(tmp_path):
    """
    Deliberately permissive. The marker is written by the desktop app's setup page
    — code in another repo — so its absence proves nothing about when the user
    arrived. Locking out someone we promised not to charge is the worse failure.
    """
    with _onboarded(tmp_path, None), \
         mock.patch.object(lic, "FREE_PREVIEW", False), \
         mock.patch.object(lic, "_PREVIEW_CUTOFF", _CUTOFF):
        assert lic.installed_before_cutoff() is True


def test_unparseable_install_date_is_treated_as_eligible(tmp_path):
    with _onboarded(tmp_path, "not-a-date"), \
         mock.patch.object(lic, "FREE_PREVIEW", False), \
         mock.patch.object(lic, "_PREVIEW_CUTOFF", _CUTOFF):
        assert lic.installed_before_cutoff() is True


def test_no_cutoff_set_means_nobody_has_arrived_late(tmp_path):
    """
    _PREVIEW_CUTOFF is None until a paid launch happens. Flipping FREE_PREVIEW off
    without setting it must not strand existing users — they stay unlocked.
    """
    with _onboarded(tmp_path, "2027-03-01T12:00:00"), \
         mock.patch.object(lic, "FREE_PREVIEW", False), \
         mock.patch.object(lic, "_PREVIEW_CUTOFF", None):
        assert lic.installed_before_cutoff() is True


def test_grandfathering_does_not_forge_a_license(tmp_path):
    """Same invariant as the preview: unlocked is not the same as licensed."""
    before = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with _onboarded(tmp_path, before), \
         mock.patch.object(lic, "FREE_PREVIEW", False), \
         mock.patch.object(lic, "_PREVIEW_CUTOFF", _CUTOFF):
        assert lic.pro_features_unlocked() is True
        assert lic.is_pro_active() is False


def test_marker_is_stamped_when_absent(tmp_path):
    """
    Eligibility must not depend on the backend's setup page having run, so the MCP
    writes its own marker at start-up when it finds none.
    """
    with _onboarded(tmp_path, None):
        lic._stamp_onboarding_if_absent()
        written = json.loads((tmp_path / "mcp_onboarded.json").read_text(encoding="utf-8"))
    assert written["source"] == "mcp_server"
    assert lic._parse_expiry(written["onboarded_at"]) is not None


def test_stamping_never_overwrites_an_existing_marker(tmp_path):
    """Overwriting would reset a genuine preview user's date to 'today'."""
    original = "2026-07-28T20:56:58.387523"
    with _onboarded(tmp_path, original):
        lic._stamp_onboarding_if_absent()
        written = json.loads((tmp_path / "mcp_onboarded.json").read_text(encoding="utf-8"))
    assert written["onboarded_at"] == original


def test_free_user_is_not_sent_to_activate_a_license(tmp_path):
    """
    Asserting on the word "locked" was the obvious test and a bad one — "Nothing
    is locked" contains it. What actually matters is the *instruction*: during the
    preview there is no key to buy, so telling a Free user to run
    activate_pro_license sends them looking for a store that does not exist.
    """
    with _no_cache(tmp_path), mock.patch.object(lic, "FREE_PREVIEW", True):
        assert "activate_pro_license" not in lic.get_license_info()["message"]

    with _no_cache(tmp_path), mock.patch.object(lic, "FREE_PREVIEW", False):
        assert "activate_pro_license" in lic.get_license_info()["message"]
