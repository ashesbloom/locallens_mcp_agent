"""
Tests for the total_files cross-check in src/mcp_server/tools/status.py

Regression context: the backend's os.walk skips only files sitting DIRECTLY in an
ignored folder and still descends into its children. Sorted output always nests
(Sorted_By_People/Mayank/...), so those folders hold zero direct files and the
ignore_list excluded nothing — a 75-file job reported total_files: 680.

Handed that contradiction with no explanation, the agent invented one ("total_files
counts everything before the ignore filter was applied"). These tests pin the
behaviour that makes the contradiction impossible to smooth over.

Run with:
    cd locallens_mcp_agent
    source venv/bin/activate
    python -m pytest tests/test_total_files_crosscheck.py -v

NOTE: this file was reconstructed from tests/__pycache__/*.pyc after being deleted.
Docstrings, structure, and constants are recovered verbatim from the bytecode; the
inline comments of the original are lost.
"""

import os
import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools.status import (
    _COUNT_MISMATCH_TOLERANCE,
    _expected_file_count,
    _flag_file_count_mismatch,
)


def _build_tree(root, top_level, nested):
    """
    Mirrors the user's real layout: `top_level` photos in the root, and an ignored
    folder whose photos live one level DOWN, never directly inside it.
    """
    for i in range(top_level):
        Path(os.path.join(root, f"top_{i}.jpg")).touch()

    ignored = os.path.join(root, "Sorted_By_People")
    nested_dir = os.path.join(ignored, "Mayank")
    os.makedirs(nested_dir)
    for i in range(nested):
        Path(os.path.join(nested_dir, f"sorted_{i}.jpg")).touch()
    return ignored


def test_nested_files_are_excluded():
    """
    The case that fails without subtree pruning. A test placing files directly in the
    ignored folder would pass even with the bug — the files must be nested.
    """
    with tempfile.TemporaryDirectory() as root:
        ignored = _build_tree(root, 75, 380)
        assert _expected_file_count(root, [ignored]) == 75
        assert _expected_file_count(root, []) == 455


def test_unscannable_source_returns_none():
    """'I could not check' must never become 'the counts disagree'."""
    assert _expected_file_count("/nope/does/not/exist", []) is None
    with tempfile.TemporaryDirectory() as root:
        assert _expected_file_count(root, "not-a-list") is None


def test_flags_the_real_mismatch():
    with tempfile.TemporaryDirectory() as root:
        ignored = _build_tree(root, 75, 380)
        payload = _flag_file_count_mismatch({
            "total_files": 455,
            "source_folder": root,
            "ignore_list": [ignored],
            "progress": 0,
        })
        assert payload["expected_after_ignore"] == 75
        assert "455" in payload["warning"] and "75" in payload["warning"]
        assert "abort_job" in payload["guidance"]


def test_agreement_adds_nothing():
    with tempfile.TemporaryDirectory() as root:
        ignored = _build_tree(root, 75, 380)
        payload = _flag_file_count_mismatch({
            "total_files": 75,
            "source_folder": root,
            "ignore_list": [ignored],
        })
        assert "warning" not in payload
        assert "expected_after_ignore" not in payload


def test_small_drift_is_not_flagged():
    """A file added between the backend's count and ours must not cry wolf."""
    with tempfile.TemporaryDirectory() as root:
        ignored = _build_tree(root, 75, 380)
        payload = _flag_file_count_mismatch({
            "total_files": 75 + _COUNT_MISMATCH_TOLERANCE,
            "source_folder": root,
            "ignore_list": [ignored],
        })
        assert "warning" not in payload


def test_incomplete_payloads_pass_through_untouched():
    assert _flag_file_count_mismatch("unexpected payload") == "unexpected payload"
    assert isinstance(_flag_file_count_mismatch({}), dict)
    assert "warning" not in _flag_file_count_mismatch({"total_files": "many"})
    assert "warning" not in _flag_file_count_mismatch({"total_files": 680})
    assert "warning" not in _flag_file_count_mismatch(
        {"total_files": 680, "source_folder": "/tmp"}
    )


def test_unscannable_source_never_warns():
    """Fail open: a vanished source folder must not manufacture a mismatch."""
    payload = _flag_file_count_mismatch({
        "total_files": 680,
        "source_folder": "/nope/does/not/exist",
        "ignore_list": [],
    })
    assert "warning" not in payload
