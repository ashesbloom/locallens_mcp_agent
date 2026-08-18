"""
LocalLens MCP Agent — Pro Tools
================================
Premium tools gated behind the Pro license tier.
Each tool is decorated with @require_pro, which checks the local license cache
before execution. If not activated, the LLM receives a friendly upgrade prompt.

FREE PREVIEW: `FREE_PREVIEW` in ../license.py is currently True, so @require_pro is
a no-op and every tool here runs for everyone without a license. All ten Pro tool
docstrings below say so; strip "(FREE right now — …)" from each when the preview
ends. See ../../../docs/RESTORING_PAID_MODE.md.

Current Pro Tools:
  - add_face_enroll       (enroll a new person for face recognition)
  - find_duplicates       (detect duplicate photos in a folder)
  - delete_duplicates     (safely remove duplicates, always dry-run first)
  - export_report         (generate a summary report of a folder's contents)
  - schedule_auto_organize / create_active_folder (scheduler tools)
  - smart_album_suggestions (AI-powered album grouping)
  - activate_pro_license  (license activation tool — free, always available)
  - get_license_status    (check current license state — free, always available)
  - revoke_pro_license    (deactivate license — free, always available)
"""

import os
import asyncio
import re
import time
import logging
import signal
import sys
import subprocess
import hashlib
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class EnrollmentEntry(BaseModel):
    """A single person-to-folder mapping for face enrollment."""
    person_name: str
    folder_path: str

from ..config import get_locallens_url, get_auth_headers, get_app_data_dir
from ..license import require_pro, activate_license, deactivate_license, get_license_info
from .actions import _DEFAULT_WAIT_S, _reject_if_job_running, _wait_for_completion
from .queries import resolve_path_preset

# Logger — MUST write only to stderr
_log = logging.getLogger("locallens_mcp.pro_tools")
if not _log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[locallens-mcp] %(levelname)s: %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False


# The backend answers 501 when an optional dependency is absent from the build
# (imagehash for find-duplicates, reportlab for PDF export). Its detail string has
# historically ended in "Run: pip install <lib>" — an imperative that an LLM client
# reads as an instruction and executes, in its own shell, against an interpreter that
# is not the backend's. The shipped backend is a self-contained PyInstaller bundle:
# no pip, no site-packages, nothing to install into. Relaying that sentence sent a
# real user (15k-photo archive, Windows 11) through a pip install that silently did
# nothing, then on to "reinstall LocalLens". Never pass it through: strip the command
# and state what is actually true — the build is missing a component, so update the app.
_PIP_INSTRUCTION_RE = re.compile(r"\s*Run:\s*pip install\s+\S+\.?", re.IGNORECASE)
_MISSING_LIB_RE = re.compile(r"['\"]([\w.-]+)['\"]\s+library is not installed", re.IGNORECASE)


def _feature_unavailable_in_build(detail: Any) -> Dict[str, Any]:
    """Turn a backend 501 into guidance the user can actually act on."""
    text = detail if isinstance(detail, str) else str(detail)
    lib = _MISSING_LIB_RE.search(text)
    component = f" (missing component: {lib.group(1)})" if lib else ""
    return {
        "error": "feature_unavailable_in_build",
        "message": (
            f"This LocalLens feature is not available in the installed build of the "
            f"LocalLens desktop app{component}."
        ),
        "guidance": (
            "Tell the user their LocalLens app needs updating to use this feature, and "
            "point them at the in-app updater or a fresh download. "
            "⛔ Do NOT run pip install, and do NOT suggest the user run pip install or "
            "any other command — the LocalLens backend ships as a self-contained bundle "
            "with no pip and no site-packages, so installing a Python package cannot fix "
            "this and will waste the user's time. Updating the app is the only fix. "
            "Do not suggest reinstalling or repairing the app beyond a normal update, "
            "and do not offer to work around it by inspecting their files yourself."
        ),
        # Kept for debugging only, with the executable instruction removed.
        "backend_detail": _PIP_INSTRUCTION_RE.sub("", text).strip(),
    }


def _handle_error(e: Exception) -> Dict[str, Any]:
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.json()
        except ValueError:
            body = e.response.text
        if e.response.status_code == 501:
            detail = body.get("detail", body) if isinstance(body, dict) else body
            return _feature_unavailable_in_build(detail)
        return {"error": body}
    return {"error": str(e)}


async def _daemon_is_running(url: str) -> bool:
    """Ask the backend whether the scheduler daemon is alive. Source of truth."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/api/scheduler/daemon-status", timeout=5.0)
            r.raise_for_status()
            return bool(r.json().get("daemon_running"))
    except Exception:
        return False


async def _poll_daemon_state(url: str, want: bool, cap_s: float = 3.0) -> bool:
    """Poll daemon-status until it matches `want`, or the cap elapses."""
    deadline = time.monotonic() + cap_s
    while True:
        if await _daemon_is_running(url) is want:
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(0.5)


def _launch_daemon_script() -> str:
    """
    The only launcher: spawn scheduler_daemon.py directly, detached.

    ponytail: only works against a LocalLens *source* checkout — the frozen backend
    bundle ships no .py files, so scheduler_daemon.py is absent there. Simplify this
    to a plain path lookup once scheduler_daemon.py is bundled in backend_server.spec.
    Do not "fix" the missing-script case by falling back to the backend's
    daemon-command endpoint; that spawns backend clones (see _ensure_daemon).
    """
    import pathlib

    backend_dir = None
    backend_dir_env = os.getenv("LOCALLENS_BACKEND_DIR")
    if backend_dir_env:
        backend_dir = pathlib.Path(os.path.expanduser(backend_dir_env))
    else:
        install_dir_file = get_app_data_dir() / "install_dir.txt"
        if install_dir_file.exists():
            try:
                backend_dir = pathlib.Path(install_dir_file.read_text().strip())
            except Exception:
                pass

    if not backend_dir or not backend_dir.exists():
        return (
            "backend directory not found — set LOCALLENS_BACKEND_DIR to your LocalLens "
            "backend folder (the one containing scheduler_daemon.py)"
        )

    daemon_script = backend_dir / "scheduler_daemon.py"
    if not daemon_script.exists():
        return f"scheduler_daemon.py not present at {daemon_script}"

    # Prefer the backend's own venv interpreter — it has the deps the daemon imports.
    if sys.platform == "win32":
        backend_python = backend_dir / "venv" / "Scripts" / "python.exe"
    else:
        backend_python = backend_dir / "venv" / "bin" / "python"
    python = str(backend_python) if backend_python.exists() else sys.executable

    kwargs: Dict[str, Any] = {
        "cwd": str(backend_dir),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True  # fully detach from the MCP process

    try:
        subprocess.Popen([python, str(daemon_script), "start"], **kwargs)
        return f"spawned {daemon_script}"
    except Exception as ex:
        return f"spawn failed: {ex}"


async def _ensure_daemon(url: str, cap_s: float = 3.0) -> Dict[str, Any]:
    """
    Make sure the scheduler daemon is running, and report what is actually true.

    Only ever launches a daemon we can name on disk, and the returned `daemon_running`
    is verified against /api/scheduler/daemon-status — never assumed from a bare spawn.

    Deliberately does NOT call POST /api/scheduler/daemon-command. That endpoint runs
    [sys.executable, "scheduler_daemon.py", "start"], and in a packaged install
    sys.executable IS the backend binary — a frozen binary cannot run a .py argument,
    so it boots a second full backend instead. That clone writes its own port to
    port.txt, so the next call resolves to the clone and spawns another: observed live
    as 5 backend servers and a hijacked port.txt. See _stop_daemon for the same reason.
    """
    if await _daemon_is_running(url):
        return {"daemon_running": True, "detail": "already running"}

    spawn_detail = _launch_daemon_script()
    if await _poll_daemon_state(url, True, cap_s):
        return {"daemon_running": True, "detail": spawn_detail}

    return {"daemon_running": False, "detail": spawn_detail}


async def _stop_daemon(url: str, cap_s: float = 3.0) -> Dict[str, Any]:
    """
    Stop the daemon by signalling the PID it recorded, and verify it actually stopped.

    Uses the PID file rather than daemon-command for the reason spelled out in
    _ensure_daemon — plus the endpoint's stop branch calls a blocking subprocess.run()
    with no timeout inside an async handler, so a spawned clone that never exits would
    wedge the backend's event loop. scheduler_daemon.py handles SIGTERM and exits.
    """
    pid_file = get_app_data_dir() / "scheduler.pid"
    if not pid_file.exists():
        return {
            "status": "stopped",
            "daemon_running": False,
            "note": "The daemon was not running. Schedules remain configured.",
        }

    try:
        os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
    except (OSError, ValueError) as ex:
        # Stale PID file, or the process is already gone — either way, not running.
        return {
            "status": "stopped",
            "daemon_running": False,
            "note": f"The daemon was not running ({ex}). Schedules remain configured.",
        }

    if await _poll_daemon_state(url, False, cap_s):
        return {
            "status": "stopped",
            "daemon_running": False,
            "note": "Daemon stopped. Schedules remain configured — use start_daemon to resume.",
        }

    return {
        "status": "still_running",
        "daemon_running": True,
        "note": (
            "A stop signal was sent but the daemon is still reporting as running. "
            "Tell the user it may not have stopped, and offer to try again."
        ),
    }


def _scheduler_next_actions(url: str, destination_folder: str) -> List[Dict[str, Any]]:
    """The three follow-ups offered after any schedule is created."""
    return [
        {
            "action": "list_schedules",
            "label": "📋 Check schedule status",
            "hint": "Call list_schedules() to see all schedules and daemon state",
        },
        {
            "action": "open_folder",
            "label": "📂 Open destination folder",
            "args": {"folder_path": destination_folder},
        },
        {
            "action": "open_scheduler_dashboard",
            "label": "📊 Open full dashboard",
            "args": {},
            "hint": f"Provide this link clearly: [Open Dashboard]({url}/scheduler-ui)",
        },
    ]


def _schedule_guidance(schedule_id: str, daemon: Dict[str, Any], active_line: str) -> str:
    """
    Build the LLM-facing guidance for a freshly created schedule.

    The 'it's running' prose is gated on the VERIFIED daemon state — a saved schedule
    with a dead daemon organizes nothing, and claiming otherwise misleads the user.
    """
    if daemon.get("daemon_running"):
        return (
            f"{active_line} "
            "Tell the user they can check status anytime by saying 'list my schedules', "
            "manage it with 'pause/resume/delete schedule', or open the full dashboard with "
            "'open scheduler dashboard' — offer them the dashboard link now so they can "
            "watch sweeps and manage the schedule from there."
        )
    return (
        f"⚠️ Schedule {schedule_id} is SAVED but is NOT being monitored: the background "
        f"daemon is not running ({daemon.get('detail', 'unknown reason')}), so no photos "
        "will be organized yet. Tell the user this plainly — do NOT say the schedule is "
        "active or that sweeps will happen. Offer to retry with "
        "manage_schedule(schedule_id='daemon', action='start_daemon'). If that fails too, "
        "the daemon script is not present on this install — tell them to set "
        "LOCALLENS_BACKEND_DIR to their LocalLens backend folder and restart. Do NOT tell "
        "them to start the daemon from the scheduler dashboard — that button cannot start "
        "it on a packaged install. The dashboard link is still useful for viewing the "
        "schedule, so you may offer it for that."
    )



def register_pro_tools(mcp: FastMCP):
    """Register all Pro-tier tools and the license management tools."""

    # ======================================================================
    #  LICENSE MANAGEMENT (always available — not gated)
    # ======================================================================

    @mcp.tool()
    async def activate_pro_license(license_key: str) -> Dict[str, Any]:
        """
        Activate a Pro license to unlock premium features like duplicate detection,
        face enrollment, scheduled auto-organize, and more.

        Purchase a license at https://locallensmcp.vercel.app
        Requires a one-time internet connection. After activation,
        all Pro features work fully offline.
        """
        return await activate_license(license_key)

    @mcp.tool()
    async def get_license_status() -> Dict[str, Any]:
        """
        Check the LocalLens (LL) license tier — Free or Pro.
        Use for "my LL license", "am I Pro", "LocalLens subscription", "upgrade status".
        Returns activation state, tier name, and activation date if active.
        No internet required — reads from local cache only.

        ⚠️ This returns license STATE only — no feature list, no pricing. For
        "what is Pro" / "free vs Pro" / "what do I get", call locallens_help(topic="pro").
        Never answer LocalLens product questions from the web.
        """
        return get_license_info()

    @mcp.tool()
    async def revoke_pro_license() -> Dict[str, Any]:
        """
        Revoke/Deactivate the current Pro license.
        This immediately reverts the application to the Free tier and removes local license data.
        """
        return deactivate_license()

    # ======================================================================
    #  PRO TOOLS — Require active license
    # ======================================================================

    @mcp.tool()
    @require_pro
    async def add_face_enroll(
        enrollments: dict,
        wait_for_completion: bool = True,
        poll_interval_s: float = 1.0,
        timeout_s: int = _DEFAULT_WAIT_S
    ) -> Dict[str, Any]:
        """
        ⚡ PRO FEATURE (FREE right now — LocalLens is in free preview, no license needed) — Enroll one or more people into the face recognition system in a single batch.
        Provide a dictionary mapping each person's name to the folder with their photos.
        The system scans each folder for images and enrolls them all in one operation.

        After enrollment, these people can be used in People sort and Find & Group filters.

        - enrollments: Dictionary of {"Person Name": "/path/to/folder"}
        - wait_for_completion: If true, waits until encoding finishes before returning (recommended)
        - poll_interval_s: How often to poll for completion status (default: 1 second)
        - timeout_s: Max wait before handing back with status="still_running" (default: 150s).
          Do NOT raise it — the MCP client cancels tool calls at ~240s.
        """
        supported_exts = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp")
        people_to_enroll = []
        skipped = []

        # Ensure we are iterating over a dictionary
        if not isinstance(enrollments, dict):
            return {"error": "The 'enrollments' argument must be a JSON object (dictionary)."}

        # Handle UX copy-paste issue where the entire arguments JSON is pasted into the enrollments field
        if "enrollments" in enrollments and isinstance(enrollments["enrollments"], dict):
            enrollments = enrollments["enrollments"]

        for person_name, folder_path in enrollments.items():
            person_name = str(person_name).strip()
            # Skip UI wrapper fields if they were accidentally included alongside the dictionary
            if person_name in ["wait_for_completion", "poll_interval_s", "timeout_s"]:
                continue
                
            # Handle potential extra quotes from user copy/paste mistakes
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
                people_to_enroll.append({
                    "person_name": person_name,
                    "image_paths": image_paths
                })
            else:
                skipped.append({"person": person_name, "reason": "no supported images found in folder"})

        if not people_to_enroll:
            return {
                "error": "No valid enrollments — check folder paths and image formats.",
                "skipped": skipped
            }

        payload = {"people_to_enroll": people_to_enroll}

        try:
            async with httpx.AsyncClient() as client:
                # Enrollment shares the same single job-status slot as sorting,
                # so it collides the same way — see _reject_if_job_running.
                busy = await _reject_if_job_running(client)
                if busy:
                    return busy
                r = await client.post(
                    f"{get_locallens_url()}/api/add-person",
                    json=payload,
                    timeout=10,
                )
                r.raise_for_status()
                if wait_for_completion:
                    result = await _wait_for_completion(client, timeout_s, poll_interval_s)
                    if skipped:
                        result["skipped"] = skipped
                    return result
                resp = r.json()
                if skipped:
                    resp["skipped"] = skipped
                return resp
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    @require_pro
    async def find_duplicates(
        source_folder: str,
        ignore_list: list[str] = [],
        similarity_threshold: float = 0.95
    ) -> Dict[str, Any]:
        """
        ⚡ PRO FEATURE (FREE right now — LocalLens is in free preview, no license needed) — Scan a folder for duplicate or near-duplicate photos.
        Uses perceptual hashing to detect visually similar images even if
        they have different filenames or resolutions.

        - source_folder: The folder to scan for duplicates
        - ignore_list: Subfolders to skip (default: none)
        - similarity_threshold: 0.0 to 1.0 — how similar images must be to be
          considered duplicates (default 0.95 = nearly identical)

        Returns groups of duplicate files that the user can review.

        On a large archive (tens of thousands of photos) hashing can outlive the wait
        window and this returns status="still_running" instead of the groups. That is
        healthy — the scan continues in the background. Report the progress and STOP;
        call get_job_progress again only when the user next asks.
        """
        normalized_source = os.path.expanduser(source_folder or "")
        if not normalized_source or not os.path.isdir(normalized_source):
            return {"error": f"Source path is not a valid directory: {normalized_source}"}

        payload = {
            "source_folder": normalized_source,
            "ignore_list": ignore_list or [],
            "similarity_threshold": similarity_threshold,
        }

        try:
            async with httpx.AsyncClient() as client:
                # One job at a time — see _reject_if_job_running for why.
                busy = await _reject_if_job_running(client)
                if busy:
                    return busy
                r = await client.post(
                    f"{get_locallens_url()}/api/find-duplicates",
                    json=payload,
                    timeout=120,  # Older backends hash inline before responding.
                )
                r.raise_for_status()
                result = r.json()

                # Two backend generations answer this endpoint. The older one hashes
                # inline and returns the groups on the POST; the newer one queues a
                # background job and reports through /api/job-status, because a 15k-photo
                # archive takes far longer to hash than any sane HTTP timeout. The MCP
                # ships independently of the desktop app, so both are live in the wild —
                # tell them apart by whether the groups came back, not by version.
                if "duplicate_groups" not in result:
                    # assume_started: the POST above confirmed this job started, so the
                    # stale-state guard must not wait to sample is_active=True — a small
                    # folder finishes hashing inside the first poll interval and would
                    # otherwise be reported as "still_running" until the timeout.
                    result = await _wait_for_completion(
                        client, _DEFAULT_WAIT_S, 1.0, assume_started=True
                    )
                    if result.get("status") != "complete":
                        return result

                # Inject next-action suggestions when duplicates are found
                if result.get("total_duplicates", 0) > 0:
                    all_duplicates = [
                        path
                        for group in result.get("duplicate_groups", [])
                        for path in group[1:]  # Skip the first file in each group (the "original")
                    ]
                    result["next_actions"] = [
                        {
                            "action": "delete_duplicates",
                            "label": f"\U0001f5d1\ufe0f Delete {len(all_duplicates)} duplicate(s)",
                            "hint": (
                                "SAFETY WORKFLOW: First call delete_duplicates(file_paths=[...], dry_run=True) "
                                "to show the user exactly what will be deleted. "
                                "Only call with dry_run=False after explicit user confirmation."
                            ),
                            "args": {"file_paths": all_duplicates, "dry_run": True},
                        },
                        {
                            "action": "open_folder",
                            "label": "\U0001f4c2 Open scanned folder",
                            "hint": "Call open_folder(folder_path=source_folder) to browse the results",
                            "args": {"folder_path": normalized_source},
                        },
                    ]
                    result["guidance"] = (
                        f"Found {result['total_duplicates']} duplicate files in "
                        f"{len(result['duplicate_groups'])} group(s). "
                        "Present the groups to the user, then offer to delete the extras. "
                        "ALWAYS use delete_duplicates with dry_run=True first and show the user "
                        "exactly which files will be removed before asking for confirmation."
                    )
                return result
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    @require_pro
    async def export_report(
        source_folder: str,
        output_path: str = "",
        ignore_list: list[str] = [],
        include_metadata: bool = True,
        include_face_summary: bool = True
    ) -> Dict[str, Any]:
        """
        ⚡ PRO FEATURE (FREE right now — LocalLens is in free preview, no license needed) — Generate and SAVE a detailed PDF/JSON report file about a photo folder.
        This is for creating a SAVED DOCUMENT — not for quick folder analysis.

        ⚠️ NOT for pre-sort checks. If the user wants to "analyse my folder", "check what's inside",
        or "see if sorting would work" → use analyse_folder() instead. This tool generates a report FILE.

        The report includes file counts, date ranges, location summary,
        face recognition results, and folder structure analysis.

        - source_folder: The folder to generate a report for
        - output_path: Where to save the report (default: source_folder/LocalLens_Report.json)
        - ignore_list: Subfolders to exclude from the scan (default: none)
        - include_metadata: Include EXIF date/location breakdown (default: true)
        - include_face_summary: Include face recognition statistics (default: true)

        Returns the report data and the path where it was saved.
        """
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
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{get_locallens_url()}/api/export-report",
                    json=payload,
                    timeout=60,
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    @require_pro
    async def create_active_folder(
        source_folder: str,
        destination_folder: str,
        primary_sort: str = "Date",
        operation_mode: str = "copy",
        face_mode: str = "balanced",
        maintain_hierarchy: bool = True,
        ignore_list: Optional[List[str]] = None,
        debounce_seconds: int = 5,
    ) -> Dict[str, Any]:
        """
        ⚡ PRO FEATURE (FREE right now — LocalLens is in free preview, no license needed) — Create an Active Folder for real-time photo organization.
        
        INSTANTLY detects when new photos are added to the source folder and organizes them.
        It also runs a hidden daily safety-sweep to catch anything missed while the system was off.
        
        Only NEW photos are processed — already-organized files are never touched.
        The active folder monitor persists across app restarts.
        
        📁 PATHS — RESOLVE PRESET NAMES FIRST (MANDATORY):
        If the user names a folder instead of typing a path ("watch my bot testing preset",
        "my saved paths", "the usual folder"), call get_path_presets BEFORE this tool and pass
        the EXACT stored path. A preset name is not a path — never guess one from the name, and
        never ask the user to re-type a path they already saved. A destination the user types
        explicitly overrides the preset's; the preset still supplies source_folder.

        - source_folder: The folder to watch actively for new photos
        - destination_folder: Where organized photos go
        - primary_sort: "Date", "Location", or "People"
        - operation_mode: "copy" (safe, keeps originals) or "move"
        - debounce_seconds: Wait time after last file event before organizing (default: 5)
        """
        # Accepts a saved preset NAME here as well as a path — see resolve_path_preset.
        resolved_source = await resolve_path_preset(source_folder, "source")
        if "error" in resolved_source:
            return resolved_source
        source_folder = resolved_source["path"]

        config = {
            "mode": "active",
            "source_folder": source_folder,
            "destination_folder": destination_folder,
            "primary_sort": primary_sort,
            "face_mode": face_mode,
            "maintain_hierarchy": maintain_hierarchy,
            "operation_mode": operation_mode,
            "ignore_list": ignore_list or [],
            "debounce_seconds": debounce_seconds
        }
        try:
            url = get_locallens_url()
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{url}/api/scheduler/create", json=config, timeout=5.0)
                r.raise_for_status()
                res = r.json()

            daemon = await _ensure_daemon(url)
            res["daemon_running"] = daemon["daemon_running"]
            res["daemon_launched"] = daemon["detail"]
            res["privacy_note"] = (
                "🔒 Your active folder config is stored locally at ~/.config/LocalLens/schedules.json. "
                "No data leaves your computer. You can delete it anytime."
            )
            schedule_id = res.get("schedule_id", "")
            res["next_actions"] = _scheduler_next_actions(url, destination_folder)
            res["guidance"] = _schedule_guidance(
                schedule_id,
                daemon,
                f"Active folder created ({schedule_id}). The daemon is watching for new photos "
                f"in {source_folder} and will organize them automatically.",
            )
            return res
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    @require_pro
    async def schedule_auto_organize(
        source_folder: str,
        destination_folder: str,
        primary_sort: str = "Date",
        interval_hours: Optional[int] = None,
        interval_minutes: Optional[int] = None,
        operation_mode: str = "copy",
        face_mode: str = "balanced",
        maintain_hierarchy: bool = True,
        ignore_list: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        ⚡ PRO FEATURE (FREE right now — LocalLens is in free preview, no license needed) — Schedule smart, background photo organization sweeps.
        
        Runs a background sweep every N hours. Ideal for bulk folders, network drives, 
        or periodic organization without the overhead of real-time monitoring.
        
        Only NEW photos are processed — already-organized files are never touched.
        The schedule persists across app restarts.
        
        📁 PATHS — RESOLVE PRESET NAMES FIRST (MANDATORY):
        If the user names a folder instead of typing a path ("use my bot testing preset",
        "my saved paths", "the usual folder"), call get_path_presets BEFORE this tool and pass
        the EXACT stored path. A preset name is not a path — never guess one from the name, and
        never ask the user to re-type a path they already saved.
        A destination the user types explicitly overrides the preset's destination; the preset
        still supplies source_folder. Example: "2h date sort, bot testing preset, output to
        /tmp/out" → source_folder=<preset's source>, destination_folder="/tmp/out".

        - source_folder: The folder to sweep for new photos
        - destination_folder: Where organized photos go
        - primary_sort: "Date", "Location", or "People"
        - interval_hours: Hours for the sweep interval (optional)
        - interval_minutes: Minutes for the sweep interval (optional)
        - operation_mode: "copy" (safe, keeps originals) or "move"

        Note: If both intervals are left empty, it defaults to 24 hours.
        """
        # Accepts a saved preset NAME here as well as a path — see resolve_path_preset.
        resolved_source = await resolve_path_preset(source_folder, "source")
        if "error" in resolved_source:
            return resolved_source
        source_folder = resolved_source["path"]

        # Smart defaulting: if both are None, default to 24h.
        # If one is provided, the other defaults to 0.
        if interval_hours is None and interval_minutes is None:
            effective_hours = 24
            effective_minutes = 0
        else:
            effective_hours = interval_hours or 0
            effective_minutes = interval_minutes or 0

        config = {
            "mode": "scheduled",
            "source_folder": source_folder,
            "destination_folder": destination_folder,
            "primary_sort": primary_sort,
            "face_mode": face_mode,
            "maintain_hierarchy": maintain_hierarchy,
            "operation_mode": operation_mode,
            "ignore_list": ignore_list or [],
            "interval_hours": effective_hours,
            "interval_minutes": effective_minutes
        }
        try:
            url = get_locallens_url()
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{url}/api/scheduler/create", json=config, timeout=5.0)
                r.raise_for_status()
                res = r.json()

            # Start the daemon and verify it actually came up before saying so.
            daemon = await _ensure_daemon(url)

            res["daemon_running"] = daemon["daemon_running"]
            res["daemon_launched"] = daemon["detail"]
            schedule_id = res.get("schedule_id", "")
            interval_desc = f"{effective_hours}h {effective_minutes}m" if effective_hours else f"{effective_minutes}m"
            res["privacy_note"] = (
                "🔒 Your schedule config is stored locally at ~/.config/LocalLens/schedules.json. "
                "No data leaves your computer. You can delete any schedule anytime."
            )
            res["next_actions"] = _scheduler_next_actions(url, destination_folder)
            res["guidance"] = _schedule_guidance(
                schedule_id,
                daemon,
                f"Schedule created ({schedule_id})! The daemon will sweep every {interval_desc}, "
                f"organizing new photos from {source_folder} by {primary_sort}.",
            )
            return res
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    @require_pro
    async def list_schedules() -> Dict[str, Any]:
        """
        ⚡ PRO (FREE right now — LocalLens is in free preview, no license needed) — List all auto-organize schedules and the daemon's current state.

        Returns:
          - daemon_running: whether the background daemon process is active
          - daemon_pid: the PID of the running daemon (if active)
          - summary: plain-English description of the overall state
          - schedules: list of schedule configs, each annotated with:
              - being_monitored: true only if daemon is running AND schedule is active
              (schedules persist in storage after the daemon stops — this is by design,
               so your schedule config isn't lost when the daemon restarts)

        If daemon_running=false, use manage_schedule(action='start_daemon') to restart it.
        """
        try:
            url = get_locallens_url()
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{url}/api/scheduler/list", timeout=5.0)
                r.raise_for_status()
                data = r.json()

            running = data.get("daemon_running", False)
            schedules = data.get("schedules", [])

            # Annotate each schedule with effective monitoring state
            for s in schedules:
                s["being_monitored"] = running and s.get("status") == "active"

            active_count = sum(1 for s in schedules if s.get("status") == "active")
            monitored_count = sum(1 for s in schedules if s.get("being_monitored"))

            data["schedules"] = schedules
            data["summary"] = (
                f"Daemon is {'✅ RUNNING (PID ' + str(data.get('daemon_pid')) + ')' if running else '🔴 STOPPED — no photos are being monitored'}. "
                f"{active_count} schedule(s) configured, {monitored_count} actively being watched."
            )
            if not running and schedules:
                data["note"] = (
                    "Schedules remain saved after the daemon stops — this is intentional so your "
                    "config isn't lost on restart. Use manage_schedule(action='start_daemon') to resume monitoring."
                )
            data["guidance"] = (
                "Present each schedule clearly with: ID, source→destination, sort mode, "
                "interval, status (🟢 active / ⏸ paused / 🔴 error), last run, next run, files organized. "
                "Then ask: 'Want to pause, resume, delete, or trigger any schedule?' "
                + ("The daemon is stopped — ask if they want to start it." if not running and schedules else "")
            )
            data["next_actions"] = [
                {
                    "action": "open_scheduler_dashboard",
                    "label": "📊 Open full dashboard",
                    "args": {},
                    "hint": f"Provide this link clearly: [Open Dashboard]({get_locallens_url()}/scheduler-ui)"
                }
            ]
            return data
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    @require_pro
    async def open_scheduler_dashboard() -> Dict[str, Any]:
        """
        ⚡ PRO (FREE right now — LocalLens is in free preview, no license needed) — Open the Scheduler Dashboard in the user's web browser.
        
        Call this when the user says "show me the scheduler dashboard", "open logs", 
        or "where is the scheduler UI?".
        """
        import webbrowser
        try:
            dashboard_url = f"{get_locallens_url()}/scheduler-ui"
            webbrowser.open(dashboard_url)
            return {
                "status": "success",
                "message": f"Browser opened to {dashboard_url}",
                "guidance": f"Tell the user: 'I have opened the full scheduler dashboard in your browser. You can also click here if it didn't open: [Open Dashboard]({dashboard_url})'"
            }
        except Exception as e:
            return _handle_error(e)


    @mcp.tool()
    @require_pro
    async def manage_schedule(
        schedule_id: str,
        action: str,
    ) -> Dict[str, Any]:
        """
        ⚡ PRO (FREE right now — LocalLens is in free preview, no license needed) — Manage an existing auto-organize schedule or the daemon process.

        - schedule_id: The ID of the schedule (e.g. "sched_abc123"), or "daemon" for daemon-only actions
        - action: One of:
            "pause"        — Stop the schedule from running (keeps the config, daemon skips it)
            "resume"       — Re-activate a paused schedule
            "delete"       — Permanently remove the schedule config
            "trigger"      — Run an immediate organize sweep right now
            "start_daemon" — Start the daemon process
            "stop_daemon"  — Stop the daemon process (schedules remain configured)
        
        The scheduler daemon automatically picks up config changes within ~5 seconds.
        """
        try:
            url = get_locallens_url()
            async with httpx.AsyncClient() as client:
                if action == "start_daemon":
                    daemon = await _ensure_daemon(url)
                    if daemon["daemon_running"]:
                        return {
                            "status": "running",
                            "daemon_running": True,
                            "detail": daemon["detail"],
                            "note": "The daemon is running — active schedules are being monitored.",
                        }
                    return {
                        "status": "not_running",
                        "daemon_running": False,
                        "detail": daemon["detail"],
                        "note": (
                            "The daemon could NOT be started, so no schedules are being monitored. "
                            "Tell the user plainly and offer the scheduler dashboard, where they "
                            "can start it manually."
                        ),
                    }

                elif action == "stop_daemon":
                    return await _stop_daemon(url)

                elif action == "delete":
                    r = await client.delete(f"{url}/api/scheduler/{schedule_id}", timeout=5.0)
                    r.raise_for_status()
                    return {**r.json(), "note": "The daemon will stop this schedule within 5 seconds."}

                elif action == "pause":
                    r = await client.post(f"{url}/api/scheduler/{schedule_id}/pause", timeout=5.0)
                    r.raise_for_status()
                    # Also abort any currently running backend job triggered by this schedule
                    try:
                        abort_r = await client.post(f"{url}/api/abort-process", timeout=5.0)
                        aborted = abort_r.status_code == 200
                    except Exception:
                        aborted = False
                    result = r.json()
                    result["job_aborted"] = aborted
                    result["note"] = "Schedule paused. Daemon will skip future sweeps until resumed."
                    return result

                elif action == "resume":
                    r = await client.post(f"{url}/api/scheduler/{schedule_id}/resume", timeout=5.0)
                    r.raise_for_status()
                    return {**r.json(), "note": "Schedule resumed. The daemon will pick it up within 5 seconds."}

                elif action == "trigger":
                    r = await client.post(f"{url}/api/scheduler/{schedule_id}/trigger", timeout=5.0)
                    r.raise_for_status()
                    return {**r.json(), "note": "Immediate sweep queued. The daemon will execute it shortly."}

                else:
                    return {
                        "status": "error",
                        "message": f"Unknown action '{action}'. Valid actions: pause, resume, delete, trigger, start_daemon, stop_daemon"
                    }
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    @require_pro
    async def smart_album_suggestions(
        max_suggestions: int = 8,
        time_range_months: int = 24,
        include_persona_context: bool = True,
    ) -> Dict[str, Any]:
        """
        ⚡ PRO FEATURE (FREE right now — LocalLens is in free preview, no license needed) — Get personalized album suggestions based on your photo
        history and personal interests.

        This does NOT scan any folder on demand. It uses metadata automatically
        collected from your previous organization sessions, combined with your
        persona profile, to suggest emotionally meaningful albums.

        Examples of what you might get:
          🎸 "Guitar Sessions — College Days"
          🏡 "Back to Lucknow — Winter Break"
          🎂 "Mom's Birthday Celebrations"
          ✈️ "Trip to Goa (December 2024)"

        - max_suggestions: How many album ideas to return (default: 8)
        - time_range_months: How far back to look in your photo history (default: 24)
        - include_persona_context: Use your persona profile for personalization (default: true)

        First-time users: You'll be prompted to take a quick persona survey to
        enable personalized suggestions. Use the persona survey endpoint to get started.

        Note: Suggestions improve as you organize more photos. The system learns
        passively from every sort job you run.
        """
        # ━━ COMING SOON — Reserved for a future update ━━
        # Smart Album Suggestions requires persona profile + metadata store integration.
        # The backend infrastructure exists but this tool will ship in a later release.
        return {
            "status": "coming_soon",
            "message": (
                "Smart Album Suggestions is coming in a future update! "
                "This feature will suggest personalized albums based on your photo history. "
                "Stay tuned."
            ),
        }

    @mcp.tool()
    @require_pro
    async def delete_duplicates(
        file_paths: list[str],
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        ⚡ PRO FEATURE (FREE right now — LocalLens is in free preview, no license needed) — Delete a list of duplicate photos, sending them to the OS Trash
        (recoverable) rather than permanently erasing them.

        ⚠️  MANDATORY SAFETY WORKFLOW — NEVER SKIP THESE STEPS:
        1. ALWAYS call with dry_run=True first.
           Show the user the full list of files that WOULD be deleted.
        2. Ask the user: "Are you sure you want to delete these X files? This will move
           them to your Trash. You can recover them from there if needed."
        3. Only call again with dry_run=False after EXPLICIT user confirmation.
        4. Never pass ALL files from a duplicate group — keep at least one file per group.
           The first file in each duplicate_groups entry is the recommended keeper.

        HOW TO GET file_paths:
        - Run find_duplicates() first. The next_actions in the response will pre-populate
          a suggested file_paths list (all files EXCEPT the first in each group).
        - You can adjust this list based on user preference (e.g. user may want to keep
          a specific copy, not just the first one).

        Parameters:
        - file_paths: List of absolute paths to files to delete
        - dry_run:    True = preview only (DEFAULT). False = actually move to Trash.

        Returns:
        - status: "preview" (dry_run) or "deleted"
        - deleted: list of files removed / that would be removed
        - failed: list of {path, error} for any files that couldn't be removed
        - total_freed_mb: disk space freed (or that would be freed)
        - use_trash: True if send2trash is available (files recoverable from Trash)
        """
        if not file_paths:
            return {"error": "file_paths list is empty. Run find_duplicates() first to get the list."}

        payload = {
            "file_paths": file_paths,
            "dry_run": dry_run,
        }

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{get_locallens_url()}/api/delete-files",
                    json=payload,
                    timeout=30,
                )
                r.raise_for_status()
                result = r.json()

                # After a real deletion, suggest opening the folder to verify
                if not dry_run and result.get("deleted"):
                    first_deleted = result["deleted"][0]
                    containing_folder = os.path.dirname(first_deleted)
                    result["next_actions"] = [
                        {
                            "action": "open_folder",
                            "label": "\U0001f4c2 Open folder to verify",
                            "hint": "Call open_folder() to confirm the duplicates are gone",
                            "args": {"folder_path": containing_folder},
                        }
                    ]
                return result
        except Exception as e:
            return _handle_error(e)
