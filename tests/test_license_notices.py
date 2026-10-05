"""
Guards for what every reader of this public repo is told — people and AI coding
agents alike — and for the product name.

- The BSL 1.1 terms must be unmissable: a root AGENTS.md (the file Codex, Cursor,
  Copilot's agent, Gemini CLI and others load), imported by CLAUDE.md for Claude
  Code, an SPDX header on every source file, and a LICENSE grant that names the
  line a fork may not cross.
- The product is "LL Agent" / "LL Agent Pro"; "LocalLens" is the separate photo
  app. And the lost locallens.app domain must not come back in any file — the
  older guard in test_claude_instructions.py only scans the server's prose, which
  is how smithery.yaml kept pointing at it.

Run with:
    python -m pytest tests/test_license_notices.py -v
"""
import re
import subprocess
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
_SPDX = "SPDX-License-Identifier: BUSL-1.1"


def _repo_files():
    """Tracked plus new (not ignored) files — a file added today is covered too."""
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [_ROOT / p for p in out.splitlines() if (_ROOT / p).is_file()]


def _text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


# History is left as it was published; tests and the release-agent incident notes
# name the banned strings in order to ban them.
_HISTORY = re.compile(r"^(release_notes/release_notes_v[\d.]+\.md|version\.json|\.github/workflows/.*"
                      r"|tests/.*|\.claude/skills/release-agent/RELEASE_MEMORY\.md)$")


def _scanned():
    for path in _repo_files():
        rel = path.relative_to(_ROOT).as_posix()
        text = None if _HISTORY.match(rel) else _text(path)
        if text is not None:
            yield rel, text


def test_no_file_links_the_lost_domain():
    hits = [f"{rel}:{n}" for rel, text in _scanned()
            for n, line in enumerate(text.splitlines(), 1)
            if re.search(r"https?://(www\.)?locallens\.app\b", line, re.I)]
    assert not hits, "locallens.app is no longer ours — use locallensmcp.vercel.app:\n  " + "\n  ".join(hits)


def test_the_paid_tier_is_never_called_localLens_pro():
    hits = [f"{rel}:{n}" for rel, text in _scanned()
            for n, line in enumerate(text.splitlines(), 1)
            if re.search(r"\blocal ?lens pro\b", line, re.I)]
    assert not hits, "The paid tier is \"LL Agent Pro\":\n  " + "\n  ".join(hits)


# ── License notices ─────────────────────────────────────────────────────────


def _source_files():
    for path in _repo_files():
        rel = path.relative_to(_ROOT).as_posix()
        if rel.endswith(".py") and (rel.startswith(("src/", "scripts/")) or "/" not in rel):
            yield rel, path


def test_every_source_file_carries_the_spdx_header():
    missing = [rel for rel, path in _source_files()
               if _SPDX not in "\n".join(path.read_text(encoding="utf-8").splitlines()[:4])]
    assert not missing, f"add '# {_SPDX}' to the top of:\n  " + "\n  ".join(missing)


def test_activate_window_page_carries_the_spdx_header():
    head = (_ROOT / "src/tray/activate_window.html").read_text(encoding="utf-8")[:400]
    assert _SPDX in head


def test_root_agents_md_tells_ai_agents_the_licence_line():
    agents = _ROOT / "AGENTS.md"
    assert agents.is_file(), "AI coding agents load AGENTS.md from the repo root"
    text = agents.read_text(encoding="utf-8")
    assert "BUSL-1.1" in text and "LICENSE.md" in text
    # The enforcement points an agent must not help strip, by their real names.
    for symbol in ("@require_pro", "is_pro_active", "activate_license", "FREE_PREVIEW"):
        assert symbol in text, symbol


def test_claude_md_imports_agents_md():
    # Claude Code reads CLAUDE.md, not AGENTS.md; the import keeps one source.
    first = (_ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[:5]
    assert "@AGENTS.md" in first


def test_licence_grant_forbids_circumventing_the_key_check():
    grant = (_ROOT / "LICENSE.md").read_text(encoding="utf-8").split("Change Date:")[0]
    assert re.search(r"circumvent", grant, re.I)
    # Production use of the Free tier must be granted in so many words, or
    # strictly only non-production use is licensed.
    assert re.search(r"Free-tier features in production", grant)
    # The personal-use loophole is closed: Pro on real photos is production use.
    assert re.search(r"personal or commercial", grant)


def test_mcp_server_states_the_licence_on_stderr_only(monkeypatch, capsys):
    # Anyone running a downloaded or forked copy sees the terms in the MCP log.
    # stdout is the JSON-RPC channel, so not one byte may land there.
    import sys
    sys.path.insert(0, str(_ROOT / "src"))
    from mcp_server import main as server_main
    monkeypatch.setattr(sys, "argv", ["locallens-mcp"])
    monkeypatch.setattr(server_main, "create_mcp_app", lambda: type("A", (), {"run": lambda self: None})())
    server_main.main()
    out, err = capsys.readouterr()
    assert out == ""
    assert "Business Source License 1.1" in err and "LL Agent" in err


def test_tray_help_names_the_licence():
    # People who only download the app read the tray's Help, not the repo.
    import sys
    sys.path.insert(0, str(_ROOT / "src"))
    from tray.actions import _HELP_TEXT
    assert "Business Source License 1.1" in _HELP_TEXT
    assert "locallensmcp.vercel.app/license" in _HELP_TEXT
