import sys
import os
import signal
import subprocess
import webbrowser
import json
import time
from pathlib import Path
from .status import get_locallens_install_dir, APP_DIR

# Import the connector logic
try:
    from mcp_server.claude_connector import (
        install_claude_connector,
        uninstall_claude_connector,
        get_connection_status,
    )
    _connector_available = True
except ImportError:
    _connector_available = False

try:
    from mcp_server.updater import check_for_updates, check_app_update
    _updater_available = True
except ImportError:
    _updater_available = False


def get_claude_connection_state() -> dict:
    """
    Cheap, poll-friendly status check for whether LocalLens is actually
    registered as an MCP server in Claude's config (not just whether the
    Claude.app process happens to be running — those are unrelated facts).

    Returns {"connected": bool, "binary_valid": bool}. Safe to call every
    few seconds — it's just a small JSON file read, no subprocess/network.
    """
    if not _connector_available:
        return {"connected": False, "binary_valid": False}
    try:
        res = get_connection_status()
        return {
            "connected": bool(res.get("connected", False)),
            "binary_valid": bool(res.get("binary_valid", False)),
        }
    except Exception:
        return {"connected": False, "binary_valid": False}


# ── Updates ──────────────────────────────────────────────────────────────────


def check_updates_now(force: bool = False) -> dict:
    """
    Check for updates to both the MCP connector/tray (this codebase, versus
    MCP_VERSION) and the LocalLens desktop app/backend (versus its live
    /api/stats app_version, since we have no other way to know it).

    Safe to call from a background thread: network calls are short-timeout
    and disk-cached for 24h by mcp_server.updater, and both checks share a
    single manifest fetch. Never raises.

    Returns {"mcp": dict|None, "app": dict|None} — see check_for_updates()
    and check_app_update() in mcp_server/updater.py for the dict shape.
    """
    if not _updater_available:
        return {"mcp": None, "app": None}
    from .status import get_installed_app_version

    try:
        mcp_update = check_for_updates(force=force)
    except Exception:
        mcp_update = None
    try:
        app_update = check_app_update(get_installed_app_version(), force=force)
    except Exception:
        app_update = None
    return {"mcp": mcp_update, "app": app_update}


def get_current_app_info() -> dict:
    """
    Return version, license tier and LocalLens backend app version for
    display in the Updates submenu info labels.

    All calls are cheap (local file reads + one localhost HTTP request).
    Safe to call from the background poll thread. Never raises.
    """
    mcp_version = "—"
    license_tier = "Free"
    license_activated = False
    app_version = None

    if _updater_available:
        try:
            from mcp_server.updater import MCP_VERSION
            mcp_version = MCP_VERSION
        except Exception:
            pass

    try:
        from mcp_server.license import get_license_info
        li = get_license_info()
        license_activated = bool(li.get("activated", False))
        license_tier = li.get("tier", "free").capitalize()
    except Exception:
        pass

    try:
        from .status import get_installed_app_version
        app_version = get_installed_app_version()
    except Exception:
        pass

    return {
        "mcp_version": mcp_version,
        "license_tier": license_tier,
        "license_activated": license_activated,
        "app_version": app_version,
    }


def install_mcp_update(latest_version: str, release_notes_url: str, upgrade_command: str) -> dict:
    """
    Attempt to install an MCP update.

    For frozen builds (py2app / PyInstaller): opens the releases page in the
    browser — the user downloads the new DMG/zip and replaces the app.
    Silent in-place replacement requires a signed updater (future: Sparkle).

    For pip installs (developer / source): runs `pip install --upgrade
    locallens-mcp` in a subprocess and returns the result.

    Returns {"method": "browser"|"pip", "success": bool, ...}. Never raises.
    """
    import sys as _sys
    url = release_notes_url or "https://github.com/ashesbloom/locallens_mcp_agent/releases/latest"

    if getattr(_sys, "frozen", False):
        # Running as a bundled .app — open the releases page, user installs manually
        open_url(url)
        return {"method": "browser", "success": True, "url": url}

    # pip / source install — upgrade in-place
    try:
        result = subprocess.run(
            [_sys.executable, "-m", "pip", "install", "--upgrade", "locallens-mcp"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return {"method": "pip", "success": True, "output": result.stdout}
        else:
            return {"method": "pip", "success": False, "error": result.stderr or result.stdout}
    except Exception as exc:
        return {"method": "pip", "success": False, "error": str(exc)}



def open_url(url: str):
    """Open an arbitrary URL in the default browser (release notes, downloads)."""
    webbrowser.open(url)


# ── Claude custom instructions (copyable) ─────────────────────────────────────

# The exact payload meant to be pasted verbatim into Claude Desktop's custom
# instructions field — kept separate from any explanatory text so the "Copy"
# action never copies more than what should actually go there.
CLAUDE_CUSTOM_INSTRUCTIONS = (
    "When I mention photo folders, file paths, or ask to analyse/sort/organize photos:\n"
    "- ALWAYS use the LocalLens MCP tools first (analyse_folder, start_sorting, etc.)\n"
    "- NEVER say \"I can't access your files\" or suggest uploading — LocalLens handles file access\n"
    "- ALWAYS call analyse_folder() BEFORE start_sorting() to check for subfolders\n"
    "- ALWAYS default to operation_mode \"copy\" unless I explicitly say \"move\"\n"
    "- NEVER invent destination folder paths — ask me or use get_path_presets()"
)

CLAUDE_INSTRUCTIONS_HOWTO = (
    "Optional, but it saves a lot of back-and-forth: paste this into Claude Desktop's "
    "custom instructions so it uses LocalLens automatically, without you having to prompt it.\n\n"
    "Where to paste it:\n"
    "Claude Desktop -> Settings (gear icon) -> Profile -> "
    "\"What personal preferences should Claude consider in responses?\"\n\n"
    "Click \"Copy to Clipboard\" below, then paste it there."
)


def copy_to_clipboard(text: str) -> bool:
    """
    Copy text to the system clipboard.
    macOS: pbcopy. Windows: clip.exe. Returns True on success, False if the
    clipboard utility isn't available or the copy failed for any reason.
    """
    try:
        if sys.platform == "darwin":
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            return proc.returncode == 0
        elif sys.platform == "win32":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            return proc.returncode == 0
    except Exception:
        pass
    return False


# ── Onboarding / Help ────────────────────────────────────────────────────────

_ONBOARD_MARKER = APP_DIR / "tray_onboarded.txt"

_WELCOME_TEXT = (
    "Welcome to LocalLens Agent! Here's how to get started:\n\n"
    "1. Click \"Local Lens\" in the menu bar to start the backend.\n"
    "2. Open \"Claude\" → \"Connect to Claude\", then restart Claude Desktop.\n"
    "3. Ask Claude to sort or analyse a photo folder — LocalLens tools appear automatically.\n\n"
    "You can revisit this anytime from \"Help & Getting Started\" in the menu."
)

_HELP_TEXT = (
    "What the status dots mean:\n\n"
    "Claude\n"
    "  \U0001F534 Not Connected — click \"Connect to Claude\" to set up\n"
    "  \U0001F7E1 Connecting…\n"
    "  \U0001F7E2 Connected — LocalLens tools are available in Claude\n\n"
    "Local Lens\n"
    "  \U0001F534 Stopped — click to start the backend\n"
    "  \U0001F7E1 Starting… (takes up to 15 seconds)\n"
    "  \U0001F7E2 Running — click to stop\n"
    "  \U0001F535 Running · Managed by App — the LocalLens desktop app controls the backend\n\n"
    "Tip: after connecting or disconnecting, restart Claude Desktop "
    "so it picks up the change."
)


def show_welcome():
    """One-time onboarding alert shown on the tray's first-ever launch."""
    _show_alert("Welcome to LocalLens", _WELCOME_TEXT)


def show_help_tips():
    """On-demand help, reachable anytime from the menu."""
    _show_alert("LocalLens — Help & Getting Started", _HELP_TEXT)


def maybe_show_welcome() -> bool:
    """
    Show the welcome alert once per install. Must be called from the main
    thread after the Cocoa run loop is active (e.g. from the first tick of
    a rumps.timer), not directly inside run_mac_tray() before app.run().

    Returns True if this call actually triggered the first-run welcome
    (so the caller can chain the "add these instructions to Claude" prompt
    right after it), False if onboarding already happened previously.
    """
    if _ONBOARD_MARKER.exists():
        return False
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        _ONBOARD_MARKER.write_text("1")
    except Exception:
        pass
    show_welcome()
    return True

def _show_alert(title, message):
    import threading
    on_main = threading.current_thread() is threading.main_thread()

    if sys.platform == "darwin":
        if on_main:
            import rumps
            rumps.alert(title, message)
        else:
            # Background threads have no Cocoa run loop — rumps.alert() silently
            # fails. Queue the message; the @rumps.timer(1) in tray_mac.py drains
            # it on the main thread every second.
            try:
                from . import tray_mac as _tray_mac
                _tray_mac._pending_alerts.append((title, message))
            except Exception:
                # Absolute fallback (e.g. during testing outside tray context)
                import rumps
                rumps.alert(title, message)
    elif sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0)

def _confirm_action(title, message):
    if sys.platform == "darwin":
        import rumps
        res = rumps.alert(title, message, cancel=True)
        return res == 1
    elif sys.platform == "win32":
        import ctypes
        MB_YESNO = 0x04
        MB_ICONQUESTION = 0x20
        IDYES = 6
        res = ctypes.windll.user32.MessageBoxW(0, message, title, MB_YESNO | MB_ICONQUESTION)
        return res == IDYES

def open_claude():
    """Launch the Claude desktop application or open browser if not found."""
    try:
        if sys.platform == "darwin":
            # Check if Claude is in Applications
            claude_path = "/Applications/Claude.app"
            if os.path.exists(claude_path) or os.path.exists(os.path.expanduser("~/Applications/Claude.app")):
                subprocess.Popen(["open", "-a", "Claude"])
            else:
                webbrowser.open("https://claude.ai")
        elif sys.platform == "win32":
            # Finding Windows Store/app installation path is complex, try simple shell execute
            try:
                subprocess.Popen(["start", "claude:"], shell=True)
            except Exception:
                webbrowser.open("https://claude.ai")
        else:
            webbrowser.open("https://claude.ai")
    except Exception as e:
        print(f"Error opening Claude: {e}")
        webbrowser.open("https://claude.ai")

def start_locallens():
    """
    Start the LocalLens backend silently.

    Returns:
        list[int] — PIDs of the backend_server worker processes that are now
                    running. The tray OWNS these and should stop them on quit.
        []        — Empty list = backend started but tray can't own it (e.g.
                    HTTP is up but PIDs not found — race condition).
        False     — Failed to start, or already running.
    """
    import tempfile
    from .status import is_locallens_running, find_backend_pids
    print(f"[LocalLens] start_locallens() called. sys.frozen={getattr(sys, 'frozen', False)!r}")

    # --- Guard: refuse to start if already running ---
    if is_locallens_running():
        existing_pids = find_backend_pids()
        pid_str = ", ".join(str(p) for p in existing_pids) if existing_pids else "unknown"
        _show_alert(
            "LocalLens Already Running",
            f"The LocalLens backend is already running (PID: {pid_str}).\n"
            "Stop it first before starting a new instance."
        )
        return False

    # NOTE: We intentionally do NOT try `open -a LocalLens` here.
    # That command matches the tray's own bundle name and returns 0 immediately,
    # causing a false-positive where the tray thinks the desktop app started the
    # backend and returns early without actually launching anything.
    # The tray always launches the backend directly and owns its PID.

    install_dir = get_locallens_install_dir()
    print(f"[LocalLens] install_dir from install_dir.txt: {install_dir}")

    if not install_dir or not install_dir.exists():
        # --- Fallback: probe standard OS install paths for the sidecar exe ---
        # For production users (installed via .msi / .dmg) the backend is a
        # PyInstaller executable bundled inside the Tauri desktop app, not a
        # Python source tree.  Try to find it directly before giving up.
        backend_exe = find_locallens_backend_exe()
        if backend_exe:
            print(f"[LocalLens] Found production backend_server exe at {backend_exe}")
            import tempfile
            stderr_log = Path(tempfile.gettempdir()) / "locallens_backend_start.log"
            with open(stderr_log, "w") as err_fh:
                if sys.platform == "win32":
                    proc = subprocess.Popen(
                        [str(backend_exe)],
                        stdout=subprocess.DEVNULL,
                        stderr=err_fh,
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    proc = subprocess.Popen(
                        [str(backend_exe)],
                        stdout=subprocess.DEVNULL,
                        stderr=err_fh,
                    )
            print(f"[LocalLens] backend_server launched, PID={proc.pid}")
            # Wait up to 10 s for the HTTP server to come up
            from .status import is_locallens_running
            for _ in range(20):
                time.sleep(0.5)
                if is_locallens_running():
                    return [proc.pid]
            return [proc.pid]  # return PID even if HTTP check timed out

        # --- No installation found — prompt to download ---
        if sys.platform == "win32":
            import ctypes
            # MB_YESNO (4) + MB_ICONQUESTION (32): Yes=6, No=7
            msg = (
                "Local Lens desktop app was not found on this machine.\n\n"
                "The MCP Agent needs Local Lens installed to start the backend.\n\n"
                "Click Yes to open the download page, or No to close this dialog."
            )
            result = ctypes.windll.user32.MessageBoxW(0, msg, "Local Lens Not Installed", 4 | 32)
            if result == 6:  # Yes — open releases page then confirm
                open_locallens_releases()
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "The Local Lens download page has been opened in your browser.\n\n"
                    "Install Local Lens and then restart the LocalLens Agent tray.",
                    "Download Started",
                    0x40  # MB_ICONINFORMATION
                )
            return "not_installed"
        else:
            _show_alert(
                "Local Lens Not Found",
                "Could not find Local Lens installation.\n\n"
                f"Expected path: {install_dir or 'unknown (install_dir.txt missing or empty)'}\n\n"
                "Opening the download page."
            )
            open_locallens_releases()
        return False

    try:
        if sys.platform == "win32":
            python_exe = install_dir / "venv" / "Scripts" / "python.exe"
        else:
            python_exe = install_dir / "venv" / "bin" / "python"

        if not python_exe.exists():
            print(f"[LocalLens] venv python not found at {python_exe}, using sys.executable")
            python_exe = Path(sys.executable)

        main_script = install_dir / "main.py"
        print(f"[LocalLens] python_exe={python_exe} (exists={python_exe.exists()})")
        print(f"[LocalLens] main_script={main_script} (exists={main_script.exists()})")

        if not main_script.exists():
            _show_alert(
                "Error Starting LocalLens",
                f"main.py not found in:\n{install_dir}\n\n"
                "Please check your LocalLens installation."
            )
            return False

        # Capture stderr to a temp file so we can surface errors in the alert.
        stderr_log = Path(tempfile.gettempdir()) / "locallens_backend_start.log"
        print(f"[LocalLens] Launching backend: {python_exe} {main_script}")
        print(f"[LocalLens] stderr → {stderr_log}")

        # Build a CLEAN environment for the backend subprocess.
        # The tray is a py2app bundle: py2app sets PYTHONPATH / PYTHONHOME /
        # RESOURCEPATH in os.environ so its own packages are found. If those
        # vars are inherited by the backend's Python process it will pick up
        # the WRONG starlette, fastapi, etc. from the tray's zip archive.
        #
        # PYTHONHOME is the most critical: Python's C loader reads it BEFORE
        # PYTHONPATH, redirecting the entire stdlib to the bundle's Resources.
        _PY2APP_VARS = {
            "PYTHONPATH", "PYTHONHOME", "RESOURCEPATH", "ARGVZERO",
            "EXECUTABLEPATH", "DYLD_FRAMEWORK_PATH", "DYLD_LIBRARY_PATH",
            "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
        }
        clean_env = {k: v for k, v in os.environ.items() if k not in _PY2APP_VARS}
        print(f"[LocalLens] Stripped env vars: {_PY2APP_VARS & set(os.environ)}")

        with open(stderr_log, "w") as err_fh:
            if sys.platform == "win32":
                subprocess.Popen(
                    [str(python_exe), str(main_script)],
                    cwd=str(install_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=err_fh,
                    env=clean_env,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
                )
            else:
                subprocess.Popen(
                    [str(python_exe), str(main_script)],
                    cwd=str(install_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=err_fh,
                    env=clean_env,
                    start_new_session=True
                )

        # Poll for up to 15 seconds (0.5s increments) for backend PIDs to appear.
        # The backend calls setproctitle() before any heavy imports, so it renames
        # itself to 'LocalLens-Backend' very quickly after exec.
        deadline = time.time() + 15
        while time.time() < deadline:
            time.sleep(0.5)
            worker_pids = find_backend_pids()
            print(f"[LocalLens] polling... find_backend_pids()={worker_pids}")
            if worker_pids:
                print(f"[LocalLens] Backend started. Tray owns PIDs: {worker_pids}")
                return worker_pids  # Tray owns these worker PIDs

        # Timed out — check if HTTP is at least up (backend started but pid detection failed)
        if is_locallens_running():
            print("[LocalLens] Backend HTTP-reachable but PIDs not tracked — treating as unowned")
            return []  # Running but can't own it

        # Read the last few lines from stderr log for the error dialog
        error_detail = ""
        try:
            log_text = stderr_log.read_text(encoding="utf-8", errors="replace")
            last_lines = "\n".join(log_text.strip().splitlines()[-8:]) if log_text.strip() else "(no output)"
            error_detail = f"\n\nError output:\n{last_lines}"
        except Exception:
            pass

        _show_alert(
            "Error Starting LocalLens",
            f"Backend did not start within 15 seconds.\n\n"
            f"Tried: {main_script}\n"
            f"Python: {python_exe}"
            f"{error_detail}\n\n"
            f"Full log: {stderr_log}"
        )
        return False

    except Exception as e:
        print(f"[LocalLens] Exception in start_locallens: {e}")
        _show_alert("Error Starting LocalLens", str(e))
        return False


def stop_backend_pids(pids: list) -> bool:
    """
    Stop a specific list of backend worker PIDs (returned by start_locallens).
    Falls back to stop_all_backends() if any PID is already dead.
    Returns True if all stopped successfully.
    """
    if not pids:
        return True
    try:
        import psutil
        targets = []
        for pid in pids:
            try:
                proc = psutil.Process(pid)
                name = proc.name().lower()
                if 'tray' not in name:
                    targets.append(proc)
                    try:
                        targets.extend(proc.children(recursive=True))
                    except psutil.NoSuchProcess:
                        pass
            except psutil.NoSuchProcess:
                pass  # Already gone — that's fine

        for proc in targets:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        _, alive = psutil.wait_procs(targets, timeout=5)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return True
    except Exception as e:
        _show_alert("Error Stopping LocalLens", str(e))
        return False


def stop_locallens_backend(pid: int) -> bool:
    """
    Stop a LocalLens backend process that the tray started directly.
    Kills the given PID AND all its child processes (e.g. uvicorn/gunicorn
    workers) so that no orphaned backend_server processes remain.

    Only call this with a PID that start_locallens() returned.
    Returns True if everything terminated cleanly.
    """
    try:
        import psutil

        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return True  # Already gone

        # Collect children BEFORE terminating the parent, while they're
        # still attached and visible in the process tree.
        try:
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            children = []

        # Sanity-check: never kill our own tray process
        try:
            parent_name = parent.name().lower()
            if "tray" in parent_name:
                return False
        except psutil.NoSuchProcess:
            pass

        # Terminate parent + all workers
        targets = [parent] + children
        for proc in targets:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Wait up to 5 s for a clean exit, then force-kill survivors
        _, alive = psutil.wait_procs(targets, timeout=5)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return True

    except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
        return True  # Already gone — that's fine

    except ImportError:
        # psutil not available — kill the entire process group
        # (start_new_session=True makes the child a session/group leader
        # so its pgid == its pid, and os.killpg kills all workers too)
        try:
            pgid = os.getpgid(pid)
            os.kill(pgid * -1, signal.SIGTERM)  # negative pid = kill group
            return True
        except ProcessLookupError:
            return True
        except Exception:
            return False

    except Exception as e:
        _show_alert("Error Stopping LocalLens", str(e))
        return False


def stop_all_backends() -> bool:
    """
    Find and terminate ALL running LocalLens backend_server processes.

    Used when the LocalLens desktop app was closed but its backend workers
    remained alive as orphans. Uses find_backend_pids() from status.py
    to discover them, then terminates each one (with children).

    Returns True if all were stopped successfully.
    """
    try:
        import psutil
        from .status import find_backend_pids, PORT_FILE

        pids = find_backend_pids()
        if not pids:
            return True  # Nothing to stop

        targets = []
        for pid in pids:
            try:
                proc = psutil.Process(pid)
                name = proc.name().lower()
                if 'tray' in name:
                    continue  # Safety: never kill ourselves
                targets.append(proc)
                # Also grab any children of each backend process
                try:
                    targets.extend(proc.children(recursive=True))
                except psutil.NoSuchProcess:
                    pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Terminate all
        for proc in targets:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Wait, then force-kill survivors
        _, alive = psutil.wait_procs(targets, timeout=5)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Clean up stale port.txt so a fresh start works cleanly
        try:
            PORT_FILE.unlink(missing_ok=True)
        except Exception:
            pass

        return True

    except ImportError:
        # psutil not available — try os.kill on each PID
        from .status import find_backend_pids
        for pid in find_backend_pids():
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        return True

    except Exception as e:
        _show_alert("Error Stopping LocalLens", str(e))
        return False

def open_locallens_releases():
    """Open the LocalLens desktop app releases page in the default browser."""
    webbrowser.open("https://github.com/ashesbloom/LocalLens/releases/latest")


def find_locallens_backend_exe() -> Path:
    """
    Locate the LocalLens backend_server executable for *production* installs
    (i.e. users who installed via the .msi/.dmg installer, not from source).

    The backend is a PyInstaller sidecar bundled inside the Tauri desktop app.
    The LocalLens app writes install_info.json to the app-data dir on first
    launch (once that feature is added).  Until then we probe the standard
    OS install paths that Tauri's NSIS/dmg installers use.

    Returns the Path to backend_server[.exe] if found, else None.
    """
    candidates = []

    if sys.platform == "win32":
        # 1. Prefer install_info.json written by the LocalLens app itself
        install_info = APP_DIR / "install_info.json"
        if install_info.exists():
            try:
                info = json.loads(install_info.read_text())
                exe = Path(info.get("backend_exe", ""))
                if exe.exists():
                    return exe
            except Exception:
                pass

        # 2. Standard Tauri NSIS install locations
        for base_var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(base_var, "")
            if base:
                candidates.append(Path(base) / "Local Lens" / "backend_server.exe")
                candidates.append(Path(base) / "LocalLens" / "backend_server.exe")
        # 3. Possible roaming appdata location
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "Local Lens" / "backend_server.exe")

    elif sys.platform == "darwin":
        # 1. Prefer install_info.json
        install_info = Path.home() / "Library" / "Application Support" / "LocalLens" / "install_info.json"
        if install_info.exists():
            try:
                info = json.loads(install_info.read_text())
                exe = Path(info.get("backend_exe", ""))
                if exe.exists():
                    return exe
            except Exception:
                pass

        # 2. Standard macOS .app bundle sidecar locations
        candidates += [
            Path("/Applications/Local Lens.app/Contents/MacOS/backend_server"),
            Path("/Applications/LocalLens.app/Contents/MacOS/backend_server"),
            Path.home() / "Applications" / "Local Lens.app" / "Contents" / "MacOS" / "backend_server",
        ]

    for p in candidates:
        if p.exists():
            print(f"[LocalLens] find_locallens_backend_exe: found {p}")
            return p

    return None

def show_claude_status_terminal():
    """Open a terminal showing Claude MCP logs."""
    try:
        if sys.platform == "darwin":
            script = 'tell application "Terminal" to do script "tail -f ~/Library/Logs/Claude/mcp*.log"'
            subprocess.Popen(["osascript", "-e", script])
        elif sys.platform == "win32":
            subprocess.Popen(["powershell", "-Command", "Start-Process powershell -ArgumentList '-NoExit -Command Get-Content -Path $env:APPDATA\\Claude\\logs\\mcp*.log -Tail 100 -Wait'"])
    except Exception as e:
        _show_alert("Error opening terminal", str(e))

def claude_setup() -> dict:
    """
    Run locallens-mcp --setup-claude via connector and show a status alert.

    Returns the raw install_claude_connector() result dict so the caller
    (tray_mac.on_claude_setup) can decide whether to also surface the
    optional "copy these instructions into Claude" window right after —
    that used to be baked into this function's alert text, gated on
    `res.get("status") == "success"`, a status install_claude_connector()
    never actually returns (real values are "installed"/"updated"/
    "already_connected"/"error"), so it silently never fired.
    """
    if not _connector_available:
        _show_alert("Error", "Claude connector not available. Please reinstall LocalLens MCP.")
        return {"status": "error"}
    try:
        res = install_claude_connector(force=False)
        msg = res.get("message", json.dumps(res))
        # On Windows, if Claude Desktop is missing, offer a direct download button
        if sys.platform == "win32" and res.get("status") == "error" and "claude.ai/download" in msg:
            import ctypes
            prompt = (
                "Claude Desktop does not appear to be installed.\n\n"
                "Would you like to open the Claude Desktop download page?\n"
                "Click Yes to open the browser, or No to skip."
            )
            result = ctypes.windll.user32.MessageBoxW(0, prompt, "Claude Not Installed", 4 | 32)
            if result == 6:  # Yes — open download page
                webbrowser.open("https://claude.ai/download")
        else:
            _show_alert("Claude Setup", msg)
        return res
    except Exception as e:
        _show_alert("Claude Setup Error", str(e))
        return {"status": "error"}

def claude_status():
    """Run locallens-mcp --claude-status via connector and show alert."""
    if not _connector_available:
        _show_alert("Error", "Claude connector not available.")
        return
    try:
        res = get_connection_status()
        if res.get("connected"):
            lines = [
                "✅ Connected to Claude",
                f"Command: {res.get('command')}",
                f"Config: {res.get('config_path')}"
            ]
            if res.get("binary_valid"):
                lines.append("Binary: Valid")
            else:
                lines.append("Binary: Invalid/Missing")
            _show_alert("Claude Status", "\n".join(lines))
        else:
            _show_alert("Claude Status", "⚪ Not connected to Claude.\nUse 'Connect to Claude' to set it up.")
    except Exception as e:
        _show_alert("Claude Status Error", str(e))

def claude_remove():
    """Run locallens-mcp --remove-claude via connector and show alert."""
    if not _connector_available:
        _show_alert("Error", "Claude connector not available.")
        return
    if not _confirm_action("Confirm Disconnect", "Are you sure you want to disconnect LocalLens from Claude?"):
        return
    try:
        res = uninstall_claude_connector()
        msg = res.get("message", json.dumps(res))
        _show_alert("Claude Remove", msg)
    except Exception as e:
        _show_alert("Claude Remove Error", str(e))
