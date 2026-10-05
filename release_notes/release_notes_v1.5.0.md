# LL Agent v1.5.0

**Organize your photo library by talking to Claude. Everything runs on your machine — no uploads, no cloud, not even metadata.**

<p align="center"><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/ll-agent-pro.png" width="420" alt="LL Agent Pro — Claude sorts your photo library. Not one photo leaves your machine."></p>

LL Agent connects Claude Desktop (or any MCP-compatible AI assistant) to your local [LocalLens](https://locallensmcp.vercel.app) photo organizer.

## ✨ Highlights

- Paid plans are live. LL Agent Pro is a yearly or monthly plan, and if you used LL Agent during the free preview you keep Pro free, permanently, with no key.
- Activate Pro… in the LL menu (the system tray on Windows) opens a small window where you paste your license key.
- License & Plans in the LL menu can deactivate Pro on this computer, after you confirm.
- Claude now asks you to confirm before it deactivates your license.
- License keys now come from Dodo Payments. A subscription re-checks about once a week, sending only the key, and keeps working for 14 days offline; a founding key never re-checks.
- On recent macOS, an activated license was forgotten every time LL Agent restarted.
- The LL menu now shows Pro turning on or off within seconds when you activate or deactivate through Claude, instead of after a restart.
- Free-preview users updating from a version older than 1.0.34 are recognised as early users and keep Pro.
- The product is now called LL Agent. Its license (Business Source License 1.1) says plainly that the Free tools are yours to use and Pro needs a key, and the Windows installer shows it.

### New: Activate Pro, right in the menu bar

Paste your key into **LL menu → Activate Pro…** — no chat needed.

<table>
<tr>
<td><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/activate-pro-window.png" width="360" alt="The Activate Pro window: paste your license key"></td>
<td><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/youre-pro.png" width="360" alt="The You're Pro screen listing every unlocked feature"></td>
</tr>
</table>

---

## 🔧 What Changed

### Added

- Paid plans are live. LL Agent Pro is a yearly or monthly plan, and if you used LL Agent during the free preview you keep Pro free, permanently, with no key.
- Activate Pro… in the LL menu (the system tray on Windows) opens a small window where you paste your license key.
- License & Plans in the LL menu can deactivate Pro on this computer, after you confirm.

### Fixed

- On recent macOS, an activated license was forgotten every time LL Agent restarted.
- The LL menu now shows Pro turning on or off within seconds when you activate or deactivate through Claude, instead of after a restart.
- Free-preview users updating from a version older than 1.0.34 are recognised as early users and keep Pro.

### Changed

- Claude now asks you to confirm before it deactivates your license.
- License keys now come from Dodo Payments. A subscription re-checks about once a week, sending only the key, and keeps working for 14 days offline; a founding key never re-checks.
- The product is now called LL Agent. Its license (Business Source License 1.1) says plainly that the Free tools are yours to use and Pro needs a key, and the Windows installer shows it.

---

## 🎬 See it in action

<table>
<tr><td><b>Sort by date, location and people in one request</b><br><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/demo/01-sort-three-ways.gif" width="640" alt="Sort by date, location and people in one request"></td></tr>
<tr><td><b>Find one person's photos from a given year</b><br><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/demo/02-find-person.gif" width="640" alt="Find one person's photos from a given year"></td></tr>
<tr><td><b>Find duplicates, review them, send them to the Trash</b> · Pro<br><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/demo/03-duplicates.gif" width="640" alt="Find duplicates, review them, send them to the Trash"></td></tr>
<tr><td><b>Ask what's running and what's enabled</b><br><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/demo/04-status-check.gif" width="640" alt="Ask what's running and what's enabled"></td></tr>
<tr><td><b>All 26 tools in Claude's connector settings</b><br><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/demo/05-26-tools.gif" width="640" alt="All 26 tools in Claude's connector settings"></td></tr>
<tr><td><b>The LL menu bar app</b><br><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/demo/06-menubar-app.gif" width="640" alt="The LL menu bar app"></td></tr>
<tr><td><b>Schedule auto-organize and open the dashboard</b> · Pro<br><img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/demo/07-schedule.gif" width="640" alt="Schedule auto-organize and open the dashboard"></td></tr>
</table>

---

## 📦 Install

### macOS — Homebrew (recommended)

```bash
brew install ashesbloom/locallens/locallens-agent
```

Homebrew clears Gatekeeper for you — there is nothing else to run. Launch **LocalLens Agent** from Applications and look for the `LL` icon in your menu bar.

### macOS — DMG

1. Download [`locallens-agent-v1.5.0-macos-arm64.dmg`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.5.0/locallens-agent-v1.5.0-macos-arm64.dmg)
2. Open it and drag **LocalLens Agent** to Applications
3. Clear Gatekeeper — the app is not yet notarized by Apple, so macOS will say it is damaged or from an unidentified developer until you do this:

   Double-click the **Fix LocalLens Agent.command** file included in the DMG, or run this once in Terminal:

   ```bash
   xattr -cr "/Applications/LocalLens Agent.app" && codesign --force --deep --sign - "/Applications/LocalLens Agent.app"
   ```

4. Launch from Applications — the `LL` icon appears in your menu bar

> Prefer Homebrew if you can. It skips this step entirely.

### Windows

1. Download [`locallens-agent-v1.5.0-windows-x86_64-setup.exe`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.5.0/locallens-agent-v1.5.0-windows-x86_64-setup.exe)
2. Run it. SmartScreen may warn about an unknown publisher — choose **More info → Run anyway**
3. The tray icon appears in your notification area

### MCP binary only (macOS / Linux / Windows)

For running the MCP server without the tray app:

```bash
# extract the archive for your platform, then:
./locallens-mcp --setup-claude
```

On Windows that is `.\locallens-mcp.exe --setup-claude`. Restart Claude Desktop to activate.

---

## ⬆️ Already have LL Agent?

Open the **LL menu (the system tray on Windows) → Check for Updates → Install Update**. It downloads, verifies the checksum and installs for you.

Homebrew users can instead run:

```bash
brew upgrade --cask locallens-agent
```

> Installed from source or pip? `pip install --upgrade locallens-mcp`.

---

## 🔑 Free vs Pro

Free is a complete photo organizer, not a trial.

| | Free | Pro |
|---|:---:|:---:|
| Sort by Date | ✅ | ✅ |
| Sort by Location | ✅ | ✅ |
| **Sort by People** (face recognition) | ✅ | ✅ |
| Find & Group — including by person | ✅ | ✅ |
| See who is enrolled | ✅ | ✅ |
| Folder analysis, saved path presets, stats | ✅ | ✅ |
| Batch face enrollment | — | ✅ |
| Duplicate detection & cleanup | — | ✅ |
| Export reports | — | ✅ |
| Scheduled auto-organize & active folders | — | ✅ |

**Used LL Agent during the free preview?** You keep Pro free, permanently — no key needed.

Get Pro from the **LL menu → Activate Pro…**, or see current plans and pricing at [locallensmcp.vercel.app/pricing](https://locallensmcp.vercel.app/pricing).

Already have a key? Paste it into **Activate Pro…**, or ask Claude: *"activate my LL Agent license"*.

---

## 📥 All downloads

| Platform | File | Type |
|---|---|---|
| macOS (Apple Silicon) | [locallens-agent-v1.5.0-macos-arm64.dmg](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.5.0/locallens-agent-v1.5.0-macos-arm64.dmg) | Menu Bar App |
| Windows (x64) | [locallens-agent-v1.5.0-windows-x86_64-setup.exe](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.5.0/locallens-agent-v1.5.0-windows-x86_64-setup.exe) | Installer |
| macOS (Apple Silicon) | [locallens-mcp-v1.5.0-macos-arm64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.5.0/locallens-mcp-v1.5.0-macos-arm64.zip) | MCP Binary |
| Windows (x64) | [locallens-mcp-v1.5.0-windows-x86_64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.5.0/locallens-mcp-v1.5.0-windows-x86_64.zip) | MCP Binary |
| Linux (x64) | [locallens-mcp-v1.5.0-linux-x86_64.tar.gz](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.5.0/locallens-mcp-v1.5.0-linux-x86_64.tar.gz) | MCP Binary |

---

## 🚀 Getting started

1. Install the **LocalLens desktop app** and run it once — [download](https://locallensmcp.vercel.app/#download)
2. Install LL Agent using any method above
3. Restart Claude Desktop
4. Ask Claude: *"Check if LocalLens is running"*

Then try *"What can LocalLens do?"* for a guided tour of all 26 tools.

<img src="https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/v1.5.0/media/claude-connector-tools.png" width="560" alt="LL Agent's tools listed under Connectors in Claude Desktop">

---

## 🔗 Links

- [Website](https://locallensmcp.vercel.app) · [Plans & pricing](https://locallensmcp.vercel.app/#pricing)
- [Full tool reference](https://github.com/ashesbloom/locallens_mcp_agent#readme)
- [Report an issue](https://github.com/ashesbloom/locallens_mcp_agent/issues)

---

*Built with privacy in mind. Your photos never leave your machine.*
