# Restoring paid mode

> How to end the free preview and turn the paid tier back on.
>
> **Nothing was deleted to build the preview.** The band map, the Lemon Squeezy
> checkout builder, `FOUNDING100`, all ten variant slots, `pro_upgrade_message()` and
> its five guarding tests, the Pro/paid copy in the tray, and the Band A list-price
> offer are all still in the tree, intact and unreached. Restoring paid mode changes
> **constants**, not logic. If you find yourself rewriting a function, stop — you have
> missed the flag that already does it.

Work top to bottom. Steps 1–3 are ordered for a reason.

---

## 1. Set the grandfathering cutoff — BEFORE anything else

`src/mcp_server/license.py`

```python
_PREVIEW_CUTOFF: Optional[str] = "2027-01-15T00:00:00Z"   # the paid-launch date
```

**This must happen before step 2.** `installed_before_cutoff()` returns `True` for
everyone while the cutoff is `None` (no launch has happened, so nobody arrived after
it). Flip `FREE_PREVIEW` off with the cutoff still unset and the gate stays open for
the whole world — the paid tier simply does not exist.

The reverse order is worse in the other direction: set a cutoff of *today* and every
free-preview user is instantly reclassified as post-launch and loses Pro. That breaks
the promise in [PRICING.md](PRICING.md) — *Free preview — grandfathering*. Use the
actual launch date, not the date you happen to be editing.

Guarded by `tests/test_free_preview.py::test_preview_user_keeps_pro_after_the_preview_ends`
and `::test_no_cutoff_set_means_nobody_has_arrived_late`.

## 2. Flip both preview flags — in the same commit

| File | Change |
|------|--------|
| `src/mcp_server/license.py` | `FREE_PREVIEW = False` |
| `locallensmcp/src/content/pricing.ts` | `export const FREE_PREVIEW = false;` |

They must move together. The site advertising a free product while the MCP refuses a
tool — or the site quoting a price for something the MCP gives away — makes a liar of
both. There is no test that can catch this; the repos are separate.

Flipping the website flag alone restores, with no further edits: the regional band
resolution, the `$49`/`₹249` frames, the Founding-100 line, the `claim →` / `get pro →`
CTAs, and the "wrong currency?" link (it is wrapped in `{!FREE_PREVIEW && …}`, not
deleted).

## 3. Fill in the Lemon Squeezy store details

`locallensmcp/src/server/pricing.ts`

- [ ] Paste the ten variant UUIDs into `BAND_PRICING` (`lifetimeVariant`,
      `annualVariant`, `monthlyVariant` per band). Empty strings make `checkoutUrl()`
      return `"#"` — that is the guard against shipping a dead checkout, not a bug.
- [ ] Set `FOUNDING_ENDS_AT` to the same date as the `FOUNDING100` discount's
      `expires_at` in Lemon Squeezy. It currently holds a stale placeholder
      (`2026-10-07`) that is inert only because the preview short-circuits before it is
      read — it goes live the instant step 2 lands.
- [ ] Decide `MONTHLY_ENABLED`. Independent of everything above. Enforcement is ready
      and tested (`tests/test_license_expiry.py`); bands C and D stay annual-only
      regardless.
- [ ] Update `FALLBACK_OFFER`'s founding label in
      `locallensmcp/src/content/pricing.ts` to match `FOUNDING_ENDS_AT`. It reads from
      `LIST_PRICE_OFFER`, which is already the correct Band A shape — only the date
      string inside it needs to agree.

## 4. Revert the preview-specific copy

Each of these has the paid original preserved next to it as a comment or in the
non-preview branch. None needs rewriting.

| File | What to restore |
|------|-----------------|
| `locallensmcp/src/routes/pricing.tsx` | `SITE_DESCRIPTION` — the paid version is commented directly above the preview one |
| `locallensmcp/src/content/copy.ts` | `titleSecond` and `contact.sub` are already the paid strings; the preview ones are separate keys (`titleSecondPreview`, `contactSubPreview`) selected by the flag, so step 2 reverts them automatically |
| `locallensmcp/src/components/site/PreviewBanner.tsx` | Renders `null` when `FREE_PREVIEW` is false — no edit needed |
| `src/tray/tray_mac.py`, `tray_win.py` | Plan screen — the paid text lives in the `else` branch and returns automatically |
| `src/mcp_server/tools/status.py` | `unlocked` / `tier_label` revert with the flag; the `pro_pitch` and `pro_showcase` dicts were never removed |
| `src/mcp_server/tools/pro_tools.py` | Ten docstrings carry `(FREE right now — …)` — seven as `⚡ PRO FEATURE …`, three (`list_schedules`, `open_scheduler_dashboard`, `manage_schedule`) as `⚡ PRO …`. Plus the FREE PREVIEW paragraph in the module docstring. **All hand-written, not flag-driven.** Strip back to `⚡ PRO FEATURE —` / `⚡ PRO —` respectively; the rest of each docstring is untouched |

The `pro_tools.py` docstrings are the one place with no automatic reversion. That is
deliberate: a docstring is read once at import, so making it conditional would mean
building strings at registration time and losing the plain-text greppability that
`docs/TESTING.md` relies on.

## 5. Clear the stale store URL

Your local Claude Desktop config sets
`LOCALLENS_STORE_URL=https://locallens.lemonsqueezy.com`, a store that never existed.
Harmless while upgrade prompts are unreachable; wrong the moment they come back. Fix it
in `claude_desktop_config.json`, or drop the override and let `license.py`'s default
apply.

## 6. Verify

```bash
python -m pytest tests/ -v
grep -rnE '(\$|₹|USD|INR|€|£)[[:space:]]*[0-9]' src/     # must be empty

cd locallensmcp && npx tsc --noEmit && npm run lint
npm run build
grep -raF -- '₹249' .output/public/    # must be EMPTY     (client bundle)
grep -raF -- '₹249' .output/server/    # must NOT be empty (server bundle)
```

**The second grep flips meaning at step 2.** During the preview it is empty, because
`FREE_PREVIEW` is a `const true` and the bundler proves the band map unreachable and
drops it from the server bundle too. Once the flag is false the map is reachable again
and must reappear. An empty result *after* restoring paid mode means the flag did not
actually flip.

Then, in the browser: `/pricing` shows a real price, `?country=IN` shows ₹249, and the
CTA opens a live Lemon Squeezy checkout rather than `#`.

Finally, run one real test-mode purchase end to end — see
[LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) Phase 5. `expires_at` parsing has only ever
been tested against Lemon Squeezy's *documented* response shape, never a live one.
