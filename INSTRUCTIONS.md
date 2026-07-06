# LocalLens MCP Agent — Instructions

> **Who is this for?** Anyone setting up, running, or debugging the LocalLens AI features.
> Read this top-to-bottom the first time. After that, jump to the scenario you need.

---

## Architecture Overview — What is Running and Why

There are **3 independent processes** that need to be understood:

```
┌────────────────────────────────────────────────────────────┐
│  Process 1: LocalLens App (FastAPI backend)                │
│  • The actual photo-organizer logic                        │
│  • Exposes HTTP API on localhost:PORT (dynamic port)       │
│  • Writes its port to ~/.config/LocalLens/port.txt         │
│  • HOW TO RUN: Just open the LocalLens desktop app         │
│  • OR: cd backend && python main.py  (for dev)             │
└──────────────────────────────┬─────────────────────────────┘
                               │ HTTP (httpx)
┌──────────────────────────────▼─────────────────────────────┐
│  Process 2: MCP Server  (locallens-mcp)                    │
│  • Wraps the FastAPI endpoints as MCP tools                │
│  • Speaks stdio JSON-RPC (NOT HTTP)                        │
│  • Used by: Claude Desktop, MCP Inspector, Claude.ai app   │
│  • HOW TO RUN: Claude Desktop manages this automatically   │
│  • For testing: npx @modelcontextprotocol/inspector locallens-mcp │
│  • Direct: locallens-mcp  (after pip install -e .)         │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  Process 3: Chat UI  (locallens-chat)                      │
│  • Gradio web app — your local AI chat interface           │
│  • Calls LocalLens HTTP API directly (NO stdio, no MCP)    │
│  • Uses Ollama for LLM reasoning (local, private)          │
│  • HOW TO RUN: locallens-chat  OR  python src/chat_ui.py   │
│  • Opens browser at http://127.0.0.1:7860                  │
└──────────────────────────────┬─────────────────────────────┘
                               │ HTTP (ollama SDK)
┌──────────────────────────────▼─────────────────────────────┐
│  Process 4: Ollama  (only needed for Chat UI)              │
│  • Local LLM server                                        │
│  • HOW TO RUN: ollama serve  (usually auto-runs as daemon) │
│  • Check: ollama list                                      │
└────────────────────────────────────────────────────────────┘
```

> **KEY INSIGHT**: The MCP Server and the Chat UI are COMPLETELY SEPARATE interfaces to the
> same LocalLens backend. You do NOT need to run both. Pick the one you need:
> - Using Claude Desktop? → You only need Process 1 + Process 2 (Claude manages Process 2)
> - Using the Chat UI? → You only need Process 1 + Process 3 + Process 4



## Prerequisites

### 1. LocalLens Desktop App
The backend must be running. Either:
- Open the LocalLens desktop app (it starts the FastAPI backend automatically), OR
- For development: run the backend manually (`cd backend && source venv/bin/activate && python main.py`)

**How to verify**: `curl http://127.0.0.1:8000/api/health` should return `{"status": "ok"}`.
If port 8000 doesn't work, check `cat ~/.config/LocalLens/port.txt` for the actual port.

### 2. Python Environment (for the MCP Agent)
```bash
cd locallens_mcp_agent
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e .
```

This installs everything from `pyproject.toml`:
- `mcp` — MCP protocol library
- `httpx` — HTTP client for talking to LocalLens backend
- `gradio` — Chat UI web framework
- `ollama` — Ollama Python SDK
- `pydantic` — Data validation

### 3. Ollama (only if using Chat UI)
```bash
# Install: https://ollama.com/download
# Then pull a model (do this once):
ollama pull llama3.1:8b        # Default model, good balance
# ollama pull qwen2.5:7b       # Alternative — faster, slightly less capable
# ollama pull mistral:7b       # Alternative option

# Verify Ollama is running:
ollama list                    # Should show your downloaded models
ollama serve                   # Start if not running (usually auto-starts)
```

---

## Scenario A: I want to use Claude Desktop with LocalLens tools

**You need running**: LocalLens app (Process 1), Claude Desktop (manages Process 2 automatically)

**Setup (one-time)**:
Add this to your Claude Desktop `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "locallens": {
      "command": "/path/to/locallens_mcp_agent/venv/bin/locallens-mcp",
      "args": []
    }
  }
}
```
Replace `/path/to/` with the actual path. On macOS:
```
/Users/YOUR_USERNAME/Git/Products/locallens_mcp_agent/venv/bin/locallens-mcp
```

**Every time you want to use it**:
1. Start LocalLens app
2. Open Claude Desktop
3. That's it — Claude automatically starts the MCP server via stdio

---

## Scenario B: I want to test MCP tools with the MCP Inspector

**You need running**: LocalLens app (Process 1), MCP Inspector (manages Process 2 for you)

```bash
# Activate virtual env first
cd locallens_mcp_agent
source venv/bin/activate

# Launch the inspector (it starts locallens-mcp automatically)
npx @modelcontextprotocol/inspector locallens-mcp
```

This opens a browser UI where you can:
- See all registered tools
- Call individual tools manually with JSON parameters
- See raw tool responses

**Note**: You do NOT run `locallens-mcp` separately — the inspector manages that process.

---

## Scenario C: I want to use the Chat UI (Ollama-powered)

**You need running**: LocalLens app (Process 1), Ollama (Process 4), Chat UI (Process 3)

```bash
# Terminal 1: Make sure LocalLens is running (open the app, or:)
# cd /path/to/LocalLens && source backend/venv/bin/activate && python backend/main.py

# Terminal 2: Make sure Ollama is running
ollama serve    # If not already running as a daemon

# Terminal 3: Start the Chat UI
cd locallens_mcp_agent
source venv/bin/activate
locallens-chat
# OR: python src/chat_ui.py
```

Chat UI opens at **http://127.0.0.1:7860** in your browser.

**Environment variables** (optional):
```bash
export LOCALLENS_OLLAMA_MODEL="llama3.1:8b"    # Which model to use
export OLLAMA_HOST=""                            # Leave empty for local Ollama
export LOCALLENS_CHAT_MAX_STEPS="6"             # Max tool-call rounds per turn
export LOCALLENS_CHAT_MAX_HISTORY="40"          # Messages kept in context
```

---

## Scenario D: Development — Running and debugging everything

```bash
# 1. Start LocalLens backend (if not using the app)
cd /path/to/LocalLens
source backend/venv/bin/activate
python backend/main.py
# Watch for: "Uvicorn running on http://127.0.0.1:PORT"

# 2. Confirm backend is up
curl http://127.0.0.1:$(cat ~/.config/LocalLens/port.txt)/api/health

# 3. Run MCP server directly (test stdio startup)
cd locallens_mcp_agent
source venv/bin/activate
locallens-mcp    # It will wait for stdin — Ctrl+C to stop

# 4. Run Chat UI
locallens-chat

# 5. Enable Pro features for dev testing (bypass license check):
export LOCALLENS_MCP_DEBUG=1
# Then activate with the test key via the chat UI:
# "activate my license" → use key: TEST-PRO-KEY-1234
```

---

## Quick Reference: What to run and when

| Goal | Processes needed | Commands |
|------|-----------------|----------|
| Use Claude Desktop | LocalLens app + (auto) | Open LocalLens, open Claude |
| Test tools with Inspector | LocalLens app | `npx @modelcontextprotocol/inspector locallens-mcp` |
| Use Chat UI | LocalLens app + Ollama | `ollama serve` then `locallens-chat` |
| Debug everything | All | See Scenario D above |

---

## Troubleshooting

### "LocalLens is not running or accessible"
- Is the LocalLens app open? Start it.
- Check the port: `cat ~/.config/LocalLens/port.txt`
- Test directly: `curl http://127.0.0.1:8000/api/health`

### "ollama package not available" or Chat UI fails to start
- Is the `ollama` Python package installed? Run `pip install -e .` in the venv.
- Is the Ollama server running? Run `ollama serve` in another terminal.
- Do you have a model? Run `ollama list` — if empty, run `ollama pull llama3.1:8b`

### "Error talking to Ollama: ..."
- Make sure Ollama is running: `ollama serve`
- Check which model is configured: default is `llama3.1:8b`
- Pull the model if missing: `ollama pull llama3.1:8b`

### LLM responses are very slow
- Check which model you're running: `ollama list`
- Smaller/faster models: `ollama pull qwen2.5:7b` or `ollama pull phi3.5`
- Monitor Ollama: open Activity Monitor → check "ollama" CPU/memory
- The system prompt is ~5000 tokens — this alone costs latency on the first turn.
  Consider switching to a model with faster time-to-first-token.

### MCP Inspector can't find `locallens-mcp`
- Make sure the venv is activated: `source venv/bin/activate`
- Make sure the package is installed: `pip install -e .`
- Use the full path: `npx @modelcontextprotocol/inspector /full/path/to/venv/bin/locallens-mcp`

### Pro tools return "pro_required" in dev
```bash
export LOCALLENS_MCP_DEBUG=1
# Activate via chat UI with key: TEST-PRO-KEY-1234
```

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.config/LocalLens/port.txt` | Port the LocalLens backend is running on |
| `~/.config/LocalLens/local_api_token.txt` | Auth token for sensitive API calls |
| `~/.config/LocalLens/mcp_license.json` | Pro license cache (machine-locked) |
| `~/.config/LocalLens/schedules.json` | Auto-organize schedule configs |
| `~/.config/LocalLens/metadata_store.db` | Smart album history (SQLite) |
| `~/.config/LocalLens/scheduler.log` | Scheduler daemon logs |
