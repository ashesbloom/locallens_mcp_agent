# LocalLens MCP Server

> **Your Photos. Your Machine. Your Rules.**

LocalLens MCP is the AI bridge for [LocalLens](https://locallens.app) — a privacy-first photo organizer that runs 100% on your computer. Connect it to Claude (or any MCP-compatible AI) and organize, search, and manage your entire photo library using plain English.

**Zero data leaves your machine. Not even metadata.**

---

## What you can do

| Say this... | What happens |
|---|---|
| *"Sort my vacation photos by location"* | Organized into folders by city/state in seconds |
| *"Find all photos of Mom from last Christmas"* | Face recognition + date filtering, no upload needed |
| *"Find duplicate photos in my Downloads"* | Reclaims gigabytes, with safe dry-run preview |
| *"Watch my camera roll and auto-sort new photos"* | Real-time monitoring, organizes instantly on arrival |
| *"What can LocalLens do?"* | Interactive feature guide, right in the chat |

---

## Prerequisites

1. **LocalLens app** must be installed and running on your machine → [Download at locallens.app](https://locallens.app)
2. **Python 3.10+**
3. **Claude Desktop** (or any MCP-compatible client)

---

## Installation

```bash
pip install locallens-mcp
```

Or install from source:

```bash
git clone https://github.com/locallens/locallens-mcp
cd locallens-mcp
pip install -e .
```

---

## Connect to Claude Desktop

Add the following to your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "locallens": {
      "command": "locallens-mcp"
    }
  }
}
```

Restart Claude Desktop. You'll see LocalLens tools appear in Claude's tool panel.

> See `claude_desktop_config.example.json` for the full config with all options.

---

## Free vs Pro

| Feature | Free | Pro |
|---|---|---|
| Folder analysis | ✅ | ✅ |
| Sort by date / location / people | ✅ | ✅ |
| View job progress | ✅ | ✅ |
| Face recognition & enrollment | — | ✅ |
| Find group (filter by person + place + date) | — | ✅ |
| Duplicate detection & cleanup | — | ✅ |
| Export reports | — | ✅ |
| Scheduled auto-organize (every N hours) | — | ✅ |
| Real-time folder watching (active folders) | — | ✅ |

**Get Pro:** Purchase a license at [locallens.app](https://locallens.app), then activate it in Claude:

```
activate_pro_license(license_key="YOUR-LICENSE-KEY")
```

Activation requires internet **once**. After that, Pro works fully offline.

---

## Privacy

LocalLens MCP is a local-only server. It:

- Communicates exclusively with the LocalLens app running on your machine via `localhost`
- Never sends photos, file paths, or metadata to any external server
- Discovers the LocalLens backend automatically via `~/.config/LocalLens/port.txt`
- Stores the Pro license cache at `~/.config/LocalLens/mcp_license.json` (local only)

The **only** network request is license activation — a one-time call to verify your key.

---

## License

This software is distributed under the [Business Source License 1.1](LICENSE.md).  
Free for personal use. Commercial and SaaS use requires a Pro license.

See [NOTICE.md](NOTICE.md) for third-party licenses.
