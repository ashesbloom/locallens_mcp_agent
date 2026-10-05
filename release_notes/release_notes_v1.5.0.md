# LL Agent v1.5.0

**Organize your photo library by talking to Claude. Everything runs on your machine — no uploads, no cloud, not even metadata.**

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

---

## 🔗 Links

- [Website](https://locallensmcp.vercel.app) · [Plans & pricing](https://locallensmcp.vercel.app/#pricing)
- [Full tool reference](https://github.com/ashesbloom/locallens_mcp_agent#readme)
- [Report an issue](https://github.com/ashesbloom/locallens_mcp_agent/issues)

---

*Built with privacy in mind. Your photos never leave your machine.*
