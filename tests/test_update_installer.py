"""
Tests for the in-app auto-updater: platform-key resolution + download URL /
checksum surfacing in mcp_server.updater, and the download/verify/install
flow in tray.actions (Issue 2 fix — see CLAUDE.md Gotchas).
"""
import hashlib
import sys
import tempfile
from unittest.mock import patch, MagicMock

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


class TestCheckForUpdatesDownloadInfo:
    def test_includes_download_url_and_sha256_when_present(self):
        manifest = {
            "mcp": {
                "latest": "9.9.9",
                "min_supported": "1.0.0",
                "changelog": [],
                "downloads": {
                    updater._get_platform_key(): {
                        "url": "https://example.com/update.dmg",
                        "sha256": "abc123",
                    }
                },
            }
        }
        with (
            patch.object(updater, "_get_manifest", return_value=manifest),
            patch.object(updater, "MCP_VERSION", "1.0.0"),
        ):
            result = updater.check_for_updates()
        assert result["download_url"] == "https://example.com/update.dmg"
        assert result["sha256"] == "abc123"

    def test_empty_when_downloads_missing(self):
        manifest = {"mcp": {"latest": "9.9.9", "changelog": []}}
        with (
            patch.object(updater, "_get_manifest", return_value=manifest),
            patch.object(updater, "MCP_VERSION", "1.0.0"),
        ):
            result = updater.check_for_updates()
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
    def test_checksum_mismatch_returns_none(self, tmp_path):
        with (
            patch.object(tempfile, "gettempdir", return_value=str(tmp_path)),
            patch("httpx.stream", return_value=_fake_stream(b"binary data")),
        ):
            result = actions._download_and_install("https://example.com/f.dmg", "0" * 64)
        assert result is None

    def test_network_error_returns_none(self):
        with patch("httpx.stream", side_effect=OSError("offline")):
            result = actions._download_and_install("https://example.com/f.dmg", "0" * 64)
        assert result is None

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


class TestInstallMcpUpdateFrozenFallback:
    def test_falls_back_to_browser_when_no_download_info(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(actions, "open_url") as mock_open,
        ):
            result = actions.install_mcp_update("1.2.3", "https://example.com/notes", "")
        assert result["method"] == "browser"
        mock_open.assert_called_once()

    def test_falls_back_to_browser_when_silent_install_returns_none(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(actions, "_download_and_install", return_value=None),
            patch.object(actions, "open_url") as mock_open,
        ):
            result = actions.install_mcp_update(
                "1.2.3", "https://example.com/notes", "",
                download_url="https://example.com/f.dmg", sha256="a" * 64,
            )
        assert result["method"] == "browser"
        mock_open.assert_called_once()
