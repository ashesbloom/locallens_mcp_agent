# LocalLens MCP Server

> **Your Photos. Your Machine. Your Rules.**

LocalLens MCP is the AI bridge for [LocalLens](https://locallens.app) — a privacy-first photo organizer that runs 100% on your computer. Connect it to Claude Desktop (or any MCP-compatible AI) and organize, search, and manage your entire photo library using plain English.

**Zero data leaves your machine. Not even metadata.**

---

## What you can do

| Say this… | What happens |
|---|---|
| *"Sort my vacation photos by location"* | Organized into folders by city/state in seconds |
| *"Find all photos of Mom from last Christmas"* | Face recognition + date filtering, no upload needed |
| *"Find duplicate photos in my Downloads"* | Reclaims gigabytes, with a safe dry-run preview |
| *"Watch my camera roll and auto-sort new photos"* | Real-time folder monitoring, organizes on arrival |
| *"Suggest albums for me"* | AI-powered smart album recommendations from your library |
| *"What can LocalLens do?"* | Interactive feature guide, right in the chat |

---

## Prerequisites

1. **LocalLens app** must be installed and running → [Download at locallens.app](https://locallens.app)
2. **Claude Desktop** (or any MCP-compatible client)

---

## Installation

### Option 1 — Download Binary (Recommended)

Download the latest release for your platform from the [Releases](https://github.com/ashesbloom/locallens_mcp_agent/releases) page:

| Platform | File |
|---|---|
| macOS (Apple Silicon) | `locallens-mcp-vX.Y.Z-macos-arm64.zip` |
| macOS (Intel) | `locallens-mcp-vX.Y.Z-macos-x86_64.zip` |
| Windows | `locallens-mcp-vX.Y.Z-windows-x86_64.zip` |
| Linux | `locallens-mcp-vX.Y.Z-linux-x86_64.tar.gz` |

Extract the archive, then run the one-time connector setup:

```bash
./locallens-mcp --setup-claude
```
*(Windows: `.\\locallens-mcp.exe --setup-claude`)*

> [!NOTE]
> On macOS the binary is unsigned. If the OS warns that the developer cannot be verified, allow it in **System Settings → Privacy & Security**, or clear the quarantine flag:
> ```bash
> xattr -dr com.apple.quarantine locallens-mcp
> ```

### Option 2 — macOS Menu Bar Agent (Tray App)

For a point-and-click experience on macOS, download the **LocalLens Agent** DMG from the [Releases](https://github.com/ashesbloom/locallens_mcp_agent/releases) page:

| Platform | File |
|---|---|
| macOS (Apple Silicon) | `locallens-agent-vX.Y.Z-macos-arm64.dmg` |
| macOS (Intel) | `locallens-agent-vX.Y.Z-macos-x86_64.dmg` |

Open the DMG, drag **LocalLens Agent** to Applications, and launch it. A menu bar icon (`LL`) will appear. From there you can:

- Connect / disconnect from Claude Desktop with one click
- Start and stop the LocalLens backend
- Check for updates
- Copy custom instructions for Claude

### Option 3 — Install from Source (Python Developers)

Requires Python 3.10+:

```bash
git clone https://github.com/ashesbloom/locallens_mcp_agent.git
cd locallens_mcp_agent
pip install -e .
```

---

## Connect to Claude Desktop

### Automatic (Recommended)

Run once after installing:

```bash
locallens-mcp --setup-claude
```

Then **restart Claude Desktop**. LocalLens tools appear in the tool panel automatically.

To check status or disconnect later:
```bash
locallens-mcp --claude-status   # print connection state as JSON
locallens-mcp --remove-claude   # remove LocalLens from Claude's config
```

### Manual

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

Restart Claude Desktop. LocalLens tools will appear in Claude's tool panel.

> See [`claude_desktop_config.example.json`](claude_desktop_config.example.json) for the full config with all options.

---

## Free vs Pro

### Free Tools

Available to everyone, no license required:

| Tool | What it does |
|---|---|
| `check_app_status` | Check if LocalLens is running and healthy |
| `get_stats` | Library-wide statistics (photo count, locations, people) |
| `get_job_progress` | Poll the status of a running sort/find job |
| `locallens_help` | Interactive guide to features, topics, and workflows |
| `get_enrolled_faces` | List all enrolled people in the face recognition system |
| `get_path_presets` | Retrieve saved folder path presets |
| `analyse_folder` | Scan a folder: subfolder list, photo counts, locations, people |
| `start_sorting` | Sort photos by Date, Location, or People |
| `abort_job` | Cancel a running sort or find job |
| `open_folder` | Open a folder in the system file browser |
| `remember_paths` | Save a folder path as a named preset for reuse |
| `forget_paths` | Remove a saved folder path preset |
| `activate_pro_license` | Activate a Pro license key |
| `get_license_status` | Check your current license tier |
| `revoke_pro_license` | Deactivate and remove the local Pro license |

### Pro Tools

Require an active Pro license (`activate_pro_license`):

| Tool | What it does |
|---|---|
| `start_find_group` | Filter photos by person, location, and date — copy to a new folder |
| `add_face_enroll` | Enroll one or more people for face recognition |
| `find_duplicates` | Detect duplicate photos in a folder |
| `delete_duplicates` | Safely remove duplicates (always dry-run first) |
| `export_report` | Generate a summary report of a folder's contents |
| `schedule_auto_organize` | Run an auto-sort sweep every N hours |
| `create_active_folder` | Watch a folder and organize new photos in real time |
| `list_schedules` | List all active schedules and folder watchers |
| `manage_schedule` | Pause, resume, or delete a schedule |
| `open_scheduler_dashboard` | Open the scheduler web dashboard |
| `smart_album_suggestions` | AI-powered album grouping suggestions for your library |

### Quick comparison

| Feature | Free | Pro |
|---|---|---|
| Folder analysis | ✅ | ✅ |
| Sort by date / location / people | ✅ | ✅ |
| Job progress & abort | ✅ | ✅ |
| Path memory (remember / forget) | ✅ | ✅ |
| Face recognition & enrollment | — | ✅ |
| Find & Group (filter by person + place + date) | — | ✅ |
| Duplicate detection & cleanup | — | ✅ |
| Export reports | — | ✅ |
| Scheduled auto-organize (every N hours) | — | ✅ |
| Real-time folder watching | — | ✅ |
| Smart album suggestions | — | ✅ |

### Activating Pro

Purchase a license at [locallens.app](https://locallens.app), then activate it in Claude:

```
activate_pro_license(license_key="YOUR-LICENSE-KEY")
```

Activation requires internet **once**. After that, all Pro features work fully offline.

---

## Privacy

LocalLens MCP is a strictly local server. It:

- Communicates exclusively with the LocalLens app on your machine via `localhost`
- Never sends photos, file paths, or metadata to any external server
- Discovers the LocalLens backend automatically via `~/.config/LocalLens/port.txt`
- Stores the Pro license cache at `~/.config/LocalLens/mcp_license.json` (local only)

The **only** network request is license activation — a one-time call to verify your key.

---

## License

This software is distributed under the [Business Source License 1.1](LICENSE.md).
Free for personal use. Commercial and SaaS use requires a Pro license.

See [NOTICE.md](NOTICE.md) for third-party licenses.
