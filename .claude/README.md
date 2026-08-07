# `.claude/` — agent configuration

Tracked in git on purpose. The release process lives here, so it has to travel
with the repo rather than sitting on one laptop. Only
`.claude/settings.local.json` (per-machine permission allowlist) stays ignored.

```
.claude/
├── README.md                        this file
├── agents/
│   └── release-preflight.md         read-only reviewer, gates a release
├── skills/
│   └── release-agent/
│       ├── SKILL.md                 the release workflow  (/release-agent)
│       └── RELEASE_MEMORY.md        why each rule exists — read before releasing
└── settings.local.json              per-machine, gitignored
```

## Releasing

Say **"release a new build"**, "cut a release", "ship it", or run
`/release-agent`. The skill is user-invocable only (`disable-model-invocation: true`)
— it commits, tags and pushes, so nothing triggers it by inference.

It will: read the diff, bump the version, generate both release logs, run the
preflight gate, commit, and then **stop and ask** before tagging. The tag is the
irreversible step — it starts five builds and a bot commit to `main`.

## The moving parts

| Piece | Does |
|---|---|
| `scripts/set_version.py` (or `.js`) | bumps 4 files, writes both release logs |
| `scripts/preflight_release.py` | deterministic gate — exits non-zero, never fixes |
| `.claude/agents/release-preflight.md` | the judgement calls a script cannot make |
| `release_notes/release_notes_template.md` | the GitHub page layout |
| `.github/workflows/release.yml` | builds, publishes the notes, then `version.json` |

## Two release logs, two audiences

- **`version.json` → `mcp.changelog[0].highlights`** — desktop "What's New" panel
  and the assistant. Plain sentences.
- **`release_notes/release_notes_v<version>.md`** — the GitHub release page. Full
  page with install, upgrade, Free vs Pro and downloads.

Both are generated from the same CLI arguments. A highlight prefixed `Added:` /
`Fixed:` / `Improved:` is grouped under **What Changed** on the GitHub page; the
prefix is stripped for `version.json`.

## Things that will bite you

Read `skills/release-agent/RELEASE_MEMORY.md` — every entry is there because it
already shipped broken. The short version:

- Never set `version.json` `mcp.latest` by hand; CI owns it.
- Never write a price, or a `locallens.app` URL.
- Never reword an `@mcp.tool()` docstring during a release — `docs/TESTING.md`
  pins exact sentences from them.
- Sorting by People is **free**. Only batch enrolment is Pro.
