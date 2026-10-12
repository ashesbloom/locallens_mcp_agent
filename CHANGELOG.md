# Changelog

All notable changes to LL Agent are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Generated from `version.json` by `scripts/gen_changelog.py` — edit that, not this.


## [1.5.0] - 2026-10-05

### Changed

- Paid plans are live. LL Agent Pro is a yearly or monthly plan, and if you used LL Agent during the free preview you keep Pro free, permanently, with no key.
- Activate Pro… in the LL menu (the system tray on Windows) opens a small window where you paste your license key.
- License & Plans in the LL menu can deactivate Pro on this computer, after you confirm.
- Claude now asks you to confirm before it deactivates your license.
- License keys now come from Dodo Payments. A subscription re-checks about once a week, sending only the key, and keeps working for 14 days offline; a founding key never re-checks.
- On recent macOS, an activated license was forgotten every time LL Agent restarted.
- The LL menu now shows Pro turning on or off within seconds when you activate or deactivate through Claude, instead of after a restart.
- Free-preview users updating from a version older than 1.0.34 are recognised as early users and keep Pro.
- The product is now called LL Agent. Its license (Business Source License 1.1) says plainly that the Free tools are yours to use and Pro needs a key, and the Windows installer shows it.

## [1.1.2] - 2026-08-22

### Changed

- Deleting duplicate photos stored on a network drive or NAS now works. Every file used to fail with a "path not found" error, even though the preview had just reported success.
- When a LocalLens operation fails, the assistant now reports it and points you at the bug-report form instead of trying to diagnose the app itself. It will also never remove your photos by another route, so deletions always go through the Trash, where they stay recoverable.

## [1.1.1] - 2026-08-18

### Changed

- Finding duplicate photos or exporting a report could fail with a missing-library error, and the assistant would then suggest installing that library by hand — which could never work. It now points you at the LocalLens app update that actually fixes it.
- On LocalLens 3.0.1 and newer, duplicate scans of large photo libraries run in the background and report progress instead of giving up partway through.

## [1.1.0] - 2026-08-13

### Changed

- Nothing about how LocalLens works changed in this release — v1.0.34 already unlocked everything. This one is the README, release notes and download page catching up to say so consistently.
- The website now has cookieless visit analytics and the README shows live download and star counts. Both are public numbers only; nothing was added to what the MCP agent itself sends over the network.

## [1.0.34] - 2026-08-12

### Changed

- LocalLens is in a free preview — every Pro feature is unlocked for everyone right now, no license required.
- Anyone using LocalLens during the free preview keeps Pro permanently once paid plans launch. You will not be charged.
- The assistant and tray no longer suggest upgrading to Pro for features that are already unlocked during the preview.

## [1.0.33] - 2026-08-11

### Changed

- Pro licenses can now be subscriptions as well as one-time purchases — they renew automatically, and a 14-day offline grace period means a failed renewal check never locks you out mid-trip.
- License terms and default config no longer point at the dead locallens.app domain.
- Upgrade prompts in the tray, README and in-chat help updated for the new pricing model — no longer claim "no subscription" and no longer list Smart Album Suggestions.

## [1.0.32] - 2026-08-08

### Changed

- License & Plans in the tray menu — your tier, activation date, and exactly what Free and Pro include
- Sort by People is free — corrected everywhere; only batch face enrolment is Pro
- LocalLens questions are answered from the built-in guide, never from a web search
- Update instructions match how you installed — app users get the tray flow, not a pip command
- Updates refuse a mismatched or unverified download instead of silently reinstalling an older build
- All links now point to locallensmcp.vercel.app — the old locallens.app address is no longer ours

## [1.0.31] - 2026-08-02

### Changed

- Concurrent job guard — blocks a second sort/find if a job is already running
- Destination path validation with opt-in creation (create_destination=True)
- Enrolled-face count fix — reads enrolled_faces key correctly from backend payload
- Daemon lifecycle overhaul — no more backend clones, SIGTERM stop, PID-file-based control
- Preset path resolution — resolve_path_preset maps preset names to real paths
- File-count cross-check — flags total_files vs scanned-file mismatches in status
- Trimmed MCP system instructions to survive client truncation; safety rules now first
- Six new test files covering all new helpers (153 tests total)

## [1.0.30] - 2026-07-29

### Changed

- Pinned the mcp dependency below 2.0.0 - mcp 2.0.0 removed mcp.server.fastmcp, which broke the v1.0.29 binaries and the macOS app bundle build
- v1.0.29 binaries are unusable and its macOS DMG was never published; upgrade straight to v1.0.30

## [1.0.29] - 2026-07-29

### Changed

- Fixed Claude Desktop refusing the connector - the server instructions no longer read as an attempt to override assistant behavior
- Rewrote the copyable Claude custom instructions: teaches the "LL" shorthand and works with Claude Desktop's "Load tools when needed" mode
- Fixed garbled dashes when copying those instructions on macOS and Windows
- check_app_status and get_license_status now mention LL/LocalLens so the connector is discoverable when tools load on demand

## [1.0.28] - 2026-07-27

### Changed

- Replaced Windows/macOS/installer branding with the new ll_red_trans logo (exe icons, DMG volume icon, NSIS installer, installer welcome screen)
- Windows tray icon now renders a theme-aware "LL" wordmark instead of a fixed dark logo, fixing invisibility on dark taskbars

## [1.0.27] - 2026-07-27

### Changed

- Status indicators now render correctly on Windows — shape-coded instead of color emoji
- Connection errors and available updates get their own indicator instead of looking idle
- Rewritten status legend in Help & Getting Started

## [1.0.26] - 2026-07-27

### Changed

- Fixed Windows NSIS installer MUI_FINISHPAGE_RUN quoting
- Fixed Windows/macOS auto-update: silent failure, wrong install path, and missing error reporting
- Update progress now shows MB downloaded
- Branded Windows setup wizard and drag-to-Applications DMG

## [1.0.25] - 2026-07-27

### Changed

- Fixed critical LLM sorting logic to block People sort when no faces are enrolled and set wait_for_completion=True by default.
- Fixed Windows process management, UTF-16LE clipboard encoding, MSIX log path detection, and daemon PID existence verification.
- Organized project repository structure into cleanly separated docs/, scripts/, and release_notes/ directories.

## [1.0.24] - 2026-07-25

### Changed

- Fix Windows MSIX config path bug for Claude Desktop Connector

## [1.0.23] - 2026-07-25

### Changed

- Added smithery.yaml for Smithery MCP directory listing
- Fixed tray Claude Setup error alerts — errors now show distinct title instead of blending with success

## [1.0.22] - 2026-07-25

### Changed

- Fixed backend exe launch logic to correctly find sidecar server
- Removed internal metadata from claude config injection to fix compatibility with Claude Desktop

## [1.0.21] - 2026-07-25

### Changed

- Fixed CI test failure: added psutil to dev extras so tray module tests run in pip install .[dev]

## [1.0.20] - 2026-07-25

### Changed

- Fixed Claude Desktop setup PATH for frozen/bundled builds
- Added silent in-app auto-updater with SHA256 verification and progress UI
- Fixed Windows backend console window visibility
- Fixed CI test failure: added psutil to dev extras

## [1.0.19] - 2026-07-24

### Changed

- Fixed Windows tray PATH error by bundling locallens-mcp.exe alongside the tray executable

## [1.0.18] - 2026-07-24

### Changed

- Added workflow_dispatch trigger to release pipeline
- Fixed macOS tray build pyproject.toml cleanup trap
- Improved Windows tray single-instance mutex and dialog threading

## [1.0.16] - 2026-07-22

### Changed

- Added Windows Tray App CI workflow with NSIS installer bundling
- Fixed UPX corruption on Windows binaries preventing python3xx.dll LoadLibrary failures
- Improved Windows tray dialogs with native prompts for missing LocalLens & Claude Desktop

## [1.0.13] - 2026-07-19

### Changed

- First public release of LocalLens MCP Agent
- Native macOS menu bar tray app — install via Homebrew
- 16 free tools for photo organization out of the box
- 10 Pro tools: face enrollment, duplicates, smart albums, scheduling
- Official LL Black branding applied across all platforms

## [1.0.12] - 2026-07-19

### Changed

- Official LL Black app icon applied to macOS DMG and Windows EXE
- Red LLAgent logo added to project documentation
- All icon assets committed and tracked in repository

## [1.0.0] - 2026-07-06

### Changed

- Official MCP launch — connect LocalLens to Claude, Cursor, and more
- Smart sorting by date, location, and people
- Face recognition with enrollment and search
- Duplicate detection and safe cleanup
- Scheduled auto-organize and real-time folder watching
- 100% local — zero data leaves your machine
