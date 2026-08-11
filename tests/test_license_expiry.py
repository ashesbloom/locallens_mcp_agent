"""
Guards for subscription expiry.

Before this existed, `is_pro_active()` checked only that a cached key was
present — the cache had no expiry field at all. That was correct while the only
thing sold was a lifetime licence, and became a revenue hole the moment a
monthly plan appeared: pay $4.99 once, cancel, keep Pro forever.

The four behaviours that matter, and why each is here:

  1. Lifetime (`expires_at: null`) never expires and never re-checks. This is
     what keeps the privacy claim literally true for one-time buyers — exactly
     one network call, ever.
  2. A live subscription is active.
  3. A lapsed subscription keeps working through a grace window. Locking
     someone out of their own photo library because a renewal could not be
     confirmed offline is a worse failure than a fortnight of unpaid access.
  4. Past the grace window it locks. Without this the whole exercise is
     decorative.

Run: python -m pytest tests/test_license_expiry.py -v
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_server import license as lic


def _iso(delta: timedelta) -> str:
    """An ISO-8601 UTC timestamp offset from now, in Lemon Squeezy's format."""
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


def _cache(tmp_path, expires_at):
    """Write a licence cache with a given expiry and point the module at it."""
    path = tmp_path / "mcp_license.json"
    path.write_text(
        json.dumps(
            {
                "license_key": "TEST-KEY",
                "activated_at": datetime.now().isoformat(),
                "machine_id": lic._get_machine_id(),
                "tier": "pro",
                "expires_at": expires_at,
            }
        ),
        encoding="utf-8",
    )
    return mock.patch.object(lic, "_license_path", lambda: path)


# ── 1. Lifetime keys ────────────────────────────────────────────────────────

def test_lifetime_key_never_expires(tmp_path):
    """expires_at null means a one-time purchase — active forever."""
    with _cache(tmp_path, None):
        assert lic.is_pro_active() is True


def test_lifetime_key_never_triggers_a_refresh(tmp_path):
    """
    The privacy promise for one-time buyers is 'exactly one network call'.
    A lifetime key must never enter the refresh path.
    """
    with _cache(tmp_path, None):
        assert lic._needs_refresh(lic._read_cache()) is False


# ── 2-4. Subscriptions ──────────────────────────────────────────────────────

def test_live_subscription_is_active(tmp_path):
    with _cache(tmp_path, _iso(timedelta(days=20))):
        assert lic.is_pro_active() is True


def test_lapsed_subscription_survives_the_grace_window(tmp_path):
    """One day past expiry, well inside the 14-day grace."""
    with _cache(tmp_path, _iso(timedelta(days=-1))):
        assert lic.is_pro_active() is True


def test_subscription_locks_after_the_grace_window(tmp_path):
    """This is the assertion the whole feature exists for."""
    with _cache(tmp_path, _iso(timedelta(days=-15))):
        assert lic.is_pro_active() is False, (
            "a cancelled subscriber kept Pro past the grace window — "
            "this is the revenue hole is_pro_active was changed to close"
        )


def test_refresh_is_attempted_near_expiry_but_not_before(tmp_path):
    """Inside 7 days of expiry we re-check; outside it we stay offline."""
    with _cache(tmp_path, _iso(timedelta(days=20))):
        assert lic._needs_refresh(lic._read_cache()) is False
    with _cache(tmp_path, _iso(timedelta(days=3))):
        assert lic._needs_refresh(lic._read_cache()) is True


# ── Parsing ─────────────────────────────────────────────────────────────────

def test_expiry_parses_lemon_squeezy_z_suffix():
    """fromisoformat only accepts 'Z' from 3.11; this package supports 3.10+."""
    parsed = lic._parse_expiry("2030-01-01T00:00:00.000000Z")
    assert parsed is not None and parsed.tzinfo is not None


def test_unparseable_expiry_is_treated_as_lifetime():
    """
    The permissive reading is deliberate: erring the other way would lock out
    a paying customer over a response-shape change.
    """
    assert lic._parse_expiry("not-a-date") is None
    assert lic._parse_expiry(None) is None
    assert lic._parse_expiry(12345) is None


def test_expiry_extracted_from_lemon_squeezy_body():
    body = {"valid": True, "license_key": {"key": "X", "expires_at": "2030-06-01T00:00:00Z"}}
    assert lic._expiry_from_body(body) == "2030-06-01T00:00:00Z"
    assert lic._expiry_from_body({"valid": True, "license_key": {"expires_at": None}}) is None
    assert lic._expiry_from_body({"valid": True}) is None
