"""
LocalLens MCP Agent — License Manager
======================================
Handles Pro tier activation, validation, and caching.

Design Principles:
  1. License validation happens ONCE on activation (online).
  2. After successful activation the license is cached locally.
  3. All subsequent Pro-tool calls check the local cache ONLY — no network needed.
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
    "license_key": "XXXX-XXXX-XXXX-XXXX",
    "activated_at": "2026-05-07T12:00:00",
    "machine_id": "<sha256 of hostname+mac>",
    "tier": "pro"
  }
"""

import hashlib
import json
import logging
import os
import platform
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from functools import wraps

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
    """
    raw = f"{platform.node()}:{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
#  License Cache I/O
# ---------------------------------------------------------------------------

# How long before expiry we start trying to refresh the licence, and how long
# a subscriber keeps working after it lapses while we cannot reach the server.
# The grace exists because the alternative — locking someone out mid-trip on a
# plane because a renewal could not be confirmed — is a far worse failure than
# a fortnight of unpaid access.
_RENEW_WINDOW = timedelta(days=7)
_OFFLINE_GRACE = timedelta(days=14)


def _parse_expiry(value: Any) -> Optional[datetime]:
    """
    Parse Lemon Squeezy's `expires_at` into an aware UTC datetime.

    Returns None for null/absent/garbage — and None means *lifetime*, which is
    the permissive case, so anything unparseable must be logged rather than
    silently granting forever access.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        # fromisoformat only learned to accept "Z" in 3.11; this package
        # supports 3.10+, so normalise it by hand.
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _log.warning("Could not parse license expiry %r — treating as lifetime.", value)
        return None
    # A naive timestamp from the API is UTC by convention.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _expiry_from_body(body: Dict[str, Any]) -> Optional[str]:
    """
    Pull `expires_at` out of a Lemon Squeezy validate/activate response.

    Shape is `{"valid": true, "license_key": {..., "expires_at": null}}`.
    Null means a one-time purchase — lifetime. Anything unexpected also
    resolves to None, which is the permissive reading; erring the other way
    would lock out a paying customer over a response-shape change.
    """
    key = body.get("license_key")
    if isinstance(key, dict):
        value = key.get("expires_at")
        return value if isinstance(value, str) else None
    return None


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
    expires_at: Optional[str] = None,
) -> None:
    """
    Write a validated license to the local cache.

    `expires_at` is the subscription period end as Lemon Squeezy reported it.
    None means a one-time / lifetime key, which never expires and never needs
    another network call.
    """
    path = _license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "license_key": license_key,
        "activated_at": datetime.now().isoformat(),
        "machine_id": _get_machine_id(),
        "tier": tier,
        "expires_at": expires_at,
    }
    if instance_id:
        data["instance_id"] = instance_id
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _log.info(f"License cached successfully (tier={tier}).")


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def is_pro_active() -> bool:
    """
    Check if Pro tier is currently active on this machine. Never hits the
    network — the refresh is a separate, explicit step (see
    `refresh_license_if_stale`).

    A lifetime key (`expires_at` is None) is active forever, which is what
    keeps the privacy promise literally true for one-time buyers: they make
    exactly one network call, ever.

    A subscription stays active until `_OFFLINE_GRACE` past its period end.
    Without that grace an offline user whose renewal could not be confirmed
    would be locked out of their own photo library.
    """
    cache = _read_cache()
    if cache is None or cache.get("tier") not in {"pro", "personal"}:
        return False

    expiry = _parse_expiry(cache.get("expires_at"))
    if expiry is None:
        return True  # lifetime

    return datetime.now(timezone.utc) < expiry + _OFFLINE_GRACE


def _needs_refresh(cache: Dict[str, Any]) -> bool:
    """True when a subscription is inside the renewal window or already past it."""
    expiry = _parse_expiry(cache.get("expires_at"))
    if expiry is None:
        return False  # lifetime keys never re-check
    return datetime.now(timezone.utc) >= expiry - _RENEW_WINDOW


async def refresh_license_if_stale() -> None:
    """
    Re-validate a subscription that is near or past its period end, and write
    the new expiry back.

    Best-effort by design: a failure here is silent, because the grace window
    in `is_pro_active` is what covers being offline. Called from `require_pro`
    so it only runs when a Pro tool is actually used.
    """
    cache = _read_cache()
    if cache is None or not _needs_refresh(cache):
        return

    key = cache.get("license_key")
    if not key:
        return

    import httpx

    validate_url, _ = _get_license_endpoints()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(validate_url, json={"license_key": key}, timeout=10)
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        _log.info("License refresh skipped (%s) — grace period still applies.", e)
        return

    if not body.get("valid"):
        # The key was revoked or refunded. Drop the cache so the user reverts
        # to Free immediately rather than riding out the grace window.
        _log.info("License is no longer valid upstream — reverting to Free.")
        path = _license_path()
        if path.exists():
            path.unlink()
        return

    _write_cache(
        key,
        cache.get("tier", "pro"),
        instance_id=cache.get("instance_id"),
        expires_at=_expiry_from_body(body),
    )
    _log.info("License refreshed.")


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
            "expires_at": cache.get("expires_at"),
            "machine_id": cache.get("machine_id"),
            "instance_id": cache.get("instance_id"),
        }
    return {
        "activated": False,
        "tier": "free",
        "message": "Pro features are locked. Use activate_pro_license(license_key=...) to unlock.",
    }


def _debug_license_bypass_enabled() -> bool:
    """Allow test keys only when debug mode is explicitly enabled."""
    return os.getenv("LOCALLENS_MCP_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _get_license_endpoints() -> Tuple[str, str]:
    """Return (validate_url, activate_url) for Lemon Squeezy licensing."""
    base = os.getenv("LOCALLENS_LICENSE_URL", "https://api.lemonsqueezy.com/v1/licenses").rstrip("/")
    if base.endswith("/validate") or base.endswith("/activate"):
        base = base.rsplit("/", 1)[0]
    validate_url = os.getenv("LOCALLENS_LICENSE_VALIDATE_URL", f"{base}/validate")
    activate_url = os.getenv("LOCALLENS_LICENSE_ACTIVATE_URL", f"{base}/activate")
    return validate_url, activate_url


async def activate_license(license_key: str) -> Dict[str, Any]:
    """
    Validate a license key against the remote licensing server.
    On success, caches the result locally so future checks are offline.

    For a lifetime key this is the only function that ever needs internet — after
    activation the user need never be online again. Subscriptions are re-validated
    near their period end by `refresh_license_if_stale`.

        Uses the Lemon Squeezy License Validation API by default. Override via:
            - LOCALLENS_LICENSE_URL (base, default https://api.lemonsqueezy.com/v1/licenses)
            - LOCALLENS_LICENSE_VALIDATE_URL (full validate URL)
            - LOCALLENS_LICENSE_ACTIVATE_URL (full activate URL)
    """
    import httpx

    validate_url, activate_url = _get_license_endpoints()
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
            r = await client.post(validate_url, json={"license_key": license_key}, timeout=10)
            r.raise_for_status()
            body = r.json()

            if not body.get("valid"):
                return {
                    "status": "invalid",
                    "message": body.get("error", "Invalid license key. Please check and try again."),
                }

            r2 = await client.post(
                activate_url,
                json={"license_key": license_key, "instance_name": machine_id},
                timeout=10,
            )
            r2.raise_for_status()
            activation = r2.json()

            if not activation.get("activated"):
                return {
                    "status": "activation_failed",
                    "message": activation.get("error", "License activation failed."),
                }

            instance_id = None
            if isinstance(activation.get("instance"), dict):
                instance_id = activation["instance"].get("id")

            _write_cache(
                license_key,
                "pro",
                instance_id=instance_id,
                expires_at=_expiry_from_body(body),
            )
            return {
                "status": "activated",
                "tier": "pro",
                "message": "Pro features unlocked.",
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


def deactivate_license() -> Dict[str, Any]:
    """Remove the local license cache, reverting to Free tier."""
    path = _license_path()
    if path.exists():
        path.unlink()
        _log.info("License deactivated — reverted to Free tier.")
        return {
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
            "now_locked": [
                "Batch face enrollment (add_face_enroll)", "Duplicate detection and cleanup",
                "Export reports",
                "Scheduled auto-organize", "Active folders", "Scheduler dashboard",
            ],
            "guidance": (
                "List still_available_free and now_locked exactly as given. Do NOT infer "
                "which features are gated — sorting by People is FREE and stays working."
            ),
        }
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

    Reuses the existing mcp_onboarded.json marker; no new state is written.
    """
    try:
        marker = _get_license_dir() / "mcp_onboarded.json"
        if not marker.exists():
            return True  # never onboarded — definitely new
        stamp = json.loads(marker.read_text(encoding="utf-8")).get("onboarded_at")
        if not stamp:
            return False
        age = datetime.now() - datetime.fromisoformat(stamp)
        return age < timedelta(days=_ONBOARDING_WINDOW_DAYS)
    except Exception:
        return False  # unreadable marker → treat as established, i.e. stay quiet


def pro_upgrade_message() -> str:
    """
    Shown when a Free user hits a Pro-gated tool.

    Leads with the in-app action; the website is a trailing suggestion, and only
    while the user is new. Never states a price — that is what the page is for.
    """
    base = (
        "This is a Pro feature. Unlock it from the LocalLens tray menu → Plan, "
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
        # No-op for lifetime keys and for subscriptions with time left, so the
        # common case stays entirely offline.
        await refresh_license_if_stale()
        if not is_pro_active():
            return {
                "error": "pro_required",
                "tool": func.__name__,
                "message": pro_upgrade_message(),
            }
        return await func(*args, **kwargs)
    return wrapper
