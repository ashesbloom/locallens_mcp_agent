---
name: release-agent
description: Release management skill for bumping versions, generating dual release notes (App GUI + GitHub Release Page), running tests, committing, and tagging releases.
---

# LocalLens Release Agent Skill

This skill provides step-by-step instructions for preparing, versioning, testing, committing, tagging, and releasing builds of the LocalLens MCP Agent.

## Step-by-Step Release Workflow

### Step 1: Pre-Release Verification & Testing
Run unit tests to ensure the codebase is clean:
```bash
venv/bin/pytest tests/
```

### Step 2: Bump Version & Generate Dual Release Notes
Use the `set_version.js` automation tool to synchronize all version fields and generate both release logs:
```bash
node set_version.js <version> "Highlight 1" "Highlight 2" ...
```

This updates:
1. `pyproject.toml` (`version`)
2. `src/mcp_server/updater.py` (`MCP_VERSION`)
3. `version.json` (App GUI Release Log / Changelog)
4. `release_notes_v<version>.md` (GitHub Release Page Notes)

### Step 3: Review Changes
Verify modified files with `git status` and `git diff`:
- `pyproject.toml`
- `src/mcp_server/updater.py`
- `version.json`
- `release_notes_v<version>.md`

### Step 4: Commit Changes
Create a standard release commit:
```bash
git add .
git commit -m "release: v<version>"
```

### Step 5: Tag Release
Create the git tag matching `v<version>`:
```bash
git tag v<version>
```

### Step 6: Push Commit & Tag to GitHub
Push the main branch and tag to GitHub to trigger CI/CD build pipelines:
```bash
git push origin main v<version>
```
