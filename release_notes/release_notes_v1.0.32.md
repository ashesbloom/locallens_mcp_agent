# LocalLens Agent v1.0.32

**Organize your photo library by talking to Claude. Everything runs on your machine — no uploads, no cloud, not even metadata.**

LocalLens MCP Agent connects Claude Desktop (or any MCP-compatible AI assistant) to your local [LocalLens](https://locallensmcp.vercel.app) photo organizer.

## ✨ Highlights

- License & Plans in the tray menu — your tier, activation date, and exactly what Free and Pro include
- Sort by People is free — corrected everywhere; only batch face enrolment is Pro
- LocalLens questions are answered from the built-in guide, never from a web search
- Update instructions match how you installed — app users get the tray flow, not a pip command
- Updates refuse a mismatched or unverified download instead of silently reinstalling an older build
- All links now point to locallensmcp.vercel.app — the old locallens.app address is no longer ours

---

## 🔧 What Changed

### Added

- License & Plans in the tray menu — your tier, activation date, and exactly what Free and Pro include

### Fixed

- Sort by People is free — corrected everywhere; only batch face enrolment is Pro
- LocalLens questions are answered from the built-in guide, never from a web search
- Update instructions match how you installed — app users get the tray flow, not a pip command
- Updates refuse a mismatched or unverified download instead of silently reinstalling an older build

### Improved

- All links now point to locallensmcp.vercel.app — the old locallens.app address is no longer ours

---

## 📦 Install

### macOS — Homebrew (recommended)

```bash
brew install ashesbloom/locallens/locallens-agent
```

Homebrew clears Gatekeeper for you — there is nothing else to run. Launch **LocalLens Agent** from Applications and look for the `LL` icon in your menu bar.

### macOS — DMG

1. Download [`locallens-agent-v1.0.32-macos-arm64.dmg`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.32/locallens-agent-v1.0.32-macos-arm64.dmg)
2. Open it and drag **LocalLens Agent** to Applications
3. Clear Gatekeeper — the app is not yet notarized by Apple, so macOS will say it is damaged or from an unidentified developer until you do this:

   Double-click the **Fix LocalLens Agent.command** file included in the DMG, or run this once in Terminal:

   ```bash
   xattr -cr "/Applications/LocalLens Agent.app" && codesign --force --deep --sign - "/Applications/LocalLens Agent.app"
   ```

4. Launch from Applications — the `LL` icon appears in your menu bar

> Prefer Homebrew if you can. It skips this step entirely.

### Windows

1. Download [`locallens-agent-v1.0.32-windows-x86_64-setup.exe`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.32/locallens-agent-v1.0.32-windows-x86_64-setup.exe)
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

## ⬆️ Already have LocalLens Agent?

Open the **LocalLens tray menu → Check for Updates → Install Update**. It downloads, verifies the checksum and installs for you.

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
| Smart album suggestions | — | ✅ |
| Scheduled auto-organize & active folders | — | ✅ |

One-time purchase, no subscription. Upgrade from the **tray menu → Plan**, or see plans at [locallensmcp.vercel.app](https://locallensmcp.vercel.app/#pricing).

Already have a key? Ask Claude: *"activate my pro license"*.

---

## 📥 All downloads

| Platform | File | Type |
|---|---|---|
| macOS (Apple Silicon) | [locallens-agent-v1.0.32-macos-arm64.dmg](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.32/locallens-agent-v1.0.32-macos-arm64.dmg) | Menu Bar App |
| Windows (x64) | [locallens-agent-v1.0.32-windows-x86_64-setup.exe](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.32/locallens-agent-v1.0.32-windows-x86_64-setup.exe) | Installer |
| macOS (Apple Silicon) | [locallens-mcp-v1.0.32-macos-arm64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.32/locallens-mcp-v1.0.32-macos-arm64.zip) | MCP Binary |
| Windows (x64) | [locallens-mcp-v1.0.32-windows-x86_64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.32/locallens-mcp-v1.0.32-windows-x86_64.zip) | MCP Binary |
| Linux (x64) | [locallens-mcp-v1.0.32-linux-x86_64.tar.gz](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.0.32/locallens-mcp-v1.0.32-linux-x86_64.tar.gz) | MCP Binary |

---

## 🚀 Getting started

1. Install the **LocalLens desktop app** and run it once — [download](https://locallensmcp.vercel.app/#download)
2. Install LocalLens Agent using any method above
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