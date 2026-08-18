# LocalLens Agent v1.1.1

**Organize your photo library by talking to Claude. Everything runs on your machine — no uploads, no cloud, not even metadata.**

LocalLens MCP Agent connects Claude Desktop (or any MCP-compatible AI assistant) to your local [LocalLens](https://locallensmcp.vercel.app) photo organizer.

## ✨ Highlights

- Finding duplicate photos or exporting a report could fail with a missing-library error, and the assistant would then suggest installing that library by hand — which could never work. It now points you at the LocalLens app update that actually fixes it.
- On LocalLens 3.0.1 and newer, duplicate scans of large photo libraries run in the background and report progress instead of giving up partway through.

---

## 🔧 What Changed

### Fixed

- Finding duplicate photos or exporting a report could fail with a missing-library error, and the assistant would then suggest installing that library by hand — which could never work. It now points you at the LocalLens app update that actually fixes it.

### Improved

- On LocalLens 3.0.1 and newer, duplicate scans of large photo libraries run in the background and report progress instead of giving up partway through.

---

## 📦 Install

### macOS — Homebrew (recommended)

```bash
brew install ashesbloom/locallens/locallens-agent
```

Homebrew clears Gatekeeper for you — there is nothing else to run. Launch **LocalLens Agent** from Applications and look for the `LL` icon in your menu bar.

### macOS — DMG

1. Download [`locallens-agent-v1.1.1-macos-arm64.dmg`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.1/locallens-agent-v1.1.1-macos-arm64.dmg)
2. Open it and drag **LocalLens Agent** to Applications
3. Clear Gatekeeper — the app is not yet notarized by Apple, so macOS will say it is damaged or from an unidentified developer until you do this:

   Double-click the **Fix LocalLens Agent.command** file included in the DMG, or run this once in Terminal:

   ```bash
   xattr -cr "/Applications/LocalLens Agent.app" && codesign --force --deep --sign - "/Applications/LocalLens Agent.app"
   ```

4. Launch from Applications — the `LL` icon appears in your menu bar

> Prefer Homebrew if you can. It skips this step entirely.

### Windows

1. Download [`locallens-agent-v1.1.1-windows-x86_64-setup.exe`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.1/locallens-agent-v1.1.1-windows-x86_64-setup.exe)
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

<!--
Paid-mode version of this section — restore verbatim once FREE_PREVIEW flips back to
false (see docs/RESTORING_PAID_MODE.md):

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

Upgrade from the **tray menu → Plan**, or see current plans and pricing at [locallensmcp.vercel.app](https://locallensmcp.vercel.app/#pricing).

Already have a key? Ask Claude: *"activate my pro license"*.
-->

## 🎉 Free preview — everything is unlocked

There is no store yet, so there is nothing to buy. Every tool below runs for
everyone, with no license key:

| | Available now |
|---|:---:|
| Sort by Date, Location, or People | ✅ |
| Find & Group — including by person | ✅ |
| Folder analysis, saved path presets, stats | ✅ |
| Batch face enrollment | ✅ |
| Duplicate detection & cleanup | ✅ |
| Export reports | ✅ |
| Scheduled auto-organize & active folders | ✅ |

**If you're using LocalLens now, you keep all of this for free, permanently** —
even after paid plans launch. That's not a trial period ending; it's a thank-you
for being here early. See [locallensmcp.vercel.app/#pricing](https://locallensmcp.vercel.app/#pricing)
for how it works.

---

## 📥 All downloads

| Platform | File | Type |
|---|---|---|
| macOS (Apple Silicon) | [locallens-agent-v1.1.1-macos-arm64.dmg](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.1/locallens-agent-v1.1.1-macos-arm64.dmg) | Menu Bar App |
| Windows (x64) | [locallens-agent-v1.1.1-windows-x86_64-setup.exe](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.1/locallens-agent-v1.1.1-windows-x86_64-setup.exe) | Installer |
| macOS (Apple Silicon) | [locallens-mcp-v1.1.1-macos-arm64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.1/locallens-mcp-v1.1.1-macos-arm64.zip) | MCP Binary |
| Windows (x64) | [locallens-mcp-v1.1.1-windows-x86_64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.1/locallens-mcp-v1.1.1-windows-x86_64.zip) | MCP Binary |
| Linux (x64) | [locallens-mcp-v1.1.1-linux-x86_64.tar.gz](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.1/locallens-mcp-v1.1.1-linux-x86_64.tar.gz) | MCP Binary |

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
