# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2026 Mayank Pandey - LL Agent. See LICENSE.md.
"""
LocalLens MCP Agent — License Manager
======================================
Handles Pro tier activation, validation, and caching.

Design Principles:
  1. Activation is online, against Dodo Payments' public license endpoints. They
     take no API key: the license key is the only credential, so the agent never
     holds a merchant secret.
  2. After successful activation the license is cached locally.
  3. Pro-tool calls check the local cache. A non-expiring key (the free founding
     keys) never calls out again. A subscription key is re-validated about once a
     week, sending only the key and this machine's activation id.
  4. If the cache file is missing or tampered with, user must re-activate.

Revenue Model:
  - Free tier:  Core tools (check_app_status, get_stats, get_job_progress,
                locallens_help, get_path_presets, get_enrolled_faces,
                analyse_folder, start_sorting, start_find_group,
                abort_job, open_folder, remember_paths, forget_paths)
  - Pro tier:   Unlocks add_face_enroll, find_duplicates, delete_duplicates,
                export_report, schedule_auto_organize, create_active_folder,
                list_schedules, manage_schedule, open_scheduler_dashboard,
                smart_album_suggestions
  - Cloud LLM:  Users choosing Groq/Gemini cloud mode may incur usage costs
                after their free API tier is exhausted (handled by the LLM
                connector, not this module).

Cache File Format (~/.config/LocalLens/mcp_license.json):
  {
    "license_key": "<uuid from the purchase email>",
    "activated_at": "2026-05-07T12:00:00",
    "machine_id": "<sha256 of hostname+mac>",
    "tier": "pro",
    "kind": "subscription" | "non_expiring",
    "validated_at": "<UTC ISO-8601, last time Dodo said valid>",
    "instance_id": "lki_..."   # Dodo activation id; deactivate needs it
  }
"""

import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from functools import lru_cache, wraps

# Logger — MUST go to stderr (stdout is MCP JSON-RPC channel)
_log = logging.getLogger("locallens_mcp.license")
if not _log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[locallens-mcp] %(levelname)s: %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False


# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------

def _get_license_dir() -> Path:
    """Return the LocalLens application data directory (cross-platform)."""
    if sys.platform == "win32":
        base = os.getenv("APPDATA")
        if not base:
            raise RuntimeError("APPDATA environment variable is not set on Windows.")
        return Path(base) / "LocalLens"
    return Path.home() / ".config" / "LocalLens"


_LICENSE_FILE_NAME = "mcp_license.json"


def _license_path() -> Path:
    return _get_license_dir() / _LICENSE_FILE_NAME


# ---------------------------------------------------------------------------
#  Machine Fingerprint
# ---------------------------------------------------------------------------

def _get_machine_id() -> str:
    """
    Generates a deterministic, privacy-respecting machine fingerprint.
    Uses hostname + primary MAC address hashed with SHA-256.
    Not perfect anti-piracy, but sufficient for indie-level licensing.

    When uuid.getnode() can't read a MAC it returns a random number, flagged by
    the multicast bit (RFC 4122) — on recent macOS that is every call, and a new
    number in every process. The cache is written by one process (the Activate
    Pro window, or the MCP server) and read by others, so a random node made
    every cache look like another machine's. Then the OS's own hardware ID is
    used instead. A real MAC keeps the original formula, so caches written on
    machines where it worked still match.
    """
    node = uuid.getnode()
    if (node >> 40) & 1:
        raw = f"hw:{_hardware_uuid()}"
    else:
        raw = f"{platform.node()}:{node}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@lru_cache(maxsize=1)
def _hardware_uuid() -> str:
    """The OS's stable machine identifier; the hostname if none can be read."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                return m.group(1)
        elif sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        else:
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(p):
                    return Path(p).read_text().strip()
    except Exception:
        pass
    return platform.node()


# ---------------------------------------------------------------------------
#  License Cache I/O
# ---------------------------------------------------------------------------

# Dodo never sends an expiry: a subscription key simply turns invalid when the
# subscription is cancelled, paused, refunded or replaced by a plan change. So a
# subscription is re-validated every _RECHECK_EVERY, and keeps working for
# _OFFLINE_GRACE past its last successful check if the server cannot be reached.
# The grace exists because locking someone out of their own photo library
# mid-trip, over a check that could not run, is a far worse failure than a
# fortnight of unpaid access.
_RECHECK_EVERY = timedelta(days=7)
_OFFLINE_GRACE = timedelta(days=14)

# A key bought through this product never expires and never re-checks. Matched by
# name because product ids differ between Dodo's test and live modes. If the
# product is ever renamed, founding keys fall back to weekly re-checks — which
# still pass, so the failure is a few extra network calls, never a lockout.
_NON_EXPIRING_PRODUCT_MARKER = "Founding"


def _parse_expiry(value: Any) -> Optional[datetime]:
    """
    Parse an ISO-8601 timestamp into an aware UTC datetime, or None.

    Used for `validated_at`, the onboarding marker and `_PREVIEW_CUTOFF`. Every
    caller treats None as the permissive case, so anything unparseable is logged
    rather than silently granting access.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        # fromisoformat only learned to accept "Z" in 3.11; this package
        # supports 3.10+, so normalise it by hand.
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _log.warning("Could not parse timestamp %r.", value)
        return None
    # A naive timestamp is UTC by convention.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _read_cache() -> Optional[Dict[str, Any]]:
    """Read and validate the local license cache. Returns None if invalid."""
    path = _license_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Basic integrity: must have the right machine_id
        if data.get("machine_id") != _get_machine_id():
            _log.warning("License cache machine_id mismatch — ignoring cached license.")
            return None
        if data.get("tier") not in {"pro", "personal"}:
            return None
        return data
    except Exception as e:
        _log.warning(f"Could not read license cache: {e}")
        return None


def _write_cache(
    license_key: str,
    tier: str = "pro",
    instance_id: Optional[str] = None,
    non_expiring: bool = True,
    activated_at: Optional[str] = None,
) -> None:
    """
    Write a validated license to the local cache, stamped as checked just now.

    Deliberately stores nothing else Dodo returns: the activate response carries
    the buyer's name and email, which have no business sitting in a local file.
    """
    path = _license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "license_key": license_key,
        "activated_at": activated_at or datetime.now().isoformat(),
        "machine_id": _get_machine_id(),
        "tier": tier,
        "kind": "non_expiring" if non_expiring else "subscription",
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    if instance_id:
        data["instance_id"] = instance_id
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _log.info(f"License cached successfully (tier={tier}, kind={data['kind']}).")


def _is_non_expiring(cache: Dict[str, Any]) -> bool:
    # A cache without "kind" predates Dodo; the only ones that exist are dev-bypass
    # caches (no store was ever live), which were always meant to be permanent.
    return cache.get("kind", "non_expiring") == "non_expiring"


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def is_pro_active() -> bool:
    """
    Check if Pro tier is currently active on this machine. Never hits the
    network — the refresh is a separate, explicit step (see
    `refresh_license_if_stale`).

    A non-expiring key is active forever, which is what keeps the privacy promise
    literally true for founding users: exactly one network call, ever.

    A subscription stays active until `_RECHECK_EVERY + _OFFLINE_GRACE` past its
    last successful validation. A failed check that *reached* Dodo and was told
    "invalid" deletes the cache instead (see `refresh_license_if_stale`), so the
    grace only ever covers being offline, never a cancelled subscription.
    """
    cache = _read_cache()
    if cache is None or cache.get("tier") not in {"pro", "personal"}:
        return False

    if _is_non_expiring(cache):
        return True

    checked = _parse_expiry(cache.get("validated_at"))
    if checked is None:
        return True  # unreadable stamp: permissive, and the next refresh rewrites it

    return datetime.now(timezone.utc) < checked + _RECHECK_EVERY + _OFFLINE_GRACE


# Paid launch v1.5.0: the free preview is over and Pro is gated (preview users stay
# unlocked through _PREVIEW_CUTOFF below). Moves only in lockstep with FREE_PREVIEW
# in the website's src/content/pricing.ts — the site offering the product free while
# the MCP refuses a tool, or quoting a price for something the MCP gives away, makes
# a liar of both. See docs/RESTORING_PAID_MODE.md.
FREE_PREVIEW = False

# The paid-launch date, as an ISO-8601 string. Anyone whose install predates it was
# a free-preview user and keeps Pro permanently — that is a public promise, not a
# courtesy (docs/PRICING.md, "Free preview — grandfathering").
#
# SET THIS BEFORE FLIPPING FREE_PREVIEW OFF. Order matters: with no cutoff,
# `installed_before_cutoff()` returns True for everyone (nobody can have arrived
# after a launch that has no date), so flipping FREE_PREVIEW alone gates nobody —
# paid mode silently never starts. Set it too early and the opposite happens:
# preview users are reclassified as post-launch and lose Pro. See
# docs/RESTORING_PAID_MODE.md and test_no_cutoff_set_means_nobody_has_arrived_late.
_PREVIEW_CUTOFF: Optional[str] = "2026-10-05T14:40:00Z"  # v1.5.0 paid launch


def _onboarding_marker() -> Path:
    """Where the first-run timestamp lives. Read by grandfathering and is_new_user."""
    return _get_license_dir() / "mcp_onboarded.json"


# Rewritten by the desktop app on every launch, so its date says nothing about when
# LocalLens was installed.
_REWRITTEN_EACH_RUN = {"port.txt"}


def _earliest_local_trace(settings_dir: Path) -> Optional[datetime]:
    """
    The oldest timestamp anywhere in the LocalLens settings dir, or None if empty.

    The marker only shipped in v1.0.34. A preview user still on an older build who
    first updates after paid launch has no marker, and stamping "now" would class
    them as post-launch and take away the Pro they were promised. The files the
    desktop app wrote back then (token, schedules, metadata db…) still carry the
    real install date, so that is what gets stamped instead.

    Errs early, on purpose: a restored backup with old dates grants Pro to someone
    who arrived late, which is the acceptable direction (see installed_before_cutoff).
    """
    def times(p: Path):
        st = p.stat()
        yield st.st_mtime
        birth = getattr(st, "st_birthtime", None)  # macOS; Windows on Python 3.12+
        if birth:
            yield birth
        elif sys.platform == "win32":
            yield st.st_ctime  # creation time on Windows (inode-change time elsewhere)

    stamps = []
    try:
        if not settings_dir.is_dir():
            return None
        for p in settings_dir.iterdir():  # files only: an empty dir proves nothing
            if p.name in _REWRITTEN_EACH_RUN:
                continue
            try:
                stamps.extend(t for t in times(p) if t > 0)
            except OSError:
                continue  # one unreadable file must not discard the rest
    except OSError:
        return None
    if not stamps:
        return None
    return datetime.fromtimestamp(min(stamps), tz=timezone.utc)


def _stamp_onboarding_if_absent() -> None:
    """
    Write the first-run marker if nothing has yet.

    Normally the desktop app's setup page writes it (`"source": "setup_page"`), but
    that code lives in the backend repo and an install path that skips the setup
    page leaves no marker at all. Since the marker is now what proves free-preview
    eligibility, the MCP stamps its own rather than depending on another repo
    having run. Best-effort: a read-only home directory must not break a tool call.
    """
    try:
        # _get_license_dir() (inside _onboarding_marker()) raises RuntimeError if
        # APPDATA is unset on Windows, and path.exists() can raise PermissionError
        # on an unreadable parent — both must stay inside this try. This is called
        # unconditionally at server startup (main.py); letting either escape would
        # kill the whole server for that user, which is a worse failure than never
        # stamping the marker at all.
        path = _onboarding_marker()
        if path.exists():
            return
        # Must run before mkdir below, which would add a "created just now" entry.
        earliest = _earliest_local_trace(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "onboarded": True,
                    # Timezone-aware, matching _parse_expiry()'s "naive == UTC by
                    # convention" rule explicitly rather than by accident — a naive
                    # local timestamp from a positive-UTC-offset install could
                    # otherwise read as later than the true instant and wrongly
                    # push a legitimate pre-cutoff install past _PREVIEW_CUTOFF.
                    "onboarded_at": (earliest or datetime.now(timezone.utc)).isoformat(),
                    "version": "1.0",
                    "source": "mcp_server_backdated" if earliest else "mcp_server",
                }
            ),
            encoding="utf-8",
        )
    except Exception as e:
        _log.debug("Could not stamp onboarding marker: %s", e)


def installed_before_cutoff() -> bool:
    """
    True when this install dates from the free preview, which grants Pro forever.

    Every ambiguous case resolves to True, deliberately. A missing marker, an
    unreadable one, a garbage timestamp — all mean "we cannot prove you arrived
    late", and the promise was that preview users keep Pro. This mirrors
    `is_pro_active()` treating an unreadable `validated_at` as active, for the same
    reason: locking out someone we promised not to charge is a far worse failure
    than granting Pro to someone who reinstalled.

    Returns False only when there is a cutoff AND a readable timestamp at or after
    it — i.e. only when we positively know the user arrived post-launch.
    """
    if _PREVIEW_CUTOFF is None:
        # No paid launch has happened, so nobody can be "after" it.
        return True

    cutoff = _parse_expiry(_PREVIEW_CUTOFF)
    if cutoff is None:
        _log.warning("_PREVIEW_CUTOFF %r is unparseable — treating all installs as "
                     "preview users.", _PREVIEW_CUTOFF)
        return True

    try:
        stamp = json.loads(_onboarding_marker().read_text(encoding="utf-8")).get("onboarded_at")
    except Exception:
        return True  # no marker, or unreadable — benefit of the doubt

    installed = _parse_expiry(stamp)
    if installed is None:
        return True

    return installed < cutoff


def pro_features_unlocked() -> bool:
    """
    Whether Pro tools may run.

    Three independent grants, any one of which is enough:
      1. `FREE_PREVIEW` — no store exists, so nothing is gated.
      2. `installed_before_cutoff()` — a free-preview user, who keeps Pro forever.
         This clause outlives the preview; it is the grandfathering promise, and
         removing it when FREE_PREVIEW flips off would break it.
      3. `is_pro_active()` — an actual paid license.

    Deliberately separate from `is_pro_active()`, which answers the narrower
    question "does this machine hold a valid paid license". Keeping them apart is
    what lets `get_license_status` keep telling the truth about the user's actual
    license while the gate is open, and keeps the expiry enforcement in
    `is_pro_active()` exercised by its own tests instead of short-circuited.
    """
    return FREE_PREVIEW or installed_before_cutoff() or is_pro_active()


def _needs_refresh(cache: Dict[str, Any]) -> bool:
    """True when a subscription's last successful check is a week old or more."""
    if _is_non_expiring(cache):
        return False  # founding keys never re-check
    checked = _parse_expiry(cache.get("validated_at"))
    return checked is None or datetime.now(timezone.utc) >= checked + _RECHECK_EVERY


async def refresh_license_if_stale() -> None:
    """
    Re-validate a subscription whose last check is a week old, and restamp it.

    Sends the key and this machine's activation id, so a seat freed on another
    device (or a key replaced by a plan change) is caught here too. Best-effort:
    network failure is silent, because the grace window in `is_pro_active` is
    what covers being offline. Called from `require_pro`, so it only runs when a
    Pro tool is actually used.
    """
    cache = _read_cache()
    if cache is None or not _needs_refresh(cache):
        return

    key = cache.get("license_key")
    if not key:
        return

    import httpx

    payload: Dict[str, Any] = {"license_key": key}
    if cache.get("instance_id"):
        payload["license_key_instance_id"] = cache["instance_id"]
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{_license_base()}/validate", json=payload, timeout=10)
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        _log.info("License refresh skipped (%s) — grace period still applies.", e)
        return

    if body.get("valid") is not True:
        # Dodo answered and said no: cancelled, paused, refunded, deactivated
        # here from another device, or replaced by a plan change. Drop the cache
        # so the user reverts to Free now rather than riding out the grace.
        _log.info("License is no longer valid upstream — reverting to Free.")
        path = _license_path()
        if path.exists():
            path.unlink()
        return

    _write_cache(
        key,
        cache.get("tier", "pro"),
        instance_id=cache.get("instance_id"),
        non_expiring=False,
        activated_at=cache.get("activated_at"),
    )
    _log.info("License re-validated.")


def get_license_info() -> Dict[str, Any]:
    """
    Return current license state for display purposes.
    Safe to call at any time — never hits the network.
    """
    cache = _read_cache()
    if cache:
        return {
            "activated": True,
            "tier": cache["tier"],
            "activated_at": cache.get("activated_at"),
            "kind": "non_expiring" if _is_non_expiring(cache) else "subscription",
            "last_checked": cache.get("validated_at"),
            "machine_id": cache.get("machine_id"),
            "instance_id": cache.get("instance_id"),
        }
    if FREE_PREVIEW:
        return {
            "activated": False,
            "tier": "free",
            "message": (
                "Nothing is locked right now — LocalLens is in free preview and every "
                "Pro feature is unlocked for everyone. Paid plans arrive later."
            ),
        }
    return {
        "activated": False,
        "tier": "free",
        "message": "Pro features are locked. Use activate_pro_license(license_key=...) to unlock.",
    }


def _debug_license_bypass_enabled() -> bool:
    """Allow test keys only when debug mode is explicitly enabled."""
    return os.getenv("LOCALLENS_MCP_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _license_base() -> str:
    """
    Dodo's public license API. Live by default; point a dev install at test mode
    with LOCALLENS_LICENSE_URL=https://test.dodopayments.com/licenses (test keys
    only exist there). Read per call, like the backend URL, so it is never stale.
    """
    return os.getenv("LOCALLENS_LICENSE_URL", "https://live.dodopayments.com/licenses").rstrip("/")


# Dodo's activate errors, as observed against the test API (2026-10-03). Each
# describes the state and the remedy; none contains a command for the assistant
# to run (an imperative in a tool error gets executed by the client).
_ACTIVATE_ERRORS = {
    404: (
        "invalid",
        "That license key was not found. It may have been copied only in part — the "
        "full key is in the purchase email.",
    ),
    403: (
        "inactive",
        "That license key is not active. This happens when its subscription was "
        "cancelled, paused or refunded, or when a plan change replaced it with a new "
        "key, which is sent by email.",
    ),
    422: (
        "limit_reached",
        "That license key is already active on 3 machines, its limit. A seat frees up "
        "when Pro is deactivated on one of them.",
    ),
}


# What Pro adds — the single list behind both the activation welcome and the
# revoke reply's `now_locked`, so the two can never disagree. It must match the
# @require_pro decorators in tools/pro_tools.py (sorting by People is FREE; only
# batch enrolment is Pro). smart_album_suggestions is gated but returns
# "coming_soon", so it is deliberately not advertised here.
# (name, emoji, what it does, an example the user could say)
_PRO_FEATURES = [
    ("Batch face enrollment (add_face_enroll)", "👤",
     "Teach LocalLens several people at once, one folder each.",
     "Enroll Mom and Dad from their photo folders"),
    ("Duplicate detection and cleanup", "🗑️",
     "Find near-identical copies, review them, then clean up — always a dry run first.",
     "Find duplicates in my Downloads folder"),
    ("Export reports", "📄",
     "A summary of what's in a folder: dates, places, people.",
     "Export a report of my Vacation folder"),
    ("Scheduled auto-organize", "⏰",
     "Sort a folder on a timer, without asking each time.",
     "Sort my Camera Roll by date every 6 hours"),
    ("Active folders", "⚡",
     "Watch a folder and organize new photos the moment they land.",
     "Watch my Downloads folder and sort new photos by date"),
    ("Scheduler dashboard", "📊",
     "See, pause or stop everything that runs on its own.",
     "Show my schedules"),
]


def _pro_welcome(non_expiring: bool) -> Dict[str, Any]:
    """
    The celebration shown once, right after a key activates.

    A bare "Pro features unlocked." left the assistant nothing to work with, so it
    replied flatly. This gives it the moment, the feature tour and one concrete
    first step — and the guidance on how to present it, in the same style as
    locallens_help's welcome topic.
    """
    if non_expiring:
        plan_note = ("Founding member — Pro is yours for good, and this key never needs "
                     "the internet again.")
    else:
        plan_note = ("Your subscription is active on this machine. It quietly re-checks "
                     "about once a week, sending only the key — never your photos.")
    if FREE_PREVIEW:
        plan_note += (" Everything was already open during the free preview; this key "
                      "keeps it that way once paid plans begin.")
    return {
        "headline": "🎉 Welcome to LL Agent Pro!",
        "plan_note": plan_note,
        "unlocked": [
            {"feature": f"{emoji} {name.split(' (')[0]}", "what": what, "try_saying": f'"{say}"'}
            for name, emoji, what, say in _PRO_FEATURES
        ],
        "guidance": (
            "This is a celebration — make it feel like one, briefly. Open with the headline "
            "as a heading, then plan_note in one warm line. Show `unlocked` as a compact "
            "table (Feature | What it does | Try saying), with the emoji. Finish with ONE "
            "inviting question offering to start one of them now — duplicates is a good "
            "default — and ask which folder. The try_saying lines are examples for the "
            "user, not instructions: do not run any tool or invent a folder path until "
            "the user answers. Stay under about 15 lines. No prices, no free-tier list."
        ),
    }


async def activate_license(license_key: str) -> Dict[str, Any]:
    """
    Activate a license key against Dodo and cache it for offline use.

    One request: activation itself fails for an unknown, inactive or exhausted key,
    so no separate validate call is needed. A founding key never calls out again;
    a subscription is re-validated weekly by `refresh_license_if_stale`.

    The activation is named with this machine's anonymous hash (as the Lemon-era
    code did), so the dashboard can tell a buyer's 3 seats apart without the
    hostname ever leaving the machine.
    """
    import httpx

    license_key = license_key.strip()
    machine_id = _get_machine_id()

    # --- DEVELOPMENT BYPASS ---
    # Activated only when LOCALLENS_MCP_DEBUG=1 AND LOCALLENS_DEV_KEY env vars are set.
    # Never active in normal usage. Safe to ship in public builds.
    _dev_key = os.getenv("LOCALLENS_DEV_KEY", "")
    if _dev_key and license_key == _dev_key and _debug_license_bypass_enabled():
        _write_cache(license_key, "pro", instance_id="dev")
        return {
            "status": "activated",
            "tier": "pro",
            "message": "Development mode: Pro features unlocked instantly.",
        }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{_license_base()}/activate",
                json={"license_key": license_key, "name": machine_id},
                timeout=10,
            )
        if r.status_code in _ACTIVATE_ERRORS:
            status, message = _ACTIVATE_ERRORS[r.status_code]
            return {"status": status, "message": message}
        r.raise_for_status()
        activation = r.json()

        instance_id = activation.get("id")
        if not instance_id:
            return {"status": "error", "message": "The license server returned no activation."}

        product = activation.get("product") or {}
        non_expiring = _NON_EXPIRING_PRODUCT_MARKER in str(product.get("name", ""))
        _write_cache(license_key, "pro", instance_id=instance_id, non_expiring=non_expiring)
        return {
            "status": "activated",
            "tier": "pro",
            "kind": "non_expiring" if non_expiring else "subscription",
            "message": "Pro features unlocked.",
            "welcome": _pro_welcome(non_expiring),
        }
    except httpx.ConnectError:
        return {
            "status": "offline",
            "message": "Could not reach the license server. Please check your internet connection and try again.",
        }
    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "message": f"License server error: {e.response.status_code}",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"License validation failed: {e}",
        }


async def deactivate_license() -> Dict[str, Any]:
    """
    Free this machine's seat on Dodo, then remove the local cache (Free tier).

    The local removal always happens, even offline: the user asked to stop using
    Pro here, and a network failure must not trap them in it. If Dodo could not be
    told, the seat stays counted against the key's 3, and the reply says so.
    """
    path = _license_path()
    cache = _read_cache()
    if path.exists():
        seat_freed: Optional[bool] = None
        instance_id = (cache or {}).get("instance_id")
        if cache and instance_id and instance_id != "dev":
            import httpx

            try:
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        f"{_license_base()}/deactivate",
                        json={"license_key": cache["license_key"],
                              "license_key_instance_id": instance_id},
                        timeout=10,
                    )
                seat_freed = r.status_code == 200
            except Exception as e:
                _log.info("Could not reach the license server to free the seat: %s", e)
                seat_freed = False
        path.unlink()
        _log.info("License deactivated — reverted to Free tier.")
        result: Dict[str, Any] = {
            "status": "deactivated",
            "message": "Pro features have been deactivated. You are on the Free tier.",
            # Spelled out because an assistant asked to summarise a bare "Pro
            # deactivated" invented the list — and wrongly told the user that
            # sorting by People had been switched off. It had not: People sort
            # runs through start_sorting, which is not Pro-gated.
            "still_available_free": [
                "Sort by Date", "Sort by Location", "Sort by People",
                "Find & Group (including by person)", "See enrolled people",
                "Analyze folders", "Path presets", "Open folder", "Stats & status",
            ],
            "now_locked": [name for name, *_ in _PRO_FEATURES],
            "guidance": (
                "List still_available_free and now_locked exactly as given. Do NOT infer "
                "which features are gated — sorting by People is FREE and stays working."
            ),
        }
        if seat_freed is not None:
            result["seat_freed"] = seat_freed
            if not seat_freed:
                result["seat_note"] = (
                    "The license server could not be reached, so this machine still counts "
                    "as one of the key's 3 activations. It frees up once this machine "
                    "deactivates again while online, or through LL Agent support."
                )
        return result
    return {"status": "already_free", "message": "No active license found."}


# ---------------------------------------------------------------------------
#  Decorator — use on any Pro-only tool
# ---------------------------------------------------------------------------

_STORE_URL = os.getenv("LOCALLENS_STORE_URL", "https://locallensmcp.vercel.app")

# Where "see plans and pricing" points — the pricing page, not a checkout URL.
# Single definition: tools/status.py imports this rather than defining its own.
PRICING_URL = os.getenv("LOCALLENS_PRICING_URL", "https://locallensmcp.vercel.app/#pricing")

# How long a user counts as "new" for the purpose of mentioning the website.
_ONBOARDING_WINDOW_DAYS = 14

# The one rule every surface that names the website must carry. The site is a
# suggestion for the human, never a source for the assistant: fetching it is how
# the assistant ended up describing an unrelated product as if it were LocalLens.
NEVER_BROWSE_NOTE = (
    "Mention this URL as a suggestion only. Do NOT open, fetch or browse it, and do "
    "not use anything from it as a source — including our own site. Every LocalLens "
    "fact you need comes from locallens_help."
)


def is_new_user() -> bool:
    """
    True only during a user's first days with LocalLens.

    Gates the *unprompted* website suggestion. A long-time user who explicitly asks
    about pricing still gets the link — that is answering the question, not touting.
    Repeating it at every turn for someone already using the app is the nag we avoid.

    Reuses the existing mcp_onboarded.json marker; no new state is written here.
    (`_stamp_onboarding_if_absent()` may create it, but only at server start.)
    """
    try:
        marker = _onboarding_marker()
        if not marker.exists():
            return True  # never onboarded — definitely new
        # _parse_expiry makes old naive stamps and current UTC ones comparable;
        # naive now() minus an aware stamp raised, which read as "established".
        stamp = _parse_expiry(json.loads(marker.read_text(encoding="utf-8")).get("onboarded_at"))
        if not stamp:
            return False
        return datetime.now(timezone.utc) - stamp < timedelta(days=_ONBOARDING_WINDOW_DAYS)
    except Exception:
        return False  # unreadable marker → treat as established, i.e. stay quiet


def pro_upgrade_message() -> str:
    """
    Shown when a Free user hits a Pro-gated tool.

    Leads with the in-app action; the website is a trailing suggestion, and only
    while the user is new. Never states a price — that is what the page is for.
    """
    base = (
        "This is a Pro feature. Unlock it from the LL tray menu → Activate Pro…, "
        "or with activate_pro_license(license_key='YOUR-KEY') if you already have a key."
    )
    if is_new_user():
        return f"{base} You can also see plans at {PRICING_URL}. {NEVER_BROWSE_NOTE}"
    return base


# Kept as a module constant for src/llm_connector/tool_registry.py, which imports it
# directly. Prefer pro_upgrade_message() — it is onboarding-aware.
PRO_UPGRADE_MESSAGE = pro_upgrade_message()


def require_pro(func: Callable) -> Callable:
    """
    Decorator for Pro-only MCP tools.
    If the user hasn't activated a Pro license, the tool returns a friendly
    upgrade prompt instead of executing. The LLM will relay this to the user.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Dict[str, Any]:
        # No-op for non-expiring keys and for subscriptions checked this week, so the
        # common case stays entirely offline.
        await refresh_license_if_stale()
        if not pro_features_unlocked():
            return {
                "error": "pro_required",
                "tool": func.__name__,
                "message": pro_upgrade_message(),
            }
        return await func(*args, **kwargs)
    return wrapper
