# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2026 Mayank Pandey - LL Agent. See LICENSE.md.
"""
Launching the Activate Pro window from the tray.

The window is a separate process because both trays own the main thread
(rumps runs NSApplication; pystray runs icon.run()) and pywebview needs the
main thread too. The child is this same app started with ACTIVATE_FLAG;
tray/main.py checks for it before any tray starts — on Windows that is also
what keeps it clear of run_win_tray()'s single-instance mutex.

Nothing is passed back from the child: activation writes mcp_license.json,
which the MCP server re-reads on every call. The tray only needs to refresh
its own cached label when the child exits — on_closed is that hook.
"""
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

ACTIVATE_FLAG = "--activate-window"

# Same words as /thanks (copy.thanks.activateClaude), so the two routes match.
ACTIVATE_FALLBACK_MESSAGE = (
    "The activation window could not open on this computer. You can still "
    'activate in Claude Desktop: say "activate my LL Agent license" followed by your key.'
)

# A non-zero exit this soon means the window never opened (pywebview or WebView2
# missing) rather than the user closing it.
_FAST_FAIL_SECONDS = 5

_lock = threading.Lock()
_child: Optional[subprocess.Popen] = None
_watcher: Optional[threading.Thread] = None


def activate_window_command() -> List[str]:
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            # py2app: sys.executable is Contents/MacOS/python, which skips
            # __boot__.py and so has no sys.path (see get_mcp_command_config in
            # claude_connector.py). The app's own launcher beside it sets that up.
            return [str(Path(sys.executable).with_name("LocalLens Agent")), ACTIVATE_FLAG]
        # PyInstaller: sys.executable is LocalLens Agent.exe itself.
        return [sys.executable, ACTIVATE_FLAG]
    entry = Path(__file__).resolve().parents[2] / "locallens_tray_entrypoint.py"
    return [sys.executable, str(entry), ACTIVATE_FLAG]


def launch_activate_window(on_closed: Callable[[bool], None]) -> bool:
    """
    Open the window unless one is already open (returns False then).
    on_closed(failed) runs on a background thread after every exit; failed is
    True only when the window could not open at all.
    """
    global _child, _watcher
    with _lock:
        if _child is not None and _child.poll() is None:
            return False
        started = time.monotonic()
        try:
            _child = subprocess.Popen(activate_window_command())
        except OSError:
            _child = None
            on_closed(True)
            return True
        proc = _child

    def _watch():
        code = proc.wait()
        on_closed(code != 0 and time.monotonic() - started < _FAST_FAIL_SECONDS)

    _watcher = threading.Thread(target=_watch, daemon=True)
    _watcher.start()
    return True
