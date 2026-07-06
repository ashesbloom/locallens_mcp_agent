"""
LocalLens MCP — Claude Desktop Connector
==========================================
Programmatically installs and removes the LocalLens MCP server entry in
Claude Desktop's configuration file, enabling a 1-click "Connect to Claude"
experience from the LocalLens desktop app.

Design Principles:
  1. Atomic writes — use temp-file + os.replace() to prevent partial corruption.
  2. Non-destructive — always preserve every other mcpServer in the config.
  3. Idempotent — re-running install is safe; skips if already up to date.
  4. Backup — creates a timestamped backup before every write (capped at 5).
  5. Version-aware — embeds a _locallens_meta block so future runs can detect
     stale configs and update them automatically.
  6. Offline-first — all logic is purely local filesystem; no network needed.

Integration Points:
  - LocalLens desktop app: call `locallens-mcp --setup-claude` via subprocess
  - Direct import: from mcp_server.claude_connector import install_claude_connector

Claude Desktop Config Locations:
  macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
  Windows: %APPDATA%/Claude/claude_desktop_config.json
  Linux:   ~/.config/Claude/claude_desktop_config.json (future-proofing)
"""

import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Logger — always stderr (stdout is MCP JSON-RPC channel)
_log = logging.getLogger("locallens_mcp.claude_connector")
if not _log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[locallens-mcp] %(levelname)s: %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False

# ── Constants ──────────────────────────────────────────────────────────────────

# Key used inside Claude's mcpServers dict to identify LocalLens
_MCP_KEY = "locallens"

# How many timestamped backups to keep before pruning the oldest
_MAX_BACKUPS = 5

# The Lemon Squeezy store URL injected as an env var into Claude's config
_STORE_URL = os.getenv("LOCALLENS_STORE_URL", "https://locallens.lemonsqueezy.com")

# Current version of this MCP package (mirrors updater.py)
try:
    from .updater import MCP_VERSION as _MCP_VERSION
except ImportError:
    _MCP_VERSION = "1.0.0"


# ── Claude Config Path ─────────────────────────────────────────────────────────


def get_claude_config_path() -> Path:
    """
    Return the absolute path to Claude Desktop's config JSON file.

    Supports macOS, Windows, and Linux (future-proofing even though Claude
    Desktop doesn't officially ship on Linux yet).

    Raises:
        RuntimeError: If APPDATA is unset on Windows.
        NotImplementedError: If running on an unsupported platform.
    """
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA environment variable is not set on Windows.")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    else:
        # Linux — ~/.config/Claude/ mirrors the XDG convention Claude Desktop
        # is likely to use if/when it ships on Linux.
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def is_claude_installed() -> bool:
    """
    Check whether Claude Desktop appears to be installed by testing if its
    config directory exists.

    Returns False when the directory is missing entirely — this likely means
    Claude Desktop has never been launched (or isn't installed). In that case,
    the UI should show "Download Claude Desktop first" rather than attempting
    config injection.
    """
    return get_claude_config_path().parent.exists()


# ── Install Method Detection ───────────────────────────────────────────────────


def detect_install_method() -> str:
    """
    Detect how locallens-mcp was installed on this machine.

    Returns one of:
      "bundled"    — Running as a PyInstaller/Briefcase frozen app bundle.
      "venv"       — Running inside a Python virtual environment.
      "uvx"        — Not in a venv but `uvx` is available on PATH.
      "global_pip" — Fallback: assume a global pip install.

    The result drives which command path we inject into Claude's config.
    """
    # 1. PyInstaller / Briefcase frozen bundle
    if getattr(sys, "frozen", False):
        return "bundled"

    # 2. Active Python virtual environment
    if sys.prefix != sys.base_prefix:
        return "venv"

    # 3. uvx (uv's tool runner) is on PATH — preferred for non-venv users
    if shutil.which("uvx") is not None:
        return "uvx"

    # 4. Fallback — assume global pip install
    return "global_pip"


def get_mcp_command_config() -> Dict[str, Any]:
    """
    Build the mcpServers config block for locallens, resolving the correct
    command based on how the MCP agent was installed.

    Returns a dict like:
        {
          "command": "/path/to/locallens-mcp",  # or "uvx" / "locallens-mcp"
          "args": [],                             # or ["locallens-mcp"] for uvx
          "env": { "LOCALLENS_STORE_URL": "..." }
        }
    """
    method = detect_install_method()
    env_block = {"LOCALLENS_STORE_URL": _STORE_URL}

    if method == "bundled":
        # Frozen app: the MCP binary lives alongside the app executable.
        # sys._MEIPASS is the PyInstaller temp dir; fall back to sys.executable dir.
        app_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        binary_name = "locallens-mcp.exe" if sys.platform == "win32" else "locallens-mcp"
        mcp_binary = app_dir / binary_name
        return {
            "command": str(mcp_binary),
            "args": [],
            "env": env_block,
        }

    if method == "venv":
        # Resolve the locallens-mcp script inside the active venv's bin/Scripts dir.
        scripts_dir = Path(sys.prefix) / (
            "Scripts" if sys.platform == "win32" else "bin"
        )
        binary_name = "locallens-mcp.exe" if sys.platform == "win32" else "locallens-mcp"
        mcp_binary = scripts_dir / binary_name
        if mcp_binary.exists():
            return {
                "command": str(mcp_binary),
                "args": [],
                "env": env_block,
            }
        # venv detected but binary not found — fall through to global_pip

    if method == "uvx":
        return {
            "command": "uvx",
            "args": ["locallens-mcp"],
            "env": env_block,
        }

    # global_pip (or venv binary not found)
    return {
        "command": "locallens-mcp",
        "args": [],
        "env": env_block,
    }


# ── Binary Verification ────────────────────────────────────────────────────────


def verify_mcp_binary() -> Dict[str, Any]:
    """
    Check if the resolved MCP binary command is actually executable.

    Returns a dict:
        {
          "valid": True | False,
          "command": "<resolved command>",
          "install_method": "venv" | "uvx" | ...,
          "reason": "<human-readable explanation if invalid>"
        }
    """
    cfg = get_mcp_command_config()
    method = detect_install_method()
    cmd = cfg["command"]

    # For absolute-path commands, just check the file exists and is executable
    if os.path.isabs(cmd):
        path = Path(cmd)
        if not path.exists():
            return {
                "valid": False,
                "command": cmd,
                "install_method": method,
                "reason": f"Binary not found at: {cmd}",
            }
        if not os.access(cmd, os.X_OK):
            return {
                "valid": False,
                "command": cmd,
                "install_method": method,
                "reason": f"Binary exists but is not executable: {cmd}",
            }
        return {"valid": True, "command": cmd, "install_method": method}

    # For bare commands ("uvx", "locallens-mcp"), verify they're on PATH
    resolved = shutil.which(cmd)
    if resolved is None:
        return {
            "valid": False,
            "command": cmd,
            "install_method": method,
            "reason": (
                f"'{cmd}' not found on PATH. "
                "Try: pip install locallens-mcp  or  pip install uv"
            ),
        }
    return {"valid": True, "command": cmd, "install_method": method}


# ── Config Read / Write Helpers ────────────────────────────────────────────────


def _load_config(config_path: Path) -> Dict[str, Any]:
    """
    Read and parse the Claude config file.

    - Returns an empty dict if the file doesn't exist yet.
    - On JSON parse error: creates a timestamped backup and returns {}.
    """
    if not config_path.exists():
        return {}

    try:
        text = config_path.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as exc:
        _log.warning("Claude config is malformed JSON (%s). Backing up and starting fresh.", exc)
        _backup_config(config_path, label="corrupt")
        return {}


def _backup_config(config_path: Path, label: str = "backup") -> Optional[Path]:
    """
    Copy config_path to a timestamped backup alongside the original.

    Example:  claude_desktop_config.json.backup.2026-07-06T150000
    Keeps at most _MAX_BACKUPS files; deletes the oldest when exceeded.

    Returns the backup path, or None if the source file doesn't exist.
    """
    if not config_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    backup_path = config_path.with_suffix(f".json.{label}.{timestamp}")
    shutil.copy2(config_path, backup_path)
    _log.info("Backup created: %s", backup_path)

    # Prune old backups — keep newest _MAX_BACKUPS
    existing: List[Path] = sorted(
        config_path.parent.glob(f"{config_path.stem}.json.{label}.*"),
        key=lambda p: p.stat().st_mtime,
    )
    for old in existing[:-_MAX_BACKUPS]:
        try:
            old.unlink()
            _log.debug("Pruned old backup: %s", old)
        except OSError:
            pass

    return backup_path


def _atomic_write(config_path: Path, config: Dict[str, Any]) -> None:
    """
    Write the config dict to disk atomically.

    Strategy: write to a sibling .tmp file in the same directory, then
    os.replace() — which is atomic on POSIX and near-atomic on Windows.
    This prevents a crash mid-write from corrupting the live config file.
    """
    tmp_path = config_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.replace(tmp_path, config_path)
    _log.debug("Atomic write complete: %s", config_path)


def _make_meta_block() -> Dict[str, Any]:
    """Return a metadata block to embed inside our injected config entry."""
    return {
        "_locallens_meta": {
            "installed_by": "locallens-mcp-connector",
            "version": _MCP_VERSION,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "install_method": detect_install_method(),
        }
    }


# ── Public API ─────────────────────────────────────────────────────────────────


def is_claude_connected() -> bool:
    """
    Return True if `locallens` is already registered in Claude's mcpServers.
    Does NOT verify that the binary is still valid — use get_connection_status()
    for a full health check.
    """
    try:
        config_path = get_claude_config_path()
        config = _load_config(config_path)
        return _MCP_KEY in config.get("mcpServers", {})
    except Exception:
        return False


def get_current_injection() -> Optional[Dict[str, Any]]:
    """
    Return the current `locallens` mcpServers entry from Claude's config,
    or None if not connected.
    """
    try:
        config_path = get_claude_config_path()
        config = _load_config(config_path)
        return config.get("mcpServers", {}).get(_MCP_KEY)
    except Exception:
        return None


def install_claude_connector(force: bool = False) -> Dict[str, Any]:
    """
    Inject the LocalLens MCP server entry into Claude Desktop's config file.

    Args:
        force: If True, overwrite even if the existing entry looks identical.

    Returns a result dict:
        {
          "status": "installed" | "updated" | "already_connected" | "error",
          "config_path": "<path>",
          "command": "<resolved command>",
          "message": "<human-readable summary>",
          "backup_path": "<path to backup>" | None,
          "claude_needs_restart": True | False,
        }

    Behaviour:
      - If Claude Desktop is not installed: returns error with install guidance.
      - If `locallens` already exists and matches: returns already_connected.
      - If `locallens` already exists but differs: updates it (re-injects).
      - Otherwise: creates a fresh entry.
      - Always writes atomically.
      - Backs up the existing config before modifying it.
    """
    try:
        config_path = get_claude_config_path()

        # Guard: Claude Desktop directory must exist
        if not config_path.parent.exists():
            return {
                "status": "error",
                "config_path": str(config_path),
                "command": None,
                "message": (
                    "Claude Desktop does not appear to be installed. "
                    "Download it from https://claude.ai/download and launch it once, "
                    "then run this command again."
                ),
                "backup_path": None,
                "claude_needs_restart": False,
            }

        # Verify binary is resolvable before touching the config
        binary_check = verify_mcp_binary()
        if not binary_check["valid"]:
            return {
                "status": "error",
                "config_path": str(config_path),
                "command": binary_check["command"],
                "message": binary_check["reason"],
                "backup_path": None,
                "claude_needs_restart": False,
            }

        # Load existing config
        config = _load_config(config_path)
        config.setdefault("mcpServers", {})

        # Build our intended entry
        desired_entry = {
            **get_mcp_command_config(),
            **_make_meta_block(),
        }

        # Idempotency check (compare command + args + env, ignoring meta timestamp)
        existing = config["mcpServers"].get(_MCP_KEY)
        if existing and not force:
            existing_comparable = {
                k: v for k, v in existing.items() if k != "_locallens_meta"
            }
            desired_comparable = {
                k: v for k, v in desired_entry.items() if k != "_locallens_meta"
            }
            if existing_comparable == desired_comparable:
                return {
                    "status": "already_connected",
                    "config_path": str(config_path),
                    "command": desired_entry["command"],
                    "message": (
                        "LocalLens is already connected to Claude Desktop. "
                        "Restart Claude Desktop if tools aren't showing up."
                    ),
                    "backup_path": None,
                    "claude_needs_restart": False,
                }

        # Determine action label for result
        action = "updated" if existing else "installed"

        # Backup before modifying
        backup_path = _backup_config(config_path, label="backup")

        # Inject
        config["mcpServers"][_MCP_KEY] = desired_entry

        # Ensure the directory exists (e.g. config file doesn't exist yet)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        _atomic_write(config_path, config)

        _log.info(
            "LocalLens MCP connector %s → %s (method: %s)",
            action,
            config_path,
            detect_install_method(),
        )

        return {
            "status": action,
            "config_path": str(config_path),
            "command": desired_entry["command"],
            "message": (
                f"LocalLens MCP server {action} successfully. "
                "Please restart Claude Desktop to apply the changes."
            ),
            "backup_path": str(backup_path) if backup_path else None,
            "claude_needs_restart": True,
        }

    except Exception as exc:
        _log.exception("install_claude_connector failed")
        return {
            "status": "error",
            "config_path": str(get_claude_config_path()),
            "command": None,
            "message": f"Unexpected error: {exc}",
            "backup_path": None,
            "claude_needs_restart": False,
        }


def uninstall_claude_connector() -> Dict[str, Any]:
    """
    Remove the LocalLens MCP server entry from Claude Desktop's config.

    Does NOT remove any other mcpServer entries. If `locallens` is not
    present, returns a no-op result.

    Returns:
        {
          "status": "removed" | "not_connected" | "error",
          "config_path": "<path>",
          "message": "<human-readable summary>",
          "backup_path": "<path to backup>" | None,
          "claude_needs_restart": True | False,
        }
    """
    try:
        config_path = get_claude_config_path()
        config = _load_config(config_path)
        servers = config.get("mcpServers", {})

        if _MCP_KEY not in servers:
            return {
                "status": "not_connected",
                "config_path": str(config_path),
                "message": "LocalLens is not connected to Claude Desktop — nothing to remove.",
                "backup_path": None,
                "claude_needs_restart": False,
            }

        # Backup before modifying
        backup_path = _backup_config(config_path, label="backup")

        # Remove only our key
        del servers[_MCP_KEY]
        if not servers:
            # Clean up empty mcpServers key rather than leaving {}
            del config["mcpServers"]

        _atomic_write(config_path, config)
        _log.info("LocalLens MCP connector removed from %s", config_path)

        return {
            "status": "removed",
            "config_path": str(config_path),
            "message": (
                "LocalLens disconnected from Claude Desktop. "
                "Restart Claude Desktop to apply the changes."
            ),
            "backup_path": str(backup_path) if backup_path else None,
            "claude_needs_restart": True,
        }

    except Exception as exc:
        _log.exception("uninstall_claude_connector failed")
        return {
            "status": "error",
            "config_path": str(get_claude_config_path()),
            "message": f"Unexpected error: {exc}",
            "backup_path": None,
            "claude_needs_restart": False,
        }


def get_connection_status() -> Dict[str, Any]:
    """
    Return a rich status dict describing the current connection state.

    This is the function the LocalLens desktop UI and `--claude-status` CLI
    subcommand consume to drive button state (Connect / Disconnect / Error).

    Returns:
        {
          "connected": True | False,
          "claude_installed": True | False,
          "config_path": "<path>",
          "command": "<command>" | None,
          "install_method": "venv" | "uvx" | "bundled" | "global_pip",
          "binary_valid": True | False,
          "binary_reason": "<reason if invalid>" | None,
          "version": "<mcp version>",
          "installed_at": "<iso timestamp>" | None,
          "other_mcp_servers": ["name1", "name2", ...],
        }
    """
    config_path = get_claude_config_path()
    installed = is_claude_installed()
    binary_check = verify_mcp_binary()
    current = get_current_injection()
    connected = current is not None

    # Extract metadata from injected block if present
    meta = (current or {}).get("_locallens_meta", {})

    # List all other registered MCP servers for informational display
    other_servers: List[str] = []
    try:
        config = _load_config(config_path)
        other_servers = [
            k for k in config.get("mcpServers", {}).keys() if k != _MCP_KEY
        ]
    except Exception:
        pass

    return {
        "connected": connected,
        "claude_installed": installed,
        "config_path": str(config_path),
        "command": (current or {}).get("command"),
        "install_method": detect_install_method(),
        "binary_valid": binary_check["valid"],
        "binary_reason": binary_check.get("reason"),
        "version": meta.get("version", _MCP_VERSION),
        "installed_at": meta.get("installed_at"),
        "other_mcp_servers": other_servers,
    }
