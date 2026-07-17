# Project: LocalLens MCP Agent

> MCP server that bridges AI assistants (Claude Desktop, Cursor, etc.) to the LocalLens privacy-first photo organizer. Speaks stdio JSON-RPC to the AI client, HTTP to the LocalLens FastAPI backend on localhost.

## Commands

```bash
# Dev install (editable)
pip install -e .                    # core only
pip install -e ".[dev]"             # + pytest, pyinstaller
pip install -e ".[chat]"           # + gradio, ollama (Chat UI)
pip install -e ".[tray]"           # + rumps/pystray, psutil, Pillow

# Run MCP server (stdio — Claude Desktop manages this normally)
locallens-mcp

# Claude Desktop connector
locallens-mcp --setup-claude       # inject into Claude config
locallens-mcp --claude-status      # print connection JSON
locallens-mcp --remove-claude      # remove from Claude config

# Chat UI (Gradio + Ollama, separate from MCP)
locallens-chat                     # or: python src/chat_ui.py

# Tests
python -m pytest tests/ -v

# Build frozen binary (macOS)
pyinstaller locallens-mcp.spec
# or: bash build_tray_mac.sh

# Lint — no linter configured yet; just pytest
```

## Architecture (Critical)

```
LocalLens Desktop App (FastAPI)    ← Process 1, writes port to ~/.config/LocalLens/port.txt
        ↑ HTTP (httpx)
MCP Server (locallens-mcp)         ← Process 2, stdio JSON-RPC to Claude Desktop
        ↑ stdio
Claude Desktop / MCP client

Chat UI (locallens-chat)           ← Process 3, separate Gradio app, calls backend HTTP directly
        ↑ HTTP
Ollama (local LLM)                 ← Process 4, only needed for Chat UI
```

- MCP Server and Chat UI are **completely independent** paths to the same backend.
- The MCP server NEVER makes outbound internet calls except one-time license activation.
- **stdout is sacred** — it carries the MCP JSON-RPC channel. ALL logging MUST go to stderr.

## Structure

```
src/
  mcp_server/                  # The MCP server package
    main.py                    # Entrypoint, CLI arg parsing, creates FastMCP app
    config.py                  # Dynamic port discovery, auth token reader
    license.py                 # Pro tier activation, @require_pro decorator, local cache
    updater.py                 # Version check against locallens.app/version.json
    claude_connector.py        # Programmatic Claude Desktop config injection (771 lines)
    tools/
      __init__.py
      status.py                # check_app_status, get_stats, get_job_progress, locallens_help
      queries.py               # get_enrolled_faces, get_path_presets, analyse_folder
      actions.py               # start_sorting, start_find_group, abort_job, open_folder, remember/forget_paths
      pro_tools.py             # Pro-gated: add_face_enroll, find_duplicates, export_report, scheduler tools
  llm_connector/               # Chat UI's Ollama integration + tool registry (NOT used by MCP server)
    ollama_connector.py
    tool_registry.py           # Maps natural language → LocalLens API calls for Ollama
  tray/                        # System tray app (macOS rumps / Windows pystray)
    tray_mac.py, tray_win.py, actions.py, status.py
  chat_ui.py                   # Gradio Chat UI entrypoint

tests/
  test_claude_connector.py     # 573 lines, comprehensive unit tests for connector

locallens_mcp_entrypoint.py    # PyInstaller entrypoint (frozen binary)
locallens_tray_entrypoint.py   # PyInstaller entrypoint for tray app
```

### Don't touch
- `venv/`, `dist/`, `build/`, `.eggs/`, `*.egg-info/` — generated
- `for dev/`, `for LLM's/` — gitignored documentation artifacts, not shipped
- `icons/` — tray app icons

## Conventions

- **Python 3.10+** required (`pyproject.toml` declares `>=3.10`)
- **Async everywhere** — all MCP tool functions are `async def`, use `httpx.AsyncClient`
- **All logging → stderr** — never `print()` to stdout in the mcp_server package. Use module-level `_log = logging.getLogger(...)` with `StreamHandler(sys.stderr)` and `_log.propagate = False`
- **`FastMCP` from `mcp.server.fastmcp`** — tools registered via `@mcp.tool()` decorator
- **Tool registration is modular** — each `tools/*.py` exports a `register_*(mcp)` function called from `main.py`
- **Pro tools use `@require_pro`** decorator from `license.py` — stacked under `@mcp.tool()`
- **`_handle_error(e)` pattern** — every tool module has this helper; returns `{"error": ...}` dicts
- **Backend URL is dynamic** — always call `get_locallens_url()` (reads port.txt per-request), never hardcode port
- **Auth headers** — use `get_auth_headers()` from config.py for sensitive endpoints (persona, metadata-store)
- **Paths** — always `os.path.expanduser()` user-supplied paths before use
- **operation_mode defaults to "copy"** — never "move" unless user explicitly asks
- **primary_sort values**: exactly `"Date"`, `"Location"`, or `"People"` — auto-correct `"Faces"` → `"People"`
- **No type: ignore comments** — code uses standard typing throughout
- **Job polling** — `_wait_for_completion()` in actions.py handles stale-state guards, min 0.5s poll interval
- **Version** — bump `MCP_VERSION` in `updater.py` on every release (currently `"1.0.0"`)

## Key Environment Variables

| Variable | Purpose |
|----------|---------|
| `LOCALLENS_MCP_DEBUG=1` | Enables dev license bypass (with `LOCALLENS_DEV_KEY`) |
| `LOCALLENS_DEV_KEY` | Test license key for dev bypass |
| `LOCALLENS_STORE_URL` | Store URL shown in Pro upgrade prompts (default: `https://locallens.app`) |
| `LOCALLENS_LICENSE_URL` | Lemon Squeezy license API base URL |
| `LOCALLENS_VERSION_URL` | Version manifest URL for update checker |
| `LOCALLENS_BACKEND_DIR` | Path to LocalLens backend dir (for scheduler daemon launch) |
| `LOCALLENS_OLLAMA_MODEL` | Ollama model name for Chat UI (default: `llama3.1:8b`) |

## File Locations (Runtime)

| File | Purpose |
|------|---------|
| `~/.config/LocalLens/port.txt` | Backend's dynamic port |
| `~/.config/LocalLens/local_api_token.txt` | Auth token for sensitive API calls |
| `~/.config/LocalLens/mcp_license.json` | Pro license cache (machine-locked via SHA-256) |
| `~/.config/LocalLens/schedules.json` | Scheduler/active folder configs |
| `~/.config/LocalLens/metadata_store.db` | Smart album metadata (SQLite) |
| `~/.config/LocalLens/scheduler.pid` | Daemon PID file |
| `~/.config/LocalLens/scheduler.log` | Daemon log output |
| `~/.config/LocalLens/mcp_update_cache.json` | Update checker cache (24h TTL) |

## Gotchas

- **stdout corruption kills MCP** — any `print()` or logger writing to stdout in `src/mcp_server/` will break the JSON-RPC protocol. Always use stderr handlers.
- **Port discovery is lazy** — `get_locallens_url()` reads `port.txt` every call to handle the case where the LocalLens app starts after the MCP server. Don't cache the URL.
- **Stale job status** — `_wait_for_completion()` requires the job to transition through `is_active=True` before accepting a terminal status. Without this guard, it exits immediately on stale state from a previous job.
- **Claude connector is atomic** — uses temp-file + `os.replace()` to prevent partial config corruption. Always preserve other mcpServers entries.
- **Claude connector backs up** — creates timestamped backups before writes, capped at 5. Never skip this.
- **License machine lock** — `mcp_license.json` contains a `machine_id` (SHA-256 of hostname + MAC). Copying the file to another machine won't work.
- **`analyse_folder` does a local filesystem scan + backend HTTP call** — it's a hybrid tool. The subfolder scan is local (os.scandir), metadata overview comes from the backend.
- **`add_face_enroll` accepts a dict, not a list** — the enrollments param is `{"Person Name": "/path/to/folder"}`. There's a guard for double-nested `enrollments.enrollments` from LLM copy-paste bugs.
- **`find_duplicates` timeout is 120s** — large folders can take a while to hash. Don't reduce this.
- **Scheduler daemon is separate** — `scheduler_daemon.py` lives in the backend repo, not here. This repo only calls its API endpoints. `_launch_daemon_silent()` spawns it detached.
- **`locallens-mcp.spec`** — PyInstaller spec bundles `src/` into the frozen binary. The entrypoint is `locallens_mcp_entrypoint.py`, not `main.py` directly.
- **Test key bypass** — requires BOTH `LOCALLENS_MCP_DEBUG=1` AND `LOCALLENS_DEV_KEY` set. The key must match `license_key` passed to `activate_pro_license`.
- **CI uses Python 3.11** — but codebase supports 3.10+. The GitHub Actions workflows run `pip install .[dev]` then `pytest tests/ -v`.
- **Release workflow** — triggered by `v*.*.*` tags. Builds cross-platform binaries via PyInstaller and uploads to GitHub Releases.

## Tool Inventory (MCP)

### Free
`check_app_status` · `get_stats` · `get_job_progress` · `locallens_help` · `get_enrolled_faces` · `get_path_presets` · `analyse_folder` · `start_sorting` · `abort_job` · `open_folder` · `remember_paths` · `forget_paths` · `activate_pro_license` · `get_license_status` · `revoke_pro_license`

### Pro (gated by `@require_pro`)
`start_find_group` · `add_face_enroll` · `find_duplicates` · `delete_duplicates` · `export_report` · `create_active_folder` · `schedule_auto_organize` · `list_schedules` · `manage_schedule` · `open_scheduler_dashboard` · `smart_album_suggestions`
