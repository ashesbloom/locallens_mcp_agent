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
            # Mock shutil.which so the shared PATH-fallback doesn't find the
            # live venv binary and short-circuit before we reach the uvx branch.
            patch("mcp_server.claude_connector.shutil.which", side_effect=lambda cmd: "uvx" if cmd == "uvx" else None),
        ):
            cfg = get_mcp_command_config()
        assert cfg["command"] == "uvx"
        assert "locallens-mcp" in cfg["args"]
        assert "env" in cfg
        assert "LOCALLENS_STORE_URL" in cfg["env"]

    def test_global_pip_config(self):
        with (
            patch("mcp_server.claude_connector.detect_install_method", return_value="global_pip"),
            # Ensure shutil.which returns None so the last-resort bare command is used.
            patch("mcp_server.claude_connector.shutil.which", return_value=None),
        ):
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

    def test_creates_config_dir_when_missing(self, tmp_path):
        """If Claude Desktop dir doesn't exist, create it and proceed."""
        missing = tmp_path / "NoClaudeDir" / "claude_desktop_config.json"
        with _patch_config_path(missing):
            result = install_claude_connector()

        assert result["status"] == "installed"
        assert missing.parent.exists()

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


# ── bundled install method (py2app & PyInstaller) ─────────────────────────────


class TestBundledInstallMethod:
    """
    Tests for the frozen-binary code paths in get_mcp_command_config().

    These exercise the paths that are NEVER reachable in a normal pip/venv run,
    so they must be verified via mocking.  They correspond directly to the
    'MCP server not attaching to Claude when launched from a bundle' bug:
    the connector must inject a complete, valid command + env into Claude's
    config even when running inside a py2app .app or a PyInstaller EXE.
    """

    def test_py2app_bundle_pythonpath_constructed(self, tmp_path):
        """
        When sys.frozen == 'macosx_app', get_mcp_command_config() must:
          - return command = the bundled python executable
          - return args = ['-m', 'mcp_server.main']
          - set PYTHONPATH to include lib/<pyver>/, lib/<pyver>/lib-dynload/, and <pyver>.zip
          - set RESOURCEPATH env var
        """
        import sys as _sys

        # Build a fake py2app Resources tree so the path-existence checks pass
        resources = tmp_path / "Contents" / "Resources"
        py_ver = f"python{_sys.version_info.major}.{_sys.version_info.minor}"
        py_ver_nodot = f"python{_sys.version_info.major}{_sys.version_info.minor}"
        lib_dir = resources / "lib" / py_ver
        dynload_dir = lib_dir / "lib-dynload"
        zip_path = resources / "lib" / f"{py_ver_nodot}.zip"

        lib_dir.mkdir(parents=True)
        dynload_dir.mkdir(parents=True)
        zip_path.write_bytes(b"PK")  # dummy zip

        fake_python = tmp_path / "Contents" / "MacOS" / "python"
        fake_python.parent.mkdir(parents=True)
        fake_python.write_text("#!/bin/sh\necho fake\n")

        with (
            patch.object(_sys, "frozen", "macosx_app", create=True),
            patch.object(_sys, "executable", str(fake_python)),
            patch.dict(os.environ, {"RESOURCEPATH": str(resources)}, clear=False),
        ):
            method = detect_install_method()
            cfg = get_mcp_command_config()

        assert method == "py2app_bundle", f"Expected py2app_bundle, got {method!r}"

        # Command must be the bundled python, args must be [-m, mcp_server.main]
        assert cfg["command"] == str(fake_python)
        assert cfg["args"] == ["-m", "mcp_server.main"]

        # RESOURCEPATH must be forwarded into the env block
        assert "RESOURCEPATH" in cfg["env"]

        # PYTHONPATH must contain the lib dir and the zip
        python_path = cfg["env"].get("PYTHONPATH", "")
        path_parts = python_path.split(os.pathsep)
        assert str(lib_dir) in path_parts, "lib dir missing from PYTHONPATH"
        assert str(zip_path) in path_parts, "zip missing from PYTHONPATH"
        assert str(dynload_dir) in path_parts, "lib-dynload missing from PYTHONPATH"

    def test_pyinstaller_bundle_uses_meipass_binary(self, tmp_path):
        """
        When sys.frozen == True and sys._MEIPASS is set, get_mcp_command_config()
        must resolve the MCP binary from sys._MEIPASS (the extraction temp dir
        where PyInstaller unpacks the bundle at runtime).
        """
        import sys as _sys

        fake_meipass = tmp_path / "meipass"
        fake_meipass.mkdir()

        binary_name = "locallens-mcp.exe" if _sys.platform == "win32" else "locallens-mcp"
        fake_binary = fake_meipass / binary_name
        fake_binary.write_text("#!/bin/sh\necho fake\n")
        fake_binary.chmod(0o755)

        with (
            patch.object(_sys, "frozen", True, create=True),
            patch.object(_sys, "_MEIPASS", str(fake_meipass), create=True),
        ):
            method = detect_install_method()
            cfg = get_mcp_command_config()

        assert method == "bundled", f"Expected bundled, got {method!r}"
        assert cfg["command"] == str(fake_binary)
        assert cfg["args"] == []


# Allow running directly for quick feedback
if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)

