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

## Shipped prose is application behaviour

`docs/TESTING.md` is a behavioural acceptance suite that pins **exact sentences**
from `@mcp.tool()` docstrings and the `instructions=` string in `main.py`.
Rewriting one for tone has already broken a test silently. Never tidy them as
part of a release. See "Trace before you change" in `CLAUDE.md`.

## Deploy path

Claude Desktop runs a **built copy** of this code, not `src/`. Source edits need
a rebuild (`pyinstaller locallens-mcp.spec` / `bash build_tray_mac.sh`) and a
Claude Desktop restart before they are observable in a real conversation.
