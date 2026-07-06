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
                get_path_presets, get_enrolled_faces, get_metadata_overview,
                start_sorting, abort_job)
  - Pro tier:   Unlocks start_find_group, add_face_enroll, find_duplicates,
                export_report, schedule_auto_organize, smart_album_suggestions
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
from datetime import datetime
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


def _write_cache(license_key: str, tier: str = "pro", instance_id: Optional[str] = None) -> None:
    """Write a validated license to the local cache."""
    path = _license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "license_key": license_key,
        "activated_at": datetime.now().isoformat(),
        "machine_id": _get_machine_id(),
        "tier": tier,
    }
    if instance_id:
        data["instance_id"] = instance_id
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _log.info(f"License cached successfully (tier={tier}).")


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def is_pro_active() -> bool:
    """Check if Pro tier is currently activated on this machine."""
    cache = _read_cache()
    return cache is not None and cache.get("tier") in {"pro", "personal"}


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

    This is the ONLY function that requires internet access.
    After activation, the user never needs to be online again.

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

            _write_cache(license_key, "pro", instance_id=instance_id)
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
        return {"status": "deactivated", "message": "Pro features have been deactivated."}
    return {"status": "already_free", "message": "No active license found."}


# ---------------------------------------------------------------------------
#  Decorator — use on any Pro-only tool
# ---------------------------------------------------------------------------

_STORE_URL = os.getenv("LOCALLENS_STORE_URL", "https://locallens.app")
PRO_UPGRADE_MESSAGE = (
    "This is a Pro feature. "
    f"To unlock it, purchase a license at {_STORE_URL} "
    "and activate it with: activate_pro_license(license_key='YOUR-KEY')"
)


def require_pro(func: Callable) -> Callable:
    """
    Decorator for Pro-only MCP tools.
    If the user hasn't activated a Pro license, the tool returns a friendly
    upgrade prompt instead of executing. The LLM will relay this to the user.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Dict[str, Any]:
        if not is_pro_active():
            return {
                "error": "pro_required",
                "tool": func.__name__,
                "message": PRO_UPGRADE_MESSAGE,
            }
        return await func(*args, **kwargs)
    return wrapper
