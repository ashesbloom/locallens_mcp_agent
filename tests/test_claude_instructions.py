"""
Tests for the prose this project ships to Claude: the copyable custom-instructions
payload in src/tray/actions.py, the FastMCP server `instructions`, and every tool
description.

Two real bugs are guarded here, both of which shipped:

1. Mojibake. The payload is piped to pbcopy/clip, which decode stdin using the
   platform locale rather than UTF-8. An em dash (U+2014) in the text arrived as
   "‚Äî" on macOS (MacRoman) and "ΓÇö" on Windows (CP437/850). Keeping the
   payload ASCII makes it immune regardless of what the clipboard tool assumes.

2. Connector quarantine. The payload used to contain
   'NEVER say "I can't access your files"'. Text instructing the assistant never
   to decline reads as a context-override attempt, and Claude Desktop responded
   by excluding the LocalLens connector entirely — tools stopped being offered.

Run with:
    cd locallens_mcp_agent
    python -m pytest tests/test_claude_instructions.py -v
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tray.actions import CLAUDE_CUSTOM_INSTRUCTIONS  # noqa: E402


def test_payload_is_ascii():
    """Non-ASCII survives neither pbcopy nor clip reliably. Keep it out."""
    offenders = sorted({c for c in CLAUDE_CUSTOM_INSTRUCTIONS if not c.isascii()})
    assert not offenders, (
        f"non-ASCII in clipboard payload: {offenders!r} — these become mojibake "
        f"on macOS and Windows. Use '-' and '->' instead of dashes and arrows."
    )


def test_payload_does_not_suppress_refusals():
    """Telling the assistant it may never decline gets the connector quarantined."""
    lowered = CLAUDE_CUSTOM_INSTRUCTIONS.lower()
    for banned in ("never say", "can't access your files", "cannot say"):
        assert banned not in lowered, (
            f"{banned!r} in the instructions payload reads as a context-override "
            f"attempt; Claude Desktop excludes the connector when it sees this."
        )


def test_payload_routes_between_local_and_cloud():
    """The payload's job is telling Claude when LocalLens applies and when it doesn't."""
    assert "LocalLens" in CLAUDE_CUSTOM_INSTRUCTIONS
    assert "cannot see" in CLAUDE_CUSTOM_INSTRUCTIONS, (
        "payload should state what LocalLens can't reach, so Claude routes "
        "off-machine work to the web/cloud tools instead"
    )


def test_payload_works_under_deferred_tool_loading():
    """
    With Claude Desktop set to "Load tools when needed", the connector's tools are
    not in context — only the profile text is. So the payload has to (a) teach the
    "LL" shorthand the user actually types and (b) say to load the tools.
    """
    assert '"LL"' in CLAUDE_CUSTOM_INSTRUCTIONS, (
        'payload must define the "LL" shorthand; without it a prompt like '
        '"is ll running" matches nothing and the connector is never loaded'
    )
    assert "load them" in CLAUDE_CUSTOM_INSTRUCTIONS, (
        "payload must tell Claude to load the connector's tools when they "
        "are not already loaded"
    )


# ── The server's own prose ──────────────────────────────────────────────────
#
# Bug 2 above shipped TWICE. Commit 4caf5c7 removed the capability-assertion
# sentence from the tray payload and the server instructions, but patched only
# main.py, pro_tools.py and status.py — so it survived in the start_sorting and
# analyse_folder docstrings, the two largest tool descriptions the client
# receives. It kept coming back because these tests only ever read the tray
# payload. The checks below read what the MCP client actually gets.
#
# Deliberately narrow: capability assertions ("you have full access") and speech
# prohibitions ("never say X") only. Emphatic rules about tool USE — "NEVER
# invent destination paths", "NEVER use move" — are load-bearing safety text
# pinned by docs/TESTING.md Tests 2, 8 and 9, and must NOT be caught here.

_OVERRIDE_PHRASES = (
    "full access",
    "do not say",
    "don't say",
    "never say",
    "cannot access",
    "can't access",
    "you have filesystem access",
    "do not tell the user",
    "never tell the user",
)


def _server_prose():
    """Every string the MCP client receives: server instructions + tool descriptions."""
    import asyncio

    from mcp_server.main import create_mcp_app

    app = create_mcp_app()
    tools = asyncio.run(app.list_tools())
    prose = [("server instructions", app.instructions or "")]
    prose += [(f"{t.name} description", t.description or "") for t in tools]
    return prose


_SERVER_PROSE = _server_prose()


@pytest.mark.parametrize(
    "label,text", _SERVER_PROSE, ids=[label for label, _ in _SERVER_PROSE]
)
def test_server_prose_does_not_assert_capabilities(label, text):
    """
    No shipped string may assert what the assistant can do, or forbid it from
    saying something. State the capability as a fact about LocalLens instead:
    "the sort runs on the user's own machine, so there is no upload step".
    """
    lowered = text.lower()
    for phrase in _OVERRIDE_PHRASES:
        assert phrase not in lowered, (
            f"{label} contains {phrase!r}. Text that asserts the assistant's "
            f"capabilities, or forbids it from saying something, reads as a "
            f"context-override attempt; Claude Desktop excludes the connector when "
            f"it sees this (see commit 4caf5c7)."
        )


# ── The instructions blob is truncated in transit ───────────────────────────
#
# Bug 3, and the reason the two below exist. The server `instructions` string
# had grown to 5054 chars. A Claude client delivered only the first 2725 and cut
# mid-word, at:
#
#     - primary_sort must be "Date", "Location", or "People" — NEVER
#
# Everything after that — the whole scheduler section, the delete-duplicates
# safety workflow, the People-sort guard — silently never arrived. Nothing
# errored; the rules just stopped being in effect. The user-visible symptom was
# the assistant saying "I don't have a way to look up which folder path that
# preset points to" while get_path_presets sat in its tool list, because the
# rule telling it to call that tool was in the dropped 46%.
#
# Tool descriptions ship per-tool and are NOT subject to this cap, which is why
# the fix moved per-tool rules into docstrings and left only cross-tool
# invariants + routing here.

_OBSERVED_TRUNCATION = 2725  # chars actually delivered, measured
_BUDGET = 2400               # stay meaningfully under it
_SAFETY_HEAD = 1200          # invariants must survive an even tighter cap


def test_instructions_fit_delivery_budget():
    """Not a style rule — text past the client's cap does not reach the model."""
    app_instructions = dict(_SERVER_PROSE)["server instructions"]
    assert len(app_instructions) < _BUDGET, (
        f"server instructions are {len(app_instructions)} chars, over the {_BUDGET} "
        f"budget. A client was measured delivering only the first "
        f"{_OBSERVED_TRUNCATION} chars and cutting mid-word. Do not raise this "
        f"number — move the rule into the docstring of the tool it governs, where "
        f"it ships per-tool and is not capped."
    )


def test_safety_rules_come_before_routing():
    """
    Ordering is the real protection: whatever the cap turns out to be on some
    other client, the invariants are the part that has to survive it.
    """
    text = dict(_SERVER_PROSE)["server instructions"]
    head = text[:_SAFETY_HEAD]
    for marker in ('get_path_presets', '"copy"', '"Faces"', "job_already_running"):
        assert marker in head, (
            f"{marker!r} is not in the first {_SAFETY_HEAD} chars of the server "
            f"instructions (found at offset {text.find(marker)}). Safety rules go "
            f"first, routing after, so truncation eats routing rather than guardrails."
        )


def test_scheduler_tools_resolve_preset_names():
    """
    The regression from the reported transcript: the user said "use bot testing
    presets" and the assistant asked for a path instead, twice. Whatever else
    moves, the tools that take a source folder must say — in their own
    description, not the truncatable blob — that a named folder means
    get_path_presets.
    """
    prose = dict(_SERVER_PROSE)
    for tool in ("schedule_auto_organize", "create_active_folder"):
        assert "get_path_presets" in prose[f"{tool} description"], (
            f"{tool} does not mention get_path_presets. When the user names a "
            f"preset instead of typing a path, this is the only place that rule "
            f"is guaranteed to reach the model."
        )

    presets_doc = prose["get_path_presets description"].lower()
    for cue in ("name", "bot testing"):
        assert cue in presets_doc, (
            f"get_path_presets description does not mention {cue!r}. Its old "
            f"200-char description never said presets are addressed by NAME, so "
            f"nothing connected the user's words to this tool."
        )
