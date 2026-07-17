import os
import asyncio
import time
import logging
import sys
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List, Optional

from ..config import get_locallens_url
from ..license import require_pro

# Suppress noisy httpx request logs from polluting stderr
logging.getLogger("httpx").setLevel(logging.WARNING)

# MCP agent logger — MUST write only to stderr.
# stdout is the MCP stdio JSON-RPC channel; any raw text there breaks the protocol.
_log = logging.getLogger("locallens_mcp.actions")
if not _log.handlers:
    _stderr_handler = logging.StreamHandler(sys.stderr)
    _stderr_handler.setFormatter(logging.Formatter("[locallens-mcp] %(levelname)s: %(message)s"))
    _log.addHandler(_stderr_handler)
    _log.setLevel(logging.INFO)
    _log.propagate = False  # Don't bubble up to root logger which may write to stdout

# Statuses that definitively signal a job has finished on the backend.
# Used to unambiguously exit the polling loop.
_TERMINAL_STATUSES = frozenset({
    "complete", "done", "finished",
    "error", "aborted", "cancelled", "warning"
})

# Minimum safe polling interval — prevents tight loops when user provides
# a zero or negative poll_interval_s (asyncio.sleep(<=0) returns instantly).
_MIN_POLL_INTERVAL_S = 0.5


def _handle_error(e: Exception) -> Dict[str, Any]:
    if isinstance(e, httpx.HTTPStatusError):
        response = e.response
        try:
            return {"error": response.json()}
        except ValueError:
            return {"error": response.text}
    return {"error": str(e)}


async def _wait_for_completion(
    client: httpx.AsyncClient,
    timeout_s: int,
    poll_interval_s: float
) -> Dict[str, Any]:
    """
    Polls /api/job-status until the backend job reaches a terminal state.

    Exit conditions (checked in order):
      1. Timeout exceeded → returns timeout result
      2. `is_active` True at any point → job has started; continue waiting
      3. `status` in TERMINAL_STATUSES after job has started → exit
      4. Fallback: job started + is_active=False + status not in active states → exit

    Stale state guard:
      If the very first poll already shows a terminal status and is_active=False,
      this is state from a *previous* job. We require the backend to transition
      through `is_active=True` (i.e., the new job must actually start) before
      we consider the terminal status as belonging to the current job.
    """
    # Clamp poll_interval_s: asyncio.sleep() with 0 or negative values returns
    # instantly, creating a tight loop that hammers the backend indefinitely.
    safe_interval = max(_MIN_POLL_INTERVAL_S, poll_interval_s)
    if safe_interval != poll_interval_s:
        _log.warning(
            f"poll_interval_s={poll_interval_s!r} is below minimum "
            f"{_MIN_POLL_INTERVAL_S}s — clamped to {safe_interval}s."
        )

    start = time.monotonic()
    last_status: Dict[str, Any] = {}
    has_started = False           # True once the job has been seen as active
    last_backend_message: Optional[str] = None

    while True:
        # --- Timeout check (always first) ---
        elapsed = time.monotonic() - start
        if elapsed > timeout_s:
            _log.warning(f"Wait timed out after {elapsed:.1f}s (limit={timeout_s}s)")
            return {
                "status": "timeout",
                "elapsed_seconds": round(elapsed, 1),
                "last_status": last_status
            }

        # --- Poll backend job status ---
        try:
            r = await client.get(f"{get_locallens_url()}/api/job-status", timeout=5)
            r.raise_for_status()
            last_status = r.json()
        except Exception as poll_err:
            # Don't crash the loop on a transient network hiccup — just log and retry
            _log.error(f"Failed to poll /api/job-status: {poll_err}")
            await asyncio.sleep(safe_interval)
            continue

        is_active: bool = bool(last_status.get("is_active", False))
        status: str = str(last_status.get("status", "")).strip().lower()
        backend_message: str = str(last_status.get("message", "")).strip()

        # --- Forward unique backend messages to stderr (NEVER stdout) ---
        if backend_message and backend_message != last_backend_message:
            _log.info(f"BACKEND: {backend_message}")
            last_backend_message = backend_message

        # --- Detect job start ---
        # We only mark the job as started when the backend reports it is actively
        # running (is_active=True). This avoids mistaking the stale terminal
        # state of a *previous* job for the current job already being done.
        if is_active:
            has_started = True

        # --- Detect job completion (only after confirmed start) ---
        if has_started:
            # Primary exit: explicit terminal status from backend
            if status in _TERMINAL_STATUSES:
                _log.info(
                    f"Job finished — status='{status}', "
                    f"elapsed={elapsed:.1f}s, progress={last_status.get('progress')}%"
                )
                return last_status

            # Fallback exit: no longer active and not in any "running" state
            if not is_active and status not in {"running", "ready", "idle", ""}:
                _log.info(
                    f"Job ended (fallback) — status='{status}', elapsed={elapsed:.1f}s"
                )
                return last_status

        await asyncio.sleep(safe_interval)


def register_actions(mcp: FastMCP):

    @mcp.tool()
    async def start_sorting(
        source_folder: str,
        destination_folder: str,
        primary_sort: str = "Date",
        face_mode: str = "balanced",
        maintain_hierarchy: bool = False,
        ignore_list: Optional[List[str]] = None,
        operation_mode: str = "copy",
        wait_for_completion: bool = False,
        poll_interval_s: float = 1.0,
        timeout_s: int = 900
    ) -> Dict[str, Any]:
        """
        Trigger photo organization on a specific source directory and output to a destination directory.

        YOU HAVE FULL ACCESS TO THE USER'S FILESYSTEM. Do NOT say you cannot access folders.
        Just call this tool with the paths the user provides.

        Parameters:
        - primary_sort: MUST be exactly "Date", "Location", or "People" — NEVER "Faces" or "Face"
        - face_mode: "fast" (HOG), "balanced", "accurate" (CNN) — only used when primary_sort is "People"
            → If user says "be quick" / "fast" → use "fast"
            → If user says "accurate" / "best quality" → use "accurate"
            → Otherwise default to "balanced"
        - operation_mode: "copy" (DEFAULT — safe) or "move" (destructive — ONLY if user explicitly asks)
        - maintain_hierarchy: False by default (flattens into sort groups). Set True only if user asks.
        - wait_for_completion: if True, waits and polls until the job finishes before returning

        ⛔ CRITICAL SAFETY RULES FOR LLMs — VIOLATION = DATA LOSS:
        1. NEVER INVENT OR FABRICATE A DESTINATION PATH. Only use:
           - A path the user EXPLICITLY typed in the conversation
           - A path returned by get_path_presets()
           Making up paths like "source_sorted_by_X" or "source_output" is FORBIDDEN.
           If user hasn't provided a destination → call get_path_presets() or ASK the user.
        2. operation_mode ALWAYS defaults to "copy". Tell user: "I'll copy to keep originals safe."
           NEVER use "move" unless user EXPLICITLY says "move" / "don't keep copies".
        3. BEFORE calling this, call analyse_folder() first to check for subfolders.
           If subfolders exist → present them and ask which to ignore.
           If no subfolders → proceed directly.
        4. This fires a background task. If wait_for_completion is False,
           you MUST repeatedly call get_job_progress() to report progress.
        5. primary_sort MUST be "Date", "Location", or "People". Code auto-corrects
           "Faces" → "People" but always use the correct value.
        """
        # --- SAFETY GUARD: Validate source exists ---
        normalized_source = os.path.expanduser(source_folder or "")
        if not normalized_source or not os.path.isdir(normalized_source):
            return {"error": f"Source path does not exist or is not a directory: {source_folder}"}

        # --- SAFETY GUARD: Validate destination exists ---
        # CRITICAL: If the destination doesn't exist, the LLM likely fabricated it.
        # We refuse to create arbitrary paths — the user must provide a real one.
        normalized_dest = os.path.expanduser(destination_folder or "")
        if not normalized_dest or not os.path.isdir(normalized_dest):
            return {
                "error": f"Destination path does not exist: {destination_folder}. "
                         "You MUST use a path the user explicitly provided or one from get_path_presets(). "
                         "NEVER fabricate or invent destination paths. Ask the user for a valid destination."
            }

        # --- SAFETY GUARD: source != destination ---
        if os.path.realpath(normalized_source) == os.path.realpath(normalized_dest):
            return {
                "error": "Source and destination cannot be the same folder. "
                         "Ask the user for a different destination path."
            }

        normalized_sort = (primary_sort or "").strip().lower()

        # LLM BUG GUARD: "Faces" and "Face" are invalid values — the correct value is "People"
        # Map common LLM mistakes to the correct backend value
        if normalized_sort in {"faces", "face"}:
            primary_sort = "People"
            normalized_sort = "people"

        payload = {
            "source_folder": normalized_source,
            "destination_folder": normalized_dest,
            "sorting_options": {
                "primary_sort": primary_sort,
                "maintain_hierarchy": maintain_hierarchy
            },
            "ignore_list": ignore_list or [],
            "operation_mode": operation_mode
        }

        # Only include face_mode when actually sorting by people
        if normalized_sort == "people":
            payload["sorting_options"]["face_mode"] = face_mode

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{get_locallens_url()}/api/start-sorting",
                    json=payload,
                    timeout=10
                )
                r.raise_for_status()
                if wait_for_completion:
                    result = await _wait_for_completion(client, timeout_s, poll_interval_s)
                    # Inject contextual next-action suggestions so the LLM can
                    # proactively offer them to the user as follow-up options.
                    if result.get("status") == "complete":
                        result["next_actions"] = [
                            {
                                "action": "open_folder",
                                "label": "\U0001f4c2 Open destination folder",
                                "hint": "Call open_folder(folder_path=destination_folder) to show results in Finder/Explorer",
                                "args": {"folder_path": normalized_dest},
                            },
                            {
                                "action": "remember_paths",
                                "label": "\U0001f4be Save these paths for next time",
                                "hint": "Call remember_paths() to save source+destination so you never have to type them again",
                                "args": {"source": normalized_source, "destination": normalized_dest},
                            },
                        ]
                        result["guidance"] = (
                            "Sort complete! Offer the user these next steps: "
                            "(1) open_folder to view results, "
                            "(2) remember_paths to save these paths for future sorts."
                        )
                    return result
                return r.json()
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    async def start_find_group(
        source_folder: str,
        destination_folder: str,
        folder_name: str,
        years: Optional[List[str]] = None,
        months: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        people: Optional[List[str]] = None,
        face_mode: Optional[str] = "balanced",
        ignore_list: Optional[List[str]] = None,
        wait_for_completion: bool = False,
        poll_interval_s: float = 1.0,
        timeout_s: int = 900
    ) -> Dict[str, Any]:
        """
        Find and extract photos matching specific criteria (people + locations + dates).
        Use this when the user asks to FIND photos — NOT to sort/organize all photos.

        WHEN TO USE THIS (not start_sorting):
        - "find photos of Mayank in Lucknow" → start_find_group
        - "get all my July photos" → start_find_group
        - "find pics of Mayank from 2024" → start_find_group
        - "sort my photos by location" → start_sorting (NOT this tool)

        HOW destination_folder + folder_name WORK:
        Results go into: destination_folder/folder_name/
        Example: destination="/Users/x/output", folder_name="home" → results in /Users/x/output/home/
        
        ⚠️ PATH PARSING RULE: If user says "put results in /Users/x/output/home":
        - destination_folder = "/Users/x/output" (the PARENT — must already exist)
        - folder_name = "home" (the LAST segment — will be CREATED as subfolder)
        - NEVER set destination_folder to the full path including folder_name

        ⛔ NEVER INVENT PATHS OR FOLDER NAMES:
        - destination_folder: ONLY use paths the user explicitly provided or from get_path_presets()
        - folder_name: ONLY use the name the user provided. If user didn't specify a name → ASK them.
          NEVER fabricate names like "Mayank_Lucknow" or "Results_2024"

        MANDATORY WORKFLOW:
        1. Call analyse_folder(source_folder) FIRST to get exact location strings and people names
        2. Use the EXACT location strings from analyse_folder response (e.g. "IN/Uttar-Pradesh/Lucknow")
           - If user says "Lucknow" → look up matching string from analyse_folder → "IN/Uttar-Pradesh/Lucknow"
           - Location matching is fuzzy (spaces/case ignored) but the format must be CC/State/City
        3. Use EXACT enrolled people names from get_enrolled_faces or analyse_folder
           - If user says "Mayank" and enrolled name is "Mayank" → use "Mayank"
           - If unsure which person → call get_enrolled_faces and ask user to confirm
        4. Parse destination path using the PATH PARSING RULE above
        5. Always set wait_for_completion=true so you can report results

        FILTER PARAMETERS (combine any — all must match):
        - years: ["2023", "2024"] — 4-digit year strings
        - months: ["01", "07", "12"] — 2-digit zero-padded month strings
        - locations: ["IN/Uttar-Pradesh/Lucknow"] — EXACT format from analyse_folder
        - people: ["Mayank", "Utkarsh Mishra"] — EXACT enrolled names
        - face_mode: "fast"/"balanced"/"accurate" — only when people filter is active

        This tool ALWAYS copies (never moves). Originals are always safe.
        """
        # --- SAFETY GUARD: Validate source ---
        normalized_source = os.path.expanduser(source_folder or "")
        if not normalized_source or not os.path.isdir(normalized_source):
            return {"error": f"Source path does not exist or is not a directory: {source_folder}"}

        # --- SAFETY GUARD: Validate destination exists ---
        normalized_dest = os.path.expanduser(destination_folder or "")
        if not normalized_dest or not os.path.isdir(normalized_dest):
            return {
                "error": f"Destination path does not exist: {destination_folder}. "
                         "NEVER fabricate paths. Use get_path_presets() or ask the user. "
                         "Remember: destination_folder is the PARENT directory. "
                         "folder_name is the subfolder that will be CREATED inside it."
            }

        payload = {
            "source_folder": normalized_source,
            "destination_folder": normalized_dest,
            "find_config": {
                "folderName": folder_name,
                "years": years or [],
                "months": months or [],
                "locations": locations or [],
                "people": people or []
            },
            "ignore_list": ignore_list or []
        }

        # Only include face_mode when people filter is active
        if people:
            payload["find_config"]["face_mode"] = face_mode

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{get_locallens_url()}/api/start-find-group",
                    json=payload,
                    timeout=10
                )
                r.raise_for_status()
                if wait_for_completion:
                    return await _wait_for_completion(client, timeout_s, poll_interval_s)
                return r.json()
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    async def abort_job() -> Dict[str, Any]:
        """
        Abort any currently running sorting, find/group, or enrollment job.
        Use when the user explicitly tells you to stop.
        Returns 'ignored' if no job is currently active.
        """
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{get_locallens_url()}/api/abort-process", timeout=5)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    async def open_folder(folder_path: str) -> Dict[str, Any]:
        """
        Open a folder in the native OS file manager (Finder on macOS, File Explorer
        on Windows, Files/Nautilus on Linux).

        WHEN TO USE:
        - After start_sorting or start_find_group completes — offer to open the destination folder
        - When the user says "show me the results", "open the folder", "where did they go?"
        - After find_duplicates — offer to open the scanned folder
        - Whenever next_actions includes {"action": "open_folder"} in a previous tool response

        This is a safe, read-only action that only opens a window — it does not move or delete files.
        """
        expanded = os.path.expanduser(folder_path or "")
        if not expanded or not os.path.isdir(expanded):
            return {"error": f"Path does not exist or is not a directory: {folder_path}"}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{get_locallens_url()}/api/open-folder",
                    json={"folder_path": expanded},
                    timeout=5,
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    async def remember_paths(
        preset_name: str,
        source: str,
        destination: str,
    ) -> Dict[str, Any]:
        """
        Save a source → destination path pair into LocalLens memory so you can reuse
        them without asking the user to type paths again.

        This is called a "path preset" inside LocalLens, but users will naturally say:
        - "remember this path" / "save this for next time" / "add to my saved locations"
        - "save in LL" / "save in the app" / "keep this in memory"
        - "add to LocalLens memory"

        WHEN TO USE:
        - After start_sorting completes (next_actions will include this suggestion)
        - When user explicitly says they want to reuse these paths
        - When you notice the user has typed the same paths more than once

        After saving, these paths are returned by get_path_presets() and you can use
        them directly in future start_sorting calls without asking the user.

        Parameters:
        - preset_name: A short, memorable label (e.g. "work photos", "phone backup", "holiday 2025")
        - source:      Absolute path to the source folder
        - destination: Absolute path to the destination folder
        """
        expanded_src = os.path.expanduser(source or "")
        expanded_dst = os.path.expanduser(destination or "")
        if not expanded_src:
            return {"error": "source path cannot be empty"}
        if not expanded_dst:
            return {"error": "destination path cannot be empty"}
        if not preset_name or not preset_name.strip():
            return {"error": "preset_name cannot be empty. Ask the user for a short memorable name."}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{get_locallens_url()}/api/presets/paths",
                    json={"name": preset_name.strip(), "source": expanded_src, "destination": expanded_dst},
                    timeout=5,
                )
                r.raise_for_status()
                result = r.json()
                result["message"] = (
                    f"Saved! Next time just say 'use my {preset_name.strip()} paths' "
                    "and I'll fill them in automatically from get_path_presets()."
                )
                return result
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    async def forget_paths(preset_name: str) -> Dict[str, Any]:
        """
        Remove a saved path preset from LocalLens memory by name.

        Users will naturally say:
        - "forget the work photos path" / "remove that saved path"
        - "delete from LL memory" / "clear that preset"
        - "stop remembering X"

        Call get_path_presets() first if you need to confirm the exact preset name.

        Parameters:
        - preset_name: Exact name of the preset to remove (case-sensitive, as saved by remember_paths)
        """
        if not preset_name or not preset_name.strip():
            return {"error": "preset_name cannot be empty. Call get_path_presets() to see saved names."}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.delete(
                    f"{get_locallens_url()}/api/presets/paths/{preset_name.strip()}",
                    timeout=5,
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return _handle_error(e)
