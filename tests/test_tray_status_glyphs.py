"""
Tests for the tray status indicators in src/tray/actions.py

These guard a rendering bug, not a style preference. The indicators used to be
astral-plane emoji (🔴 U+1F534, 🟡 U+1F7E1, 🟢 U+1F7E2, 🔵 U+1F535), which live
only in Segoe UI Emoji. Win32 MessageBoxW and the pystray Win32 menus draw
through GDI, which does no color-emoji fallback — so all four collapsed to the
same gray disc and the status legend became unreadable on Windows.

Run with:
    cd locallens_mcp_agent
    python -m pytest tests/test_tray_status_glyphs.py -v
"""

import sys
from pathlib import Path

# Make sure the src directory is on sys.path for direct test runs
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# tray.actions imports cleanly without pystray/rumps, so this runs on any
# platform in CI — unlike tray_win/tray_mac, which need their tray backend.
from tray.actions import (  # noqa: E402
    STATUS_OFF, STATUS_STARTING, STATUS_ON, STATUS_EXTERNAL, STATUS_ALERT,
    _HELP_TEXT,
)

GLYPHS = {
    "STATUS_OFF": STATUS_OFF,
    "STATUS_STARTING": STATUS_STARTING,
    "STATUS_ON": STATUS_ON,
    "STATUS_EXTERNAL": STATUS_EXTERNAL,
    "STATUS_ALERT": STATUS_ALERT,
}


def test_glyphs_are_distinct():
    """Every state must be visually separable — no two share a glyph."""
    assert len(set(GLYPHS.values())) == len(GLYPHS), (
        f"Duplicate status glyph: {GLYPHS}"
    )


def test_glyphs_are_single_characters():
    """Multi-codepoint sequences (emoji + variation selector / ZWJ) break
    alignment in fixed-layout Win32 dialogs."""
    for name, glyph in GLYPHS.items():
        assert len(glyph) == 1, f"{name} is {len(glyph)} codepoints, expected 1"


def test_glyphs_are_not_emoji():
    """The actual regression guard.

    The whole 🔴🟡🟢🔵 family lives above the Basic Multilingual Plane
    (U+1F534 etc.). Requiring BMP fails the moment anyone reintroduces one.
    """
    for name, glyph in GLYPHS.items():
        assert ord(glyph) < 0x10000, (
            f"{name} = {glyph!r} (U+{ord(glyph):04X}) is an astral-plane "
            "character. Win32 GDI has no color-emoji fallback and will render "
            "it as an indistinguishable gray disc — use a Geometric Shapes "
            "glyph (U+25xx) instead."
        )


def test_help_text_documents_every_state():
    """The Help & Getting Started legend must explain all five indicators —
    an undocumented glyph is exactly how 'Connection Error' stayed invisible."""
    for name, glyph in GLYPHS.items():
        assert glyph in _HELP_TEXT, f"{name} ({glyph}) is missing from _HELP_TEXT"


def test_help_text_has_no_emoji():
    """The legend is rendered by the same GDI dialog as the indicators, so it
    must be free of astral-plane characters too."""
    offenders = [(i, c) for i, c in enumerate(_HELP_TEXT) if ord(c) >= 0x10000]
    assert not offenders, (
        f"_HELP_TEXT contains astral-plane characters at {offenders}"
    )
