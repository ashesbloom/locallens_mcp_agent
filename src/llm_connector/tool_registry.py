"""
LocalLens LLM Connector — Tool Registry
=========================================
Standalone synchronous implementations of every MCP tool for the Chat UI.

The Chat UI cannot use the MCP stdio protocol — it calls the LocalLens
FastAPI backend directly via httpx.  This module mirrors every tool from
  - mcp_server/tools/status.py
  - mcp_server/tools/queries.py
  - mcp_server/tools/actions.py
  - mcp_server/tools/pro_tools.py

Pro tools are gated behind license.is_pro_active() and return the same
upgrade prompt that the MCP @require_pro decorator returns.
"""

import inspect
import logging
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from mcp_server.config import get_auth_headers, get_locallens_url
from mcp_server.license import (
    activate_license,
    deactivate_license,
    get_license_info,
    is_pro_active,
    PRO_UPGRADE_MESSAGE,
)

# ---------------------------------------------------------------------------
#  Logger — stderr only (stdout is MCP's JSON-RPC channel)
# ---------------------------------------------------------------------------

_log = logging.getLogger("locallens_mcp.tool_registry")
if not _log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("[locallens-mcp] %(levelname)s: %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)
    _log.propagate = False


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT_S = 30
_MIN_POLL_INTERVAL_S = 0.5
_TERMINAL_STATUSES = frozenset({
    "complete", "done", "finished",
    "error", "aborted", "cancelled", "warning",
})


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _handle_error(exc: Exception) -> Dict[str, Any]:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        url = str(exc.response.url)
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text
        return {"error": detail, "status_code": status, "url": url}
    return {"error": str(exc)}


def _normalize_path(p: str) -> str:
    """Expand ~ and strip whitespace/quotes from a user-supplied path."""
    if not p:
        return p
    return os.path.expanduser(str(p).strip().strip("'").strip('"'))


# Placeholder paths the model hallucinates — never valid
_FAKE_PATH_FRAGMENTS = frozenset({
    "/Users/name", "/Users/username", "/Users/user",
    "/home/name", "/home/user", "/path/to",
    "~/", "/Users/mayank/",  # partial/guessed
})


def _looks_fake(path: str) -> bool:
    """Return True if the path looks like a model hallucination / placeholder."""
    if not path:
        return True
    p = path.lower().rstrip("/")
    # Fake if it literally is one of the placeholders, or starts with one
    for fake in _FAKE_PATH_FRAGMENTS:
        if p == fake.lower().rstrip("/") or p.startswith(fake.lower()):
            return True
    return False


def _resolve_path(path: str, preset_key: str) -> str:
    """
    Return a valid absolute path, falling back to the saved preset if needed.

    preset_key: "source_folder" | "destination_folder"

    Preset API returns: {"PresetName": {"source": "...", "destination": "..."}, ...}
    We look for the first preset whose source/destination exists on disk.
    """
    normalized = _normalize_path(path)
    if normalized and not _looks_fake(normalized) and os.path.exists(normalized):
        return normalized  # Path is real — use it as-is

    # Path is fake or doesn't exist — auto-fetch from saved presets
    _log.warning(
        "Path '%s' is invalid or fake — auto-fetching preset '%s'",
        path, preset_key,
    )
    try:
        presets = _request_json("GET", "/api/presets/paths", timeout_s=5)
        # Preset structure: {"PresetName": {"source": "...", "destination": "..."}}
        # Map our key names to the preset sub-keys
        sub_key = "source" if preset_key == "source_folder" else "destination"
        for preset_name, preset in presets.items():
            if not isinstance(preset, dict):
                continue
            candidate = preset.get(sub_key, "")
            if candidate and os.path.exists(candidate):
                _log.info(
                    "Auto-resolved '%s' -> preset '%s' %s = %s",
                    path, preset_name, sub_key, candidate,
                )
                return candidate
    except Exception as e:
        _log.error("Failed to fetch presets: %s", e)

    # Last resort: return normalized path (backend will produce a clear error)
    return normalized or path


def _pro_gate(func: Callable) -> Callable:
    """Synchronous Pro-gating wrapper for chat-UI tools."""
    def wrapper(*args, **kwargs) -> Dict[str, Any]:
        if not is_pro_active():
            return {
                "error": "pro_required",
                "tool": func.__name__,
                "message": PRO_UPGRADE_MESSAGE,
            }
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    # Preserve the original signature so inspect.signature() filtering works
    wrapper.__wrapped__ = func
    return wrapper


def _request_json(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
    auth: bool = False,
) -> Any:
    url = f"{get_locallens_url()}{path}"
    headers = get_auth_headers() if auth else {"Content-Type": "application/json"}
    with httpx.Client() as client:
        response = client.request(method, url, json=payload, headers=headers, timeout=timeout_s)
        response.raise_for_status()
        return response.json()


def _wait_for_completion(
    timeout_s: int = 900,
    poll_interval_s: float = 1.0,
) -> Dict[str, Any]:
    """
    Synchronous polling loop that waits for a backend job to reach a terminal state.

    Fixed: also exits on terminal status even when has_started=False, handling jobs
    that complete between the trigger call and the first poll (race condition).
    """
    safe_interval = max(_MIN_POLL_INTERVAL_S, poll_interval_s)
    start = time.monotonic()
    last_status: Dict[str, Any] = {}
    has_started = False
    poll_count = 0

    with httpx.Client() as client:
        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout_s:
                _log.warning("Wait timed out after %.1fs (limit=%ds)", elapsed, timeout_s)
                return {
                    "status": "timeout",
                    "elapsed_seconds": round(elapsed, 1),
                    "last_status": last_status,
                }

            try:
                r = client.get(f"{get_locallens_url()}/api/job-status", timeout=5)
                r.raise_for_status()
                last_status = r.json()
            except Exception as poll_err:
                _log.error("Failed to poll /api/job-status: %s", poll_err)
                time.sleep(safe_interval)
                continue

            poll_count += 1
            is_active = bool(last_status.get("is_active", False))
            status = str(last_status.get("status", "")).strip().lower()
            progress = last_status.get("progress", 0)

            if is_active:
                has_started = True
                if poll_count % 5 == 0:
                    _log.info("Job running: status=%s progress=%s%% elapsed=%.0fs",
                              status, progress, elapsed)

            # Always exit on terminal status (fixes race: job done before first poll)
            if status in _TERMINAL_STATUSES:
                _log.info("Job finished: status=%s elapsed=%.1fs", status, elapsed)
                return last_status

            # Fallback exit: was active, now gone, not an idle/init state
            if has_started and not is_active and status not in {"running", "ready", "idle", ""}:
                _log.info("Job ended (fallback): status=%s elapsed=%.1fs", status, elapsed)
                return last_status

            time.sleep(safe_interval)


# ===================================================================
#  FREE TOOLS — Status & Telemetry
# ===================================================================

def check_app_status() -> Dict[str, Any]:
    """Check if LocalLens is running and healthy."""
    try:
        status: Dict[str, Any] = {}
        with httpx.Client() as client:
            r1 = client.get(f"{get_locallens_url()}/api/health", timeout=5)
            if r1.status_code == 200:
                status["health"] = r1.json()

            r2 = client.get(f"{get_locallens_url()}/api/check-dependencies", timeout=5)
            if r2.status_code == 200:
                status["dependencies"] = r2.json()

        status["license"] = get_license_info()
        return status if status else {"status": "offline", "message": "LocalLens is not responding"}
    except Exception:
        return {"status": "offline", "message": "LocalLens is not running or accessible"}


def get_stats() -> Dict[str, Any]:
    """Get a snapshot of the LocalLens installation."""
    try:
        stats = _request_json("GET", "/api/stats", timeout_s=8)
        if isinstance(stats, dict):
            stats["license"] = get_license_info()
        return stats
    except Exception as exc:
        return {"error": str(exc), "message": "Could not retrieve stats"}


def get_job_progress() -> Dict[str, Any]:
    """Check the current (or most recent) background job status."""
    try:
        return _request_json("GET", "/api/job-status", timeout_s=8)
    except Exception as exc:
        return {"error": str(exc)}


# ===================================================================
#  FREE TOOLS — Queries
# ===================================================================

def get_path_presets() -> Dict[str, Any]:
    """List saved source/destination path presets."""
    try:
        return _request_json("GET", "/api/presets/paths", timeout_s=8)
    except Exception as exc:
        return _handle_error(exc)


def get_enrolled_faces() -> Dict[str, Any]:
    """List enrolled people and their image counts."""
    try:
        return _request_json("GET", "/api/enrolled-faces", timeout_s=8)
    except Exception as exc:
        return _handle_error(exc)


def get_metadata_overview(
    source_folder: str,
    ignore_list: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Scan a folder and summarize dates, locations, and people found."""
    source_folder = _resolve_path(source_folder, "source_folder")
    if not source_folder:
        return {"error": "source_folder is required"}
    payload = {"source_folder": source_folder, "ignore_list": ignore_list or []}
    try:
        return _request_json("POST", "/api/metadata-overview", payload, timeout_s=30)
    except Exception as exc:
        return _handle_error(exc)


# ===================================================================
#  FREE TOOLS — Actions
# ===================================================================

def start_sorting(
    source_folder: str,
    destination_folder: str,
    primary_sort: str = "Date",
    face_mode: str = "balanced",
    maintain_hierarchy: bool = True,
    ignore_list: Optional[List[str]] = None,
    operation_mode: str = "copy",  # SAFE default — never move unless user explicitly asks
    wait_for_completion: bool = True,  # Block until done; LLM doesn't need to manually poll
    poll_interval_s: float = 1.0,
    timeout_s: int = 900,
) -> Dict[str, Any]:
    """Trigger a sorting job on a source folder. Optionally wait for completion."""
    source_folder = _resolve_path(source_folder, "source_folder")
    destination_folder = _resolve_path(destination_folder, "destination_folder")
    if not source_folder or not destination_folder:
        return {"error": "source_folder and destination_folder are required"}

    normalized_sort = (primary_sort or "").strip().lower()
    payload = {
        "source_folder": source_folder,
        "destination_folder": destination_folder,
        "sorting_options": {
            "primary_sort": primary_sort,
            "maintain_hierarchy": maintain_hierarchy,
        },
        "ignore_list": ignore_list or [],
        "operation_mode": operation_mode,
    }

    if normalized_sort in {"faces", "face", "people"}:
        payload["sorting_options"]["face_mode"] = face_mode

    try:
        result = _request_json("POST", "/api/start-sorting", payload, timeout_s=10)
        if wait_for_completion:
            return _wait_for_completion(timeout_s, poll_interval_s)
        return result
    except Exception as exc:
        return _handle_error(exc)


def abort_job() -> Dict[str, Any]:
    """Abort any running job."""
    try:
        return _request_json("POST", "/api/abort-process", timeout_s=5)
    except Exception as exc:
        return _handle_error(exc)


# ===================================================================
#  LICENSE TOOLS — Always available
# ===================================================================

def activate_pro_license(license_key: str) -> Dict[str, Any]:
    """Activate a Pro license key. Requires one-time internet connection."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an existing event loop (e.g. Gradio) — run in a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, activate_license(license_key)).result()
        return loop.run_until_complete(activate_license(license_key))
    except RuntimeError:
        return asyncio.run(activate_license(license_key))


def get_license_status() -> Dict[str, Any]:
    """Check the current license tier (Free or Pro). No internet required."""
    return get_license_info()


def revoke_pro_license() -> Dict[str, Any]:
    """Revoke the current Pro license, reverting to Free tier."""
    return deactivate_license()


# ===================================================================
#  PRO TOOLS — Require active license
# ===================================================================

@_pro_gate
def start_find_group(
    source_folder: str,
    destination_folder: str,
    folder_name: str,
    years: Optional[List[str]] = None,
    months: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    people: Optional[List[str]] = None,
    face_mode: str = "fast",
    ignore_list: Optional[List[str]] = None,
    wait_for_completion: bool = True,  # Block until done; LLM doesn't need to manually poll
    poll_interval_s: float = 1.0,
    timeout_s: int = 900,
) -> Dict[str, Any]:
    """⚡ PRO — Find and group photos matching specific criteria into a named subfolder."""
    source_folder = _resolve_path(source_folder, "source_folder")
    destination_folder = _resolve_path(destination_folder, "destination_folder")
    payload = {
        "source_folder": source_folder,
        "destination_folder": destination_folder,
        "find_config": {
            "folderName": folder_name,
            "years": years or [],
            "months": months or [],
            "locations": locations or [],
            "people": people or [],
        },
        "ignore_list": ignore_list or [],
    }
    if people:
        payload["find_config"]["face_mode"] = face_mode

    try:
        result = _request_json("POST", "/api/start-find-group", payload, timeout_s=10)
        if wait_for_completion:
            return _wait_for_completion(timeout_s, poll_interval_s)
        return result
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def add_face_enroll(
    enrollments: dict,
    wait_for_completion: bool = True,
    poll_interval_s: float = 1.0,
    timeout_s: int = 900,
) -> Dict[str, Any]:
    """⚡ PRO — Enroll one or more people into the face recognition system."""
    supported_exts = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp")
    people_to_enroll = []
    skipped = []

    if not isinstance(enrollments, dict):
        return {"error": "The 'enrollments' argument must be a JSON object (dictionary)."}

    # Handle nested wrapper
    if "enrollments" in enrollments and isinstance(enrollments["enrollments"], dict):
        enrollments = enrollments["enrollments"]

    for person_name, folder_path in enrollments.items():
        person_name = str(person_name).strip()
        if person_name in {"wait_for_completion", "poll_interval_s", "timeout_s"}:
            continue

        clean_path = str(folder_path).strip().strip("'").strip('"')
        normalized_folder = os.path.expanduser(clean_path)

        if not person_name:
            skipped.append({"reason": "empty person_name"})
            continue
        if not normalized_folder or not os.path.isdir(normalized_folder):
            skipped.append({"person": person_name, "reason": f"folder not found: {normalized_folder}"})
            continue

        image_paths = []
        for root, _dirs, files in os.walk(normalized_folder):
            for file in files:
                if file.lower().endswith(supported_exts):
                    image_paths.append(os.path.join(root, file))

        if image_paths:
            people_to_enroll.append({"person_name": person_name, "image_paths": image_paths})
        else:
            skipped.append({"person": person_name, "reason": "no supported images found in folder"})

    if not people_to_enroll:
        return {"error": "No valid enrollments — check folder paths and image formats.", "skipped": skipped}

    payload = {"people_to_enroll": people_to_enroll}
    try:
        result = _request_json("POST", "/api/add-person", payload, timeout_s=10)
        if wait_for_completion:
            result = _wait_for_completion(timeout_s, poll_interval_s)
        if skipped:
            result["skipped"] = skipped
        return result
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def find_duplicates(
    source_folder: str,
    ignore_list: Optional[List[str]] = None,
    similarity_threshold: float = 0.95,
) -> Dict[str, Any]:
    """⚡ PRO — Scan a folder for duplicate/near-duplicate photos using perceptual hashing."""
    normalized_source = os.path.expanduser(source_folder or "")
    if not normalized_source or not os.path.isdir(normalized_source):
        return {"error": f"Source path is not a valid directory: {normalized_source}"}

    payload = {
        "source_folder": normalized_source,
        "ignore_list": ignore_list or [],
        "similarity_threshold": similarity_threshold,
    }
    try:
        return _request_json("POST", "/api/find-duplicates", payload, timeout_s=120)
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def export_report(
    source_folder: str,
    output_path: str = "",
    ignore_list: Optional[List[str]] = None,
    include_metadata: bool = True,
    include_face_summary: bool = True,
) -> Dict[str, Any]:
    """⚡ PRO — Generate a detailed JSON report about a photo folder."""
    normalized_source = os.path.expanduser(source_folder or "")
    if not normalized_source or not os.path.isdir(normalized_source):
        return {"error": f"Source path is not a valid directory: {normalized_source}"}

    payload = {
        "source_folder": normalized_source,
        "ignore_list": ignore_list or [],
        "output_path": output_path,
        "include_metadata": include_metadata,
        "include_face_summary": include_face_summary,
    }
    try:
        return _request_json("POST", "/api/export-report", payload, timeout_s=60)
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def create_active_folder(
    source_folder: str,
    destination_folder: str,
    primary_sort: str = "Date",
    operation_mode: str = "copy",
    face_mode: str = "balanced",
    maintain_hierarchy: bool = True,
    ignore_list: Optional[List[str]] = None,
    debounce_seconds: int = 5,
) -> Dict[str, Any]:
    """⚡ PRO — Create a real-time Active Folder for instant photo organization."""
    config = {
        "mode": "active",
        "source_folder": source_folder,
        "destination_folder": destination_folder,
        "primary_sort": primary_sort,
        "face_mode": face_mode,
        "maintain_hierarchy": maintain_hierarchy,
        "operation_mode": operation_mode,
        "ignore_list": ignore_list or [],
        "debounce_seconds": debounce_seconds,
    }
    try:
        result = _request_json("POST", "/api/scheduler/create", config, timeout_s=5)
        result["privacy_note"] = (
            "🔒 Your active folder config is stored locally at ~/.config/LocalLens/schedules.json. "
            "No data leaves your computer. You can delete it anytime."
        )
        return result
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def schedule_auto_organize(
    source_folder: str,
    destination_folder: str,
    primary_sort: str = "Date",
    interval_hours: int = 24,
    interval_minutes: int = 0,
    operation_mode: str = "copy",
    face_mode: str = "balanced",
    maintain_hierarchy: bool = True,
    ignore_list: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """⚡ PRO — Schedule periodic background photo organization sweeps."""
    config = {
        "mode": "scheduled",
        "source_folder": source_folder,
        "destination_folder": destination_folder,
        "primary_sort": primary_sort,
        "face_mode": face_mode,
        "maintain_hierarchy": maintain_hierarchy,
        "operation_mode": operation_mode,
        "ignore_list": ignore_list or [],
        "interval_hours": interval_hours,
        "interval_minutes": interval_minutes,
    }
    try:
        result = _request_json("POST", "/api/scheduler/create", config, timeout_s=5)
        result["privacy_note"] = (
            "🔒 Your schedule config is stored locally at ~/.config/LocalLens/schedules.json. "
            "No data leaves your computer. You can delete any schedule anytime."
        )
        return result
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def list_schedules() -> Dict[str, Any]:
    """⚡ PRO — List all auto-organize schedules and active folders."""
    try:
        data = _request_json("GET", "/api/scheduler/list", timeout_s=5)
        running = data.get("daemon_running", False)
        schedules = data.get("schedules", [])

        for s in schedules:
            s["being_monitored"] = running and s.get("status") == "active"

        active_count = sum(1 for s in schedules if s.get("status") == "active")
        monitored_count = sum(1 for s in schedules if s.get("being_monitored"))

        data["schedules"] = schedules
        data["summary"] = (
            f"Daemon is {'✅ RUNNING (PID ' + str(data.get('daemon_pid')) + ')' if running else '🔴 STOPPED'}. "
            f"{active_count} schedule(s) configured, {monitored_count} actively being watched."
        )
        return data
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def manage_schedule(
    schedule_id: str,
    action: str,
) -> Dict[str, Any]:
    """⚡ PRO — Manage an existing schedule: pause, resume, delete, or trigger."""
    valid_actions = {"pause", "resume", "delete", "trigger"}
    if action not in valid_actions:
        return {
            "error": f"Unknown action '{action}'. Valid: {', '.join(sorted(valid_actions))}",
        }

    try:
        if action == "delete":
            return _request_json("DELETE", f"/api/scheduler/{schedule_id}", timeout_s=5)
        elif action == "pause":
            return _request_json("POST", f"/api/scheduler/{schedule_id}/pause", timeout_s=5)
        elif action == "resume":
            return _request_json("POST", f"/api/scheduler/{schedule_id}/resume", timeout_s=5)
        elif action == "trigger":
            return _request_json("POST", f"/api/scheduler/{schedule_id}/trigger", timeout_s=5)
    except Exception as exc:
        return _handle_error(exc)


@_pro_gate
def smart_album_suggestions(
    max_suggestions: int = 8,
    time_range_months: int = 24,
    include_persona_context: bool = True,
) -> Dict[str, Any]:
    """⚡ PRO — Get personalized album suggestions based on your photo history."""
    payload = {
        "max_suggestions": max(1, min(20, max_suggestions)),
        "time_range_months": max(1, min(60, time_range_months)),
        "include_persona_context": include_persona_context,
    }
    try:
        result = _request_json("POST", "/api/smart-albums/suggest", payload, timeout_s=30, auth=True)

        # Build user-friendly guidance
        suggestions = result.get("suggestions", [])
        needs_survey = result.get("needs_survey", False)
        needs_photos = result.get("needs_more_photos", False)
        parts = []
        if needs_photos:
            parts.append("📸 Organize some photos first! Smart Albums learn from your sort jobs.")
        if needs_survey:
            parts.append("💡 Take the persona survey for more personalized names.")
        if suggestions:
            parts.append(f"✅ Found {len(suggestions)} album suggestion(s).")
        result["guidance"] = " ".join(parts)
        result["privacy_note"] = (
            "🔒 All metadata and persona data stored locally at "
            "~/.config/LocalLens/metadata_store.db — nothing leaves your machine."
        )
        return result
    except Exception as exc:
        return _handle_error(exc)


# ===================================================================
#  TOOL SPECS — OpenAI function-calling format for Ollama
# ===================================================================

TOOL_SPECS: List[Dict[str, Any]] = [
    # ── Status ──
    {
        "type": "function",
        "function": {
            "name": "check_app_status",
            "description": "Check if LocalLens is running. Call first in every conversation.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Get LocalLens version, enrolled faces count, and license tier.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_progress",
            "description": "Check current background job status. Call after any job until is_active=false.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── Queries ──
    {
        "type": "function",
        "function": {
            "name": "get_path_presets",
            "description": "List saved source/destination path presets.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_enrolled_faces",
            "description": "List enrolled people for face recognition. Call before any People sort.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metadata_overview",
            "description": "Scan a folder and summarize dates, locations, people. Call BEFORE start_sorting or start_find_group.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_folder": {"type": "string", "description": "Folder to scan"},
                    "ignore_list": {"type": "array", "items": {"type": "string"}, "description": "Subfolders to skip"},
                },
                "required": ["source_folder"],
            },
        },
    },
    # ── Actions ──
    {
        "type": "function",
        "function": {
            "name": "start_sorting",
            "description": "Organize photos. primary_sort: Date|Location|People|Hybrid. operation_mode: copy (safe) or move.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_folder": {"type": "string", "description": "Folder to sort"},
                    "destination_folder": {"type": "string", "description": "Output folder"},
                    "primary_sort": {"type": "string", "description": "Date, Location, People, or Hybrid"},
                    "face_mode": {"type": "string", "description": "fast, balanced, or accurate (People sort only)"},
                    "maintain_hierarchy": {"type": "boolean"},
                    "ignore_list": {"type": "array", "items": {"type": "string"}},
                    "operation_mode": {"type": "string", "description": "copy (safe) or move"},
                    "wait_for_completion": {"type": "boolean", "description": "If true, blocks until the job finishes"},
                    "poll_interval_s": {"type": "number", "description": "Seconds between status polls (min 0.5)"},
                    "timeout_s": {"type": "integer", "description": "Max wait time in seconds (default 900)"},
                },
                "required": ["source_folder", "destination_folder"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abort_job",
            "description": "Abort any currently running job.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── License ──
    {
        "type": "function",
        "function": {
            "name": "activate_pro_license",
            "description": "Activate a Pro license key (one-time internet required).",
            "parameters": {
                "type": "object",
                "properties": {
                    "license_key": {"type": "string", "description": "License key"},
                },
                "required": ["license_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_license_status",
            "description": "Check current license tier (Free or Pro). Offline.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "revoke_pro_license",
            "description": "Remove Pro license and revert to Free tier.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── Pro: Find & Group ──
    {
        "type": "function",
        "function": {
            "name": "start_find_group",
            "description": "PRO: Find photos matching date/location/people filters and copy to a named subfolder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_folder": {"type": "string"},
                    "destination_folder": {"type": "string"},
                    "folder_name": {"type": "string", "description": "Name of output subfolder"},
                    "years": {"type": "array", "items": {"type": "string"}, "description": "4-digit year strings, e.g. ['2024']"},
                    "months": {"type": "array", "items": {"type": "string"}, "description": "2-digit month strings, e.g. ['01']"},
                    "locations": {"type": "array", "items": {"type": "string"}, "description": "Location strings, e.g. ['IN/Uttar-Pradesh/Lucknow']"},
                    "people": {"type": "array", "items": {"type": "string"}, "description": "Enrolled person names"},
                    "face_mode": {"type": "string", "description": "fast or accurate"},
                    "ignore_list": {"type": "array", "items": {"type": "string"}},
                    "wait_for_completion": {"type": "boolean"},
                    "poll_interval_s": {"type": "number"},
                    "timeout_s": {"type": "integer"},
                },
                "required": ["source_folder", "destination_folder", "folder_name"],
            },
        },
    },
    # ── Pro: Face Enrollment ──
    {
        "type": "function",
        "function": {
            "name": "add_face_enroll",
            "description": "PRO: Enroll people for face recognition. Pass {\"Name\": \"/path/to/folder\"}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enrollments": {
                        "type": "object",
                        "description": "Map of person name → folder path with reference photos",
                    },
                    "wait_for_completion": {"type": "boolean"},
                    "poll_interval_s": {"type": "number"},
                    "timeout_s": {"type": "integer"},
                },
                "required": ["enrollments"],
            },
        },
    },
    # ── Pro: Duplicates ──
    {
        "type": "function",
        "function": {
            "name": "find_duplicates",
            "description": "PRO: Find duplicate/near-duplicate photos using perceptual hashing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_folder": {"type": "string"},
                    "ignore_list": {"type": "array", "items": {"type": "string"}},
                    "similarity_threshold": {"type": "number", "description": "0.0–1.0, default 0.95"},
                },
                "required": ["source_folder"],
            },
        },
    },
    # ── Pro: Export Report ──
    {
        "type": "function",
        "function": {
            "name": "export_report",
            "description": "PRO: Generate a detailed JSON report of a photo folder's contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_folder": {"type": "string"},
                    "output_path": {"type": "string"},
                    "ignore_list": {"type": "array", "items": {"type": "string"}},
                    "include_metadata": {"type": "boolean"},
                    "include_face_summary": {"type": "boolean"},
                },
                "required": ["source_folder"],
            },
        },
    },
    # ── Pro: Active Folder ──
    {
        "type": "function",
        "function": {
            "name": "create_active_folder",
            "description": "PRO: Watch a folder in real-time and organize photos the moment they appear.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_folder": {"type": "string"},
                    "destination_folder": {"type": "string"},
                    "primary_sort": {"type": "string", "description": "Date, Location, or People"},
                    "operation_mode": {"type": "string", "description": "copy (safe) or move"},
                    "face_mode": {"type": "string"},
                    "maintain_hierarchy": {"type": "boolean"},
                    "ignore_list": {"type": "array", "items": {"type": "string"}},
                    "debounce_seconds": {"type": "integer"},
                },
                "required": ["source_folder", "destination_folder"],
            },
        },
    },
    # ── Pro: Schedule Auto Organize ──
    {
        "type": "function",
        "function": {
            "name": "schedule_auto_organize",
            "description": "PRO: Schedule recurring background photo organization every N hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_folder": {"type": "string"},
                    "destination_folder": {"type": "string"},
                    "primary_sort": {"type": "string"},
                    "interval_hours": {"type": "integer", "description": "Hours between sweeps (default 24)"},
                    "interval_minutes": {"type": "integer", "description": "Additional minutes (default 0)"},
                    "operation_mode": {"type": "string"},
                    "face_mode": {"type": "string"},
                    "maintain_hierarchy": {"type": "boolean"},
                    "ignore_list": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["source_folder", "destination_folder"],
            },
        },
    },
    # ── Pro: List Schedules ──
    {
        "type": "function",
        "function": {
            "name": "list_schedules",
            "description": "PRO: List all auto-organize schedules and active folders.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── Pro: Manage Schedule ──
    {
        "type": "function",
        "function": {
            "name": "manage_schedule",
            "description": "PRO: Pause, resume, delete, or trigger an existing schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "string", "description": "Schedule ID or 'daemon'"},
                    "action": {"type": "string", "description": "pause, resume, delete, trigger, start_daemon, or stop_daemon"},
                },
                "required": ["schedule_id", "action"],
            },
        },
    },
    # ── Pro: Smart Album Suggestions ──
    {
        "type": "function",
        "function": {
            "name": "smart_album_suggestions",
            "description": "PRO: Get personalized album suggestions based on photo history and persona profile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_suggestions": {"type": "integer", "description": "Max suggestions (default 8)"},
                    "time_range_months": {"type": "integer", "description": "Months to look back (default 24)"},
                    "include_persona_context": {"type": "boolean", "description": "Use persona profile (default true)"},
                },
                "required": [],
            },
        },
    },
]


# ===================================================================
#  DISPATCH MAP
# ===================================================================

_TOOL_DISPATCH: Dict[str, Callable] = {
    # Free — Status
    "check_app_status": check_app_status,
    "get_stats": get_stats,
    "get_job_progress": get_job_progress,
    # Free — Queries
    "get_path_presets": get_path_presets,
    "get_enrolled_faces": get_enrolled_faces,
    "get_metadata_overview": get_metadata_overview,
    # Free — Actions
    "start_sorting": start_sorting,
    "abort_job": abort_job,
    # License management
    "activate_pro_license": activate_pro_license,
    "get_license_status": get_license_status,
    "revoke_pro_license": revoke_pro_license,
    # Pro tools
    "start_find_group": start_find_group,
    "add_face_enroll": add_face_enroll,
    "find_duplicates": find_duplicates,
    "export_report": export_report,
    "create_active_folder": create_active_folder,
    "schedule_auto_organize": schedule_auto_organize,
    "list_schedules": list_schedules,
    "manage_schedule": manage_schedule,
    "smart_album_suggestions": smart_album_suggestions,
}


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a tool call by name, filtering to known arguments."""
    tool_fn = _TOOL_DISPATCH.get(name)
    if not tool_fn:
        return {"error": "unknown_tool", "message": f"Tool '{name}' is not available."}

    args = arguments or {}
    if not isinstance(args, dict):
        return {"error": "invalid_arguments", "message": "Tool arguments must be an object."}

    # Use the wrapped function's signature for Pro-gated tools
    sig_fn = getattr(tool_fn, "__wrapped__", tool_fn)
    signature = inspect.signature(sig_fn)
    filtered = {key: value for key, value in args.items() if key in signature.parameters}

    try:
        return tool_fn(**filtered)
    except TypeError as exc:
        return {"error": "invalid_arguments", "message": str(exc)}
    except Exception as exc:
        return {"error": "tool_failed", "message": str(exc)}
