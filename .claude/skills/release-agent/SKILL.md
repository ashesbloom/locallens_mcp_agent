---
name: release-agent
description: Cut a LocalLens MCP Agent release — bump the version, write both release logs, verify nothing is stale or leaking, commit, tag and push. Use when asked to "release a new build", "cut a release", "ship it", "trigger a build", "push a new version", or "bump the version".
disable-model-invocation: true
---

# LocalLens Release Agent

Releases here are **tag-driven**. Pushing `v<version>` triggers
`.github/workflows/release.yml`, which builds five artifacts, publishes the
release notes, and commits `version.json` back to `main`. There is no undo that
does not involve deleting a public tag, so every gate below runs before the tag.

Read `RELEASE_MEMORY.md` (next to this file) first. It holds the non-obvious
facts — why `mcp.latest` is CI-owned, which domain is dead, what the assistant
has previously got wrong. Skipping it is how those bugs come back.

## The two release logs

They are different documents with different audiences. Both are required.

| | Desktop UI + assistant | GitHub release page |
|---|---|---|
| Lives in | `version.json` → `mcp.changelog[0].highlights` | `release_notes/release_notes_v<version>.md` |
| Written by | `scripts/set_version.py` | same script, from `release_notes/release_notes_template.md` |
| Read by | tray "What's New", `check_for_updates()`, quoted verbatim by the assistant | humans deciding whether to download |
| Tone | plain sentences, user-visible outcomes, no category prefixes | full page: highlights, grouped changes, install, upgrade, Free vs Pro, downloads |
| Published by | CI (`update-version-manifest`) | CI (`gh release edit --notes-file`) |

Both come from the same CLI arguments. Prefix a highlight `Added:` / `Fixed:` /
`Improved:` / `Changed:` / `Removed:` and it is grouped under **What Changed** on
the GitHub page; the prefix is stripped for `version.json`.

## Workflow

### 1. Understand what is actually being released

Read the diff — `git status --short` then `git --no-pager diff`. Do not write
release notes from commit subjects or from a summary of the diff; write them from
the code. Highlights describe what changed **for the user**, not which functions
moved.

If the working tree spans unrelated concerns, split it into separate commits
before the release commit. Prefer a split that needs no hunk-level staging: the
version bump rewrites `pyproject.toml`, `updater.py` and `version.json` *after*
earlier commits are made, so those files land twice without conflict.

### 2. Pick the version

Patch bump unless the change is user-visibly larger. `git tag --list 'v*' | sort -V | tail -1`
for the current one.

### 3. Bump and generate both logs

```bash
python scripts/set_version.py <version> \
  "Added: <user-visible thing>" \
  "Fixed: <user-visible thing>" \
  "Improved: <user-visible thing>"
```

Updates `pyproject.toml`, `updater.py` `MCP_VERSION`, the `version.json`
changelog, and writes `release_notes/release_notes_v<version>.md`.

It deliberately does **not** touch `version.json` `mcp.latest`. Leave it alone.

### 4. Read the generated notes and fill the gaps

Open `release_notes/release_notes_v<version>.md`. The template supplies install,
upgrade, Free vs Pro, downloads and links; the generator supplies highlights and
grouped changes. Check the positioning line at the top still describes *this*
release, and that the Free/Pro table matches the `@require_pro` decorators in
`src/mcp_server/tools/pro_tools.py` — the decorators are the source of truth, the
prose is what has to be checked against them.

Never write a price. No price exists anywhere in this repo, and inventing one is
the failure the licensing work was done to prevent.

### 5. Preflight

```bash
python scripts/preflight_release.py <version>
```

Must exit 0. It checks junk files, version agreement across all four files, that
`mcp.latest` is still the *previous* version, that the notes are fully
substituted and carry no dead-domain links, that tests pass, and that the tag is
unused.

For the judgement a script cannot make — secrets, a hardcoded price, prose that
regressed against `docs/TESTING.md` — dispatch the `release-preflight` subagent
over the staged diff.

### 6. Commit

Conventional prefix (`feat:` `fix:` `ci:` `chore:` `docs:` `release:`), imperative
subject under ~72 characters. The body explains **why**, and names the user-facing
symptom for anything that shipped broken — a reader six months out needs the
failure, not the patch.

Version-bump commit is always exactly:

```
release: v<version>
```

Sign off with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 7. Tag and push — confirm with the human first

This is the irreversible step. Show the exact command and wait.

```bash
git tag v<version>
git push origin main v<version>
```

### 8. Watch CI

```bash
gh run watch
```

Then verify the two things that have silently failed before:

```bash
gh release view v<version> --json body --jq '.body' | head -40   # must NOT be empty
curl -s https://raw.githubusercontent.com/ashesbloom/locallens_mcp_agent/main/version.json \
  | python3 -c "import json,sys; m=json.load(sys.stdin)['mcp']; print(m['latest']); print(m['downloads'])"
```

`mcp.latest` must equal the new version, and every `downloads` URL must contain
`v<version>` with a non-empty `sha256`. If `latest` advanced but the URLs point at
the previous release, clients will silently reinstall the old build — the
manifest must be fixed immediately.

## Never

- Set `version.json` `mcp.latest` by hand.
- Commit SHA256 digests to the release notes — CI appends them at publish time.
- Write a price, or a `locallens.app` URL.
- Tag before `preflight_release.py` exits 0.
- Reword a `@mcp.tool()` docstring or the `instructions=` string as part of a
  release tidy-up. `docs/TESTING.md` pins exact sentences from them; see the
  "Trace before you change" section of `CLAUDE.md`.
