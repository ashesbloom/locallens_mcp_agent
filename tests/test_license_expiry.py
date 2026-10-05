"""
Guards for Pro licensing against Dodo Payments.

Dodo sends no expiry. A subscription key simply turns invalid upstream when the
subscription is cancelled, paused, refunded or replaced by a plan change, so the
MCP re-validates a subscription weekly and keeps it working through an offline
grace window. The behaviours that matter, and why each is here:

  1. A non-expiring (founding) key never expires and never re-checks. This is what
     keeps the privacy claim literally true for founding users — exactly one
     network call, ever.
  2. A recently validated subscription is active.
  3. One that could not be re-checked keeps working through the grace window.
     Locking someone out of their own photo library because a check could not run
     offline is a worse failure than a fortnight of unpaid access.
  4. Past the grace window it locks. Without this the whole exercise is decorative.
  5. When Dodo answers "invalid", Pro ends at once — the grace is for being
     offline, never for a cancelled subscription.

The fake responses below are copied from the real test-mode API (2026-10-03).

Run: python -m pytest tests/test_license_expiry.py -v
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_server import license as lic


def _ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _cache(tmp_path, kind="subscription", validated_days_ago=0.0, **extra):
    """Write a licence cache and point the module at it."""
    path = tmp_path / "mcp_license.json"
    data = {
        "license_key": "TEST-KEY",
        "activated_at": datetime.now().isoformat(),
        "machine_id": lic._get_machine_id(),
        "tier": "pro",
        "kind": kind,
        "validated_at": _ago(validated_days_ago),
        "instance_id": "lki_test",
        **extra,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return mock.patch.object(lic, "_license_path", lambda: path)


class _Dodo:
    """A fake Dodo license API. Records every request it receives."""

    def __init__(self, routes):
        self.routes = routes  # path suffix -> (status, json body) | Exception
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for suffix, reply in self.routes.items():
            if request.url.path.endswith(suffix):
                if isinstance(reply, Exception):
                    raise reply
                status, body = reply
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"code": "NOT_FOUND"})

    def patch(self):
        real = httpx.AsyncClient
        transport = httpx.MockTransport(self.handler)
        return mock.patch.object(
            httpx, "AsyncClient", lambda *a, **k: real(*a, transport=transport, **k)
        )


_ACTIVATED = {
    "id": "lki_0NotQdIYCsxhDMRZtu2iw",
    "name": "x",
    "license_key_id": "lic_x",
    "product": {"product_id": "pdt_x", "name": "LL Agent Pro — Yearly"},
    "customer": {"customer_id": "cus_x", "name": "Buyer", "email": "buyer@example.com"},
}


# ── 1. Non-expiring (founding) keys ─────────────────────────────────────────

def test_non_expiring_key_never_expires(tmp_path):
    with _cache(tmp_path, kind="non_expiring", validated_days_ago=400):
        assert lic.is_pro_active() is True


def test_non_expiring_key_never_triggers_a_refresh(tmp_path):
    """The privacy promise for founding users is 'exactly one network call'."""
    with _cache(tmp_path, kind="non_expiring", validated_days_ago=400):
        assert lic._needs_refresh(lic._read_cache()) is False


def test_pre_dodo_cache_without_kind_stays_permanent(tmp_path):
    """Only dev-bypass caches predate Dodo; they were always meant to be permanent."""
    path = tmp_path / "mcp_license.json"
    path.write_text(json.dumps({
        "license_key": "DEV", "machine_id": lic._get_machine_id(), "tier": "pro",
        "expires_at": None, "instance_id": "dev",
    }), encoding="utf-8")
    with mock.patch.object(lic, "_license_path", lambda: path):
        assert lic.is_pro_active() is True
        assert lic._needs_refresh(lic._read_cache()) is False


# ── 2-4. Subscriptions ──────────────────────────────────────────────────────

def test_recently_validated_subscription_is_active(tmp_path):
    with _cache(tmp_path, validated_days_ago=1):
        assert lic.is_pro_active() is True


def test_unchecked_subscription_survives_the_grace_window(tmp_path):
    """Ten days since the last check: past the weekly re-check, inside the grace."""
    with _cache(tmp_path, validated_days_ago=10):
        assert lic.is_pro_active() is True


def test_subscription_locks_after_the_grace_window(tmp_path):
    """This is the assertion the whole feature exists for."""
    with _cache(tmp_path, validated_days_ago=22):
        assert lic.is_pro_active() is False, (
            "a subscription that has not validated in 3 weeks kept Pro — "
            "the offline grace has become a free tier"
        )


def test_refresh_is_weekly_not_constant(tmp_path):
    with _cache(tmp_path, validated_days_ago=2):
        assert lic._needs_refresh(lic._read_cache()) is False
    with _cache(tmp_path, validated_days_ago=8):
        assert lic._needs_refresh(lic._read_cache()) is True


# ── 5. Re-validation against Dodo ───────────────────────────────────────────

def test_refresh_sends_key_and_this_machines_activation(tmp_path):
    dodo = _Dodo({"/validate": (200, {"valid": True})})
    with _cache(tmp_path, validated_days_ago=8), dodo.patch():
        asyncio.run(lic.refresh_license_if_stale())
        cache = lic._read_cache()
    sent = json.loads(dodo.requests[0].content)
    assert sent == {"license_key": "TEST-KEY", "license_key_instance_id": "lki_test"}
    assert lic._parse_expiry(cache["validated_at"]) > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert cache["kind"] == "subscription" and cache["instance_id"] == "lki_test"


def test_invalid_upstream_ends_pro_immediately(tmp_path):
    """Cancelled, refunded, or seat freed elsewhere: no grace for any of these."""
    dodo = _Dodo({"/validate": (200, {"valid": False})})
    with _cache(tmp_path, validated_days_ago=8), dodo.patch():
        asyncio.run(lic.refresh_license_if_stale())
        assert lic._read_cache() is None
        assert lic.is_pro_active() is False


def test_offline_refresh_keeps_the_license(tmp_path):
    dodo = _Dodo({"/validate": httpx.ConnectError("offline")})
    with _cache(tmp_path, validated_days_ago=8), dodo.patch():
        asyncio.run(lic.refresh_license_if_stale())
        assert lic.is_pro_active() is True


# ── Activation ──────────────────────────────────────────────────────────────

def test_activation_caches_a_subscription_without_personal_data(tmp_path):
    dodo = _Dodo({"/activate": (201, _ACTIVATED)})
    path = tmp_path / "mcp_license.json"
    with mock.patch.object(lic, "_license_path", lambda: path), dodo.patch():
        result = asyncio.run(lic.activate_license("  TEST-KEY \n"))
    assert result["status"] == "activated" and result["kind"] == "subscription"
    sent = json.loads(dodo.requests[0].content)
    assert sent == {"license_key": "TEST-KEY", "name": lic._get_machine_id()}
    stored = path.read_text(encoding="utf-8")
    assert "lki_0NotQdIYCsxhDMRZtu2iw" in stored
    assert "buyer@example.com" not in stored and "Buyer" not in stored


def test_founding_product_activates_as_non_expiring(tmp_path):
    founding = {**_ACTIVATED, "product": {"product_id": "pdt_f", "name": "LL Agent Pro — Founding"}}
    dodo = _Dodo({"/activate": (201, founding)})
    path = tmp_path / "mcp_license.json"
    with mock.patch.object(lic, "_license_path", lambda: path), dodo.patch():
        assert asyncio.run(lic.activate_license("K"))["kind"] == "non_expiring"
        assert lic._needs_refresh(lic._read_cache()) is False


def test_activation_errors_describe_state_and_cache_nothing(tmp_path):
    """
    Each Dodo refusal maps to a distinct status. Messages must not contain a tool
    call: an imperative in a tool error gets executed by the assistant.
    """
    path = tmp_path / "mcp_license.json"
    for code, status in [(404, "invalid"), (403, "inactive"), (422, "limit_reached")]:
        dodo = _Dodo({"/activate": (code, {"code": "X"})})
        with mock.patch.object(lic, "_license_path", lambda: path), dodo.patch():
            result = asyncio.run(lic.activate_license("K"))
        assert result["status"] == status
        assert not path.exists()
        assert "(" not in result["message"] and "_license" not in result["message"]


def test_license_api_defaults_to_live_and_test_is_one_env_var(monkeypatch):
    monkeypatch.delenv("LOCALLENS_LICENSE_URL", raising=False)
    assert lic._license_base() == "https://live.dodopayments.com/licenses"
    monkeypatch.setenv("LOCALLENS_LICENSE_URL", "https://test.dodopayments.com/licenses/")
    assert lic._license_base() == "https://test.dodopayments.com/licenses"


# ── Deactivation ────────────────────────────────────────────────────────────

def test_deactivation_frees_the_seat_upstream(tmp_path):
    dodo = _Dodo({"/deactivate": (200, {})})
    with _cache(tmp_path), dodo.patch():
        result = asyncio.run(lic.deactivate_license())
        assert lic._read_cache() is None
    assert result["status"] == "deactivated" and result["seat_freed"] is True
    sent = json.loads(dodo.requests[0].content)
    assert sent == {"license_key": "TEST-KEY", "license_key_instance_id": "lki_test"}


def test_offline_deactivation_still_reverts_to_free(tmp_path):
    """A network failure must never trap someone in Pro they asked to stop."""
    dodo = _Dodo({"/deactivate": httpx.ConnectError("offline")})
    with _cache(tmp_path), dodo.patch():
        result = asyncio.run(lic.deactivate_license())
        assert lic._read_cache() is None
    assert result["seat_freed"] is False and "seat_note" in result


def _revoke_tool_app():
    # Built before _Dodo.patch(): the mcp package evaluates `httpx.AsyncClient | None`
    # at import time, which fails once AsyncClient is swapped for a lambda.
    from mcp.server.fastmcp import FastMCP
    from mcp_server.tools.pro_tools import register_pro_tools

    app = FastMCP("t")
    register_pro_tools(app)
    return app


def _call(app, args):
    result = asyncio.run(app.call_tool("revoke_pro_license", args))
    return (result[1] if isinstance(result, tuple) else result)["result"]


def test_revoke_tool_asks_before_deactivating(tmp_path):
    """One "deactivate my license" in chat used to free the seat and lock Pro at once."""
    app, dodo = _revoke_tool_app(), _Dodo({"/deactivate": (200, {})})
    with _cache(tmp_path), dodo.patch():
        result = _call(app, {})
        assert lic._read_cache() is not None, "deactivated without the user confirming"
    assert dodo.requests == []
    assert result["status"] == "confirmation_required"


def test_revoke_tool_deactivates_once_confirmed(tmp_path):
    app, dodo = _revoke_tool_app(), _Dodo({"/deactivate": (200, {})})
    with _cache(tmp_path), dodo.patch():
        result = _call(app, {"confirm": True})
        assert lic._read_cache() is None
    assert result["status"] == "deactivated" and result["seat_freed"] is True


# ── Parsing ─────────────────────────────────────────────────────────────────

def test_timestamps_parse_z_suffix():
    """fromisoformat only accepts 'Z' from 3.11; this package supports 3.10+."""
    parsed = lic._parse_expiry("2030-01-01T00:00:00.000000Z")
    assert parsed is not None and parsed.tzinfo is not None


def test_unparseable_timestamp_is_none():
    assert lic._parse_expiry("not-a-date") is None
    assert lic._parse_expiry(None) is None
    assert lic._parse_expiry(12345) is None


# ── The welcome after activation ────────────────────────────────────────────

def test_activation_returns_a_welcome_worth_presenting(tmp_path):
    """
    A bare "Pro features unlocked." left the assistant nothing to celebrate with,
    and it replied flatly. The welcome carries the moment and a first step.
    """
    dodo = _Dodo({"/activate": (201, _ACTIVATED)})
    with mock.patch.object(lic, "_license_path", lambda: tmp_path / "c.json"), dodo.patch():
        welcome = asyncio.run(lic.activate_license("K"))["welcome"]
    assert welcome["headline"] and welcome["unlocked"] and welcome["guidance"]
    assert all(item["try_saying"] for item in welcome["unlocked"])
    assert "re-checks" in welcome["plan_note"]
    text = json.dumps(welcome, ensure_ascii=False)
    for token in ("$", "₹", "€", "£", "USD", "INR"):
        assert token not in text, f"price token {token!r} in the welcome"
    assert "People" not in text, "sorting by People is FREE — it must never be sold as Pro"
    assert "Smart album" not in text and "smart_album" not in text  # still coming soon


def test_founding_welcome_says_it_is_for_good():
    note = lic._pro_welcome(non_expiring=True)["plan_note"]
    assert "for good" in note and "re-checks" not in note


def test_revoke_lists_exactly_the_features_the_welcome_sold(tmp_path):
    """One list feeds both, and the revoke wording the assistant quotes is unchanged."""
    with _cache(tmp_path), _Dodo({"/deactivate": (200, {})}).patch():
        locked = asyncio.run(lic.deactivate_license())["now_locked"]
    assert locked == [
        "Batch face enrollment (add_face_enroll)", "Duplicate detection and cleanup",
        "Export reports", "Scheduled auto-organize", "Active folders", "Scheduler dashboard",
    ]
    assert len(lic._pro_welcome(False)["unlocked"]) == len(locked)


# ── Machine ID must be the same in every process ────────────────────────────
# The window process writes the cache and the tray / MCP server read it. On recent
# macOS, uuid.getnode() is a random number per process (RFC 4122 multicast bit set),
# so the cache was "for another machine" everywhere but where it was written.

_RANDOM_NODES = (0xA99506673E95, 0xED23F37D7FFE)  # multicast bit set → random


def test_machine_id_is_stable_when_getnode_is_random(monkeypatch):
    monkeypatch.setattr(lic, "_hardware_uuid", lambda: "1C2D3E4F-AAAA-BBBB-CCCC-0123456789AB")
    ids = set()
    for node in _RANDOM_NODES:  # two processes, two random nodes
        monkeypatch.setattr(lic.uuid, "getnode", lambda n=node: n)
        ids.add(lic._get_machine_id())
    assert len(ids) == 1


def test_machine_id_keeps_the_original_formula_for_a_real_mac(monkeypatch):
    # Existing caches on machines with a readable MAC must keep matching.
    import hashlib
    monkeypatch.setattr(lic.uuid, "getnode", lambda: 0x3C22FB0A1B2C)
    monkeypatch.setattr(lic.platform, "node", lambda: "studio.local")
    want = hashlib.sha256(f"studio.local:{0x3C22FB0A1B2C}".encode()).hexdigest()[:32]
    assert lic._get_machine_id() == want


def test_hardware_uuid_reads_ioplatformuuid_on_macos(monkeypatch):
    out = ' |   "IOPlatformSerialNumber" = "X"\n |   "IOPlatformUUID" = "1C2D3E4F-AAAA-BBBB-CCCC-0123456789AB"\n'
    monkeypatch.setattr(lic.sys, "platform", "darwin")
    monkeypatch.setattr(lic.subprocess, "run",
                        lambda *a, **k: mock.Mock(stdout=out, returncode=0))
    lic._hardware_uuid.cache_clear()
    try:
        assert lic._hardware_uuid() == "1C2D3E4F-AAAA-BBBB-CCCC-0123456789AB"
    finally:
        lic._hardware_uuid.cache_clear()
