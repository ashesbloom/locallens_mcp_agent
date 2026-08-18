import os
import asyncio
import time
import logging
import sys
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List, Optional

from ..config import get_locallens_url
from .queries import resolve_path_preset

# NOTE: nothing in this module is @require_pro, and that is deliberate. Sorting —
# including primary_sort="People" — is FREE. require_pro used to be imported here
# unused, which reads like an oversight and invites someone to "fix" it by gating
# start_sorting. Only batch enrolment (add_face_enroll, in pro_tools.py) is Pro.

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

# How long a tool blocks waiting for a job before handing back to the LLM.
# MUST stay well under the MCP client's own request timeout — Claude Desktop
# cancels a tool call at 240s. The old 900s default was unreachable: every job
# longer than 4 minutes got cancelled client-side, the wait was orphaned, and the
# model fell back to polling get_job_progress by hand (5+ round trips of tokens
# for one sort). Returning early with progress is cheaper and more honest.
_DEFAULT_WAIT_S = 150


def _handle_error(e: Exception) -> Dict[str, Any]:
    if isinstance(e, httpx.HTTPStatusError):
        response = e.response
        try:
            return {"error": response.json()}
        except ValueError:
            return {"error": response.text}
    return {"error": str(e)}


def _count_enrolled(faces_data: Any) -> Optional[int]:
    """
    Extracts the enrolled-person count from an /api/enrolled-faces payload.

    Returns None when the payload shape isn't recognized — callers MUST treat that
    as "could not check", never as zero. Conflating the two is what broke this
    before: the backend emits `enrolled_faces`, older code probed `faces`/`enrolled`,
    and the .get() chain fell through to [] on every healthy install, blocking
    People sorts with a bogus "no faces are enrolled" error.
    """
    if isinstance(faces_data, list):
        return len(faces_data)
    if isinstance(faces_data, dict):
        for key in ("enrolled_faces", "faces", "enrolled"):
            value = faces_data.get(key)
            if isinstance(value, list):
                return len(value)
    return None


# Max new directory levels create_destination will make below an existing folder.
# A legitimate destination sits at most a couple of levels under somewhere real;
# a deeper chain means the path is malformed or hallucinated.
_MAX_NEW_DEST_LEVELS = 4


def _resolve_destination(
    destination_folder: str,
    create: bool
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Validates a destination path, creating it only on explicit opt-in.

    Returns (normalized_path, None) on success, or (None, error_dict) on refusal.

    Existence is NOT a reliable proxy for "the user meant this path" — a path the
    user typed verbatim may simply not exist yet. So a missing destination is a
    soft refusal that tells the caller how to proceed: confirm with the user, then
    retry with create=True. The confirmation is the safety mechanism, not the mkdir.
    """
    normalized = os.path.expanduser(destination_folder or "")
    if not normalized:
        return None, {"error": "Destination path is empty. Ask the user for a destination."}

    if os.path.isdir(normalized):
        return normalized, None

    if os.path.exists(normalized):
        return None, {"error": f"Destination exists but is not a directory: {normalized}"}

    if not create:
        return None, {
            "error": f"Destination path does not exist: {destination_folder}",
            "guidance": (
                "Do NOT fabricate a different path. If the user explicitly gave you this "
                "path, confirm it with them ('this folder doesn't exist yet — create it?') "
                "and retry the SAME call with create_destination=True. If you invented this "
                "path, use get_path_presets() or ask the user instead."
            ),
            "retry_with": "create_destination=True",
        }

    # Walk up to the nearest existing ancestor, counting the levels we'd create.
    # Guards against a garbled path (e.g. a typo'd root) spawning a deep bogus tree.
    ancestor, new_levels = normalized, 0
    while not os.path.isdir(ancestor):
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor, new_levels = parent, new_levels + 1

    if ancestor == os.path.dirname(ancestor):
        return None, {
            "error": f"Refusing to create {normalized}: no existing parent folder. "
                     "The path is probably misspelled. Confirm it with the user."
        }

    if new_levels > _MAX_NEW_DEST_LEVELS:
        return None, {
            "error": f"Refusing to create {new_levels} nested folders under {ancestor}. "
                     f"At most {_MAX_NEW_DEST_LEVELS} new levels are allowed — a deeper "
                     "path usually means it's wrong. Confirm the destination with the user."
        }

    try:
        os.makedirs(normalized, exist_ok=True)
    except OSError as e:
        return None, {"error": f"Could not create destination {normalized}: {e}"}

    _log.info("Created destination folder: %s", normalized)
    return normalized, None


async def _wait_for_completion(
    client: httpx.AsyncClient,
    timeout_s: int,
    poll_interval_s: float,
    assume_started: bool = False
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

    assume_started:
      Set this only when the caller has already been told by the backend that THIS
      job started (e.g. the POST returned status="started"). That is the one piece of
      knowledge the stale-state guard lacks, and without it a job that finishes inside
      the first poll interval is unobservable: `is_active=True` never gets sampled, so
      every exit condition above stays gated and the caller spins until timeout_s,
      reporting "still_running" for a job that is already done. Short scans hit this
      routinely — a few dozen photos hash in well under one poll.
      Leave it False when the POST does not confirm a start, or the guard is defeated
      and a previous job's terminal state can be misread as this one's result.
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
    has_started = assume_started  # True once the job has been seen as active
    last_backend_message: Optional[str] = None

    while True:
        # --- Timeout check (always first) ---
        elapsed = time.monotonic() - start
        if elapsed > timeout_s:
            _log.warning(f"Stopped waiting after {elapsed:.1f}s (limit={timeout_s}s)")
            return {
                "status": "still_running",
                "elapsed_seconds": round(elapsed, 1),
                "progress": last_status.get("progress"),
                "message": (
                    f"Still running after {elapsed:.0f}s. This tool stopped waiting so it "
                    "doesn't hold the conversation open — the job continues in the background."
                ),
                "guidance": (
                    "Report the progress above to the user, then STOP. Do NOT poll in a loop: "
                    "every get_job_progress call costs the user tokens and the job is unaffected "
                    "by watching it. Ask if they want you to check again, and only call "
                    "get_job_progress when they say yes."
                ),
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


async def _reject_if_job_running(client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    """
    Refuses to queue a job while the backend already has one running.

    /api/job-status is a SINGLE GLOBAL SLOT carrying no job id, so a second job makes
    every later poll ambiguous: _wait_for_completion latches onto whichever job the
    backend happens to be reporting. That is not theoretical — it announced job A's
    "380 of 602 complete" as job B's result while B was ~30% through, and both jobs
    split the same CPU, so each ran at roughly half speed.

    Returns an error dict to hand straight back to the caller, or None when clear.

    Fail-open on an unreachable/unparseable backend: we cannot prove a job is running,
    and "I could not check" must never be reported as "a job is running". The POST that
    follows will surface the real connection error with a better message than we can.
    """
    try:
        r = await client.get(f"{get_locallens_url()}/api/job-status", timeout=5)
        r.raise_for_status()
        status = r.json()
    except Exception as e:
        _log.warning("Could not check for a running job (%s) — proceeding.", e)
        return None

    if not isinstance(status, dict) or not status.get("is_active"):
        return None

    return {
        "error": "job_already_running",
        "message": (
            f"A {status.get('job_type') or 'sorting'} job is already running: "
            f"{status.get('progress', '?')}% of {status.get('total_files', '?')} files, "
            f"writing to {status.get('destination_folder') or 'an unknown folder'}."
        ),
        "guidance": (
            "Do NOT start another job. LocalLens tracks one job at a time, so a second one "
            "makes both slower AND makes progress reports unreliable. Tell the user what is "
            "already running and offer two choices: wait for it (get_job_progress), or "
            "cancel it (abort_job) and then retry this call."
        ),
        "current_job": status,
    }


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
        create_destination: bool = False,
        wait_for_completion: bool = True,
        poll_interval_s: float = 1.0,
        timeout_s: int = _DEFAULT_WAIT_S
    ) -> Dict[str, Any]:
        """
        Trigger photo organization on a specific source directory and output to a destination directory.

        The sort runs on the user's own machine, so there is no upload step — pass the
        folder paths straight through.

        Parameters:
        - primary_sort: MUST be exactly "Date", "Location", or "People" — NEVER "Faces" or "Face"
        - face_mode: "fast" (HOG), "balanced", "accurate" (CNN) — only used when primary_sort is "People"
            → If user says "be quick" / "fast" → use "fast"
            → If user says "accurate" / "best quality" → use "accurate"
            → Otherwise default to "balanced"
        - operation_mode: "copy" (DEFAULT — safe) or "move" (destructive — ONLY if user explicitly asks)
        - maintain_hierarchy: False by default (flattens into sort groups). Set True only if user asks.
        - wait_for_completion: leave True (default). Waits up to timeout_s, then returns
          status="still_running" with the current progress rather than blocking forever.
          Only set False if you have a specific reason to fire-and-forget.
        - timeout_s: how long to wait before handing back (default 150s). Do NOT raise it —
          the MCP client cancels tool calls at ~240s, so a longer wait just gets thrown away.

        ⛔ CRITICAL SAFETY RULES FOR LLMs — VIOLATION = DATA LOSS:
        1. NEVER INVENT OR FABRICATE A DESTINATION PATH. Only use:
           - A path the user EXPLICITLY typed in the conversation
           - A path returned by get_path_presets()
           Making up paths like "source_sorted_by_X" or "source_output" is FORBIDDEN.
           If user hasn't provided a destination → call get_path_presets() or ASK the user.
           create_destination: leave False on the first attempt. If the call comes back
           saying the destination doesn't exist, do NOT switch to a different path —
           ask the user "that folder doesn't exist yet, create it?" and once they agree,
           retry the SAME path with create_destination=True. Never set it on the first
           try, and never set it for a path the user did not type.
        2. operation_mode ALWAYS defaults to "copy". Tell user: "I'll copy to keep originals safe."
           NEVER use "move" unless user EXPLICITLY says "move" / "don't keep copies".
        3. BEFORE calling this, call analyse_folder() first to check for subfolders.
           If subfolders exist → present them and ask which to ignore.
           If no subfolders → proceed directly.
        4. wait_for_completion defaults to True. If the job outlives timeout_s the tool returns
           status="still_running" — report that progress to the user and STOP. Do not poll
           get_job_progress in a loop; it burns the user's tokens and does not speed anything up.
           Only one job can run at a time — if one is already running this returns
           error="job_already_running" instead of starting a second.
        5. primary_sort MUST be "Date", "Location", or "People". Code auto-corrects
           "Faces" → "People" but always use the correct value.

        ⚠️ PEOPLE SORT REQUIRES ENROLLED FACES:
           If primary_sort is "People" but no faces are enrolled, this tool will BLOCK
           and return an error. Tell the user to enroll faces first using add_face_enroll().
        """
        # --- SAFETY GUARD: Validate source exists ---
        # Accepts a saved preset NAME here as well as a path — see resolve_path_preset.
        resolved_source = await resolve_path_preset(source_folder, "source")
        if "error" in resolved_source:
            return resolved_source
        normalized_source = resolved_source["path"]

        # --- SAFETY GUARD: Resolve destination (creates only with create_destination=True) ---
        normalized_dest, dest_error = _resolve_destination(destination_folder, create_destination)
        if dest_error:
            return dest_error

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

        # --- SAFETY GUARD: People sort requires enrolled faces ---
        # Without enrolled faces, People sort puts EVERYTHING into "No_Faces_Found/"
        # which is a waste of the user's time. Block early with a helpful message.
        if normalized_sort == "people":
            try:
                async with httpx.AsyncClient() as check_client:
                    faces_resp = await check_client.get(
                        f"{get_locallens_url()}/api/enrolled-faces", timeout=5
                    )
                    faces_resp.raise_for_status()
                    faces_data = faces_resp.json()
                    # None = payload shape unrecognized → treat as "unknown", not zero,
                    # and let the sort proceed (same policy as the except branch below).
                    enrolled_count = _count_enrolled(faces_data)
                    if enrolled_count == 0:
                        return {
                            "error": "no_enrolled_faces",
                            "message": (
                                "No faces are enrolled yet. People sort requires at least one "
                                "enrolled person — otherwise all photos end up in a single "
                                "'No_Faces_Found' folder. "
                                "Please enroll faces first using add_face_enroll(), then retry."
                            ),
                            "required_action": "enroll_faces",
                            "guidance": (
                                "Tell the user: 'No faces are enrolled yet, so a People sort would "
                                "put all photos into a single No_Faces_Found folder. "
                                "Would you like to enroll someone first? Just say something like "
                                "\"add Mom to face recognition\" and provide 3-5 clear photos.' "
                                "Alternatively, suggest sorting by Date or Location instead."
                            ),
                        }
            except Exception:
                # If we can't check enrolled faces (e.g. backend not responding),
                # let the sort proceed — the backend will handle it.
                pass

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
                # One job at a time — see _reject_if_job_running for why.
                busy = await _reject_if_job_running(client)
                if busy:
                    return busy
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
        create_destination: bool = False,
        wait_for_completion: bool = True,
        poll_interval_s: float = 1.0,
        timeout_s: int = _DEFAULT_WAIT_S
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
        - create_destination: leave False on the first attempt. If the call reports the
          destination doesn't exist, do NOT substitute another path — ask the user
          "that folder doesn't exist yet, create it?" and retry the SAME path with
          create_destination=True once they agree. This creates the PARENT only;
          folder_name is created by the backend either way.

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
        # Accepts a saved preset NAME here as well as a path — see resolve_path_preset.
        resolved_source = await resolve_path_preset(source_folder, "source")
        if "error" in resolved_source:
            return resolved_source
        normalized_source = resolved_source["path"]

        # --- SAFETY GUARD: Resolve destination parent (folder_name is created by the backend) ---
        normalized_dest, dest_error = _resolve_destination(destination_folder, create_destination)
        if dest_error:
            dest_error["reminder"] = (
                "destination_folder is the PARENT directory. "
                "folder_name is the subfolder created inside it — do not merge them."
            )
            return dest_error

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
                # One job at a time — see _reject_if_job_running for why.
                busy = await _reject_if_job_running(client)
                if busy:
                    return busy
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
