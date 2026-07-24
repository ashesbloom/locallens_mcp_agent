"""
Windows system-tray app for LocalLens Agent.

Full parity with the macOS rumps-based tray (tray_mac.py).  Uses pystray
for the system tray icon and ctypes MessageBoxW for native dialogs.

Architecture:
  - Background polling thread: updates cached status globals every 3 s
  - Background update-check thread: checks for updates every hour
  - Refresh thread: calls icon.update_menu() every 1 s + drains alert queue
  - All blocking operations (start/stop backend, connect/disconnect Claude)
    run in background threads — never block the pystray callback thread
  - Alerts are shown via MessageBoxW (thread-safe on Windows)
"""
import threading
import time
import sys
import os
import signal
import ctypes
import pystray
from PIL import Image

from .status import is_locallens_running, is_locallens_app_running
from .actions import (
    open_claude, start_locallens, stop_backend_pids, stop_all_backends,
    show_claude_status_terminal,
    claude_setup, claude_status, claude_remove,
    get_claude_connection_state, maybe_show_welcome, show_help_tips,
    check_updates_now, open_url, copy_to_clipboard,
    get_current_app_info, install_mcp_update,
    CLAUDE_CUSTOM_INSTRUCTIONS, CLAUDE_INSTRUCTIONS_HOWTO,
)


# ── Status indicators ────────────────────────────────────────────────────────
# Matching the Mac tray exactly: four Unicode large-circle emoji
STATUS_OFF = "🔴"          # not running / not connected
STATUS_STARTING = "🟡"     # transient: starting / connecting / stopping
STATUS_ON = "🟢"           # running / connected
STATUS_EXTERNAL = "🔵"     # running, but owned by the LocalLens desktop app


# ── Cached state (written by background threads, read by menu text fns) ──────
_cached_claude_connected = False
_cached_claude_binary_valid = False
_cached_ll_running = False
_cached_app_running = False
_managed_ll_pids: list = []
_stop_event = threading.Event()

# Transient action states — drive the 🟡 indicators
_claude_action_in_progress = False
_ll_starting = False
_ll_stopping = False

# Update cache
_cached_update_info: dict = {"mcp": None, "app": None}
_notified_update_versions: set = set()
_cached_app_info: dict = {
    "mcp_version": "…", "license_tier": "Free",
    "license_activated": False, "app_version": None,
}

# Pending alerts queue — background threads append, refresh thread drains.
# Protected by a lock because multiple threads can append concurrently.
_pending_alerts: list = []
_pending_alerts_lock = threading.Lock()

# Global reference so background threads can call icon.update_menu()
_icon: pystray.Icon = None


# ── Win32 helpers ─────────────────────────────────────────────────────────────

MB_OK = 0x00
MB_YESNO = 0x04
MB_ICONINFO = 0x40
MB_ICONQUESTION = 0x20
MB_ICONWARNING = 0x30
IDYES = 6


def _msg_box(title: str, message: str, flags: int = MB_OK | MB_ICONINFO) -> int:
    """Thread-safe wrapper around MessageBoxW."""
    return ctypes.windll.user32.MessageBoxW(0, message, title, flags)


def _confirm(title: str, message: str) -> bool:
    """Show a Yes / No dialog.  Returns True if user clicked Yes."""
    return _msg_box(title, message, MB_YESNO | MB_ICONQUESTION) == IDYES


# ── PID helpers ───────────────────────────────────────────────────────────────

def _is_pid_alive(pid: int) -> bool:
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
    except Exception:
        return False


def _any_pid_alive(pids: list) -> bool:
    return any(_is_pid_alive(p) for p in pids)


# ── Background polling threads ───────────────────────────────────────────────

def _poll_status():
    """Poll backend / Claude connection status every 3 seconds."""
    global _cached_claude_connected, _cached_claude_binary_valid
    global _cached_ll_running, _cached_app_running, _managed_ll_pids
    while not _stop_event.is_set():
        # Claude connection state (reads config JSON — no process scan)
        state = get_claude_connection_state()
        _cached_claude_connected = state["connected"]
        _cached_claude_binary_valid = state["binary_valid"]

        _cached_app_running = is_locallens_app_running()

        if _managed_ll_pids:
            if _any_pid_alive(_managed_ll_pids):
                _cached_ll_running = True
            else:
                _managed_ll_pids = []
                _cached_ll_running = is_locallens_running()
        else:
            _cached_ll_running = is_locallens_running()

        _stop_event.wait(3)


_UPDATE_CHECK_INTERVAL_SECONDS = 3600


def _queue_update_notifications(update_info: dict):
    """Append a one-time alert for any update not already surfaced this session."""
    labels = {"mcp": "LocalLens MCP Connector", "app": "LocalLens App"}
    for key, label in labels.items():
        info = update_info.get(key)
        if not info or not info.get("update_available"):
            continue
        token = f"{key}:{info['latest_version']}"
        if token in _notified_update_versions:
            continue
        _notified_update_versions.add(token)
        with _pending_alerts_lock:
            _pending_alerts.append((
                f"Update Available — {label}",
                f"{label} {info['latest_version']} is available "
                f"(you have {info['current_version']}).\n\n"
                "Open \"Updates\" in the tray menu to see what's new and download it."
            ))


def _update_check_loop():
    """Check for updates once an hour (disk-cached; doesn't hit network every time)."""
    global _cached_update_info, _cached_app_info
    while not _stop_event.is_set():
        info = check_updates_now()
        _queue_update_notifications(info)
        _cached_update_info = info
        try:
            _cached_app_info = get_current_app_info()
        except Exception:
            pass
        _stop_event.wait(_UPDATE_CHECK_INTERVAL_SECONDS)


def _refresh_loop():
    """
    Every 1 s: refresh the menu text and drain any queued alerts.

    Also runs one-time onboarding on the first tick (after the icon is live).
    """
    onboarding_done = False
    while not _stop_event.is_set():
        # ── One-time onboarding ──────────────────────────────────────────
        if not onboarding_done:
            onboarding_done = True
            if maybe_show_welcome():
                _show_claude_instructions_dialog()

        # ── Drain pending alerts ─────────────────────────────────────────
        while True:
            with _pending_alerts_lock:
                if not _pending_alerts:
                    break
                title, message = _pending_alerts.pop(0)
            _msg_box(title, message)

        # ── Refresh menu text ────────────────────────────────────────────
        if _icon is not None:
            try:
                _icon.update_menu()
            except Exception:
                pass

        _stop_event.wait(1)


# ── Icon loading ──────────────────────────────────────────────────────────────

def _load_tray_icon() -> Image.Image:
    """
    Load the bundled black LL icon (visible on both light and dark taskbars).
    Tries the PyInstaller bundle path first, then the dev-mode project root.
    Falls back to a dark programmatic icon if the file can't be found.
    """
    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "icons", "ll_black", "32x32.png"))
    # Dev-mode: icons/ sits two levels above this file (src/tray/tray_win.py)
    dev_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.append(os.path.join(dev_root, "icons", "ll_black", "32x32.png"))

    for path in candidates:
        if os.path.exists(path):
            try:
                return Image.open(path).convert("RGBA")
            except Exception:
                pass  # corrupt file — fall through to programmatic fallback

    # Fallback: dark programmatic icon
    from PIL import ImageDraw, ImageFont
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "LL", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - tw) / 2, (64 - th) / 2), "LL", fill="#1a1a1a", font=font)
    return image


# ── Dynamic menu text (called by pystray on every menu open) ─────────────────

def _claude_title(_item=None):
    if _claude_action_in_progress:
        return f"{STATUS_STARTING}  Claude — Connecting…"
    if not _cached_claude_connected:
        return f"{STATUS_OFF}  Claude — Not Connected"
    if not _cached_claude_binary_valid:
        return f"{STATUS_OFF}  Claude — Connection Error"
    return f"{STATUS_ON}  Claude — Connected"


def _ll_title(_item=None):
    if _ll_starting:
        return f"{STATUS_STARTING}  Local Lens — Starting…"
    if _ll_stopping:
        return f"{STATUS_STARTING}  Local Lens — Stopping…"
    if not _cached_ll_running:
        return f"{STATUS_OFF}  Local Lens — Stopped"
    if _cached_app_running:
        return f"{STATUS_EXTERNAL}  Local Lens — Running · Managed by App"
    return f"{STATUS_ON}  Local Lens — Running"


def _updates_title(_item=None):
    mcp_u = _cached_update_info.get("mcp")
    app_u = _cached_update_info.get("app")
    if not mcp_u and not app_u:
        return f"{STATUS_ON}  Updates — Up to Date"
    parts = []
    if mcp_u:
        parts.append(f"MCP v{mcp_u['latest_version']}")
    if app_u:
        parts.append(f"App v{app_u['latest_version']}")
    return f"{STATUS_STARTING}  Updates — Available — {', '.join(parts)}"


def _info_mcp_title(_item=None):
    return f"  ℹ  MCP Agent v{_cached_app_info.get('mcp_version', '…')}"


def _info_plan_title(_item=None):
    return f"  ℹ  Plan: {_cached_app_info.get('license_tier', 'Free')}"


def _info_app_title(_item=None):
    app_ver = _cached_app_info.get("app_version")
    if app_ver:
        return f"  ℹ  LocalLens App v{app_ver}"
    if _cached_ll_running:
        return "  ℹ  LocalLens App: Running"
    return "  ℹ  LocalLens App: Not Running"


def _install_update_title(_item=None):
    mcp_u = _cached_update_info.get("mcp")
    if mcp_u and mcp_u.get("update_available"):
        return f"⬇  Install Update v{mcp_u['latest_version']}…"
    return "✓  MCP Agent is Up to Date"


# ── Menu callbacks ────────────────────────────────────────────────────────────

def on_open_claude(icon, item):
    open_claude()


def on_claude_setup(icon, item):
    """Connect to Claude — runs in a background thread so the tray stays responsive."""
    global _claude_action_in_progress
    if _claude_action_in_progress:
        return
    _claude_action_in_progress = True
    if _icon:
        _icon.update_menu()

    def _setup_bg():
        global _claude_action_in_progress
        res = {"status": "error"}
        try:
            res = claude_setup()
        finally:
            _claude_action_in_progress = False
            _refresh_claude_state_now()
        if res.get("status") in ("installed", "updated", "already_connected"):
            _show_claude_instructions_dialog()

    threading.Thread(target=_setup_bg, daemon=True).start()


def _refresh_claude_state_now():
    """Immediately refresh Claude connection state (no 3 s wait)."""
    global _cached_claude_connected, _cached_claude_binary_valid
    state = get_claude_connection_state()
    _cached_claude_connected = state["connected"]
    _cached_claude_binary_valid = state["binary_valid"]
    if _icon:
        _icon.update_menu()


def on_claude_status_check(icon, item):
    threading.Thread(target=claude_status, daemon=True).start()


def on_claude_remove(icon, item):
    global _claude_action_in_progress
    if _claude_action_in_progress:
        return
    _claude_action_in_progress = True
    if _icon:
        _icon.update_menu()

    def _remove_bg():
        global _claude_action_in_progress
        try:
            claude_remove()
        finally:
            _claude_action_in_progress = False
            _refresh_claude_state_now()

    threading.Thread(target=_remove_bg, daemon=True).start()


def on_copy_instructions(icon, item):
    threading.Thread(target=_show_claude_instructions_dialog, daemon=True).start()


def _show_claude_instructions_dialog():
    """Show custom instructions and offer to copy them to clipboard."""
    msg = (
        f"{CLAUDE_INSTRUCTIONS_HOWTO}\n\n"
        "─── Instructions to copy ───\n\n"
        f"{CLAUDE_CUSTOM_INSTRUCTIONS}\n\n"
        "─────────────────────────\n\n"
        "Click Yes to copy these instructions to your clipboard,\n"
        "or No to skip."
    )
    if _confirm("Add LocalLens to Claude's Instructions (optional)", msg):
        if copy_to_clipboard(CLAUDE_CUSTOM_INSTRUCTIONS):
            _msg_box(
                "Copied!",
                "The instructions are now on your clipboard.\n"
                "Paste them into Claude Desktop's custom instructions field."
            )
        else:
            _msg_box(
                "Copy Failed",
                "Could not access the clipboard.\n"
                "Please copy the instructions manually.",
                MB_OK | MB_ICONWARNING,
            )


def on_claude_terminal(icon, item):
    show_claude_status_terminal()


def on_ll_status(icon, item):
    """
    Start / stop the LocalLens backend.

    Heavy work (start_locallens polls for up to 15 s, stop can take 5 s) runs
    on a background thread so the tray menu never freezes.
    """
    global _ll_starting, _ll_stopping
    global _cached_ll_running, _cached_app_running, _managed_ll_pids

    if not _cached_ll_running and not _ll_starting:
        # ── NOT RUNNING: start in background ─────────────────────────────
        _ll_starting = True
        if _icon:
            _icon.update_menu()

        def _start_bg():
            global _ll_starting, _cached_ll_running, _cached_app_running, _managed_ll_pids
            try:
                result = start_locallens()
            except Exception as exc:
                _ll_starting = False
                with _pending_alerts_lock:
                    _pending_alerts.append(("Error Starting LocalLens", str(exc)))
                if _icon:
                    _icon.update_menu()
                return

            _ll_starting = False

            if result == "not_installed":
                # User was shown the download prompt. Quit the tray — there's
                # nothing it can do without LocalLens installed.
                _stop_event.set()
                if _icon:
                    _icon.stop()
                os._exit(0)

            if result is not False:
                _managed_ll_pids = result if isinstance(result, list) else []
                _cached_ll_running = is_locallens_running()
                _cached_app_running = is_locallens_app_running()

            if _icon:
                _icon.update_menu()

        threading.Thread(target=_start_bg, daemon=True).start()

    elif _cached_app_running and not _ll_starting:
        # ── DESKTOP APP IS RUNNING: don't touch it ───────────────────────
        with _pending_alerts_lock:
            _pending_alerts.append((
                "LocalLens is Running",
                "The LocalLens desktop app is currently open.\n"
                "Close the desktop app first if you want the agent "
                "to manage the backend."
            ))

    elif _cached_ll_running and not _cached_app_running and not _ll_starting and not _ll_stopping:
        # ── BACKEND ALIVE BUT APP GONE: stop in background ───────────────
        _ll_stopping = True
        if _icon:
            _icon.update_menu()

        def _stop_bg():
            global _ll_stopping, _cached_ll_running, _managed_ll_pids
            try:
                stopped = False
                if _managed_ll_pids:
                    stopped = stop_backend_pids(_managed_ll_pids)
                if not stopped:
                    stopped = stop_all_backends()
                if stopped:
                    _managed_ll_pids = []
                    _cached_ll_running = False
            finally:
                _ll_stopping = False
                if _icon:
                    _icon.update_menu()

        threading.Thread(target=_stop_bg, daemon=True).start()


def on_check_updates(icon, item):
    """Check for updates in the background."""
    def _check_bg():
        global _cached_update_info, _cached_app_info
        info = check_updates_now(force=True)
        _cached_update_info = info
        try:
            _cached_app_info = get_current_app_info()
        except Exception:
            pass
        mcp_u, app_u = info.get("mcp"), info.get("app")
        if mcp_u or app_u:
            lines = []
            if mcp_u:
                lines.append(
                    f"LocalLens MCP Connector: v{mcp_u['latest_version']} available "
                    f"(you have {mcp_u['current_version']})."
                )
            if app_u:
                lines.append(
                    f"LocalLens App: v{app_u['latest_version']} available "
                    f"(you have {app_u['current_version']})."
                )
            with _pending_alerts_lock:
                _pending_alerts.append((
                    "Update Available",
                    "\n".join(lines) + "\n\nUse \"Install Update…\" in the Updates menu to upgrade."
                ))
        else:
            ai = _cached_app_info
            mcp_ver = ai.get("mcp_version", "—")
            tier = ai.get("license_tier", "Free")
            with _pending_alerts_lock:
                _pending_alerts.append((
                    "You're Up to Date  ✓",
                    f"MCP Agent v{mcp_ver} · {tier} Plan\nEverything is on the latest version."
                ))
        if _icon:
            _icon.update_menu()

    threading.Thread(target=_check_bg, daemon=True).start()


def on_update_details(icon, item):
    """Show update details or current version info."""
    def _details_bg():
        mcp_u = _cached_update_info.get("mcp")
        app_u = _cached_update_info.get("app")
        info = _cached_app_info

        if not mcp_u and not app_u:
            mcp_ver = info.get("mcp_version", "unknown")
            tier = info.get("license_tier", "Free")
            app_ver = info.get("app_version")
            app_line = f"LocalLens App v{app_ver}" if app_ver else "LocalLens App: not running"
            _msg_box(
                "You're Up to Date  ✓",
                f"MCP Agent v{mcp_ver} · {tier} Plan\n{app_line}\n\n"
                "Everything is on the latest version."
            )
            return

        lines = []
        if mcp_u:
            lines.append(
                f"MCP Agent — v{mcp_u['latest_version']} available  "
                f"(you have v{mcp_u['current_version']})"
            )
            for h in mcp_u.get("highlights", []):
                lines.append(f"   • {h}")
        if app_u:
            if lines:
                lines.append("")
            lines.append(
                f"LocalLens App — v{app_u['latest_version']} available  "
                f"(you have v{app_u['current_version']})"
            )

        msg = "\n".join(lines) + "\n\nWould you like to install the update?"
        if _confirm("Update Available", msg):
            _install_update_bg()

    threading.Thread(target=_details_bg, daemon=True).start()


def _install_update_bg():
    """Shared update logic — always call from a background thread."""
    mcp_u = _cached_update_info.get("mcp")
    info = _cached_app_info
    mcp_ver = info.get("mcp_version", "unknown")

    if not mcp_u or not mcp_u.get("update_available"):
        _msg_box(
            "Already Up to Date  ✓",
            f"MCP Agent v{mcp_ver} is the latest version. Nothing to install."
        )
        return

    latest = mcp_u["latest_version"]
    highlights = mcp_u.get("highlights", [])
    hl_text = ("\n" + "\n".join(f"   • {h}" for h in highlights[:5])) if highlights else ""

    msg = (
        f"Current version: v{mcp_ver}\n"
        f"New version:     v{latest}"
        f"{hl_text}\n\n"
        "The download page will open in your browser.\n"
        "Replace the existing app with the new one after downloading.\n\n"
        "Proceed with the update?"
    )
    if not _confirm(f"Install MCP Update v{latest}", msg):
        return

    result = install_mcp_update(
        latest_version=latest,
        release_notes_url=mcp_u.get("release_notes_url", ""),
        upgrade_command=mcp_u.get("upgrade_command", ""),
    )

    if result.get("method") == "pip":
        if result.get("success"):
            _msg_box(
                "Update Installed  ✓",
                f"LocalLens MCP has been updated to v{latest}.\n"
                "Restart LocalLens Agent for the changes to take effect."
            )
        else:
            _msg_box(
                "Update Failed",
                f"Could not install v{latest} via pip:\n\n"
                f"{result.get('error', 'Unknown error')}\n\n"
                "Try updating manually from the releases page.",
                MB_OK | MB_ICONWARNING,
            )


def on_install_update(icon, item):
    """One-click update: pip-upgrade for source installs, browser for frozen builds."""
    threading.Thread(target=_install_update_bg, daemon=True).start()


def on_help(icon, item):
    threading.Thread(target=show_help_tips, daemon=True).start()


def on_quit(icon, item):
    """Stop owned backends and exit the tray app cleanly."""
    global _managed_ll_pids
    _stop_event.set()
    if _managed_ll_pids:
        stop_backend_pids(_managed_ll_pids)
    elif _cached_ll_running and not _cached_app_running:
        stop_all_backends()
    icon.stop()
    os._exit(0)  # ensure the process truly exits; pystray.stop() alone can leave a zombie on Windows


# ── Build menu and run ────────────────────────────────────────────────────────

def run_win_tray():
    global _icon

    # ── Single-instance enforcement via Win32 named mutex ─────────────
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "LocalLensAgent_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        _msg_box(
            "Already Running",
            "LocalLens Agent is already running.\n\n"
            "Check the system tray (bottom-right, near the clock).",
            MB_OK | MB_ICONINFO,
        )
        os._exit(0)

    # ── Start background threads ─────────────────────────────────────────
    threading.Thread(target=_poll_status, daemon=True).start()
    threading.Thread(target=_update_check_loop, daemon=True).start()

    image = _load_tray_icon()

    # ── Claude submenu ───────────────────────────────────────────────────
    claude_submenu = pystray.Menu(
        pystray.MenuItem("Connect to Claude", on_claude_setup),
        pystray.MenuItem("Check Connection", on_claude_status_check),
        pystray.MenuItem("Disconnect from Claude", on_claude_remove),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Copy Custom Instructions…", on_copy_instructions),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("View MCP Logs", on_claude_terminal),
    )

    # ── Updates submenu ──────────────────────────────────────────────────
    updates_submenu = pystray.Menu(
        pystray.MenuItem(_info_mcp_title, None, enabled=False),
        pystray.MenuItem(_info_plan_title, None, enabled=False),
        pystray.MenuItem(_info_app_title, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Check for Updates", on_check_updates),
        pystray.MenuItem("What's New / Download…", on_update_details),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_install_update_title, on_install_update),
    )

    # ── Main menu ────────────────────────────────────────────────────────
    menu = pystray.Menu(
        pystray.MenuItem("Open Claude", on_open_claude),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_claude_title, claude_submenu),
        pystray.MenuItem(_ll_title, on_ll_status),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_updates_title, updates_submenu),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Help & Getting Started", on_help),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit LocalLens Agent", on_quit),
    )

    _icon = pystray.Icon("LocalLensAgent", image, "LocalLens Agent", menu)

    # Start the refresh/onboarding thread (reads _icon, so must start after it's set)
    threading.Thread(target=_refresh_loop, daemon=True).start()

    _icon.run()
