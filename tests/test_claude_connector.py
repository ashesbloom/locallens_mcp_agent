"""
Tests for src/mcp_server/claude_connector.py

Run with:
    cd locallens_mcp_agent
    source venv/bin/activate
    python -m pytest tests/test_claude_connector.py -v
"""

import json
import os
import sys
import shutil
import tempfile
import time
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ── Patch sys.platform and HOME before importing the module ───────────────────
# We patch at the function level inside each test using mock.patch, so the
# module import itself is clean.

# Make sure the src directory is on sys.path for direct test runs
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.claude_connector import (
    _MCP_KEY,
    _atomic_write,
    _backup_config,
    _load_config,
    detect_install_method,
    get_claude_config_path,
    get_connection_status,
    get_current_injection,
    get_mcp_command_config,
    install_claude_connector,
    is_claude_connected,
    is_claude_installed,
    uninstall_claude_connector,
    verify_mcp_binary,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_claude_dir(tmp_path):
    """Create a temp directory that mimics the Claude Desktop config dir."""
    claude_dir = tmp_path / "Claude"
    claude_dir.mkdir()
    return claude_dir


@pytest.fixture()
def tmp_config(tmp_claude_dir):
    """Return a Path to a (not yet created) claude_desktop_config.json."""
    return tmp_claude_dir / "claude_desktop_config.json"


@pytest.fixture()
def config_with_other_server(tmp_config):
    """Write a config file that already has an unrelated MCP server."""
    cfg = {
        "mcpServers": {
            "some_other_tool": {
                "command": "other-tool",
                "args": [],
            }
        }
    }
    tmp_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return tmp_config


@pytest.fixture()
def config_with_locallens(tmp_config):
    """Write a config file that already has locallens registered."""
    cfg = {
        "mcpServers": {
            "locallens": {
                "command": "locallens-mcp",
                "args": [],
                "env": {"LOCALLENS_STORE_URL": "https://locallens.lemonsqueezy.com"},
            }
        }
    }
    tmp_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return tmp_config


@pytest.fixture()
def corrupt_config(tmp_config):
    """Write a syntactically broken JSON file."""
    tmp_config.write_text("{bad json: yes,,,}", encoding="utf-8")
    return tmp_config


def _patch_config_path(config_path: Path):
    """Helper: patch get_claude_config_path to return a temp path."""
    return patch(
        "mcp_server.claude_connector.get_claude_config_path",
        return_value=config_path,
    )


# ── get_claude_config_path ─────────────────────────────────────────────────────


class TestGetClaudeConfigPath:
    def test_macos(self):
        with patch("sys.platform", "darwin"), patch.dict(os.environ, {}, clear=False):
            path = get_claude_config_path()
        assert "Claude" in path.parts
        assert path.name == "claude_desktop_config.json"
        assert "Library" in path.parts  # macOS-specific

    def test_windows(self):
        fake_appdata = "C:\\Users\\User\\AppData\\Roaming"
        with (
            patch("sys.platform", "win32"),
            patch.dict(os.environ, {"APPDATA": fake_appdata}),
        ):
            path = get_claude_config_path()
        assert str(path).endswith("claude_desktop_config.json")
        assert "Claude" in path.parts

    def test_windows_no_appdata(self):
        env_without_appdata = {k: v for k, v in os.environ.items() if k != "APPDATA"}
        with (
            patch("sys.platform", "win32"),
            patch.dict(os.environ, env_without_appdata, clear=True),
        ):
            with pytest.raises(RuntimeError, match="APPDATA"):
                get_claude_config_path()

    def test_linux(self):
        with patch("sys.platform", "linux"):
            path = get_claude_config_path()
        assert path.name == "claude_desktop_config.json"
        assert "Claude" in path.parts
        assert ".config" in path.parts


# ── is_claude_installed ────────────────────────────────────────────────────────


class TestIsClaudeInstalled:
    def test_returns_true_when_dir_exists(self, tmp_claude_dir, tmp_config):
        with _patch_config_path(tmp_config):
            assert is_claude_installed() is True

    def test_returns_false_when_dir_missing(self, tmp_path):
        missing_config = tmp_path / "NoSuchDir" / "claude_desktop_config.json"
        with _patch_config_path(missing_config):
            assert is_claude_installed() is False


# ── detect_install_method ──────────────────────────────────────────────────────


class TestDetectInstallMethod:
    def test_bundled(self):
        with patch.object(sys, "frozen", True, create=True):
            assert detect_install_method() == "bundled"

    def test_venv(self):
        with (
            patch.object(sys, "frozen", False, create=True),
            patch("sys.prefix", "/fake/venv"),
            patch("sys.base_prefix", "/usr"),
        ):
            assert detect_install_method() == "venv"

    def test_uvx(self):
        with (
            patch.object(sys, "frozen", False, create=True),
            patch("sys.prefix", sys.base_prefix),  # no venv
            patch("shutil.which", side_effect=lambda cmd: "/usr/bin/uvx" if cmd == "uvx" else None),
        ):
            assert detect_install_method() == "uvx"

    def test_global_pip(self):
        with (
            patch.object(sys, "frozen", False, create=True),
            patch("sys.prefix", sys.base_prefix),
            patch("shutil.which", return_value=None),
        ):
            assert detect_install_method() == "global_pip"


# ── get_mcp_command_config ─────────────────────────────────────────────────────


class TestGetMcpCommandConfig:
    def test_uvx_config(self):
        with (
            patch("mcp_server.claude_connector.detect_install_method", return_value="uvx"),
        ):
            cfg = get_mcp_command_config()
        assert cfg["command"] == "uvx"
        assert "locallens-mcp" in cfg["args"]
        assert "env" in cfg
        assert "LOCALLENS_STORE_URL" in cfg["env"]

    def test_global_pip_config(self):
        with patch("mcp_server.claude_connector.detect_install_method", return_value="global_pip"):
            cfg = get_mcp_command_config()
        assert cfg["command"] == "locallens-mcp"
        assert cfg["args"] == []
        assert "LOCALLENS_STORE_URL" in cfg["env"]

    def test_venv_config_uses_absolute_path(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        binary = bin_dir / "locallens-mcp"
        binary.touch()

        with (
            patch("mcp_server.claude_connector.detect_install_method", return_value="venv"),
            patch("sys.prefix", str(tmp_path)),
            patch("sys.platform", "linux"),
        ):
            cfg = get_mcp_command_config()
        assert cfg["command"] == str(binary)

    def test_env_block_always_present(self):
        for method in ("bundled", "uvx", "global_pip"):
            with patch("mcp_server.claude_connector.detect_install_method", return_value=method):
                cfg = get_mcp_command_config()
            assert "env" in cfg, f"env block missing for method={method}"
            assert "LOCALLENS_STORE_URL" in cfg["env"]


# ── _load_config ──────────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        assert _load_config(tmp_path / "nonexistent.json") == {}

    def test_parses_valid_json(self, tmp_config, config_with_other_server):
        result = _load_config(config_with_other_server)
        assert "mcpServers" in result

    def test_handles_corrupt_json_and_creates_backup(self, corrupt_config):
        result = _load_config(corrupt_config)
        assert result == {}
        # A backup file should have been created (label is "corrupt")
        backups = list(corrupt_config.parent.glob("*.corrupt.*"))
        assert len(backups) == 1


# ── _atomic_write ─────────────────────────────────────────────────────────────


class TestAtomicWrite:
    def test_write_creates_file(self, tmp_config):
        data = {"mcpServers": {"locallens": {"command": "test"}}}
        _atomic_write(tmp_config, data)
        assert tmp_config.exists()
        written = json.loads(tmp_config.read_text())
        assert written == data

    def test_no_tmp_file_left_behind(self, tmp_config):
        data = {"foo": "bar"}
        _atomic_write(tmp_config, data)
        tmp_file = tmp_config.with_suffix(".json.tmp")
        assert not tmp_file.exists()


# ── install_claude_connector ──────────────────────────────────────────────────


class TestInstallClaudeConnector:
    def test_fresh_install(self, tmp_config):
        """Install into a Claude dir with no existing config."""
        with (
            _patch_config_path(tmp_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value={"command": "locallens-mcp", "args": [], "env": {}}),
        ):
            result = install_claude_connector()

        assert result["status"] == "installed"
        assert result["claude_needs_restart"] is True

        written = json.loads(tmp_config.read_text())
        assert "locallens" in written["mcpServers"]

    def test_preserves_other_mcp_servers(self, config_with_other_server):
        """Other mcpServer entries must survive the injection."""
        with (
            _patch_config_path(config_with_other_server),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value={"command": "locallens-mcp", "args": [], "env": {}}),
        ):
            result = install_claude_connector()

        assert result["status"] == "installed"
        written = json.loads(config_with_other_server.read_text())
        assert "some_other_tool" in written["mcpServers"]
        assert "locallens" in written["mcpServers"]

    def test_idempotent_when_config_matches(self, tmp_config):
        """Re-running install when the entry is identical → already_connected."""
        desired = {"command": "locallens-mcp", "args": [], "env": {}}
        cfg = {"mcpServers": {"locallens": desired}}
        tmp_config.write_text(json.dumps(cfg), encoding="utf-8")

        with (
            _patch_config_path(tmp_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value=desired),
        ):
            result = install_claude_connector()

        assert result["status"] == "already_connected"
        assert result["claude_needs_restart"] is False

    def test_force_overwrites_when_already_connected(self, tmp_config):
        """force=True should re-inject even if config looks identical."""
        desired = {"command": "locallens-mcp", "args": [], "env": {}}
        cfg = {"mcpServers": {"locallens": desired}}
        tmp_config.write_text(json.dumps(cfg), encoding="utf-8")

        with (
            _patch_config_path(tmp_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value=desired),
        ):
            result = install_claude_connector(force=True)

        assert result["status"] == "updated"

    def test_updates_stale_entry(self, tmp_config):
        """If the existing entry has a different command, it should update."""
        old_entry = {"command": "/old/path/locallens-mcp", "args": []}
        cfg = {"mcpServers": {"locallens": old_entry}}
        tmp_config.write_text(json.dumps(cfg), encoding="utf-8")

        new_cmd = {"command": "/new/path/locallens-mcp", "args": [], "env": {}}
        with (
            _patch_config_path(tmp_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "/new/path/locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value=new_cmd),
        ):
            result = install_claude_connector()

        assert result["status"] == "updated"
        written = json.loads(tmp_config.read_text())
        assert written["mcpServers"]["locallens"]["command"] == "/new/path/locallens-mcp"

    def test_error_when_claude_not_installed(self, tmp_path):
        """If Claude Desktop dir doesn't exist, return a helpful error."""
        missing = tmp_path / "NoClaudeDir" / "claude_desktop_config.json"
        with _patch_config_path(missing):
            result = install_claude_connector()

        assert result["status"] == "error"
        assert "not appear to be installed" in result["message"]

    def test_error_when_binary_invalid(self, tmp_config):
        """If the binary can't be found, return an error before touching config."""
        with (
            _patch_config_path(tmp_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": False, "command": "locallens-mcp",
                                "reason": "Not found on PATH"}),
        ):
            result = install_claude_connector()

        assert result["status"] == "error"
        assert "Not found on PATH" in result["message"]
        # Config file should NOT have been written
        assert not tmp_config.exists()

    def test_backup_created_on_existing_config(self, config_with_other_server):
        """A backup file must be created before modifying an existing config."""
        with (
            _patch_config_path(config_with_other_server),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value={"command": "locallens-mcp", "args": [], "env": {}}),
        ):
            result = install_claude_connector()

        assert result["backup_path"] is not None
        assert Path(result["backup_path"]).exists()

    def test_version_meta_block_injected(self, tmp_config):
        """The injected entry must contain a _locallens_meta block."""
        with (
            _patch_config_path(tmp_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value={"command": "locallens-mcp", "args": [], "env": {}}),
        ):
            install_claude_connector()

        written = json.loads(tmp_config.read_text())
        entry = written["mcpServers"]["locallens"]
        assert "_locallens_meta" in entry
        assert "version" in entry["_locallens_meta"]
        assert "installed_at" in entry["_locallens_meta"]
        assert entry["_locallens_meta"]["installed_by"] == "locallens-mcp-connector"

    def test_corrupt_config_gets_backed_up_then_overwritten(self, corrupt_config):
        """A corrupt config must be backed up and then replaced with valid JSON."""
        with (
            _patch_config_path(corrupt_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
            patch("mcp_server.claude_connector.get_mcp_command_config",
                  return_value={"command": "locallens-mcp", "args": [], "env": {}}),
        ):
            result = install_claude_connector()

        assert result["status"] == "installed"
        # The resulting config must be valid JSON
        written = json.loads(corrupt_config.read_text())
        assert "locallens" in written["mcpServers"]


# ── uninstall_claude_connector ────────────────────────────────────────────────


class TestUninstallClaudeConnector:
    def test_removes_locallens_key(self, config_with_locallens):
        with _patch_config_path(config_with_locallens):
            result = uninstall_claude_connector()

        assert result["status"] == "removed"
        written = json.loads(config_with_locallens.read_text())
        assert "locallens" not in written.get("mcpServers", {})

    def test_preserves_other_servers(self, tmp_config):
        """Uninstall should remove only locallens, leaving others intact."""
        cfg = {
            "mcpServers": {
                "locallens": {"command": "locallens-mcp"},
                "other_tool": {"command": "other"},
            }
        }
        tmp_config.write_text(json.dumps(cfg), encoding="utf-8")

        with _patch_config_path(tmp_config):
            uninstall_claude_connector()

        written = json.loads(tmp_config.read_text())
        assert "other_tool" in written.get("mcpServers", {})
        assert "locallens" not in written.get("mcpServers", {})

    def test_empty_mcpservers_key_removed(self, config_with_locallens):
        """If locallens was the only server, the empty mcpServers key is pruned."""
        with _patch_config_path(config_with_locallens):
            uninstall_claude_connector()

        written = json.loads(config_with_locallens.read_text())
        assert "mcpServers" not in written

    def test_not_connected_is_noop(self, tmp_config):
        """Uninstalling when not connected returns not_connected without modifying file."""
        cfg = {"mcpServers": {"other": {"command": "x"}}}
        tmp_config.write_text(json.dumps(cfg), encoding="utf-8")
        original_mtime = tmp_config.stat().st_mtime

        with _patch_config_path(tmp_config):
            result = uninstall_claude_connector()

        assert result["status"] == "not_connected"
        # File should not have been touched
        assert tmp_config.stat().st_mtime == original_mtime


# ── get_connection_status ─────────────────────────────────────────────────────


class TestGetConnectionStatus:
    def test_connected_state(self, config_with_locallens):
        with (
            _patch_config_path(config_with_locallens),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
        ):
            status = get_connection_status()

        assert status["connected"] is True
        assert status["claude_installed"] is True
        assert "locallens-mcp" in status["command"]

    def test_disconnected_state(self, config_with_other_server):
        with (
            _patch_config_path(config_with_other_server),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
        ):
            status = get_connection_status()

        assert status["connected"] is False
        assert "some_other_tool" in status["other_mcp_servers"]

    def test_claude_not_installed(self, tmp_path):
        missing = tmp_path / "NoClaudeDir" / "claude_desktop_config.json"
        with (
            _patch_config_path(missing),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": False, "command": "locallens-mcp",
                                "reason": "Not found"}),
        ):
            status = get_connection_status()

        assert status["claude_installed"] is False
        assert status["connected"] is False
        assert status["binary_valid"] is False

    def test_status_has_all_required_keys(self, tmp_config):
        required_keys = {
            "connected", "claude_installed", "config_path", "command",
            "install_method", "binary_valid", "binary_reason", "version",
            "installed_at", "other_mcp_servers",
        }
        with (
            _patch_config_path(tmp_config),
            patch("mcp_server.claude_connector.verify_mcp_binary",
                  return_value={"valid": True, "command": "locallens-mcp"}),
        ):
            status = get_connection_status()

        assert required_keys.issubset(status.keys())


# ── backup pruning ────────────────────────────────────────────────────────────


class TestBackupPruning:
    def test_old_backups_are_pruned(self, tmp_config):
        """After _MAX_BACKUPS+2 backups, only _MAX_BACKUPS should remain."""
        from mcp_server.claude_connector import _MAX_BACKUPS

        tmp_config.write_text("{}", encoding="utf-8")

        # Create _MAX_BACKUPS + 2 backups
        for _ in range(_MAX_BACKUPS + 2):
            _backup_config(tmp_config, label="backup")
            time.sleep(0.01)  # Ensure distinct mtime ordering

        backups = list(tmp_config.parent.glob("*.backup.*"))
        assert len(backups) <= _MAX_BACKUPS


# Allow running directly for quick feedback
if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
