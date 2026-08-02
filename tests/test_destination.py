"""
Tests for _resolve_destination in src/mcp_server/tools/actions.py

Run with:
    cd locallens_mcp_agent
    source venv/bin/activate
    python -m pytest tests/test_destination.py -v
"""

import os
import sys
import tempfile
from pathlib import Path

# Make sure the src directory is on sys.path for direct test runs
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools.actions import _MAX_NEW_DEST_LEVELS, _resolve_destination


def test_existing_dir_passes_through():
    with tempfile.TemporaryDirectory() as tmp:
        path, err = _resolve_destination(tmp, create=False)
        assert err is None
        assert path == tmp


def test_missing_dir_refuses_without_opt_in():
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "output", "Date")
        path, err = _resolve_destination(target, create=False)
        assert path is None
        assert err["retry_with"] == "create_destination=True"
        assert not os.path.exists(target), "must not create anything when create=False"


def test_missing_dir_created_with_opt_in():
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "output", "Date")
        path, err = _resolve_destination(target, create=True)
        assert err is None
        assert path == target
        assert os.path.isdir(target)


def test_refuses_runaway_nesting():
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, *["deep"] * (_MAX_NEW_DEST_LEVELS + 1))
        path, err = _resolve_destination(target, create=True)
        assert path is None
        assert "nested folders" in err["error"]
        assert not os.path.exists(target)


def test_refuses_file_as_destination():
    with tempfile.NamedTemporaryFile() as f:
        path, err = _resolve_destination(f.name, create=True)
        assert path is None
        assert "not a directory" in err["error"]


def test_refuses_empty_path():
    path, err = _resolve_destination("", create=True)
    assert path is None
    assert "empty" in err["error"].lower()
