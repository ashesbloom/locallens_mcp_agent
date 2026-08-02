"""
Tests for the scheduler daemon startup + guidance contract in
src/mcp_server/tools/pro_tools.py

The bug these guard: a schedule was created, the daemon silently failed to start,
and the guidance text still told the assistant "the daemon will sweep every 2h".
A saved schedule with a dead daemon organizes nothing.

Run with:
    cd locallens_mcp_agent
    python -m pytest tests/test_daemon_guidance.py -v
"""

import asyncio
import signal
import sys
from pathlib import Path

# Make sure the src directory is on sys.path for direct test runs
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools import pro_tools
from mcp_server.tools.pro_tools import (
    _ensure_daemon,
    _schedule_guidance,
    _scheduler_next_actions,
    _stop_daemon,
)

ACTIVE_LINE = "Schedule created (sched_abc)! The daemon will sweep every 2h 0m."


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _RecordingClient:
    """Stand-in for httpx.AsyncClient that records every request it is given."""

    requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        _RecordingClient.requests.append(("GET", url))
        return _FakeResponse({"daemon_running": False, "daemon_pid": None})

    async def post(self, url, **kwargs):
        _RecordingClient.requests.append(("POST", url))
        return _FakeResponse({"status": "dispatched"})


def test_guidance_keeps_active_claim_when_daemon_verified_running():
    text = _schedule_guidance(
        "sched_abc", {"daemon_running": True, "detail": "already running"}, ACTIVE_LINE
    )
    assert ACTIVE_LINE in text
    assert "dashboard" in text.lower()


def test_guidance_never_claims_sweeps_when_daemon_is_dead():
    text = _schedule_guidance(
        "sched_abc",
        {"daemon_running": False, "detail": "scheduler_daemon.py not present at /bundle"},
        ACTIVE_LINE,
    )
    # The whole point: the optimistic sentence must be gone.
    assert "will sweep" not in text
    assert "NOT being monitored" in text
    assert "start_daemon" in text
    # The real reason must reach the user, not just a diagnostic key.
    assert "scheduler_daemon.py not present at /bundle" in text
    assert "dashboard" in text.lower()


def test_next_actions_offers_the_dashboard():
    actions = _scheduler_next_actions("http://127.0.0.1:8000", "/tmp/out")
    names = [a["action"] for a in actions]
    assert "open_scheduler_dashboard" in names
    dash = next(a for a in actions if a["action"] == "open_scheduler_dashboard")
    assert "http://127.0.0.1:8000/scheduler-ui" in dash["hint"]


def test_ensure_daemon_reports_false_when_nothing_can_start_it(monkeypatch):
    """A bare spawn must never be reported as success."""
    spawned = []

    async def never_alive(url):
        return False

    def fake_spawn():
        spawned.append(True)
        return "backend directory not found"

    monkeypatch.setattr(pro_tools, "_daemon_is_running", never_alive)
    monkeypatch.setattr(pro_tools, "_launch_daemon_script", fake_spawn)

    result = asyncio.run(_ensure_daemon("http://127.0.0.1:8000", cap_s=0.0))
    assert result["daemon_running"] is False
    assert spawned, "local launch fallback should have been attempted"
    assert "backend directory not found" in result["detail"]


def test_ensure_daemon_skips_launching_when_already_alive(monkeypatch):
    spawned = []

    async def alive(url):
        return True

    monkeypatch.setattr(pro_tools, "_daemon_is_running", alive)
    monkeypatch.setattr(pro_tools, "_launch_daemon_script", lambda: spawned.append(True))

    result = asyncio.run(_ensure_daemon("http://127.0.0.1:8000", cap_s=0.0))
    assert result["daemon_running"] is True
    assert not spawned, "must not spawn a second daemon when one is already running"


def test_ensure_daemon_never_posts_to_daemon_command(monkeypatch):
    """
    The daemon must never be started via POST /api/scheduler/daemon-command.

    That endpoint Popens [sys.executable, "scheduler_daemon.py", "start"], and in a
    packaged install sys.executable IS the backend binary — so it boots a second full
    backend, which overwrites port.txt and makes the next call spawn yet another.
    Observed live: 5 backend servers, port.txt hijacked to a clone's port.
    """
    _RecordingClient.requests = []
    monkeypatch.setattr(pro_tools.httpx, "AsyncClient", _RecordingClient)
    monkeypatch.setattr(pro_tools, "_launch_daemon_script", lambda: "no backend dir")

    result = asyncio.run(_ensure_daemon("http://127.0.0.1:8000", cap_s=0.0))

    assert result["daemon_running"] is False
    posts = [url for method, url in _RecordingClient.requests if method == "POST"]
    assert posts == [], f"must issue no POSTs; got {posts}"


def test_stop_daemon_signals_the_pid_and_never_posts(monkeypatch, tmp_path):
    """Stopping goes through the PID file, not the clone-spawning endpoint."""
    (tmp_path / "scheduler.pid").write_text("4242")
    killed = []

    _RecordingClient.requests = []
    monkeypatch.setattr(pro_tools.httpx, "AsyncClient", _RecordingClient)
    monkeypatch.setattr(pro_tools, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(pro_tools.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    result = asyncio.run(_stop_daemon("http://127.0.0.1:8000", cap_s=0.0))

    assert killed == [(4242, signal.SIGTERM)]
    assert result["daemon_running"] is False
    posts = [url for method, url in _RecordingClient.requests if method == "POST"]
    assert posts == [], f"must issue no POSTs; got {posts}"


def test_stop_daemon_without_pid_file_reports_not_running(monkeypatch, tmp_path):
    killed = []
    monkeypatch.setattr(pro_tools, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(pro_tools.os, "kill", lambda pid, sig: killed.append(pid))

    result = asyncio.run(_stop_daemon("http://127.0.0.1:8000", cap_s=0.0))
    assert not killed, "no pid file means there is nothing to signal"
    assert result["daemon_running"] is False
    assert "not running" in result["note"].lower()
