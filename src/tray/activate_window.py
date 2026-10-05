# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2026 Mayank Pandey - LL Agent. See LICENSE.md.
"""
The Activate Pro window — runs in its own process, started by the tray with
--activate-window (tray/activation.py explains why it can't share the tray's
process). The page is activate_window.html; this module is its Python side.

Design: docs/superpowers/specs/2026-10-03-activate-pro-window-design.md
"""
import asyncio
import os
import sys
import threading
from importlib import resources

from mcp_server.license import activate_license

from .actions import get_pricing_url, open_claude, open_url, read_clipboard


class Api:
    """
    What the page calls as window.pywebview.api.<name>(). pywebview runs each
    call on a worker thread, so asyncio.run is safe here. Public attributes are
    exposed to the page too, which is why the window handle is `_window`.
    """

    def __init__(self):
        self._window = None
        # Held while a key is being activated; run() waits on it before exiting.
        self._activating = threading.Lock()

    def activate(self, key: str) -> dict:
        # The page must always get a dict back: an exception here would leave it
        # stuck on "Checking your key…".
        with self._activating:
            try:
                return asyncio.run(activate_license(str(key)))
            except Exception as e:
                return {"status": "error", "message": f"Activation failed: {e}"}

    def paste(self) -> str:
        return read_clipboard().strip()

    def open_pricing(self) -> None:
        open_url(get_pricing_url())

    def open_claude(self) -> None:
        open_claude()
        self.close()

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()


def load_page() -> str:
    # importlib.resources reads from py2app's zip and PyInstaller's datas alike.
    return resources.files("tray").joinpath("activate_window.html").read_text(encoding="utf-8")


def run() -> None:
    import webview  # only the child process needs it; CI and the tray never import it

    if sys.platform == "win32":
        # Without the WebView2 runtime, pywebview silently falls back to IE's
        # MSHTML, which can't render this page. Exit fast instead: the tray reads
        # a quick non-zero exit as "could not open" and shows its fallback alert.
        from webview.platforms import winforms
        if winforms.renderer != "edgechromium":
            sys.exit(1)

    api = Api()
    api._window = webview.create_window(
        "Activate LL Agent Pro",
        html=load_page(),
        js_api=api,
        width=520,
        height=640,
        resizable=False,
        frameless=True,
        # Frameless windows default to dragging from anywhere, key field included;
        # the page's 40 px strip (pywebview-drag-region) is the only handle.
        easy_drag=False,
        on_top=True,
        background_color="#FAF9F6",
    )
    webview.start()

    # The window is gone, but a normal exit would hang: Done, × and Open Claude
    # close it from inside a bridge call, and pywebview then hands that call's
    # return value to the closed page from a non-daemon thread that waits forever
    # on the stopped run loop. Let an in-flight activation finish writing the
    # license (so a Dodo seat is never used without a local record), then leave.
    api._activating.acquire(timeout=30)
    os._exit(0)
