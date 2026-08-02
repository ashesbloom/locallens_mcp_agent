"""
Tests for the one-job-at-a-time guard and the bounded wait in
src/mcp_server/tools/actions.py

Regression context: /api/job-status is a single global slot with no job id. A
second job started while one was running made every poll ambiguous — the agent
read job A's "380 of 602 complete" and reported it as job B's result while B was
still ~30% through, and both jobs split the same CPU.

Run with:
    cd locallens_mcp_agent
    source venv/bin/activate
    python -m pytest tests/test_concurrent_job.py -v
"""

import asyncio
import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools.actions import (
    _DEFAULT_WAIT_S,
    _reject_if_job_running,
    _wait_for_completion,
)


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient — only .get() is exercised."""

    def __init__(self, payload=None, raises=None):
        self._payload = payload
        self._raises = raises

    async def get(self, url, timeout=None):
        if self._raises:
            raise self._raises
        return _FakeResponse(self._payload)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


# Captured verbatim from the live backend while a sort was running.
RUNNING_JOB = {
    "is_active": True,
    "progress": 53,
    "status": "running",
    "job_type": "sorting",
    "total_files": 602,
    "destination_folder": "/Users/x/Git/Bot testing/output",
}


def test_blocks_when_a_job_is_running():
    err = asyncio.run(_reject_if_job_running(_FakeClient(RUNNING_JOB)))
    assert err is not None
    assert err["error"] == "job_already_running"
    # The message must name the running job so the agent can tell the user what
    # it is, instead of silently retrying or inventing an explanation.
    assert "602" in err["message"]
    assert "output" in err["message"]
    assert err["current_job"]["progress"] == 53


def test_allows_when_idle():
    for payload in (
        {"is_active": False, "status": "complete"},
        {"is_active": False, "status": "ready"},
    ):
        assert asyncio.run(_reject_if_job_running(_FakeClient(payload))) is None


def test_fails_open_when_backend_unreachable():
    """
    The critical case. "I could not reach the backend" is NOT "a job is running".
    A guard that blocks on its own ignorance would make every sort impossible the
    moment the status endpoint hiccups — the same failure mode that once blocked
    People sorts and destination folders.
    """
    for boom in (ConnectionError("refused"), ValueError("not json")):
        assert asyncio.run(_reject_if_job_running(_FakeClient(raises=boom))) is None


def test_fails_open_on_unrecognized_payload():
    for payload in (None, "unexpected", [], {}):
        assert asyncio.run(_reject_if_job_running(_FakeClient(payload))) is None


def test_wait_hands_back_instead_of_blocking():
    """A job that outlives timeout_s must return a reportable status, not hang."""
    result = asyncio.run(_wait_for_completion(_FakeClient(RUNNING_JOB), 0, 0.5))
    assert result["status"] == "still_running"
    assert "STOP" in result["guidance"]


def test_default_wait_stays_under_client_cancel():
    """
    Claude Desktop cancels a tool call at ~240s. A default above that is dead code:
    the wait is always thrown away and the model falls back to manual polling.
    """
    assert _DEFAULT_WAIT_S < 240
