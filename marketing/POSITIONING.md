# LocalLens MCP — Positioning

> Grounded in what's actually shipped (see `for LLM's/README.md`, `docs/TESTING.md`, `src/mcp_server/tools/`). No invented features.

## Core positioning

**LocalLens is the first privacy-first photo organizer you talk to instead of click through** — via an MCP server that plugs into Claude Desktop, Cursor, or any MCP-speaking client, with every operation running 100% on-device.

Two things compound into one pitch:
1. LocalLens already does local face recognition, geo-sorting, duplicate detection, and scheduled auto-organizing.
2. It's exposed as a standard **MCP server**, not a proprietary chat widget — so it rides the same wave every agentic AI client is standardizing on, for free, going forward.

## Taglines (pick one per surface)

- "Your photos. Your machine. Your words." (site hero — echoes existing README line "Your Memories, Your Machine, Your Privacy")
- "Sort your photos by asking, not clicking."
- "The photo organizer that plugs into your AI assistant — not the other way around."
- "MCP-native. Cloud-free. Face-recognition included."

## Who it's for

- Privacy-conscious users already using Claude Desktop / Cursor who want their photo library reachable from the same chat window.
- People with large, messy photo libraries (10k+ photos) who want natural-language multi-filter search ("Vidushi's 2025 Lucknow photos") instead of manual folder-diving.
- Anyone burned by cloud photo AI (Google Photos, iCloud) wanting equivalent AI convenience with zero upload.

## Comparison angle

| | LocalLens MCP | Cloud photo AI (Google Photos / iCloud) | Generic local photo app |
|---|---|---|---|
| Face recognition, geo-sort | ✅ local | ✅ cloud-processed | ❌ or manual only |
| Natural-language / AI-assistant control | ✅ via MCP, any client | ✅ but locked to their app | ❌ |
| Data ever leaves device | ❌ never (one-time license check only) | ✅ always | ❌ n/a but no AI either |
| Works in Claude Desktop / Cursor today | ✅ | ❌ | ❌ |
| Scheduled autonomous organizing | ✅ (`schedule_auto_organize`) | ✅ | ❌ |

The row that matters most: **"AI-assistant control that works in Claude Desktop / Cursor today."** No cloud photo product can claim that — they're closed ecosystems. That's the wedge.

## What NOT to claim yet

- **No "smart album" / AI curation claims.** `smart_album_suggestions` is registered as a tool but isn't ready to promote — don't imply proactive album discovery is a current feature.
- **No "local AI chat" / Ollama UI claims.** `chat_ui.py` exists in the repo but isn't a finished, supported surface — don't market a local chatbot experience until it actually is one.
- **Copy/move mode is not a differentiator.** Every file manager has copy vs. move. Don't lead with it — it only matters as one ingredient in the guardrails story below, not as a headline feature.

## Sharper examples (grounded, "old way vs. new way")

- **Multi-person enrollment in one message:** "here's Priya's folder, here's Raj's, enroll both" → one `add_face_enroll` call, not a one-person-at-a-time tagging wizard.
- **Judgment-based duplicate cleanup:** "show me what's over 95% similar before deleting anything" → staged `find_duplicates` → confirm → `delete_duplicates`, not a blind "delete all duplicates" button.
- **Mid-job abort by just saying stop:** no more force-quitting the app to cancel a runaway sort.
- **Schedules you edit by talking, not by re-opening settings:** "pause that Sunday job for two weeks" — the assistant already knows which job from the conversation.
- **Works from inside Cursor mid coding-session**, not just a dedicated photo app — "clean up my screenshots folder" without alt-tabbing anywhere.

## Objection handling

- *"Isn't giving an LLM access to my files risky?"* → Guardrails are the answer, not a caveat: copy-mode default, source≠destination check, path-hallucination prevention, explicit confirmation before `move`. Frame these as the product, not fine print (see `docs/TESTING.md` Marketing Needed section).
- *"Why would I trust local face recognition?"* → Machine-locked license, encrypted face encodings, purge endpoint (`DELETE /api/metadata-store/purge`) — the privacy audit (`for LLM's/privacy_audit_and_disclaimer_plan.md`) already closed every item on this.
