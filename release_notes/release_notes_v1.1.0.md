# LocalLens Agent v1.1.0

**Organize your photo library by talking to Claude. Everything runs on your machine — no uploads, no cloud, not even metadata.**

LocalLens MCP Agent connects Claude Desktop (or any MCP-compatible AI assistant) to your local [LocalLens](https://locallensmcp.vercel.app) photo organizer.

## ✨ What this release is

Nothing about how LocalLens works changed here — `v1.0.34` already unlocked every Pro
feature for everyone. This release is about saying so consistently, everywhere someone
might land before they ever open the app:

- The README led with a Free-vs-Pro paywall table and a "purchase a license" line.
  Neither was true anymore. Both now lead with the free preview instead — Pro tools are
  listed as unlocked, not pitched.
- An example Claude Desktop config in the README pointed `LOCALLENS_STORE_URL` at a
  Lemon Squeezy store that never existed. Removed.
- The repo carried a `requirements.txt` nobody referenced — `pyproject.toml` has been
  the real source of dependencies for a while. Removed, so there's one place to look,
  not two that can quietly drift apart.
- Download count, release version, and star count now show as badges at the top of the
  README, pulled live from GitHub's own public numbers.
- The website gained cookieless visit analytics (Vercel Web Analytics — no cookies, no
  personal data collected). That's the only place any usage data is measured; the MCP
  agent itself still makes no calls of its own beyond a license check, and that check is
  moot right now since nothing is gated.

---

## 📦 Install

### macOS — Homebrew (recommended)

```bash
brew install ashesbloom/locallens/locallens-agent
```

Homebrew clears Gatekeeper for you — there is nothing else to run. Launch **LocalLens Agent** from Applications and look for the `LL` icon in your menu bar.

### macOS — DMG

1. Download [`locallens-agent-v1.1.0-macos-arm64.dmg`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.0/locallens-agent-v1.1.0-macos-arm64.dmg)
2. Open it and drag **LocalLens Agent** to Applications
3. Clear Gatekeeper — the app is not yet notarized by Apple, so macOS will say it is damaged or from an unidentified developer until you do this:

   Double-click the **Fix LocalLens Agent.command** file included in the DMG, or run this once in Terminal:

   ```bash
   xattr -cr "/Applications/LocalLens Agent.app" && codesign --force --deep --sign - "/Applications/LocalLens Agent.app"
   ```

4. Launch from Applications — the `LL` icon appears in your menu bar

> Prefer Homebrew if you can. It skips this step entirely.

### Windows

1. Download [`locallens-agent-v1.1.0-windows-x86_64-setup.exe`](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.0/locallens-agent-v1.1.0-windows-x86_64-setup.exe)
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
| macOS (Apple Silicon) | [locallens-agent-v1.1.0-macos-arm64.dmg](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.0/locallens-agent-v1.1.0-macos-arm64.dmg) | Menu Bar App |
| Windows (x64) | [locallens-agent-v1.1.0-windows-x86_64-setup.exe](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.0/locallens-agent-v1.1.0-windows-x86_64-setup.exe) | Installer |
| macOS (Apple Silicon) | [locallens-mcp-v1.1.0-macos-arm64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.0/locallens-mcp-v1.1.0-macos-arm64.zip) | MCP Binary |
| Windows (x64) | [locallens-mcp-v1.1.0-windows-x86_64.zip](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.0/locallens-mcp-v1.1.0-windows-x86_64.zip) | MCP Binary |
| Linux (x64) | [locallens-mcp-v1.1.0-linux-x86_64.tar.gz](https://github.com/ashesbloom/locallens_mcp_agent/releases/download/v1.1.0/locallens-mcp-v1.1.0-linux-x86_64.tar.gz) | MCP Binary |

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
