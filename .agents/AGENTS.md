# Agent Guidelines & Release Roles for LocalLens MCP Agent

This document defines project-specific rules, guidelines, and roles for AI agents working in this repository.

## Release Agent Role & Protocol

When performing a release, version bump, commit, or tag operation, the agent MUST follow these strict rules:

### Pre-Release Checks
1. **Run Unit Tests**: Always execute `venv/bin/pytest tests/` and verify all tests pass before making any version changes or release commits.
2. **Inspect Working Directory**: Check `git status --short` to ensure all necessary source changes are accounted for.

### Version Management with `set_version.js`
1. Always run `node set_version.js <version> ["Highlight 1"] ["Highlight 2"] ...` to bump version numbers consistently across the codebase.
2. `set_version.js` automatically updates:
   - `pyproject.toml` (`version = "<version>"`)
   - `src/mcp_server/updater.py` (`MCP_VERSION = "<version>"`)
   - `version.json` (App GUI Changelog & `mcp.latest` version)
   - `release_notes_v<VERSION>.md` (GitHub Release Page notes)

### Dual Release Notes Requirement
Every release must produce TWO sets of release notes:
1. **Application GUI Release Log**: Embedded in `version.json` under `mcp.changelog`. Displayed in the system tray app and update notification dialogs.
2. **GitHub Release Page Notes**: Formatted markdown in `release_notes_v<VERSION>.md`. Download URLs, asset names, and Gatekeeper commands must match `v<VERSION>`.

### Release Commit & Tagging Protocol
1. **Commit Message Format**: Use `release: v<VERSION>` or `chore(release): v<VERSION>`.
2. **Tag Format**: Create annotated or lightweight git tag `v<VERSION>` matching the version number exactly (e.g. `v1.0.18`).
3. **Verification**: Run `git status` and `git tag -l "v<VERSION>"` to verify the commit and tag are cleanly set.
