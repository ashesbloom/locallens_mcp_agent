**The first public release of LocalLens MCP Agent — your AI-powered bridge to privacy-first photo organization.**

LocalLens MCP Agent connects Claude Desktop (or any MCP-compatible AI assistant) to your local [LocalLens](https://locallens.app) photo organizer. Everything runs on your machine. Zero data leaves your device.

---

## What's New in v1.0.19

- Fixed Windows tray PATH error by bundling locallens-mcp.exe alongside the tray executable

---

## What's Included

- **macOS Menu Bar App** — Native tray app for Apple Silicon with one-click Claude Desktop integration
- **MCP Server Binaries** — Standalone binaries for macOS (arm64), Windows (x64), and Linux (x64)
- **16 Free Tools** — Full photo organization capabilities out of the box
- **10 Pro Tools** — Advanced features for power users (requires Pro license)

---

## Downloads

| Platform | File | Type |
|----------|------|------|
| macOS (Apple Silicon) | [locallens-agent-macos-arm64.dmg](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.19/locallens-agent-v1.0.19-macos-arm64.dmg) | Menu Bar App |
| macOS (Apple Silicon) | [locallens-mcp-macos-arm64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.19/locallens-mcp-v1.0.19-macos-arm64.zip) | MCP Binary |
| Windows (x64) | [locallens-mcp-windows-x86_64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.19/locallens-mcp-v1.0.19-windows-x86_64.zip) | MCP Binary |
| Linux (x64) | [locallens-mcp-linux-x86_64.tar.gz](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.19/locallens-mcp-v1.0.19-linux-x86_64.tar.gz) | MCP Binary |

---

## Installation

### macOS — Homebrew (Recommended)

\`\`\`bash
brew install ashesbloom/locallens/locallens-agent
\`\`\`

The menu bar app will be available in your Applications folder.

### macOS — DMG

**Fix Gatekeeper (required for unsigned apps):**
  - Run  in terminal:
     \`\`\`bash
     xattr -cr "/Applications/LocalLens Agent.app" && codesign --force --deep --sign - "/Applications/LocalLens Agent.app"
     \`\`\`

1. Download `locallens-agent-v1.0.19-macos-arm64.dmg`
2. Open the DMG and drag **LocalLens Agent** to Applications
3. Run the included **Fix LocalLens Agent.command** to clear macOS Gatekeeper
4. Launch from Applications — look for the `LL` icon in your menu bar

### macOS / Linux — MCP Binary

\`\`\`bash
# Extract and set up
tar -xzf locallens-mcp-v1.0.19-macos-arm64.tar.gz   # or .zip on macOS
./locallens-mcp --setup-claude

# Restart Claude Desktop to activate
\`\`\`

### Windows — MCP Binary

\`\`\`powershell
# Extract the zip, then run:
.\locallens-mcp.exe --setup-claude

# Restart Claude Desktop to activate
\`\`\`

---

## Features

### Free Tools
No license required — start organizing immediately:

| Tool | Description |
|------|-------------|
| `check_app_status` | Verify LocalLens backend is running |
| `get_stats` | View your photo library statistics |
| `analyse_folder` | Scan and analyze any photo folder |
| `start_sorting` | Organize photos by date, location, or people |
| `start_find_group` | Find and group similar photos |
| `get_enrolled_faces` | List recognized people in your library |
| `get_path_presets` | View saved folder presets |
| `remember_paths` / `forget_paths` | Manage folder presets |
| `get_job_progress` | Monitor running organization jobs |
| `abort_job` | Cancel a running job |
| `open_folder` | Open organized folders in Finder/Explorer |
| `locallens_help` | Get help and documentation |
| `activate_pro_license` | Activate a Pro license |
| `get_license_status` | Check current license status |
| `revoke_pro_license` | Deactivate Pro license |

### Pro Tools
Unlock with a [Pro license](https://locallens.app):

| Tool | Description |
|------|-------------|
| `add_face_enroll` | Teach LocalLens to recognize new people |
| `find_duplicates` | Detect duplicate photos across folders |
| `delete_duplicates` | Safely remove duplicate files |
| `export_report` | Generate organization reports |
| `schedule_auto_organize` | Set up recurring organization jobs |
| `create_active_folder` | Create watched folders for auto-import |
| `list_schedules` | View all scheduled jobs |
| `manage_schedule` | Edit or delete schedules |
| `open_scheduler_dashboard` | Access the scheduler UI |
| `smart_album_suggestions` | Get AI-powered album recommendations |

---

## Prerequisites

1. **LocalLens Desktop App** — Download from [locallens.app](https://locallens.app)
2. **Claude Desktop** — Or any MCP-compatible AI client

---

## Getting Started

1. Install LocalLens from [locallens.app](https://locallens.app) and run it once
2. Install LocalLens MCP Agent using your preferred method above
3. Restart Claude Desktop
4. Ask Claude: *"Check if LocalLens is running"*

You're ready to organize your photos with AI.

---

## Links

- [LocalLens Website](https://locallens.app)
- [Report Issues](https://github.com/ashesbloom/locallens_mcp_agent/issues)

---

*Built with privacy in mind. Your photos stay on your machine.*