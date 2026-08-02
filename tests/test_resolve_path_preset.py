"""
Tests for resolve_path_preset — accepting a saved preset NAME wherever a source
folder path is expected.

Why this exists in code and not only in prose: the rule telling the assistant to
call get_path_presets lived in the server `instructions` blob, past the point
where the client truncates it (see tests/test_claude_instructions.py). The
assistant therefore told the user "I don't have a way to look up which folder
path that preset points to" while the tool sat unused in its list. The prose was
fixed too, but this path holds even when no prose survives the trip.

No pytest-asyncio here — the project ships bare pytest, so coroutines are driven
with asyncio.run() the same way tests/test_claude_instructions.py does it.

Run with:
    python -m pytest tests/test_resolve_path_preset.py -v
"""

import asyncio
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools import queries  # noqa: E402
from mcp_server.tools.queries import resolve_path_preset  # noqa: E402


_PRESETS = {
    "Bot testing": {
        "source": "/Users/someone/Git/Bot testing/test",
        "destination": "/Users/someone/Git/Bot testing/output",
    },
    "New test": {
        "source": "/Users/someone/Mayank/Images",
        "destination": "/Users/someone/Mayank/test",
    },
}


def _resolve(value, side="source"):
    return asyncio.run(resolve_path_preset(value, side))


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient: one GET returning `payload`."""

    def __init__(self, payload, boom=False):
        self._payload, self._boom = payload, boom

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, timeout=None):
        if self._boom:
            raise RuntimeError("backend unreachable")
        payload = self._payload

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        return _Resp()


@pytest.fixture
def presets(monkeypatch):
    """Serve _PRESETS from the backend, unless a test asks for something else."""

    def _install(payload=_PRESETS, boom=False):
        fake = type(
            "_httpx",
            (),
            {"AsyncClient": staticmethod(lambda *a, **k: _FakeClient(payload, boom))},
        )
        monkeypatch.setattr(queries, "httpx", fake)

    _install()
    return _install


def test_real_directory_wins(tmp_path, presets):
    """A path that exists is used as-is — presets never shadow a real folder."""
    presets({"tmp": {"source": "/somewhere/else"}})
    got = _resolve(str(tmp_path))
    assert got["path"] == str(tmp_path)
    assert "resolved_from_preset" not in got


def test_preset_name_resolves_to_its_source(presets):
    """The reported bug: "Bot testing" is a name, not a path. Turn it into one."""
    got = _resolve("Bot testing")
    assert got["path"] == "/Users/someone/Git/Bot testing/test"
    assert got["resolved_from_preset"] == "Bot testing"


def test_preset_name_is_case_and_space_insensitive(presets):
    """Users type "bot testing"; the preset is saved as "Bot testing"."""
    assert _resolve("  bot TESTING ")["path"] == "/Users/someone/Git/Bot testing/test"


def test_destination_side_is_selectable(presets):
    got = _resolve("Bot testing", "destination")
    assert got["path"] == "/Users/someone/Git/Bot testing/output"


def test_unknown_name_lists_the_real_ones(presets):
    """
    The error is the teaching moment: an assistant that guessed a name gets the
    actual names back, so its next call can be right instead of a re-ask.
    """
    got = _resolve("holiday snaps")
    assert "path" not in got
    assert '"Bot testing"' in got["error"]
    assert '"New test"' in got["error"]
    assert "do not guess" in got["error"].lower()


def test_backend_down_reports_the_path_not_the_presets(presets):
    """Don't blame presets for an unrelated outage — the path is still the problem."""
    presets(boom=True)
    got = _resolve("/no/such/folder")
    assert "path" not in got
    assert "not an existing folder" in got["error"]


def test_empty_input_is_an_error_not_a_lookup(presets):
    assert "path" not in _resolve("")
