"""
Tests for the copyable Claude custom-instructions payload in src/tray/actions.py

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
