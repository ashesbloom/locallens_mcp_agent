"""
Tests for the Activate Pro window: the clipboard helper, the pywebview bridge,
the page's offline/price guards, the --activate-window dispatch and the tray-side
launcher. Spec: docs/superpowers/specs/2026-10-03-activate-pro-window-design.md

Runs on any OS: pywebview is imported lazily inside activate_window.run(), and
rumps/pystray are never imported here.
"""
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tray import actions  # noqa: E402


class _Run:
    """Stands in for subprocess.run and records the call."""

    def __init__(self, stdout=b"", returncode=0, raises=None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if self.raises:
            raise self.raises
        return types.SimpleNamespace(stdout=self.stdout, returncode=self.returncode)


def test_read_clipboard_macos_decodes_utf8_with_locale(monkeypatch):
    fake = _Run(stdout="key-ä\n".encode("utf-8"))
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    monkeypatch.setattr(actions.subprocess, "run", fake)
    assert actions.read_clipboard() == "key-ä\n"
    cmd, kw = fake.calls[0]
    assert cmd == ["pbpaste"]
    assert kw["env"]["LC_CTYPE"] == "UTF-8"


def test_read_clipboard_windows_uses_powershell(monkeypatch):
    fake = _Run(stdout=b"abc\r\n")
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setattr(actions.subprocess, "run", fake)
    assert actions.read_clipboard() == "abc\r\n"
    assert fake.calls[0][0][0] == "powershell"


def test_license_snapshot_follows_the_cache_file(monkeypatch, tmp_path):
    """Pro deactivated from Claude still read "Pro — Active" in the tray until a restart."""
    import json
    from mcp_server import license as lic

    path = tmp_path / "mcp_license.json"
    monkeypatch.setattr(lic, "_license_path", lambda: path)
    path.write_text(json.dumps({
        "license_key": "K", "activated_at": "2026-10-05T00:00:00", "tier": "pro",
        "machine_id": lic._get_machine_id(), "kind": "subscription",
        "validated_at": "2099-01-01T00:00:00+00:00", "instance_id": "lki_x",
    }), encoding="utf-8")
    assert actions.license_snapshot()["license_activated"] is True
    path.unlink()  # what deactivate_license() does from the MCP process
    assert actions.license_snapshot()["license_activated"] is False


def test_license_snapshot_marks_a_preview_user(monkeypatch):
    """After launch an early user has no key but keeps Pro; the tray must say so."""
    from mcp_server import license as lic

    monkeypatch.setattr(lic, "get_license_info", lambda: {
        "activated": False, "tier": "pro", "preview_user": True, "message": "…"})
    snap = actions.license_snapshot()
    assert snap["license_preview_user"] is True and snap["license_activated"] is False
    assert "early user" in snap["license_tier"].lower()


def test_deactivate_pro_reverts_to_free_and_never_raises(monkeypatch):
    from mcp_server import license as lic

    async def fake():
        return {"status": "deactivated", "seat_freed": True}

    monkeypatch.setattr(lic, "deactivate_license", fake)
    done = actions.deactivate_pro()
    assert done["status"] == "deactivated" and "Free" in done["summary"]

    async def boom():
        raise RuntimeError("disk")

    monkeypatch.setattr(lic, "deactivate_license", boom)
    failed = actions.deactivate_pro()
    assert failed["status"] == "error" and failed["summary"]


def test_read_clipboard_never_raises(monkeypatch):
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    monkeypatch.setattr(actions.subprocess, "run", _Run(raises=OSError("no pbpaste")))
    assert actions.read_clipboard() == ""
    monkeypatch.setattr(actions.subprocess, "run", _Run(stdout=b"x", returncode=1))
    assert actions.read_clipboard() == ""


from tray import activate_window  # noqa: E402


def test_activate_returns_license_result_unchanged(monkeypatch):
    seen = {}

    async def fake_activate(key):
        seen["key"] = key
        return {"status": "activated", "tier": "pro", "welcome": {"unlocked": []}}

    monkeypatch.setattr(activate_window, "activate_license", fake_activate)
    out = activate_window.Api().activate("  KEY-1\n")
    assert out == {"status": "activated", "tier": "pro", "welcome": {"unlocked": []}}
    assert seen["key"] == "  KEY-1\n"  # stripping is activate_license's job


def test_activate_never_raises(monkeypatch):
    async def boom(key):
        raise ValueError("bad json")

    monkeypatch.setattr(activate_window, "activate_license", boom)
    out = activate_window.Api().activate("KEY")
    assert out["status"] == "error"
    assert "bad json" in out["message"]


def test_paste_trims_clipboard(monkeypatch):
    monkeypatch.setattr(activate_window, "read_clipboard", lambda: "  e7925221-41d1\n")
    assert activate_window.Api().paste() == "e7925221-41d1"


def test_open_claude_then_closes(monkeypatch):
    calls = []
    monkeypatch.setattr(activate_window, "open_claude", lambda: calls.append("claude"))
    api = activate_window.Api()
    api._window = types.SimpleNamespace(destroy=lambda: calls.append("destroy"))
    api.open_claude()
    assert calls == ["claude", "destroy"]


def test_close_without_window_is_harmless():
    activate_window.Api().close()


def test_window_handle_is_not_exposed_to_js():
    # pywebview exposes public attributes of js_api to the page; the window must stay private.
    assert not [n for n in vars(activate_window.Api()) if not n.startswith("_")]


def test_load_page_reads_the_html():
    assert "<canvas" in activate_window.load_page()


from tray import main as tray_main  # noqa: E402


def test_flag_runs_window_and_never_starts_a_tray(monkeypatch):
    ran = []
    monkeypatch.setattr(sys, "argv", ["LocalLens Agent", "--activate-window"])
    monkeypatch.setattr(activate_window, "run", lambda: ran.append("window"))
    # If main() fell through, importing these stubs would record a tray start.
    for name, fn in (("tray.tray_mac", "run_mac_tray"), ("tray.tray_win", "run_win_tray")):
        stub = types.ModuleType(name)
        setattr(stub, fn, lambda: ran.append("tray"))
        monkeypatch.setitem(sys.modules, name, stub)
    tray_main.main()
    assert ran == ["window"]


from tray import activation  # noqa: E402


@pytest.fixture(autouse=False)
def fresh_launcher(monkeypatch):
    monkeypatch.setattr(activation, "_child", None)
    yield


def test_command_dev_runs_entrypoint(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = activation.activate_window_command()
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("locallens_tray_entrypoint.py")
    assert cmd[2] == "--activate-window"


def test_command_py2app_uses_launcher_not_bare_python(monkeypatch):
    monkeypatch.setattr(sys, "frozen", "macosx_app", raising=False)
    monkeypatch.setattr(activation.sys, "platform", "darwin")
    monkeypatch.setattr(activation.sys, "executable", "/A/LocalLens Agent.app/Contents/MacOS/python")
    assert activation.activate_window_command() == [
        "/A/LocalLens Agent.app/Contents/MacOS/LocalLens Agent", "--activate-window"]


def test_command_pyinstaller_reuses_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(activation.sys, "platform", "win32")
    monkeypatch.setattr(activation.sys, "executable", r"C:\LL\LocalLens Agent.exe")
    assert activation.activate_window_command() == [r"C:\LL\LocalLens Agent.exe", "--activate-window"]


class _Proc:
    def __init__(self, code=0, alive=False):
        self.code, self.alive = code, alive

    def poll(self):
        return None if self.alive else self.code

    def wait(self):
        return self.code


def _launch(monkeypatch, proc, elapsed=0.0):
    results = []
    clock = iter([100.0, 100.0 + elapsed])
    monkeypatch.setattr(activation.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(activation.subprocess, "Popen", lambda cmd: proc)
    started = activation.launch_activate_window(results.append)
    activation._watcher.join(timeout=2)
    return started, results


def test_clean_exit_reports_success(monkeypatch, fresh_launcher):
    assert _launch(monkeypatch, _Proc(code=0), elapsed=30) == (True, [False])


def test_fast_nonzero_exit_reports_failure(monkeypatch, fresh_launcher):
    assert _launch(monkeypatch, _Proc(code=1), elapsed=1) == (True, [True])


def test_slow_nonzero_exit_is_not_a_launch_failure(monkeypatch, fresh_launcher):
    assert _launch(monkeypatch, _Proc(code=1), elapsed=60) == (True, [False])


def test_second_launch_while_open_is_refused(monkeypatch, fresh_launcher):
    monkeypatch.setattr(activation, "_child", _Proc(alive=True))
    monkeypatch.setattr(activation.subprocess, "Popen", lambda cmd: pytest.fail("spawned twice"))
    assert activation.launch_activate_window(lambda failed: None) is False


def test_missing_launcher_reports_failure(monkeypatch, fresh_launcher):
    def boom(cmd):
        raise FileNotFoundError(cmd[0])

    results = []
    monkeypatch.setattr(activation.subprocess, "Popen", boom)
    assert activation.launch_activate_window(results.append) is True
    assert results == [True]


def test_fallback_names_the_claude_route():
    assert 'say "activate my LL Agent license"' in activation.ACTIVATE_FALLBACK_MESSAGE


PAGE = (_SRC / "tray" / "activate_window.html").read_text(encoding="utf-8")


def test_page_is_offline_safe():
    # No CDN, no web fonts, no links: pricing opens through Api.open_pricing().
    assert re.findall(r"https?://", PAGE) == []


def test_page_states_no_price():
    assert "$" not in PAGE and "₹" not in PAGE
    assert not re.search(r"/mo\b|/yr\b", PAGE)


def test_page_titles_every_activation_status():
    for status in ("invalid", "inactive", "limit_reached", "offline", "error"):
        assert re.search(rf"\b{status}\s*:", PAGE), status


def test_page_has_no_second_feature_list():
    # Cards come from welcome.unlocked (license._PRO_FEATURES), never hard-coded.
    for name in ("Batch face enrollment", "Export reports", "Active folders"):
        assert name not in PAGE


def test_page_honours_reduced_motion():
    assert "prefers-reduced-motion" in PAGE


def test_page_fits_a_window_shorter_than_asked_for():
    # Windows display scaling hands the page a client area a little under 640px;
    # a fixed-height box clipped Open Claude / Done off the bottom (seen on Win 11).
    assert re.search(r"#app\{[^}]*height:100vh", PAGE)
    assert re.search(r"#cards\{[^}]*min-height:0", PAGE)
    assert "#cards.tight .csay{display:none}" in PAGE


def test_run_opens_the_spec_window_dragged_only_by_its_strip(monkeypatch):
    seen = {}
    fake = types.ModuleType("webview")
    fake.create_window = lambda title, **kw: seen.update(kw) or "win"
    fake.start = lambda: seen.setdefault("started", True)
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(activate_window.os, "_exit", lambda code: None)
    activate_window.run()
    assert seen["js_api"]._window == "win" and seen["started"]
    assert (seen["width"], seen["height"]) == (520, 640)
    assert seen["frameless"] and seen["on_top"] and not seen["resizable"]
    assert seen["background_color"] == "#FAF9F6"
    # pywebview defaults easy_drag=True for frameless windows, which turns the whole
    # page — key field included — into a drag handle. Only the 40 px strip should drag.
    assert seen["easy_drag"] is False


def _fake_webview(monkeypatch, renderer):
    created = []
    wv = types.ModuleType("webview")
    wv.create_window = lambda title, **kw: created.append(kw) or "win"
    wv.start = lambda: None
    platforms = types.ModuleType("webview.platforms")
    winforms = types.ModuleType("webview.platforms.winforms")
    winforms.renderer = renderer
    platforms.winforms = winforms
    for name, mod in (("webview", wv), ("webview.platforms", platforms),
                      ("webview.platforms.winforms", winforms)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(activate_window.sys, "platform", "win32")
    monkeypatch.setattr(activate_window.os, "_exit", lambda code: None)
    return created


def test_windows_without_webview2_exits_fast_for_the_fallback(monkeypatch):
    # pywebview silently drops to IE's MSHTML when WebView2 is missing; that engine
    # can't render the page. A quick non-zero exit makes the tray show its fallback.
    created = _fake_webview(monkeypatch, "mshtml")
    with pytest.raises(SystemExit) as exit_:
        activate_window.run()
    assert exit_.value.code != 0 and created == []


def test_windows_with_webview2_opens_the_window(monkeypatch):
    created = _fake_webview(monkeypatch, "edgechromium")
    activate_window.run()
    assert len(created) == 1


def test_run_ends_the_process_once_the_window_closes(monkeypatch):
    # Done / x / Open Claude call close() inside a bridge call. pywebview then tries to
    # hand that call's return value to the page that just closed, from a non-daemon
    # thread that waits forever, so a normal interpreter exit hangs (beach ball, and
    # the tray never learns the window closed). run() must end the process itself,
    # but only after an in-flight activation has finished writing the license.
    import asyncio
    import threading
    import time

    order = []

    async def slow_activate(key):
        await asyncio.sleep(0.3)
        order.append("license written")
        return {"status": "activated"}

    apis = []
    fake = types.ModuleType("webview")
    fake.create_window = lambda title, **kw: apis.append(kw["js_api"]) or "win"

    def start():  # the window closes 50 ms into an activation
        threading.Thread(target=apis[0].activate, args=("KEY",), daemon=True).start()
        time.sleep(0.05)

    fake.start = start
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(activate_window, "activate_license", slow_activate)
    monkeypatch.setattr(activate_window.os, "_exit", lambda code: order.append(("exit", code)))
    activate_window.run()
    assert order == ["license written", ("exit", 0)]
