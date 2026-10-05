# Release Memory

Durable facts about releasing this project. Each one is here because it was
learned by shipping something broken. Read before every release; update whenever
a release teaches you something new.

---

## `locallens.app` is dead — never link it

The domain lapsed and now serves **Whistle Enterprise**, a meeting-notes product.
`https://locallens.app/download` 301-redirects to `whistle-enterprise.com`.

Asked about Pro licensing, the assistant checked `get_license_status` — which
returns only `{activated, tier, activated_at}` — found no pricing, fell back to
the `locallens.app` URL it had been handed in shipped prose, and described a
stranger's product to the user as LocalLens fact.

| Use | Not |
|---|---|
| `https://locallensmcp.vercel.app` | `https://locallens.app` |
| `https://locallensmcp.vercel.app/#pricing` | any checkout URL |
| `https://locallensmcp.vercel.app/#download` | `locallens.app/download` |
| `https://github.com/ashesbloom/locallens_mcp_agent/releases/latest` | `locallens.app/changelog` |
| `https://github.com/ashesbloom/locallens_mcp_agent/issues` | `locallens.app/feedback` |

Guarded by `test_no_dead_domain_in_shipped_prose` in
`tests/test_claude_instructions.py` and by `preflight_release.py`.

**Open item:** the pricing URL is a placeholder pending a dedicated Pro path.
It is defined once, as `PRICING_URL` in `src/mcp_server/license.py`. Swapping it
is a one-line change there — but note `claude_connector.py` also injects
`LOCALLENS_PRICING_URL` into Claude Desktop's config, and **that env value wins
over the code default on an existing install**, so a changed default does not
reach anyone who set up before the change.

## `mcp.latest` belongs to CI, not to the release commit

`scripts/set_version.py` deliberately does not write it. CI's
`update-version-manifest` job sets `mcp.latest` and `mcp.downloads` in a single
`jq` expression, in one commit, after the builds finish.

Both failure modes have shipped:

- **v1.0.30** — `latest` bumped while `downloads` still held the previous
  release's url + sha. That pair is self-consistent, so the checksum *verifies*
  and the tray silently reinstalls the **old** version.
- **v1.0.31** — right URL, empty `sha256`, so the silent path could not run at all.

`check_for_updates()` now discards download info whose URL does not contain
`v<latest>` or whose sha is blank, falling back to the browser. `preflight_release.py`
fails if a release commit bumped `mcp.latest`.

## Release notes were generated for 15 releases and never published

`set_version.py` has written `release_notes/release_notes_v*.md` since v1.0.16.
None of the three `softprops/action-gh-release@v2` upload steps passed
`body_path`, so `gh release view v1.0.31 --json body` returned `""` — every
release page was blank.

Published since v1.0.32 by the `update-version-manifest` job via
`gh release edit --notes-file`, deliberately **before** it publishes `mcp.latest`,
so nobody is offered an update whose page is still empty.

Publishing from that job rather than the upload jobs is also deliberate: the
three upload jobs run concurrently and would race for the same release body.

## The template must not wrap itself in a code fence

`release_notes_template.md` used to enclose the whole template in a ```` ```markdown ````
fence, which forced every inner fence to be escaped as `` \``` ``. The generator
stripped the outer fence but never the escapes, so v1.0.16–v1.0.31 all shipped
literal `` \```bash `` where a code block should be. Everything after the
`## GitHub Release Note Template` heading is now raw markdown.

### `---` under a text line is a heading, not a rule

v1.0.32 first published with its closing line — *"Built with privacy in mind."* —
rendered as a large H2. The generator `.strip()`s the template, so the notes file
ended mid-line, and CI's `cat >>` joined the `---` separator directly beneath that
text. Markdown reads `---` under a text line as a **setext H2 underline**.

Both ends are fixed (`printf '\n'` in the workflow, a trailing newline from the
generators). If you ever hand-edit a notes file, keep the blank line before any
`---`.

## Free vs Pro — get this right, it has been wrong in public

**Sort by People is FREE.** It runs through `start_sorting`, which carries no
`@require_pro`. Copy claiming otherwise shipped for months and led the assistant
to tell a user that deactivating Pro had disabled their People sort. It had not.

Only **batch enrolment through the assistant** (`add_face_enroll`) is Pro.

The gated set is exactly the functions decorated `@require_pro` in
`src/mcp_server/tools/pro_tools.py`. Treat the decorators as the source of truth
and every piece of prose — README, release notes, `locallens_help`, tray dialogs —
as something to check against them.

## Never state a price

No price string exists anywhere in this repo, by design. Point at the pricing
page and let the user read the number there. This applies to release notes, tool
output, tray dialogs and anything the assistant is handed.

## YAML block scalars and heredocs

In `release.yml`, a heredoc inside a `run: |` step must stay **indented to the
block scalar's level**. YAML strips the common indent, so bash still receives the
body at column 0. Flush-left content ends the scalar early, and a bare `---` then
parses as a second YAML document.

## Bundled installs cannot run pip

`sys.frozen` is **not** a reliable bundle test. py2app sets it in `__boot__.py`,
but Claude Desktop launches the connector as

```
dist/LocalLens Agent.app/Contents/MacOS/python -m mcp_server.main
```

which never executes `__boot__.py`. Every bundle user was therefore told to run
`pip install --upgrade locallens-mcp`, which cannot work for them. Use
`_is_bundled()` from `src/mcp_server/updater.py`, which also checks whether any
parent of `sys.executable` ends in `.app`.

## An undeclared dependency ships a dead feature, silently

`find_duplicates` was broken in **every build ever shipped**. `backend/main.py`
did `import imagehash` inside the endpoint body, against a package that appeared
in no requirements file — so the endpoint answered 501 for every user while
looking perfectly healthy from here.

Four layers all reported green, and it is worth knowing why each missed it:

- **PyInstaller / py2app** only *warn* about unresolved imports — and a deferred
  import inside a function body is not in the startup graph at all.
- **The CI smoke test** runs `--claude-status`, which walks the *startup* import
  graph. A function-level import does not execute until someone calls it.
- **pytest** never imported it either; the tests mock the backend.
- **The dev venv had the package.** This is the trap that makes it invisible: a
  build made locally works, and only CI's fresh venv reproduces the failure.

Gated since v1.1.2 by `scripts/check_optional_imports.py` — preflight check 7,
plus a `build-check.yml` step placed *before* `pip install`, because the script is
pure stdlib and fails in seconds. It fails when a third-party import is declared
in no dependency file. A module that is genuinely fine while undeclared goes in
its `ACKNOWLEDGED` map **with a reason**: `imagehash` was also wrapped in
`try/except ImportError`, and its except branch raised a 501 that killed a whole
feature. Guarded is not the same as harmless.

Two things it cannot see, by construction:

- **Transitive deps.** `fastapi` requires `starlette`, so importing starlette works
  though no file names it. Pass `--acknowledge starlette`.
- **A dependency's own optional extras.** `send2trash` chooses its Windows backend
  on whether `pywin32` imports, inside its own package — nothing here names it.
  That gap is exactly what produced the v1.1.2 UNC delete bug.

Run it against the backend repo too; that is where the dead features are:

```bash
python scripts/check_optional_imports.py \
  --source <path-to>/LocalLens/backend \
  --requirements <path-to>/LocalLens/backend/requirements.txt \
  --acknowledge starlette
```

As of 2026-08-22 that reports `reportlab`, `apscheduler` and `watchdog` — all
present in the dev venv, none in `requirements.txt`, so `export_report`'s PDF and
the scheduler daemon are dead in shipped builds for the imagehash reason.

## Shipped prose is application behaviour

`docs/TESTING.md` is a behavioural acceptance suite that pins **exact sentences**
from `@mcp.tool()` docstrings and the `instructions=` string in `main.py`.
Rewriting one for tone has already broken a test silently. Never tidy them as
part of a release. See "Trace before you change" in `CLAUDE.md`.

## Deploy path

Claude Desktop runs a **built copy** of this code, not `src/`. Source edits need
a rebuild (`pyinstaller locallens-mcp.spec` / `bash build_tray_mac.sh`) and a
Claude Desktop restart before they are observable in a real conversation.

## Licence Change Date — every release gets its own four years

BSL 1.1 converts a version to Apache 2.0 on its Change Date **or** the fourth
anniversary of its release, *whichever comes first*. v1.0.1–v1.0.32 shipped with
`Change Date: 2026-07-18`, set in a commit made that same day: the field was read
as "effective from". All of them converted within weeks, irrevocably. v1.0.0
(2029-06-01) and v1.0.33+ (2030-08-08) are unaffected.

Since 2026-10-01 `scripts/set_version.py` (and `set_version.js`, in lockstep)
writes `Licensed Work: LL Agent v<version>` (renamed from "LocalLens MCP Agent" in v1.5.0; the regex accepts both) and `Change Date: <today +
4 years>` into `LICENSE.md`, plus the same date into `NOTICE.md`. The step runs
first and aborts before writing anything if a line doesn't match (pinned by
`tests/test_license_bump.py`). `preflight_release.py` refuses the tag unless
the licence names this version and the date is at least 4 years minus 30 days
out. The website reads both values from the tagged `LICENSE.md`
(`locallensmcp/src/lib/latestVersion.ts`), so there is nothing to bump there.


## Ending the free preview has three license states, not two (v1.5.0)

The paid flip (`FREE_PREVIEW = False` + `_PREVIEW_CUTOFF`) left a free-preview user
with no key in a state nothing reported: `pro_features_unlocked()` let every Pro
tool run, but `get_license_info()` only knew "key" or "Free", so
`get_license_status` said "Pro features are locked", `locallens_help(topic="pro")`
pitched Pro, and the tray offered Activate Pro… — to the exact users promised Pro
for free. Caught by the `release-preflight` subagent, not by a test or the
script. `get_license_info()` now returns `preview_user: True` for that case, and
`status.py` and both trays branch on it (`tests/test_free_preview.py`). Any future
change to who gets Pro must be checked against what each surface *says*, not only
against what the gate *does*.

## Tests must not read the current LICENSE.md line verbatim

`set_version.py` rewrites the Licensed Work line on every release, so a test that
`.replace()`s one exact version string silently no-ops after the next bump and
fails during the release itself (v1.5.0). Match the line with a regex.

## Tests that call a Pro tool must unlock it themselves

Since the paid flip, whether a Pro tool runs depends on the machine's install stamp.
The dev Mac predates the cutoff, so a test that drives a `@require_pro` tool passes
locally and fails on a fresh CI runner (v1.5.0: `test_delete_duplicates_sends_canonical_paths_and_guidance_on_windows`,
caught by CI Build Check *after* the tag). Patch `mcp_server.license.pro_features_unlocked`
in any test that is not about licensing, and before tagging run the suite once with
`HOME=$(mktemp -d)` to see what CI sees.
