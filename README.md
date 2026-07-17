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
2. **Claude Desktop** (or any MCP-compatible client)

---

## Installation

### Option 1 — Download Executable (Recommended)

1. Download the latest binary zip for your system from the [Releases](https://github.com/ashesbloom/locallens_mcp_agent/releases) page:
   - macOS: `locallens-mcp-vX.Y.Z-macos-arm64.zip` (Apple Silicon) or `-macos-x86_64.zip` (Intel)
   - Windows: `locallens-mcp-vX.Y.Z-windows-x86_64.zip`
   - Linux: `locallens-mcp-vX.Y.Z-linux-x86_64.tar.gz`
2. Extract the archive.
3. Open your terminal, navigate to the extracted file, and run the connector setup command:
   ```bash
   ./locallens-mcp --setup-claude
   ```
   *(On Windows: run `.\locallens-mcp.exe --setup-claude`)*

> [!NOTE]
> On macOS, because the binary is unsigned, the OS might warn that the developer cannot be verified. You can allow it in **System Settings > Privacy & Security**, or run:
> `xattr -dr com.apple.quarantine locallens-mcp`

### Option 2 — Install via pip (For Python Developers)
Requires Python 3.10+:

```bash
pip install locallens-mcp
```

Or install from source:

```bash
git clone https://github.com/ashesbloom/locallens_mcp_agent.git
cd locallens_mcp_agent
pip install -e .
```

---

## Connect to Claude Desktop

### Option 1 — Automatic (Recommended)

Run this once after installing:

```bash
locallens-mcp --setup-claude
```

Then **restart Claude Desktop**. LocalLens tools will appear in the tool panel automatically.

To check the status or disconnect later:
```bash
locallens-mcp --claude-status   # print connection state as JSON
locallens-mcp --remove-claude   # remove LocalLens from Claude config
```

### Option 2 — Manual

Add the following to your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "locallens": {
      "command": "locallens-mcp",
      "env": {
        "LOCALLENS_STORE_URL": "https://locallens.lemonsqueezy.com"
      }
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
