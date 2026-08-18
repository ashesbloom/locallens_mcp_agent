"""
Tests for the backend-501 guard in src/mcp_server/tools/pro_tools.py

Regression cover for a real support case: a user with a ~15,000-photo archive on
Windows 11 asked their assistant to de-duplicate. The backend answered 501 with
"The 'imagehash' library is not installed. Run: pip install imagehash", _handle_error
relayed it verbatim, and the assistant obeyed the sentence — running pip in its own
shell, against an interpreter that is not the backend's. The shipped backend is a
PyInstaller bundle with no pip and no site-packages, so it changed nothing, and the
assistant escalated to telling the user to reinstall LocalLens.

The rule this file pins: a 501 must never carry a shell command back to the model.

Run with:
    cd locallens_mcp_agent
    source venv/bin/activate
    python -m pytest tests/test_missing_dependency_guidance.py -v
"""

import sys
from pathlib import Path

import httpx
import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools.pro_tools import _handle_error  # noqa: E402


def _status_error(status_code: int, body) -> httpx.HTTPStatusError:
    """Build a real HTTPStatusError the way httpx would raise it."""
    request = httpx.Request("POST", "http://127.0.0.1:8000/api/find-duplicates")
    if isinstance(body, str):
        response = httpx.Response(status_code, text=body, request=request)
    else:
        response = httpx.Response(status_code, json=body, request=request)
    return httpx.HTTPStatusError("err", request=request, response=response)


# The exact strings the backend emits today (backend/main.py:1019 and :1179).
IMAGEHASH_501 = {
    "detail": "The 'imagehash' library is not installed. Run: pip install imagehash"
}
REPORTLAB_501 = {
    "detail": "The 'reportlab' library is not installed. Run: pip install reportlab"
}


def _assert_no_executable_instruction(result):
    """
    The backend's own words are relayed only with the command stripped.

    `guidance` is exempt and deliberately says "do NOT run pip install" — naming the
    command in order to forbid it is the whole point. Every other field must be clean,
    since those are what the model reads as a description of what happened.
    """
    relayed = {k: v for k, v in result.items() if k != "guidance"}
    blob = repr(relayed).lower()
    assert "pip install" not in blob
    assert "run:" not in blob
    # And the one mention that is allowed must be a prohibition, never a suggestion.
    assert "do not run pip install" in result["guidance"].lower()


@pytest.mark.parametrize("body", [IMAGEHASH_501, REPORTLAB_501])
def test_501_never_relays_a_pip_command(body):
    _assert_no_executable_instruction(_handle_error(_status_error(501, body)))


@pytest.mark.parametrize(
    "body,expected_component",
    [(IMAGEHASH_501, "imagehash"), (REPORTLAB_501, "reportlab")],
)
def test_501_names_the_component_and_the_real_fix(body, expected_component):
    result = _handle_error(_status_error(501, body))
    assert result["error"] == "feature_unavailable_in_build"
    # The component name survives for the user's benefit, without the command.
    assert expected_component in result["message"]
    # The only actionable remedy is updating the desktop app.
    assert "updat" in result["guidance"].lower()


def test_501_with_unrecognised_detail_still_suppresses_commands():
    """A future 501 we have not seen must fail safe, not fall through to passthrough."""
    body = {"detail": "Some new optional thing is missing. Run: pip install whatever"}
    result = _handle_error(_status_error(501, body))
    assert result["error"] == "feature_unavailable_in_build"
    _assert_no_executable_instruction(result)


def test_501_with_plain_text_body():
    """Not every backend error is JSON; the guard must handle text bodies too."""
    result = _handle_error(
        _status_error(501, "The 'imagehash' library is not installed. Run: pip install imagehash")
    )
    assert result["error"] == "feature_unavailable_in_build"
    _assert_no_executable_instruction(result)


def test_non_501_errors_are_unchanged():
    """Only 501 is special-cased — everything else keeps its passthrough behaviour."""
    body = {"detail": "Source path is not a valid directory."}
    result = _handle_error(_status_error(400, body))
    assert result == {"error": body}


def test_non_http_errors_are_unchanged():
    result = _handle_error(ValueError("boom"))
    assert result == {"error": "boom"}


# ── The stale-state guard vs. jobs that finish too fast to observe ────────────
# _wait_for_completion gates every exit condition behind has_started, which only
# flips when a poll samples is_active=True. A duplicate scan over a few dozen
# photos finishes inside the first poll interval, so that sample never happens and
# the caller would spin to timeout_s reporting "still_running" for a finished job.
# assume_started carries the POST's "status: started" confirmation into the guard.

import asyncio  # noqa: E402

from mcp_server.tools import actions as _actions  # noqa: E402


class _FakeClient:
    """Serves a job-status that is already terminal — never is_active=True."""

    def __init__(self):
        self.polls = 0

    async def get(self, url, timeout=None):
        self.polls += 1
        return httpx.Response(
            200,
            json={"is_active": False, "status": "complete", "progress": 100,
                  "job_type": "duplicates", "duplicate_groups": []},
            request=httpx.Request("GET", url),
        )


def test_assume_started_accepts_an_already_finished_job():
    client = _FakeClient()
    result = asyncio.run(
        _actions._wait_for_completion(client, timeout_s=5, poll_interval_s=0.5,
                                      assume_started=True)
    )
    assert result["status"] == "complete"
    assert client.polls == 1  # returns on the first poll, no spinning


def test_default_still_guards_against_stale_terminal_state():
    """Without the flag, identical state must NOT be accepted — that is the guard."""
    client = _FakeClient()
    result = asyncio.run(
        _actions._wait_for_completion(client, timeout_s=2, poll_interval_s=0.5)
    )
    assert result["status"] == "still_running"  # timed out rather than trusting it
    assert client.polls > 1
