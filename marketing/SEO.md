# LocalLens MCP — SEO Notes

## Target keywords (by intent)

**High-intent, low-competition (MCP is new — own these early):**
- "MCP photo organizer"
- "Claude Desktop photo sorting"
- "MCP server for photos"
- "local photo organizer MCP"
- ~~"Cursor photo management tool"~~ — **not yet.** No Cursor integration ships (see
  the site repo's `marketing/CLAIMS.md`). Reinstate when it does.

**Category / comparison intent:**
- "privacy-first photo organizer" (already used in existing README — reuse verbatim for consistency)
- "offline face recognition photo sorter"
- "photo organizer no cloud upload"
- "local alternative to Google Photos AI"

**Feature intent:**
- "sort photos by face recognition locally"
- "find duplicate photos offline"
- "auto organize photos by location"
- "ai photo organizer without uploading"

## Page-level suggestions

- **Landing page `<title>`**: "LocalLens — Sort Your Photos by Talking to Claude, 100% Offline"
- **Meta description** (≤160 chars): "LocalLens is a local, privacy-first photo organizer you control from Claude Desktop via MCP. Face recognition, geo-sort, duplicate cleanup — zero cloud."
  > The site repo's `marketing/AI-VISIBILITY.md` is the canonical source for this string —
  > it is what `routes/__root.tsx` and `lib/seo.ts` are kept in sync with. Edit it there first.
- **`/mcp` or `/claude` landing page**: dedicated page targeting "MCP photo organizer" / "Claude Desktop photo tool" — this is the least contested keyword cluster right now since MCP adoption is early; a first-mover page here can rank fast.

## Structured content ideas (own the "MCP + photos" niche before others do)

- A comparison table page: "LocalLens vs Google Photos vs Apple Photos — privacy & AI control" (feeds the COMPARISON table in `POSITIONING.md`).
- A "What is MCP?" explainer page linking back to LocalLens — captures searchers learning about MCP generally, not just LocalLens specifically.
- Changelog/release posts should keep mentioning "MCP server" and "Claude Desktop" by name in the first paragraph — search engines and LLM answer engines (Perplexity, ChatGPT browsing) weight early keyword placement.

## LLM-answer-engine visibility (new SEO surface, worth calling out)

Because this product IS an MCP server, it's likely to get cited by name inside Claude/other assistants answering "how do I connect my photos to Claude." Make sure:
- `for LLM's/README.md` and `docs/TESTING.md` framing (already precise and structured) is mirrored in public docs — LLMs training/browsing on clear, structured markdown cite it more readily than marketing fluff.
- The GitHub repo README states plainly, near the top: "LocalLens MCP is a Model Context
  Protocol (MCP) server that connects a local, privacy-first photo library to Claude Desktop
  and other MCP clients." — exact-phrase matching helps both classic SEO and LLM retrieval.
  Do **not** restore the earlier wording that named Cursor: it was never true, the README
  never adopted it, and an inaccurate description is worse than a narrow one when answer
  engines quote it verbatim.
