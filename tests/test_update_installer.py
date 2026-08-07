"""
Tests for the in-app auto-updater: platform-key resolution + download URL /
checksum surfacing in mcp_server.updater, and the download/verify/install
flow in tray.actions (Issue 2 fix — see CLAUDE.md Gotchas).
"""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mcp_server import updater
from tray import actions


class TestGetPlatformKey:
    def test_darwin(self):
        with patch.object(sys, "platform", "darwin"):
            assert updater._get_platform_key() == "macos-arm64"

    def test_win32(self):
        with patch.object(sys, "platform", "win32"):
            assert updater._get_platform_key() == "windows-x86_64"

    def test_linux(self):
        with patch.object(sys, "platform", "linux"):
            assert updater._get_platform_key() == "linux-x86_64"


def _manifest(latest="9.9.9", url=None, sha256="abc123"):
    """Manifest with a downloads block for this platform. url defaults to a
    correctly-versioned asset for `latest`."""
    if url is None:
        url = f"https://example.com/releases/download/v{latest}/agent-v{latest}.dmg"
    return {
        "mcp": {
            "latest": latest,
            "min_supported": "1.0.0",
            "changelog": [],
            "downloads": {updater._get_platform_key(): {"url": url, "sha256": sha256}},
        }
    }


def _check(manifest):
    with (
        patch.object(updater, "_get_manifest", return_value=manifest),
        patch.object(updater, "MCP_VERSION", "1.0.0"),
    ):
        return updater.check_for_updates()


class TestCheckForUpdatesDownloadInfo:
    def test_includes_download_url_and_sha256_when_present(self):
        result = _check(_manifest())
        assert result["download_url"].endswith("/agent-v9.9.9.dmg")
        assert result["sha256"] == "abc123"

    def test_empty_when_downloads_missing(self):
        result = _check({"mcp": {"latest": "9.9.9", "changelog": []}})
        assert result["download_url"] == ""
        assert result["sha256"] == ""

    def test_empty_when_url_is_for_a_different_version(self):
        """
        The v1.0.30 shape: `latest` bumped, downloads still pointing at the
        previous release. Its url+sha pair is self-consistent, so the checksum
        would VERIFY and the tray would silently install the old version.
        """
        result = _check(_manifest(
            latest="9.9.9",
            url="https://example.com/releases/download/v9.9.8/agent-v9.9.8.dmg",
            sha256="a" * 64,
        ))
        assert result["update_available"] is True
        assert result["download_url"] == ""
        assert result["sha256"] == ""

    def test_empty_when_sha256_is_blank(self):
        """The v1.0.31 shape: right url, checksum not filled in by CI yet."""
        result = _check(_manifest(sha256=""))
        assert result["download_url"] == ""
        assert result["sha256"] == ""


def _fake_stream(content: bytes):
    """Context-manager mock mimicking httpx.stream(...)."""
    resp = MagicMock()
    resp.headers = {"content-length": str(len(content))}
    resp.raise_for_status = MagicMock()
    resp.iter_bytes = MagicMock(return_value=iter([content]))
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestDownloadAndInstall:
    def test_checksum_mismatch_returns_reason(self, tmp_path):
        with (
            patch.object(tempfile, "gettempdir", return_value=str(tmp_path)),
            patch("httpx.stream", return_value=_fake_stream(b"binary data")),
        ):
            result = actions._download_and_install("https://example.com/f.dmg", "0" * 64)
        assert result == "checksum mismatch"

    def test_network_error_returns_reason(self):
        with patch("httpx.stream", side_effect=OSError("offline")):
            result = actions._download_and_install("https://example.com/f.dmg", "0" * 64)
        assert "offline" in result

    def test_success_calls_macos_installer(self, tmp_path):
        content = b"binary data"
        real_sha = hashlib.sha256(content).hexdigest()
        with (
            patch.object(tempfile, "gettempdir", return_value=str(tmp_path)),
            patch("httpx.stream", return_value=_fake_stream(content)),
            patch.object(actions, "_install_macos_update") as mock_mac,
            patch.object(actions, "_install_windows_update") as mock_win,
            patch.object(actions.sys, "platform", "darwin"),
        ):
            result = actions._download_and_install("https://example.com/f.dmg", real_sha)
        assert result == {"method": "silent", "success": True, "restart_required": True}
        mock_mac.assert_called_once()
        mock_win.assert_not_called()

    def test_success_calls_windows_installer(self, tmp_path):
        content = b"binary data"
        real_sha = hashlib.sha256(content).hexdigest()
        with (
            patch.object(tempfile, "gettempdir", return_value=str(tmp_path)),
            patch("httpx.stream", return_value=_fake_stream(content)),
            patch.object(actions, "_install_macos_update") as mock_mac,
            patch.object(actions, "_install_windows_update") as mock_win,
            patch.object(actions.sys, "platform", "win32"),
        ):
            result = actions._download_and_install("https://example.com/f.exe", real_sha)
        assert result == {"method": "silent", "success": True, "restart_required": False}
        mock_win.assert_called_once()
        mock_mac.assert_not_called()

    def test_install_failure_reports_error(self, tmp_path):
        content = b"binary data"
        real_sha = hashlib.sha256(content).hexdigest()
        with (
            patch.object(tempfile, "gettempdir", return_value=str(tmp_path)),
            patch("httpx.stream", return_value=_fake_stream(content)),
            patch.object(actions, "_install_macos_update", side_effect=RuntimeError("boom")),
            patch.object(actions.sys, "platform", "darwin"),
        ):
            result = actions._download_and_install("https://example.com/f.dmg", real_sha)
        assert result == {"method": "silent", "success": False, "error": "boom"}

    def test_progress_callback_invoked(self, tmp_path):
        content = b"x" * 1000
        real_sha = hashlib.sha256(content).hexdigest()
        seen = []
        with (
            patch.object(tempfile, "gettempdir", return_value=str(tmp_path)),
            patch("httpx.stream", return_value=_fake_stream(content)),
            patch.object(actions, "_install_macos_update"),
            patch.object(actions.sys, "platform", "darwin"),
        ):
            actions._download_and_install(
                "https://example.com/f.dmg", real_sha,
                progress_cb=lambda d, t: seen.append((d, t)),
            )
        assert seen == [(1000, 1000)]


class TestFormatDownloadProgress:
    def test_percent_and_megabytes(self):
        mb = 1024 * 1024
        assert actions.format_download_progress(20 * mb, 148 * mb) == "13%  (20 / 148 MB)"

    def test_falls_back_to_bytes_without_content_length(self):
        # total == 0 means the server sent no content-length; a percentage of
        # an unknown total would be meaningless.
        assert actions.format_download_progress(20 * 1024 * 1024, 0) == "20 MB"


class TestCurrentAppBundle:
    def test_resolves_nearest_app_ancestor(self):
        exe = "/Users/x/Applications/LocalLens Agent.app/Contents/MacOS/LocalLens Agent"
        with patch.object(sys, "executable", exe):
            assert actions._current_app_bundle() == Path(
                "/Users/x/Applications/LocalLens Agent.app"
            )

    def test_none_when_not_running_from_a_bundle(self):
        with patch.object(sys, "executable", "/usr/local/bin/python3"):
            assert actions._current_app_bundle() is None


def _mount_with_app(tmp_path):
    """Create a fake mounted DMG containing one .app, as hdiutil would."""
    mount = tmp_path / "mnt"
    (mount / "LocalLens Agent.app").mkdir(parents=True)
    return mount


class TestInstallMacosUpdate:
    """
    The old implementation hardcoded /Applications and called `open -a` while
    the old process was still alive — so a bundle in ~/Applications got a
    second copy and the app never actually restarted.
    """

    def test_replaces_the_bundle_it_is_running_from(self, tmp_path):
        mount = _mount_with_app(tmp_path)
        installed = tmp_path / "Applications" / "LocalLens Agent.app"
        installed.mkdir(parents=True)
        exe = str(installed / "Contents" / "MacOS" / "LocalLens Agent")

        with (
            patch.object(tempfile, "mkdtemp", return_value=str(mount)),
            patch.object(sys, "executable", exe),
            patch("shutil.rmtree") as rmtree,
            patch.object(actions.subprocess, "run") as run,
            patch.object(actions, "_relaunch_after_exit"),
        ):
            actions._install_macos_update(tmp_path / "update.dmg")

        ditto = next(c for c in run.call_args_list if c.args[0][0] == "ditto")
        assert ditto.args[0][2] == str(installed)
        # Removed, and NOT with ignore_errors — a failure must surface.
        rmtree.assert_any_call(installed)

    def test_falls_back_to_applications_outside_a_bundle(self, tmp_path):
        mount = _mount_with_app(tmp_path)
        with (
            patch.object(tempfile, "mkdtemp", return_value=str(mount)),
            patch.object(sys, "executable", "/usr/local/bin/python3"),
            patch("shutil.rmtree"),
            patch.object(actions.subprocess, "run") as run,
            patch.object(actions, "_relaunch_after_exit"),
        ):
            actions._install_macos_update(tmp_path / "update.dmg")

        ditto = next(c for c in run.call_args_list if c.args[0][0] == "ditto")
        assert ditto.args[0][2] == "/Applications/LocalLens Agent.app"

    def test_removal_failure_propagates(self, tmp_path):
        mount = _mount_with_app(tmp_path)
        installed = tmp_path / "Applications" / "LocalLens Agent.app"
        installed.mkdir(parents=True)
        exe = str(installed / "Contents" / "MacOS" / "LocalLens Agent")

        def _fail_on_bundle(path, *a, **kw):
            if Path(path) == installed:
                raise PermissionError("read-only volume")

        with (
            patch.object(tempfile, "mkdtemp", return_value=str(mount)),
            patch.object(sys, "executable", exe),
            patch("shutil.rmtree", side_effect=_fail_on_bundle),
            patch.object(actions.subprocess, "run"),
            patch.object(actions, "_relaunch_after_exit"),
            pytest.raises(PermissionError),
        ):
            actions._install_macos_update(tmp_path / "update.dmg")

    def test_relaunch_waits_for_this_process_to_exit(self, tmp_path):
        app = tmp_path / "LocalLens Agent.app"
        with patch.object(actions.subprocess, "Popen") as popen:
            actions._relaunch_after_exit(app)

        argv, kwargs = popen.call_args.args[0], popen.call_args.kwargs
        assert argv[:2] == ["/bin/sh", "-c"]
        # Must poll our own PID before opening, or `open` just re-activates
        # the still-registered old instance instead of launching the new one.
        assert f"kill -0 {os.getpid()}" in argv[2]
        assert f'open -a "{app}"' in argv[2]
        # Detached, so it outlives the process it is waiting on.
        assert kwargs["start_new_session"] is True


def _fake_win_subprocess(returncode=0, wait_side_effect=None):
    """
    Stand-in for the subprocess module inside tray.actions.

    _install_windows_update touches Windows-only attributes (STARTUPINFO,
    DETACHED_PROCESS, ...) that don't exist on macOS/Linux, so the whole
    module reference is swapped rather than patched attribute by attribute.
    """
    proc = MagicMock()
    if wait_side_effect is not None:
        proc.wait.side_effect = wait_side_effect
    else:
        proc.wait.return_value = returncode
    fake = MagicMock()
    fake.Popen.return_value = proc
    fake.TimeoutExpired = subprocess.TimeoutExpired  # real class, for `except`
    return fake


class TestInstallWindowsUpdate:
    """
    The Popen handle used to be discarded, so an aborted NSIS section (locked
    locallens-mcp.exe, killed process tree) failed completely silently.
    """

    def test_silent_when_installer_succeeds(self, tmp_path):
        with patch.object(actions, "subprocess", _fake_win_subprocess(returncode=0)):
            actions._install_windows_update(tmp_path / "setup.exe")  # no raise

    def test_raises_on_nonzero_exit(self, tmp_path):
        with (
            patch.object(actions, "subprocess", _fake_win_subprocess(returncode=2)),
            pytest.raises(RuntimeError, match="exited with code 2"),
        ):
            actions._install_windows_update(tmp_path / "setup.exe")

    def test_raises_on_timeout(self, tmp_path):
        timeout = subprocess.TimeoutExpired(cmd="setup.exe", timeout=300)
        with (
            patch.object(actions, "subprocess", _fake_win_subprocess(wait_side_effect=timeout)),
            pytest.raises(RuntimeError, match="did not finish"),
        ):
            actions._install_windows_update(tmp_path / "setup.exe")

    def test_install_failure_surfaces_through_download_and_install(self, tmp_path):
        """The raise must reach the tray as a reportable error, not vanish."""
        content = b"binary data"
        real_sha = hashlib.sha256(content).hexdigest()
        with (
            patch.object(tempfile, "gettempdir", return_value=str(tmp_path)),
            patch("httpx.stream", return_value=_fake_stream(content)),
            patch.object(actions, "_install_windows_update", side_effect=RuntimeError("locked")),
            patch.object(actions.sys, "platform", "win32"),
        ):
            result = actions._download_and_install("https://example.com/f.exe", real_sha)
        assert result == {"method": "silent", "success": False, "error": "locked"}


class TestInstallMcpUpdateFrozenFallback:
    def test_falls_back_to_browser_when_no_download_info(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(actions, "open_url") as mock_open,
        ):
            result = actions.install_mcp_update("1.2.3", "https://example.com/notes", "")
        assert result["method"] == "browser"
        # No silent install was promised, so the browser tab needs no excuse —
        # the trays stay quiet when "reason" is absent.
        assert "reason" not in result
        mock_open.assert_called_once()

    def test_falls_back_to_browser_when_silent_install_fails(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(actions, "_download_and_install", return_value="checksum mismatch"),
            patch.object(actions, "open_url") as mock_open,
        ):
            result = actions.install_mcp_update(
                "1.2.3", "https://example.com/notes", "",
                download_url="https://example.com/f.dmg", sha256="a" * 64,
            )
        assert result["method"] == "browser"
        # The user was told it would install in the background — the tray needs
        # this to explain the browser tab it gets instead.
        assert result["reason"] == "checksum mismatch"
        mock_open.assert_called_once()
