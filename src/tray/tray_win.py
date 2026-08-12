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
import os
import signal
import ctypes
import pystray
from PIL import Image, ImageDraw, ImageFont

from .status import is_locallens_running, is_locallens_app_running
from .actions import (
    open_claude, start_locallens, stop_backend_pids, stop_all_backends,
    show_claude_status_terminal,
    claude_setup, claude_status, claude_remove,
    get_claude_connection_state, maybe_show_welcome, show_help_tips,
    check_updates_now, open_url, copy_to_clipboard,
    get_current_app_info, install_mcp_update, format_download_progress,
    get_pricing_url, FREE_PREVIEW,
    CLAUDE_CUSTOM_INSTRUCTIONS, CLAUDE_INSTRUCTIONS_HOWTO,
    STATUS_OFF, STATUS_STARTING, STATUS_ON, STATUS_EXTERNAL, STATUS_ALERT,
)


# ── Cached state (written by background threads, read by menu text fns) ──────
_cached_claude_connected = False
_cached_claude_binary_valid = False
_cached_ll_running = False
_cached_app_running = False
_managed_ll_pids: list = []
_cached_dark_taskbar = True
_stop_event = threading.Event()

# Transient action states — drive the ◎ "working" indicators
_claude_action_in_progress = False
_ll_starting = False
_ll_stopping = False

# Update cache
_cached_update_info: dict = {"mcp": None, "app": None}
# (downloaded_bytes, total_bytes), set by the update-download background
# thread; read by _install_update_title. None = no download in progress.
_update_download_progress: tuple = None
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
    global _cached_dark_taskbar
    while not _stop_event.is_set():
        # Repaint the "LL" icon if the user flipped light/dark since last tick
        dark = _taskbar_is_dark()
        if dark != _cached_dark_taskbar:
            _cached_dark_taskbar = dark
            if _icon is not None:
                _icon.icon = _render_ll_icon(dark)

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


# ── Tray icon ─────────────────────────────────────────────────────────────────
#
# The notification area shows the "LL" wordmark, not the app logo — same as the
# macOS menu bar (tray_mac.py sets app.title = "LL").  The logo is a detailed
# starburst; at the 16 px the tray actually renders it collapses into a smudge,
# whereas two letters stay readable.  The app logo is still used everywhere it
# has room: the .exe, the installer, and the taskbar/Alt-Tab entries.

def _taskbar_is_dark() -> bool:
    """
    True when the notification area is drawn dark.

    SystemUsesLightTheme is the *taskbar* toggle; AppsUseLightTheme (the one
    that's easy to grab by mistake) controls in-app chrome and can be set the
    other way round.  Missing value = pre-1903 Windows, which only ever had the
    dark taskbar.
    """
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "SystemUsesLightTheme")[0] == 0
    except Exception:
        return True


def _tray_font(size: int):
    """Segoe UI Bold — the Windows system font. Falls back down to whatever exists."""
    for name in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _render_ll_icon(dark_taskbar: bool) -> Image.Image:
    """
    Draw the "LL" wordmark in whichever ink the current taskbar theme needs.

    The theme flag carries the contrast; the thin outline only defines the edge.
    That covers accent-coloured and translucent taskbars too — Windows offers
    those only while dark mode is on, so they get the light ink. A thicker
    outline would cover the rest, but at the 16 px the tray renders it stops
    being an outline and becomes a halo two-thirds the size of the letters.
    """
    ink, outline = ("#ffffff", "#000000") if dark_taskbar else ("#101010", "#ffffff")
    # 4x the 16 px tray slot — supersampling keeps the downscaled strokes clean,
    # and Windows picks whatever size it needs from this one bitmap.
    size = 64
    # Draw oversized, then crop to the actual glyphs and scale to fit. The font
    # is Segoe UI Bold on Windows but whatever the fallback resolves to
    # elsewhere, and their metrics differ enough that a fixed point size would
    # leave the wordmark cropped on one machine and swimming in space on another.
    scratch = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    ImageDraw.Draw(scratch).text(
        (size // 2, size // 2), "LL", font=_tray_font(size),
        fill=ink, stroke_width=2, stroke_fill=outline,
    )
    glyphs = scratch.crop(scratch.getbbox())
    glyphs.thumbnail((size - 4, size - 4), Image.LANCZOS)

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image.paste(glyphs, ((size - glyphs.width) // 2, (size - glyphs.height) // 2))
    return image


# ── Dynamic menu text (called by pystray on every menu open) ─────────────────

def _claude_title(_item=None):
    if _claude_action_in_progress:
        return f"{STATUS_STARTING}  Claude — Connecting…"
    if not _cached_claude_connected:
        return f"{STATUS_OFF}  Claude — Not Connected"
    if not _cached_claude_binary_valid:
        return f"{STATUS_ALERT}  Claude — Connection Error"
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
    return f"{STATUS_ALERT}  Updates — Available — {', '.join(parts)}"


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
    if _update_download_progress is not None:
        return f"⬇  Downloading update… {format_download_progress(*_update_download_progress)}"
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


def on_plan(icon, item):
    """
    License & Plans. The assistant used to point users at a "Settings →
    License/Plans" screen that did not exist; this is that screen.

    States no price on purpose — the pricing page is the only source for that.
    """
    info = _cached_app_info
    tier = info.get("license_tier", "Free")

    if info.get("license_activated"):
        activated = info.get("license_activated_at") or "unknown"
        _msg_box(
            "License & Plans",
            f"Plan: {tier}\n"
            f"Activated: {str(activated)[:10]}\n\n"
            "Everything is unlocked: batch face enrolment, duplicate detection "
            "and cleanup, export reports, scheduled sweeps and "
            "active folders.\n\n"
            "This licence is tied to this machine.",
        )
        return

    # Free preview: nothing is gated, so this must not read as an upsell. The
    # grandfathering line is the point — it is a real commitment (docs/PRICING.md)
    # and the tray is where an existing user looks for it. Mirrors tray_mac.py.
    if FREE_PREVIEW:
        if _confirm(
            "License & Plans",
            "Plan: Free preview\n\n"
            "Everything is unlocked - sort by date, location and people, "
            "find & group, batch face enrolment, duplicate detection and "
            "cleanup, export reports, scheduled sweeps and active folders.\n\n"
            "No licence needed, and nothing to buy yet.\n\n"
            "You are an early user: when paid plans launch, you keep Pro free. "
            "You will not be charged.\n\n"
            "Open the website to learn more?",
        ):
            open_url(get_pricing_url())
        return

    if _confirm(
        "License & Plans",
        "Plan: Free\n\n"
        "Included now - sort by date, location AND people, find & group, "
        "folder analysis, saved path presets, stats.\n\n"
        "Pro adds - batch face enrolment, duplicate detection and cleanup, "
        "export reports, scheduled sweeps, active folders.\n\n"
        "Current plans and pricing are on the website.\n\n"
        "Open the plans and pricing page?",
    ):
        open_url(get_pricing_url())


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
    global _update_download_progress
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
    has_silent_download = bool(mcp_u.get("download_url") and mcp_u.get("sha256"))

    msg = (
        f"Current version: v{mcp_ver}\n"
        f"New version:     v{latest}"
        f"{hl_text}\n\n"
    )
    msg += (
        "LocalLens Agent will download and install this update in the\n"
        "background, then restart automatically.\n\n"
        "Proceed with the update?"
        if has_silent_download else
        "The download page will open in your browser.\n"
        "Replace the existing app with the new one after downloading.\n\n"
        "Proceed with the update?"
    )
    if not _confirm(f"Install MCP Update v{latest}", msg):
        return

    if has_silent_download:
        _update_download_progress = (0, 0)

        def _progress(downloaded, total):
            global _update_download_progress
            _update_download_progress = (downloaded, total)

        result = install_mcp_update(
            latest_version=latest,
            release_notes_url=mcp_u.get("release_notes_url", ""),
            upgrade_command=mcp_u.get("upgrade_command", ""),
            download_url=mcp_u.get("download_url", ""),
            sha256=mcp_u.get("sha256", ""),
            progress_cb=_progress,
        )
        _update_download_progress = None
    else:
        result = install_mcp_update(
            latest_version=latest,
            release_notes_url=mcp_u.get("release_notes_url", ""),
            upgrade_command=mcp_u.get("upgrade_command", ""),
        )

    if result.get("method") == "silent":
        if result.get("success"):
            if not result.get("restart_required"):
                _msg_box(
                    "Update Installed  ✓",
                    f"LocalLens MCP has been updated to v{latest}."
                )
            # restart_required is False on Windows — the installer already
            # terminated this process and relaunched the new one.
        else:
            _msg_box(
                "Update Failed",
                f"Could not install v{latest}:\n\n{result.get('error', 'Unknown error')}\n\n"
                "Try updating manually from the releases page.",
                MB_OK | MB_ICONWARNING,
            )
    elif result.get("method") == "pip":
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
    elif result.get("reason"):
        # The dialog promised a silent background install and the download then
        # failed — without this the user just gets an unexplained browser tab.
        # No alert when there is no reason: that path already told them the
        # download page would open.
        _msg_box(
            "Automatic Update Failed",
            f"Could not download v{latest} ({result['reason']}).\n\n"
            "The releases page has been opened — install it manually from there.",
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
    global _icon, _cached_dark_taskbar

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

    _cached_dark_taskbar = _taskbar_is_dark()
    image = _render_ll_icon(_cached_dark_taskbar)

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
        pystray.MenuItem(_info_plan_title, on_plan),
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
