import rumps
import threading
import time
from .status import is_locallens_running, is_locallens_app_running
from .actions import (
    open_claude, start_locallens, stop_backend_pids, stop_all_backends,
    show_claude_status_terminal,
    claude_setup, claude_status, claude_remove,
    get_claude_connection_state, maybe_show_welcome, show_help_tips,
    check_updates_now, open_url, copy_to_clipboard,
    CLAUDE_CUSTOM_INSTRUCTIONS, CLAUDE_INSTRUCTIONS_HOWTO,
)

# Claude Status now reflects whether LocalLens is actually registered as an
# MCP server in Claude's config (get_claude_connection_state) — NOT whether
# the Claude.app process happens to be open. Those are unrelated: a user can
# have Claude running with LocalLens never connected, or vice versa.
_cached_claude_connected = False
_cached_claude_binary_valid = False
_cached_ll_running = False
_cached_app_running = False
# List of worker PIDs the tray started — empty means we don't own the backend
_managed_ll_pids: list = []
_stop_polling = False
# Thread-safe queue for error messages to be shown on the main thread.
# Background threads append (title, message) tuples; the @rumps.timer drains it.
_pending_alerts: list = []

# {"mcp": dict|None, "app": dict|None} — see check_updates_now() in actions.py
_cached_update_info: dict = {"mcp": None, "app": None}
# Dedup key set ("mcp:1.2.0", "app:2.4.0") so an hourly recheck doesn't
# re-notify about a version we've already told the user about this session.
_notified_update_versions: set = set()

def _is_pid_alive(pid: int) -> bool:
    """Check if a specific PID is still a running process."""
    try:
        import psutil
        proc = psutil.Process(pid)
        # status() raises NoSuchProcess if dead; also check it's not a zombie
        return proc.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
    except Exception:
        return False


def _any_pid_alive(pids: list) -> bool:
    """Return True if at least one PID in the list is still alive."""
    return any(_is_pid_alive(p) for p in pids)


def _poll_status():
    global _cached_claude_connected, _cached_claude_binary_valid
    global _cached_ll_running, _cached_app_running, _managed_ll_pids
    while not _stop_polling:
        claude_state = get_claude_connection_state()
        _cached_claude_connected = claude_state["connected"]
        _cached_claude_binary_valid = claude_state["binary_valid"]
        _cached_app_running = is_locallens_app_running()

        if _managed_ll_pids:
            # The tray owns specific worker PIDs — check them directly.
            # This avoids false-negatives when the desktop app overwrites port.txt.
            if _any_pid_alive(_managed_ll_pids):
                _cached_ll_running = True
            else:
                # All our workers died on their own
                _managed_ll_pids = []
                _cached_ll_running = is_locallens_running()
        else:
            _cached_ll_running = is_locallens_running()

        time.sleep(3)


# How often to re-check for updates. check_updates_now() itself hits a
# 24h-TTL disk cache (see mcp_server/updater.py), so this just controls how
# quickly a fresh manifest gets picked up after the cache expires — it does
# NOT mean we hit the network every hour.
_UPDATE_CHECK_INTERVAL_SECONDS = 3600


def _queue_update_notifications(update_info: dict):
    """Append a one-time _pending_alerts entry for any update not already surfaced this session."""
    labels = {"mcp": "LocalLens MCP Connector", "app": "LocalLens App"}
    for key, label in labels.items():
        info = update_info.get(key)
        if not info or not info.get("update_available"):
            continue
        token = f"{key}:{info['latest_version']}"
        if token in _notified_update_versions:
            continue
        _notified_update_versions.add(token)
        _pending_alerts.append((
            f"Update Available — {label}",
            f"{label} {info['latest_version']} is available "
            f"(you have {info['current_version']}).\n\n"
            "Open \"Updates\" in the menu bar to see what's new and download it."
        ))


def _update_check_loop():
    global _cached_update_info
    while not _stop_polling:
        info = check_updates_now()
        _queue_update_notifications(info)
        _cached_update_info = info
        time.sleep(_UPDATE_CHECK_INTERVAL_SECONDS)


# Status indicators — all four are drawn from the same Unicode "large circle"
# family (introduced together in Emoji 12, 2019) so they render at a
# consistent size/weight on Apple Color Emoji.
STATUS_OFF = "🔴"        # not running / not connected
STATUS_STARTING = "🟡"   # transient: starting backend or connecting to Claude
STATUS_ON = "🟢"         # running / connected
STATUS_EXTERNAL = "🔵"   # running, but owned by the LocalLens desktop app

# Whether a Claude connect/disconnect action is currently in flight — drives
# the transient 🟡 "Connecting…" state on the Claude Status row.
_claude_action_in_progress = False


class LocalLensAgentApp(rumps.App):
    def __init__(self):
        # Text-only menu bar title — no icon, just "LL"
        super(LocalLensAgentApp, self).__init__("LL", quit_button=None)
        self._onboarding_checked = False

        # ── Primary Action ───────────────────────────────────────────────
        self.btn_open_claude = rumps.MenuItem("Open Claude", callback=self.on_open_claude)

        # ── Claude Connection ────────────────────────────────────────────
        self.btn_claude_status = rumps.MenuItem(self._claude_title(STATUS_OFF, "Not Connected"))

        self.btn_claude_setup = rumps.MenuItem("Connect to Claude", callback=self.on_claude_setup)
        self.btn_claude_status_check = rumps.MenuItem("Check Connection", callback=self.on_claude_status_check)
        self.btn_claude_remove = rumps.MenuItem("Disconnect from Claude", callback=self.on_claude_remove)
        self.btn_claude_instructions = rumps.MenuItem(
            "Copy Custom Instructions…", callback=self.on_copy_instructions
        )
        self.btn_claude_terminal = rumps.MenuItem("View MCP Logs", callback=self.on_claude_terminal)

        self.btn_claude_status.update([
            self.btn_claude_setup,
            self.btn_claude_status_check,
            self.btn_claude_remove,
            None,
            self.btn_claude_instructions,
            None,
            self.btn_claude_terminal
        ])

        # ── Backend Status ───────────────────────────────────────────────
        self.btn_ll_status = rumps.MenuItem(
            self._ll_title(STATUS_OFF, "Stopped"), callback=self.on_ll_status
        )

        # ── Updates ──────────────────────────────────────────────────────
        self.btn_updates = rumps.MenuItem(self._updates_title(STATUS_ON, "Up to Date"))
        self.btn_updates_check = rumps.MenuItem("Check for Updates", callback=self.on_check_updates)
        self.btn_updates_details = rumps.MenuItem("What's New / Download…", callback=self.on_update_details)
        self.btn_updates.update([
            self.btn_updates_check,
            self.btn_updates_details,
        ])

        # ── Help & Quit ─────────────────────────────────────────────────
        self.btn_help = rumps.MenuItem("Help & Getting Started", callback=self.on_help)
        self.btn_quit = rumps.MenuItem("Quit LocalLens Agent", callback=self.on_quit)

        self.menu = [
            self.btn_open_claude,
            None,
            self.btn_claude_status,
            self.btn_ll_status,
            None,
            self.btn_updates,
            None,
            self.btn_help,
            None,
            self.btn_quit
        ]

    @staticmethod
    def _claude_title(icon: str, label: str) -> str:
        return f"{icon}  Claude — {label}"

    @staticmethod
    def _ll_title(icon: str, label: str) -> str:
        return f"{icon}  Local Lens — {label}"

    @staticmethod
    def _updates_title(icon: str, label: str) -> str:
        return f"{icon}  Updates — {label}"

    @rumps.timer(1)
    def update_status(self, _):
        """Update the menu text from the background thread's cached status.

        This runs on the main thread every second. It also drains _pending_alerts
        so that error messages from background threads are shown safely, and
        (once) shows the first-run welcome prompt now that the Cocoa run loop
        is actually active.
        """
        if not self._onboarding_checked:
            self._onboarding_checked = True
            if maybe_show_welcome():
                # First-ever launch: immediately follow up with the "add
                # these to Claude" prompt too, per the user's request that
                # first-time entry should surface it (not just after a
                # successful "Connect to Claude" click, handled separately
                # in on_claude_setup below).
                self._show_claude_instructions_window()

        # Drain any queued alerts from background threads
        while _pending_alerts:
            title, message = _pending_alerts.pop(0)
            rumps.alert(title=title, message=message, ok="OK")

        self._update_claude_button()
        self._update_ll_button()
        self._update_updates_button()

    def _update_claude_button(self):
        """
        Update the Claude Status button. Reflects whether LocalLens is
        actually registered as an MCP server in Claude's config — NOT
        whether the Claude.app process happens to be running (those are
        unrelated facts; conflating them was the original bug).
        """
        if _claude_action_in_progress:
            self.btn_claude_status.title = self._claude_title(STATUS_STARTING, "Connecting…")
        elif not _cached_claude_connected:
            self.btn_claude_status.title = self._claude_title(STATUS_OFF, "Not Connected")
        elif not _cached_claude_binary_valid:
            self.btn_claude_status.title = self._claude_title(STATUS_OFF, "Connection Error")
        else:
            self.btn_claude_status.title = self._claude_title(STATUS_ON, "Connected")

    def _update_ll_button(self):
        """
        Update the LocalLens status button based on three states:
          1. Backend NOT running                        → off, stopped
          2. Backend running + desktop app running      → external (protected)
          3. Backend running + desktop app NOT running  → on, running
        """
        if not _cached_ll_running:
            self.btn_ll_status.title = self._ll_title(STATUS_OFF, "Stopped")
        elif _cached_app_running:
            # Desktop app is open — backend is protected
            self.btn_ll_status.title = self._ll_title(STATUS_EXTERNAL, "Running · Managed by App")
        else:
            # Backend alive but desktop app gone — tray can stop it
            self.btn_ll_status.title = self._ll_title(STATUS_ON, "Running")

    def _update_updates_button(self):
        """Reflect the last update check (refreshed hourly by _update_check_loop, or on-demand)."""
        mcp_u = _cached_update_info.get("mcp")
        app_u = _cached_update_info.get("app")
        if not mcp_u and not app_u:
            self.btn_updates.title = self._updates_title(STATUS_ON, "Up to Date")
            return
        parts = []
        if mcp_u:
            parts.append(f"Connector v{mcp_u['latest_version']}")
        if app_u:
            parts.append(f"App v{app_u['latest_version']}")
        self.btn_updates.title = self._updates_title(STATUS_STARTING, "Available — " + ", ".join(parts))

    def on_check_updates(self, sender):
        global _cached_update_info
        self.btn_updates.title = self._updates_title(STATUS_STARTING, "Checking…")

        def _check_bg():
            global _cached_update_info
            info = check_updates_now(force=True)
            _cached_update_info = info
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
                _pending_alerts.append((
                    "Update Available",
                    "\n".join(lines) + "\n\nOpen \"What's New / Download…\" for details."
                ))
            else:
                _pending_alerts.append((
                    "You're Up to Date",
                    "LocalLens and the MCP connector are both on the latest version."
                ))

        threading.Thread(target=_check_bg, daemon=True).start()

    def on_update_details(self, sender):
        mcp_u = _cached_update_info.get("mcp")
        app_u = _cached_update_info.get("app")
        if not mcp_u and not app_u:
            rumps.alert("You're Up to Date", "LocalLens and the MCP connector are both on the latest version.")
            return

        lines = []
        url = None
        if mcp_u:
            lines.append(f"LocalLens MCP Connector — v{mcp_u['latest_version']} (you have {mcp_u['current_version']})")
            for h in mcp_u.get("highlights", []):
                lines.append(f"   • {h}")
            url = mcp_u.get("release_notes_url") or url
        if app_u:
            if lines:
                lines.append("")
            lines.append(f"LocalLens App — v{app_u['latest_version']} (you have {app_u['current_version']})")
            # Prefer the app's own download link if both are present — it's
            # the more common case a user needs a direct action for.
            url = app_u.get("download_url") or url

        res = rumps.alert("Update Available", "\n".join(lines), ok="Open Download Page", cancel="Close")
        if res == 1 and url:
            open_url(url)

    def on_open_claude(self, sender):
        open_claude()

    def on_claude_setup(self, sender):
        global _claude_action_in_progress
        _claude_action_in_progress = True
        self._update_claude_button()
        res = {"status": "error"}
        try:
            res = claude_setup()
        finally:
            _claude_action_in_progress = False
            self._refresh_claude_state_now()
        # Whenever a connect actually succeeds (fresh install, update, or it
        # was already connected), offer the optional Claude instructions —
        # this is the "whenever the user connects" trigger from the request.
        if res.get("status") in ("installed", "updated", "already_connected"):
            self._show_claude_instructions_window()

    def on_claude_status_check(self, sender):
        claude_status()

    def on_copy_instructions(self, sender):
        self._show_claude_instructions_window()

    def _show_claude_instructions_window(self):
        """
        Show the optional "paste this into Claude" instructions in a small
        editable/selectable text window with a one-click copy-to-clipboard
        button, instead of dumping raw text into a plain alert (which isn't
        copyable and mixes the payload with the "how to add it" preamble).
        """
        resp = rumps.Window(
            message=CLAUDE_INSTRUCTIONS_HOWTO,
            title="Add LocalLens to Claude's Instructions (optional)",
            default_text=CLAUDE_CUSTOM_INSTRUCTIONS,
            ok="Copy to Clipboard",
            cancel="Not Now",
            dimensions=(420, 160),
        ).run()
        if not resp.clicked:
            return
        text_to_copy = resp.text or CLAUDE_CUSTOM_INSTRUCTIONS
        if copy_to_clipboard(text_to_copy):
            rumps.alert(
                "Copied!",
                "The instructions are now on your clipboard.\n"
                "Paste them into Claude Desktop's custom instructions field."
            )
        else:
            rumps.alert(
                "Copy Failed",
                "Could not access the clipboard. Select the text above manually and copy it (⌘C)."
            )

    def on_claude_remove(self, sender):
        global _claude_action_in_progress
        _claude_action_in_progress = True
        self._update_claude_button()
        try:
            claude_remove()
        finally:
            _claude_action_in_progress = False
            self._refresh_claude_state_now()

    def _refresh_claude_state_now(self):
        """
        Re-check the real connection state immediately after a connect/
        disconnect action instead of waiting up to 3s for the next poll
        tick — keeps the UI feeling responsive right after the click.
        """
        global _cached_claude_connected, _cached_claude_binary_valid
        state = get_claude_connection_state()
        _cached_claude_connected = state["connected"]
        _cached_claude_binary_valid = state["binary_valid"]
        self._update_claude_button()

    def on_claude_terminal(self, sender):
        show_claude_status_terminal()

    def on_help(self, sender):
        show_help_tips()

    def on_ll_status(self, sender):
        global _cached_ll_running, _cached_app_running, _managed_ll_pids
        if not _cached_ll_running:
            # --- NOT RUNNING: start it in a background thread so the UI
            # never freezes (start_locallens polls for up to 15 seconds).
            self.btn_ll_status.title = self._ll_title(STATUS_STARTING, "Starting…")

            def _start_in_background():
                global _cached_ll_running, _cached_app_running, _managed_ll_pids
                try:
                    result = start_locallens()
                except Exception as exc:
                    _pending_alerts.append(("Error Starting LocalLens", str(exc)))
                    return
                if result is not False:
                    _managed_ll_pids = result if isinstance(result, list) else []
                    _cached_ll_running = is_locallens_running()
                    _cached_app_running = is_locallens_app_running()

            threading.Thread(target=_start_in_background, daemon=True).start()

        elif _cached_app_running:
            # --- DESKTOP APP IS RUNNING: don't touch it ---
            rumps.alert(
                "LocalLens is Running",
                "The LocalLens desktop app is currently open.\n"
                "Close the desktop app first if you want the agent to manage the backend."
            )
        else:
            # --- BACKEND ALIVE BUT APP GONE: stop it ---
            self.btn_ll_status.title = self._ll_title(STATUS_STARTING, "Stopping…")
            stopped = False
            if _managed_ll_pids:
                stopped = stop_backend_pids(_managed_ll_pids)
            if not stopped:
                stopped = stop_all_backends()
            if stopped:
                _managed_ll_pids = []
                _cached_ll_running = False
            self._update_ll_button()


    def on_quit(self, sender):
        global _stop_polling, _managed_ll_pids
        _stop_polling = True
        # Stop backend if we own it, or if it's an orphan (app not running)
        if _managed_ll_pids:
            stop_backend_pids(_managed_ll_pids)
        elif _cached_ll_running and not _cached_app_running:
            stop_all_backends()
        rumps.quit_application()

def run_mac_tray():
    t = threading.Thread(target=_poll_status, daemon=True)
    t.start()

    update_thread = threading.Thread(target=_update_check_loop, daemon=True)
    update_thread.start()

    app = LocalLensAgentApp()
    # Always use text-only "LL" in the menu bar — no icon file needed
    app.title = "LL"
    app.run()
