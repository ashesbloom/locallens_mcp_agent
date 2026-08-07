# Spec — Settings → License & Plans (LocalLens desktop app)

**Status:** handoff. Implement in the **backend/desktop repo**, not here.
**Why it exists:** the assistant told a user to "check inside LL → Settings →
License/Plans", a screen that does not exist. The MCP side and the tray now answer
this properly; the desktop app is the remaining gap.

## Rules that must not be broken

1. **Never state a price in code.** No price is defined anywhere in the MCP repo, and
   asserting one is exactly the failure this work fixed. Read it from your pricing
   source or link out.
2. **The website is a suggestion, never a data source.** Show the URL, let the user
   click it. Nothing in the app should fetch, scrape or summarise the site.
3. **The in-app route is primary**, the website is secondary. Upgrade/activate lives in
   the app; the pricing page is a trailing "see plans" link.
4. **Do not nag.** Show the website suggestion during onboarding only. A returning user
   opening this panel wants their licence state, not marketing.

## Panel contents

| Field | Source |
|---|---|
| Plan (Free / Pro) | `mcp_license.json` → `tier` |
| Activated on | `mcp_license.json` → `activated_at` |
| Machine binding | `mcp_license.json` → `machine_id` (state that it is machine-locked) |
| Feature matrix | Mirror the Free/Pro split below |
| Actions | `Activate licence…` (key input) · `Manage / See plans` → `LOCALLENS_PRICING_URL` |

Read the cache directly (`~/.config/LocalLens/mcp_license.json`, or `%APPDATA%\LocalLens\`
on Windows). It is written by `activate_pro_license` in the MCP and is the single source
of truth for tier.

## Feature matrix (keep in sync with `locallens_help(topic="pro")`)

**Free** — sort by Date, sort by Location, **sort by People**, find & group (including by
person), see enrolled people, folder analysis, saved path presets, open folder,
stats & status.

**Pro** — batch face enrolment (`add_face_enroll`), duplicate detection, duplicate
cleanup, export reports, smart album suggestions, scheduled auto-organize, active
folders, scheduler dashboard.

> **Sort by People is FREE.** It runs through `start_sorting`, which carries no
> `@require_pro`. Copy claiming otherwise shipped for months and led the assistant to
> tell a user that deactivating Pro had disabled their People sort — it had not. Only
> *bulk enrolment through the assistant* is Pro.

The gated set is exactly the tools decorated with `@require_pro` in
`src/mcp_server/tools/pro_tools.py` — treat the decorators as the source of truth and
the prose as something that must be checked against them.

## Configuration

`LOCALLENS_PRICING_URL` — pricing page. Default `https://locallensmcp.vercel.app/#pricing`.
Defined once in `src/mcp_server/license.py`; the Claude Desktop connector also injects it
into the MCP server's env block, and **that env value overrides the code default** on an
existing install.

## Done when

- A Free user sees their tier, the feature split, and one non-pushy "see plans" link.
- A Pro user sees tier, activation date, and that the licence is machine-locked — with no
  upgrade prompt at all.
- No price string appears anywhere in the app's source.
