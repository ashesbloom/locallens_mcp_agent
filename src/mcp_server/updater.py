"""
LocalLens MCP — Update Checker
================================
Checks https://locallens.app/version.json for a newer MCP version.

Design principles:
  - Silent on failure (network down, timeout, bad JSON) — returns None, never raises
  - Cached to disk for TTL_HOURS so it never hammers the server
  - Zero user data sent — only the MCP version number is compared locally
  - Works fully offline once cached; gracefully degrades with no cache

Version file schema expected at https://locallens.app/version.json:
{
  "mcp": {
    "latest": "1.1.0",
    "min_supported": "1.0.0",
    "release_notes_url": "https://locallens.app/changelog",
    "changelog": [
      {
        "version": "1.1.0",
        "date": "August 2026",
        "highlights": [
          "Smart Album Suggestions — now live!",
          "Built-in Chat UI (requires locallens-mcp[chat])"
        ]
      }
    ]
  },
  "app": {
    "latest": "2.0.0",
    "download_url": "https://locallens.app/download"
  }
}
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from packaging.version import Version, InvalidVersion

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Current version of this MCP package — bump this on every release
MCP_VERSION = "1.0.0"

# How often to check for updates (hours). Users never get hammered.
TTL_HOURS = 24

# Where the canonical version manifest lives
VERSION_URL = os.getenv(
    "LOCALLENS_VERSION_URL",
    "https://locallens.app/version.json"
)

# Local cache file
_CACHE_FILE = Path.home() / ".config" / "LocalLens" / "mcp_update_cache.json"


# ── Core logic ─────────────────────────────────────────────────────────────────

def _read_cache() -> Optional[Dict[str, Any]]:
    """Return cached update data if it exists and is within TTL."""
    try:
        if not _CACHE_FILE.exists():
            return None
        data = json.loads(_CACHE_FILE.read_text())
        fetched_at = data.get("_fetched_at", 0)
        if time.time() - fetched_at > TTL_HOURS * 3600:
            return None  # expired
        return data
    except Exception:
        return None


def _write_cache(data: Dict[str, Any]) -> None:
    """Persist update data to disk with a timestamp."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data["_fetched_at"] = time.time()
        _CACHE_FILE.write_text(json.dumps(data))
    except Exception:
        pass  # silently fail — caching is best-effort


def _fetch_version_manifest() -> Optional[Dict[str, Any]]:
    """
    Fetch the version manifest. Checks in order:
      1. Local override file (~/.config/LocalLens/version_override.json)
         — For testing and pre-launch when the website isn't live yet.
      2. Remote URL (https://locallens.app/version.json)
         — Production path once the website is deployed.
    
    Returns None on any failure (never raises).
    """
    # 1. Local override (useful for testing + pre-launch)
    override_file = Path.home() / ".config" / "LocalLens" / "version_override.json"
    if override_file.exists():
        try:
            data = json.loads(override_file.read_text())
            logger.debug("[updater] Using local version_override.json")
            return data
        except Exception:
            pass  # corrupted override file — fall through to remote

    # 2. Remote fetch
    try:
        headers = {
            "User-Agent": f"locallens-mcp/{MCP_VERSION}",
            "Accept": "application/json",
        }
        with httpx.Client(timeout=5.0) as client:
            r = client.get(VERSION_URL, headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.debug(f"[updater] Version fetch failed (OK if offline): {e}")
        return None


def check_for_updates(force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Check if a newer MCP version is available.

    Returns a dict if an update is available:
        {
            "update_available": True,
            "current_version": "1.0.0",
            "latest_version": "1.1.0",
            "is_critical": False,       # True if current < min_supported
            "highlights": [...],         # from changelog for latest_version
            "release_notes_url": "...",
            "upgrade_command": "pip install --upgrade locallens-mcp"
        }

    Returns None if:
        - Already on the latest version
        - Network is unavailable
        - Any error occurs (always safe to call)
    """
    try:
        # Try cache first (unless forced)
        manifest = None if force else _read_cache()

        if manifest is None:
            manifest = _fetch_version_manifest()
            if manifest:
                _write_cache(manifest)

        if not manifest:
            return None

        mcp_info = manifest.get("mcp", {})
        latest_str = mcp_info.get("latest", "")
        min_supported_str = mcp_info.get("min_supported", "")

        if not latest_str:
            return None

        current = Version(MCP_VERSION)
        latest = Version(latest_str)

        if current >= latest:
            return None  # already up to date

        # Determine if this is a critical update (current is below min supported)
        is_critical = False
        if min_supported_str:
            try:
                min_supported = Version(min_supported_str)
                is_critical = current < min_supported
            except InvalidVersion:
                pass

        # Find highlights for the latest version from changelog
        highlights = []
        for entry in mcp_info.get("changelog", []):
            if entry.get("version") == latest_str:
                highlights = entry.get("highlights", [])
                break

        return {
            "update_available": True,
            "current_version": MCP_VERSION,
            "latest_version": latest_str,
            "is_critical": is_critical,
            "highlights": highlights,
            "release_notes_url": mcp_info.get(
                "release_notes_url", "https://locallens.app/changelog"
            ),
            "upgrade_command": "pip install --upgrade locallens-mcp",
        }

    except (InvalidVersion, Exception) as e:
        logger.debug(f"[updater] check_for_updates failed silently: {e}")
        return None
