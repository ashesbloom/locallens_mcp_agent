import threading
import time
import sys
import os
import pystray
from PIL import Image
from .status import is_claude_running, is_locallens_running, is_locallens_app_running
from .actions import (
    open_claude, start_locallens, stop_backend_pids, stop_all_backends,
    show_claude_status_terminal,
    claude_setup, claude_status, claude_remove
)

# Status indicators
STATUS_ON = "🟢"
STATUS_OFF = "⚪"

# Global state for caching status to avoid lag when menu opens
_claude_running = False
_ll_running = False
_app_running = False
_managed_ll_pids: list = []
_stop_event = threading.Event()

def status_updater():
    """Background thread to poll status."""
    global _claude_running, _ll_running, _app_running, _managed_ll_pids
    while not _stop_event.is_set():
        _claude_running = is_claude_running()
        _app_running = is_locallens_app_running()

        if _managed_ll_pids:
            if any(_is_pid_alive(p) for p in _managed_ll_pids):
                _ll_running = True
            else:
                _managed_ll_pids = []
                _ll_running = is_locallens_running()
        else:
            _ll_running = is_locallens_running()

        time.sleep(3)

def _is_pid_alive(pid: int) -> bool:
    """Check if a specific PID is still a running process."""
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
    except Exception:
        return False

_ll_starting = False

def get_claude_text(item):
    icon = STATUS_ON if _claude_running else STATUS_OFF
    return f"{icon}  Claude — {'Connected' if _claude_running else 'Not Connected'}"

def get_ll_text(item):
    if _ll_starting:
        return "🟡  Local Lens — Starting…"
    if not _ll_running:
        return "🔴  Local Lens — Stopped"
    if _app_running:
        return "🔵  Local Lens — Running · Managed by App"
    return "🟢  Local Lens — Running"

def on_open_claude(icon, item):
    open_claude()

def on_claude_setup(icon, item):
    claude_setup()

def on_claude_status_check(icon, item):
    claude_status()

def on_claude_remove(icon, item):
    claude_remove()

def on_claude_terminal(icon, item):
    show_claude_status_terminal()

def on_ll_status(icon, item):
    global _ll_starting, _ll_running, _app_running, _managed_ll_pids
    if not _ll_running and not _ll_starting:
        # --- NOT RUNNING: start it ---
        _ll_starting = True
        icon.update_menu()
        result = start_locallens()
        _ll_starting = False
        if result is not False:
            _managed_ll_pids = result if isinstance(result, list) else []
            _ll_running = is_locallens_running()
            _app_running = is_locallens_app_running()
        icon.update_menu()
    elif _ll_running and _app_running and not _ll_starting:
        # --- DESKTOP APP IS RUNNING: don't touch it ---
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "The LocalLens desktop app is currently open.\n"
            "Close the desktop app first if you want the tray to manage the backend.",
            "LocalLens is Running",
            0
        )
    elif _ll_running and not _app_running and not _ll_starting:
        # --- BACKEND ALIVE BUT APP GONE: stop it ---
        _ll_starting = True
        icon.update_menu()
        stopped = False
        if _managed_ll_pids:
            stopped = stop_backend_pids(_managed_ll_pids)
        if not stopped:
            stopped = stop_all_backends()
        if stopped:
            _managed_ll_pids = []
            _ll_running = False
        _ll_starting = False
        icon.update_menu()

def on_quit(icon, item):
    global _managed_ll_pids
    _stop_event.set()
    if _managed_ll_pids:
        stop_backend_pids(_managed_ll_pids)
    elif _ll_running and not _app_running:
        stop_all_backends()
    icon.stop()

def run_win_tray():
    # Start background polling thread
    t = threading.Thread(target=status_updater, daemon=True)
    t.start()
    
    # Generate a programmatic "LL" icon — no external icon file needed
    from PIL import ImageDraw, ImageFont
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "LL", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - tw) / 2, (64 - th) / 2), "LL", fill="white", font=font)

    claude_submenu = pystray.Menu(
        pystray.MenuItem("Connect to Claude", on_claude_setup),
        pystray.MenuItem("Check Status", on_claude_status_check),
        pystray.MenuItem("Disconnect", on_claude_remove),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Terminal Logs", on_claude_terminal)
    )

    menu = pystray.Menu(
        pystray.MenuItem("Open Claude", on_open_claude),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(get_claude_text, claude_submenu),
        pystray.MenuItem(get_ll_text, on_ll_status),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit)
    )

    icon = pystray.Icon("LocalLensAgent", image, "LocalLens Agent", menu)
    icon.run()
