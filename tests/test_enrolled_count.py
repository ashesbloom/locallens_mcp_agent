"""
Tests for _count_enrolled in src/mcp_server/tools/actions.py

Regression guard: the People-sort precheck used to read `faces`/`enrolled` from
the /api/enrolled-faces payload, but the backend emits `enrolled_faces`. The
.get() chain fell through to [] on every healthy install, so People sorts were
blocked unconditionally with "no faces are enrolled".

Run with:
    cd locallens_mcp_agent
    source venv/bin/activate
    python -m pytest tests/test_enrolled_count.py -v
"""

import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp_server.tools.actions import _count_enrolled

# Captured verbatim from a live LocalLens backend (GET /api/enrolled-faces).
LIVE_PAYLOAD = {
    "enrolled_faces": [
        {"name": "Mayank", "count": 4},
        {"name": "p", "count": 6},
        {"name": "Utkarsh Mishra", "count": 7},
        {"name": "Vidushi Pandey", "count": 6},
        {"name": "Vinayak Trivedi", "count": 6},
        {"name": "Vineeta Pandey", "count": 6},
    ]
}


def test_counts_real_backend_payload():
    assert _count_enrolled(LIVE_PAYLOAD) == 6


def test_empty_enrollment_is_zero():
    assert _count_enrolled({"enrolled_faces": []}) == 0


def test_accepts_legacy_key_shapes():
    assert _count_enrolled({"faces": [{"name": "A"}]}) == 1
    assert _count_enrolled({"enrolled": [{"name": "A"}, {"name": "B"}]}) == 2


def test_bare_list_payload():
    assert _count_enrolled([{"name": "A"}]) == 1


def test_unknown_shape_is_none_not_zero():
    """
    The critical distinction: an unrecognized payload means "we could not check",
    NOT "nobody is enrolled". Returning 0 here is what caused the original bug —
    it must never compare equal to 0 and trip the block.
    """
    for payload in ({"something_else": [1, 2]}, {}, None, "unexpected"):
        assert _count_enrolled(payload) is None
        assert _count_enrolled(payload) != 0
