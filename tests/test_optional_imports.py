"""
Tests for scripts/check_optional_imports.py

The gate exists because LocalLens shipped `find_duplicates` broken in every build for
months: `import imagehash` sat inside an endpoint body against a package no requirements
file declared. Four layers all reported green — PyInstaller only warns about unresolved
imports and never sees a deferred one; the CI smoke test walks the startup graph, which a
function-level import is not in; pytest mocks the backend; and the maintainer's dev venv
happened to have the package. It was only ever missing for users.

Run with:
    cd locallens_mcp_agent
    python -m pytest tests/test_optional_imports.py -v
"""

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from check_optional_imports import audit, declared_packages  # noqa: E402


# ── The gate itself ─────────────────────────────────────────────────────────


def test_this_repo_declares_every_import():
    """The actual release gate. A failure here names the undeclared package."""
    problems = audit(_ROOT / "src", [_ROOT / "pyproject.toml"])
    assert not problems, "undeclared imports:\n  " + "\n  ".join(problems)


def test_runs_as_a_cli_and_exits_zero():
    """preflight_release.py shells out to it, so the exit code is load-bearing."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPTS / "check_optional_imports.py")],
        cwd=_ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ── Dependency parsing ──────────────────────────────────────────────────────


def test_environment_markers_do_not_shred_the_dependency_list(tmp_path):
    """
    The bug this script hit on its own first run. A naive ["']([^"']+)["'] stops at the
    apostrophes inside "rumps>=0.4.0; sys_platform == 'darwin'" and mangles everything
    after it — which made the script report pystray as undeclared when it was declared
    on the very next line.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        'dependencies = ["httpx>=0.24.0"]\n'
        "[project.optional-dependencies]\n"
        'tray = [\n'
        '    "psutil>=5.9.0",\n'
        "    \"rumps>=0.4.0; sys_platform == 'darwin'\",\n"
        "    \"pystray>=0.19.0; sys_platform == 'win32'\",\n"
        "]\n",
        encoding="utf-8",
    )
    assert declared_packages([pyproject]) == {"httpx", "psutil", "rumps", "pystray"}


def test_requirements_txt_strips_versions_markers_and_comments(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text(
        "fastapi\n"
        "numpy>=1.26.4,<2\n"
        "rawpy; sys_platform == 'win32'\n"
        "# a comment\n"
        "Pillow  # trailing comment\n"
        "-r other.txt\n"
        "\n",
        encoding="utf-8",
    )
    assert declared_packages([req]) == {"fastapi", "numpy", "rawpy", "pillow"}


# ── Detection ───────────────────────────────────────────────────────────────


def _fixture(tmp_path, source_code, requirements="fastapi\n"):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(source_code, encoding="utf-8")
    req = tmp_path / "requirements.txt"
    req.write_text(requirements, encoding="utf-8")
    return src, [req]


def test_catches_the_imagehash_shape(tmp_path):
    """A deferred import inside a function — invisible to every other layer."""
    src, reqs = _fixture(tmp_path, (
        "def find_duplicates():\n"
        "    try:\n"
        "        import imagehash\n"
        "    except ImportError:\n"
        "        raise RuntimeError('not installed')\n"
    ))
    problems = audit(src, reqs)
    assert len(problems) == 1
    assert "imagehash" in problems[0]
    assert "deferred inside find_duplicates()" in problems[0]


def test_catches_a_module_level_undeclared_import(tmp_path):
    src, reqs = _fixture(tmp_path, "from reportlab.pdfgen import canvas\n")
    assert any("reportlab" in p for p in audit(src, reqs))


def test_declared_imports_pass(tmp_path):
    src, reqs = _fixture(tmp_path, "import fastapi\n")
    assert audit(src, reqs) == []


def test_stdlib_is_never_flagged(tmp_path):
    src, reqs = _fixture(tmp_path, "import os, sys, json, sqlite3\nimport winreg\n")
    assert audit(src, reqs) == []


def test_acknowledged_modules_are_skipped(tmp_path):
    """
    The transitive-dependency escape hatch: fastapi requires starlette, so importing
    starlette works even though no file names it. This check reads dependency files,
    not an installed environment, so it cannot resolve that on its own.
    """
    src, reqs = _fixture(tmp_path, "from starlette.responses import JSONResponse\n")
    assert any("starlette" in p for p in audit(src, reqs))
    assert audit(src, reqs, acknowledged={"starlette"}) == []


def test_findings_are_grouped_one_line_per_module(tmp_path):
    """Five `from reportlab.x import y` lines are one missing package, not five."""
    src, reqs = _fixture(tmp_path, (
        "from reportlab.pdfgen import canvas\n"
        "from reportlab.lib import colors\n"
        "from reportlab.platypus import Table\n"
    ))
    problems = audit(src, reqs)
    assert len(problems) == 1
    assert "+1 more" in problems[0]
