"""
Tests for the Windows notification-area icon in src/tray/tray_win.py

The tray used to load icons/ll_black/32x32.png — a dark logo that disappeared
against a dark taskbar. It now draws the "LL" wordmark in ink chosen from the
taskbar theme, matching the macOS menu bar.

These tests measure contrast at 16 px, the size the notification area actually
renders, because that is where the failure modes live: an inverted theme branch
makes the icon invisible, and an outline thick enough to look safe at 64 px
becomes a halo that swallows the letters once it is scaled down.

Run with:
    cd locallens_mcp_agent
    python -m pytest tests/test_tray_icon.py -v
"""

import sys
import types
from pathlib import Path

import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# pystray is win32-only (see pyproject [tray]), so it never installs on a Linux
# CI runner. The icon rendering is pure Pillow and never touches it — stub it
# out so this module imports anywhere.
sys.modules.setdefault("pystray", types.ModuleType("pystray")).Icon = object

pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from tray.tray_win import _render_ll_icon  # noqa: E402

TRAY_PX = 16  # notification area at 100% DPI

# Sampled from the Windows 11 shell.
DARK_TASKBAR = (32, 32, 32)
LIGHT_TASKBAR = (243, 243, 243)
ACCENT_TASKBAR = (0, 120, 215)  # "show accent colour on taskbar" — dark mode only


def _luma(px):
    return 0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2]


def _legible_pixel_count(dark_taskbar: bool, background) -> int:
    """
    How many of the 256 tray pixels stand out against `background`.

    Composites the icon at its real size rather than inspecting the 64 px
    source: downscaling is what dilutes thin strokes, so contrast measured
    before it would be measuring the wrong image.
    """
    icon = _render_ll_icon(dark_taskbar).resize((TRAY_PX, TRAY_PX), Image.LANCZOS)
    canvas = Image.new("RGB", icon.size, background)
    canvas.paste(icon, (0, 0), icon)
    return sum(1 for px in canvas.getdata() if abs(_luma(px) - _luma(background)) > 96)


@pytest.mark.parametrize(
    "dark_taskbar, background",
    [
        (True, DARK_TASKBAR),
        (False, LIGHT_TASKBAR),
        # Accent and translucent taskbars are offered only alongside dark mode,
        # so they always get the light-ink variant.
        (True, ACCENT_TASKBAR),
    ],
)
def test_icon_is_legible_on_its_taskbar(dark_taskbar, background):
    assert _legible_pixel_count(dark_taskbar, background) >= 8


def test_ink_follows_the_theme():
    """
    The regression guard: each variant must be *more* legible on its own
    taskbar than on the opposite one. Swapping the branch in _render_ll_icon
    still produces a perfectly nice icon — just an invisible one.
    """
    assert _legible_pixel_count(True, DARK_TASKBAR) > _legible_pixel_count(True, LIGHT_TASKBAR)
    assert _legible_pixel_count(False, LIGHT_TASKBAR) > _legible_pixel_count(False, DARK_TASKBAR)


@pytest.mark.parametrize("dark_taskbar", [True, False])
def test_wordmark_fills_the_icon(dark_taskbar):
    """
    Crop-and-fit should leave the glyphs nearly edge to edge whatever font the
    platform resolved. A font-loading regression falls back to a bitmap face
    that would otherwise render a few specks in the middle of the canvas.
    """
    icon = _render_ll_icon(dark_taskbar)
    left, top, right, bottom = icon.getbbox()
    # "LL" is wider than it is tall, so the fit is bounded by width — assert on
    # the long axis rather than both, or this just measures the font's aspect.
    assert max(right - left, bottom - top) >= icon.width - 6


def test_icon_background_is_transparent():
    """Tray icons composite onto the taskbar — an opaque square looks like a bug."""
    assert _render_ll_icon(dark_taskbar=True).getpixel((0, 0))[3] == 0
