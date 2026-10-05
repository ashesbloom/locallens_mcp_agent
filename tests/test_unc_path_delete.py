r"""
Tests for the Windows UNC path handling in src/mcp_server/tools/pro_tools.py

Regression cover for a real support case. A customer on Windows 11 keeping ~15,000 photos
on an Unraid share asked their assistant to clean up duplicates in '//cube/data/photos'.
find_duplicates worked. delete_duplicates(dry_run=True) reported success. Calling it again
with dry_run=False failed for EVERY file:

    [Errno 3] The system cannot find the path specified.:
        '\\?\//cube/data/photos\Unknown_Date\<file>'

The chain, verified by replaying send2trash's own logic rather than inferred:

  1. The customer typed a forward-slash UNC path. os.path.join during the backend scan
     appends with a backslash, so stored paths are hybrids:
     '//cube/data/photos\Unknown_Date\a.jpg'.
  2. Nothing on either side of the MCP boundary normalised the separators — the MCP passed
     file_paths through verbatim, and the backend's os.path.expanduser does not touch them.
  3. pywin32 is absent from the backend's requirements.txt, so send2trash falls back from
     win/modern.py (which strips '\\?\') to win/legacy.py (which adds it).
  4. legacy.prefix_and_path() detects UNC with path.startswith('\\'), which is False for a
     path beginning '//', so it takes the local-path branch and builds '\\?\' + path.
  5. '\\?\' is the ONLY Win32 path form that rejects forward slashes. Every ordinary API —
     including the os.path.isfile the dry run relies on — goes through a parser that folds
     '/' to '\' for you. That asymmetry is exactly why the preview passed and the delete
     failed, and why the customer got no warning.

The fix is to normalise before the path is handed on: ntpath.normpath folds '/' to '\',
which makes send2trash take its UNC branch and build a resolvable '\\?\UNC\...' instead.

ntpath is pure Python and imports on every platform, so the Windows semantics below are
exercised for real on macOS and on Linux CI, without a Windows machine.

Run with:
    cd locallens_mcp_agent
    python -m pytest tests/test_unc_path_delete.py -v
"""

import ntpath
import os
import posixpath
import sys
from pathlib import Path

import httpx
import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools.pro_tools import (  # noqa: E402
    _DELETE_FAILED_GUIDANCE,
    _REPORT_GUIDANCE,
    _canonical,
    _handle_error,
)

# The customer's path, in the hybrid separator form the backend actually stored.
REPORTED_PATH = r"//cube/data/photos\Unknown_Date\IMG_1234.jpg"

# What Windows reported back, verbatim from the bug report.
REPORTED_BROKEN_PREFIX = r"\\?\//cube/data/photos\Unknown_Date\IMG_1234.jpg"


def _send2trash_prefix_and_path(path):
    r"""
    Copied verbatim from send2trash 2.1.0, win/legacy.py lines 90-111 — the branch that
    runs in the shipped build, because pywin32 is not bundled. Reproduced here rather than
    imported so the test states the third-party behaviour it depends on, and still runs on
    a machine where send2trash's Windows module cannot be imported at all.
    """
    prefix, long_path = "\\\\?\\", path

    if not path.startswith(prefix):
        if path.startswith("\\\\"):
            # Likely a UNC name
            prefix = "\\\\?\\UNC"
            long_path = prefix + path[1:]
        else:
            # Likely a local path
            long_path = prefix + path
    elif path.startswith(prefix + "UNC\\"):
        prefix = "\\\\?\\UNC"

    return prefix, long_path


# ── The bug ─────────────────────────────────────────────────────────────────


def test_unnormalised_path_reproduces_the_reported_error():
    """
    Pins WHY it broke. Without normalisation send2trash builds the exact string Windows
    rejected — if this ever stops matching, the root-cause analysis above is stale.
    """
    _, long_path = _send2trash_prefix_and_path(REPORTED_PATH)
    assert long_path == REPORTED_BROKEN_PREFIX


def test_normalising_first_produces_a_resolvable_unc_path():
    """Pins WHY the fix works: normpath is what makes the UNC branch fire."""
    prefix, long_path = _send2trash_prefix_and_path(ntpath.normpath(REPORTED_PATH))
    assert prefix == "\\\\?\\UNC"
    assert long_path == r"\\?\UNC\cube\data\photos\Unknown_Date\IMG_1234.jpg"
    assert not long_path.startswith(r"\\?\//")


def test_ntpath_normpath_folds_forward_slashes_and_keeps_the_unc_root():
    """The single behaviour the whole fix rests on."""
    assert ntpath.normpath(REPORTED_PATH) == r"\\cube\data\photos\Unknown_Date\IMG_1234.jpg"


# ── The fix must not break POSIX ────────────────────────────────────────────


def test_posix_normpath_leaves_backslashes_alone():
    """
    Why _canonical needs no sys.platform guard: os.path is already ntpath on Windows and
    posixpath elsewhere. On POSIX a backslash is a legal filename character, and normpath
    correctly refuses to treat it as a separator.
    """
    assert posixpath.normpath("/Users/x/a\\b.jpg") == "/Users/x/a\\b.jpg"


@pytest.mark.parametrize(
    "already_fine",
    [
        "/Users/mayank/Pictures/a.jpg",
        r"C:\Users\mayank\Pictures\a.jpg",
        r"\\cube\data\photos\a.jpg",
    ],
)
def test_canonical_is_a_noop_on_paths_that_are_already_correct(already_fine):
    """Local folders — the overwhelmingly common case — must be untouched."""
    assert _canonical(already_fine) == os.path.normpath(already_fine)


def test_canonical_expands_the_user_home():
    """CLAUDE.md's path convention: user-supplied paths get expanduser before use."""
    assert _canonical("~/Pictures") == os.path.normpath(os.path.expanduser("~/Pictures"))
    assert "~" not in _canonical("~/Pictures")


# ── Guidance on failure ─────────────────────────────────────────────────────
#
# The second half of the same support case. The backend answers HTTP 200 with a populated
# failed[] array, so _handle_error never fires and the model received a raw OS error with
# no instruction attached. It then went looking for the cause in LocalLens itself. The real
# hazard is not wasted effort: the obvious "workaround" for a failed delete is to remove the
# files with a shell command, which bypasses the OS Trash that makes this tool recoverable.


def test_delete_guidance_forbids_deleting_by_any_other_route():
    """The data-loss guard. This is the sentence that matters most in this file."""
    lowered = _DELETE_FAILED_GUIDANCE.lower()
    assert "do not remove, move or trash these files by any other route" in lowered
    assert "shell command" in lowered
    assert "permanently" in lowered


def test_delete_guidance_carries_no_executable_instruction():
    """
    Same rule the 501 guard established in 1.1.1: an error string that contains an imperative
    shell command gets executed by the client. Naming a command in order to forbid it is fine;
    handing one over is not.
    """
    lowered = _DELETE_FAILED_GUIDANCE.lower()
    for command in ("run:", "rm -", "del ", "remove-item", "os.remove", "sudo "):
        assert command not in lowered, f"guidance hands the model {command!r}"


@pytest.mark.parametrize("guidance", [_REPORT_GUIDANCE, _DELETE_FAILED_GUIDANCE])
def test_guidance_routes_to_the_maintainer_not_to_self_diagnosis(guidance):
    """LocalLens is BSL 1.1 and ships as a bundle — there is nothing here to patch."""
    assert "https://locallensmcp.vercel.app/#contact" in guidance
    assert "https://github.com/ashesbloom/locallens_mcp_agent/issues" in guidance
    assert "business source license" in guidance.lower()


@pytest.mark.parametrize("guidance", [_REPORT_GUIDANCE, _DELETE_FAILED_GUIDANCE])
def test_guidance_never_ships_the_dead_domain(guidance):
    """locallens.app lapsed and now serves Whistle Enterprise. See test_claude_instructions."""
    assert "locallens.app" not in guidance


# ── Wiring ──────────────────────────────────────────────────────────────────


def _status_error(status_code, body):
    request = httpx.Request("POST", "http://127.0.0.1:8000/api/delete-files")
    return httpx.HTTPStatusError(
        "err", request=request, response=httpx.Response(status_code, json=body, request=request)
    )


def test_backend_defects_carry_the_report_pointer():
    """A 5xx is the backend failing, which is the case worth handing to the maintainer."""
    result = _handle_error(_status_error(500, {"detail": "boom"}))
    assert result["guidance"] == _REPORT_GUIDANCE
    assert result["error"] == {"detail": "boom"}


def test_client_errors_do_not_carry_the_report_pointer():
    """A 4xx is a bad call, not a defect — telling the user to file a bug misdirects them."""
    assert "guidance" not in _handle_error(_status_error(400, {"detail": "empty list"}))


def test_connection_failures_do_not_carry_the_report_pointer():
    """"LocalLens is not running" is fixed by starting it, not by emailing the maintainer."""
    request = httpx.Request("POST", "http://127.0.0.1:8000/api/delete-files")
    assert "guidance" not in _handle_error(httpx.ConnectError("refused", request=request))


def test_501_guard_still_wins():
    """
    The 1.1.1 fix must keep its own guidance — that one names updating the app, which is the
    actual remedy for a missing build component, and is more specific than 'report it'.
    """
    body = {"detail": "The 'imagehash' library is not installed. Run: pip install imagehash"}
    result = _handle_error(_status_error(501, body))
    assert result["error"] == "feature_unavailable_in_build"
    assert "pip install" not in repr({k: v for k, v in result.items() if k != "guidance"})


# ── Wiring, end to end ──────────────────────────────────────────────────────
#
# Everything above tests helpers in isolation. This one drives the real tool through
# FastMCP with a stubbed backend, because the two lines that matter are wiring: if someone
# later drops the _canonical() call from the payload, every test above still passes.
#
# pro_tools' `os` is swapped for one whose `.path` is ntpath, which is what running on
# Windows actually means for this code — os.path is bound per-platform at import.


def test_delete_duplicates_sends_canonical_paths_and_guidance_on_windows():
    import asyncio
    import json
    import types
    from unittest.mock import patch

    import mcp_server.tools.pro_tools as pro_tools
    from mcp_server.main import create_mcp_app

    captured = {}

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            # What the customer's Windows box returned: 200, nothing deleted, all failed.
            return {
                "status": "deleted",
                "dry_run": False,
                "use_trash": True,
                "deleted": [],
                "total_freed_mb": 0.0,
                "failed": [
                    {"path": path, "error": "[Errno 3] The system cannot find the path specified."}
                    for path in captured["payload"]["file_paths"]
                ],
            }

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, timeout=None):
            captured["payload"] = json
            return _FakeResponse()

    app = create_mcp_app()
    windows_os = types.SimpleNamespace(path=ntpath, name="nt")

    async def _call():
        # delete_duplicates is Pro. Unlock it explicitly: otherwise the result depends on
        # whether this machine's install stamp predates the paid launch (fresh CI: it doesn't).
        with patch("mcp_server.license.pro_features_unlocked", return_value=True), \
                patch.object(pro_tools.httpx, "AsyncClient", _FakeClient), \
                patch.object(pro_tools, "os", windows_os):
            return await app.call_tool(
                "delete_duplicates",
                {"file_paths": [REPORTED_PATH], "dry_run": False},
            )

    result = asyncio.run(_call())

    # The payload the backend would have received is now a real UNC path, so send2trash
    # takes its UNC branch instead of building the string Windows rejected.
    assert captured["payload"]["file_paths"] == [r"\\cube\data\photos\Unknown_Date\IMG_1234.jpg"]
    _, long_path = _send2trash_prefix_and_path(captured["payload"]["file_paths"][0])
    assert long_path == r"\\?\UNC\cube\data\photos\Unknown_Date\IMG_1234.jpg"

    # And a total failure now reaches the model with instructions, not just an errno.
    rendered = json.dumps(result, default=str)
    assert "Do NOT remove, move or trash these files by any other route" in rendered
    assert "https://locallensmcp.vercel.app/#contact" in rendered
