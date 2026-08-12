# Launch checklist — LocalLens Pro paid tier

Work top to bottom. Later phases depend on earlier ones.
Pricing rationale lives in [PRICING.md](PRICING.md); don't re-litigate it here.

---

## Phase 0 — Already shipped (committed and pushed)

- [x] Pricing decided and recorded in `docs/PRICING.md`
- [x] Regional bands + resolved-offer routing built on the website (`locallensmcp/`) —
      `/api/public/offer` returns one resolved price, never a band letter; the band map
      itself lives server-only in `src/server/pricing.ts`, kept out of the client bundle
      by `importProtection` in `vite.config.ts`
- [x] Contact-sheet pricing page (`src/components/site/Pricing.tsx`) with the two
      purchase paths (lifetime-during-founding-window / annual after, plus an optional
      monthly frame gated by `MONTHLY_ENABLED`)
- [x] Seven stale "one-time purchase, no subscription" claims removed (5 Python, 2
      website); Smart Album Suggestions removed from all marketing surfaces (it returns
      `{"status": "coming_soon"}` — was being sold as live in 12 places)
- [x] License expiry enforcement shipped — `src/mcp_server/license.py`: lifetime keys
      (`expires_at: null`) never re-check; subscriptions get a 7-day pre-expiry refresh
      window and a 14-day offline grace before locking. 9 dedicated tests in
      `tests/test_license_expiry.py`
- [x] BSL Change Date bumped `2026-07-18` → `2030-08-08`; `Licensed Work` scoped to
      `v1.0.33 and later`; the `"Lemon Squeezy URL here "` placeholder replaced
- [x] `MCP_VERSION` bumped to `1.0.33` and released — `v1.0.33` is tagged, so the 2030
      Change Date now actually protects something (commits `7900d04`, `a903c01`)
- [x] `pytest` 205 passing · `tsc --noEmit` clean · `eslint` clean
- [x] Both repos committed and pushed to `origin/main`; `locallensmcp/` now auto-deploys
      to Vercel via GitHub Actions on push

**What Phase 0 does *not* include:** a working purchase. All ten Lemon Squeezy variant
UUIDs are still empty strings, so every Pro CTA resolves to `checkoutUrl() === "#"` by
design. Nobody can buy anything yet — see Phase 2.

---

## Phase 1 — Decisions

- [x] **Band D price.** ₹249/year, confirmed and shipped in `BAND_PRICING`. Nets ~$2.24
      after Lemon Squeezy fees.
- [ ] **Founding window close date.** Still open, and deliberately *not* to be set yet —
      see Phase 2. `FOUNDING_ENDS_AT` in `src/server/pricing.ts` currently holds a
      placeholder (`2026-10-07T00:00:00Z`) that must not be mistaken for a real deadline.

---

## Phase 2 — Lemon Squeezy rejected the store application (current blocker)

**2026-08-12: Lemon Squeezy declined the application.** Their stated reason: no live
public site, no social presence, no customer base to underwrite yet. This is standard
merchant-of-record vetting — Tanay's reply explicitly invites resubmission once those
exist. Decision made: build the presence, then reapply, rather than switch processors.

- [ ] Publish the site somewhere it's actually reachable from — repo description/
      homepage on GitHub at minimum
- [ ] Stand up at least one public channel (README + stars, a Show HN / Product Hunt /
      relevant subreddit post — the free tier needs no purchase, so this alone can
      generate real users)
- [ ] Once there's something concrete, reply to Tanay with it and resubmit

### Free preview — the current operating state

Since nothing can be sold, nothing is gated. **Every Pro feature is unlocked for
everyone**, controlled by two flags that must always agree:

| Flag | File | Effect |
|------|------|--------|
| `FREE_PREVIEW` | `src/mcp_server/license.py` | `pro_features_unlocked()` returns true, so `@require_pro` is a no-op on all ten Pro tools |
| `FREE_PREVIEW` | `locallensmcp/src/content/pricing.ts` | `resolveOffer()` returns one free offer to everyone, before it reads `country` |

**Flip both in the same change**, together with the variant UUIDs. The site giving Pro
away while the MCP still refuses a tool — or the reverse — makes a liar of both.

Deliberate properties of this state, so they aren't mistaken for bugs later:

- `is_pro_active()` is untouched and still reports the honest answer, so
  `get_license_status` and the tray don't tell people they own a license they never
  bought. Expiry enforcement stays live and tested (`tests/test_free_preview.py` pins
  this separation).
- The pricing page shows no price at all, in any region. Regional discretion is moot
  while there's nothing to discreetly price — and the band map is tree-shaken out of
  even the server bundle.
- The Pro CTA points at `/#download` instead of a dead `"#"` checkout link.
- The founding line is hidden (`founding: null`) — no countdown against a store that
  can't take an order.

**Guardrail:** `FOUNDING_ENDS_AT` is a wall-clock constant that ticks whether or not a
store exists. Don't set it to a real date until Lemon Squeezy actually approves — that's
the first step of Phase 3. It's currently inert (the preview short-circuits before it's
read), but it becomes live the instant `FREE_PREVIEW` flips, so check it's still in the
future at that moment.

### Grandfathering — decided

**Nobody who used LocalLens during the preview ever pays.** They keep every Pro feature
permanently, free. Advertised on the site; full reasoning and the rejected alternatives
are in [PRICING.md](PRICING.md) under *Free preview — grandfathering*.

Two mechanisms, both generous by default:

- **Automatic** — `installed_before_cutoff()` in `src/mcp_server/license.py` reads the
  `onboarded_at` stamp in `~/.config/LocalLens/mcp_onboarded.json`. Predates
  `_PREVIEW_CUTOFF` → Pro stays unlocked, with no key and no network call. A missing or
  unreadable marker counts as **eligible**, on purpose.
- **Manual claim** — contact form, no proof required, for anyone who reinstalled or
  changed machine.

This is why `pro_features_unlocked()` keeps working after `FREE_PREVIEW` flips off: the
cutoff check is a second, permanent clause inside it, not part of the preview switch.

---

## Phase 3 — Lemon Squeezy store setup (once approved)

Full step-by-step for undoing the preview is in
[RESTORING_PAID_MODE.md](RESTORING_PAID_MODE.md) — follow that, not memory.

- [ ] **Set `_PREVIEW_CUTOFF`** in `src/mcp_server/license.py` to the paid-launch date
      **before** flipping either `FREE_PREVIEW`. Order matters: flip the preview off with
      no cutoff set and every existing user loses the grandfathering they were promised.
- [ ] **Confirm the founding window close date** now that there's a real timeline, and
      set it in three places: Lemon Squeezy, `FOUNDING_ENDS_AT` in `src/server/
      pricing.ts`, and `docs/PRICING.md`
- [ ] **Create Product 1 — "LocalLens Pro"** (subscription), six variants:
      `A Monthly $4.99` · `A Annual $49` · `B Monthly $2.99` · `B Annual $29` ·
      `C Annual $19` · `D Annual ₹249`
- [ ] **Create Product 2 — "LocalLens Pro — Lifetime"** (one-time payment), four variants
      at **list** price: `A $98` · `B $58` · `C $38` · `D ₹498`
- [ ] **Enable license key generation on all ten variants.** Activation limit **3**.
- [ ] **Create the `FOUNDING100` discount:**
      - 50% off
      - `max_redemptions: 100`
      - `expires_at:` the date confirmed above
      - limited to the four **Lifetime** variants only
- [ ] **Test the cap before trusting it.** In test mode, temporarily set
      `max_redemptions: 2`, buy twice, confirm the third attempt is rejected. Then set
      it back to 100.
- [ ] **Copy the ten variant UUIDs** from each checkout URL (`/buy/<uuid>`).

---

## Phase 4 — Wire the website (15 minutes)

In `locallensmcp/src/server/pricing.ts` (not `content/pricing.ts` — the band map and
variant IDs are server-only, enforced by `importProtection`):

- [ ] Paste the UUIDs into `BAND_PRICING` — `lifetimeVariant`, `annualVariant`, and
      (if `MONTHLY_ENABLED`) `monthlyVariant` per band. Until filled, the Buy button
      deliberately stays inert (`checkoutUrl()` returns `"#"` on an empty string), so a
      half-configured store can't ship a dead link that looks live.
- [ ] Confirm `FOUNDING_ENDS_AT` (set in Phase 3) is correct — `isFoundingOpen()` reads
      it fresh on every request, so no redeploy is needed for the window to close, only
      for it to open with the right date.
- [ ] Decide separately whether to flip `MONTHLY_ENABLED` to `true` — it's independent
      of the founding date and gated behind `pricing.monthly !== null` per band (Bands
      C/D have no monthly regardless: a ₹79/month charge loses ~60% to Lemon Squeezy's
      flat $0.50 fee).

**Contact form** — the only way a buyer can reach you about a key. It fails *quietly*:
with either variable unset the route returns a clean `500 "Contact form is not
configured."` and nothing is logged anywhere you'd notice.

- [ ] Set `RESEND_API_KEY` and `CONTACT_TO_EMAIL` in Vercel **production** env
- [ ] Verify a sending domain in Resend, then move `from:` in
      `src/routes/api/public/contact.ts` off the shared `onboarding@resend.dev`. Until a
      domain is verified, Resend only delivers to the account owner's own address, and
      mail from the shared sender lands in spam far more often.
- [ ] Submit a real message on the live site; confirm it arrives and that **Reply** goes
      back to the sender (the route sets `reply_to`, not `from`)

- [ ] `npx tsc --noEmit` and `npm run lint`
- [ ] Commit in `locallensmcp/` (separate repo) — CI deploys automatically on push
- [ ] **Verify live:** load `/pricing` from two countries (or two VPN exits) inside the
      same hour and confirm each sees its own price — this proves the ISR cache isn't
      pinning one band for everyone

---

## Phase 5 — End-to-end purchase test (30 minutes)

- [ ] Buy a Lifetime variant in Lemon Squeezy **test mode**
- [ ] Confirm the license key arrives by email
- [ ] `activate_pro_license(license_key="...")` in Claude Desktop
- [ ] Confirm `~/.config/LocalLens/mcp_license.json` is written, with `expires_at`
      present in the shape `_parse_expiry()` expects (this has only been tested against
      documented Lemon Squeezy response shape, never a live one — first real chance to
      confirm it)
- [ ] `get_license_status` reports Pro
- [ ] Run `find_duplicates` (a `@require_pro` tool) and confirm it executes
- [ ] Refund the test order and confirm the key is revoked

---

## Phase 6 — The open question about enforcement

- [ ] **Does the shipping backend gate the Pro endpoints?**

The backend copy at `../Local Lens/ll codebase/` is dated **6 May 2026**, has **zero**
license logic, and doesn't contain `/api/find-duplicates` at all — its routes stop at
sorting, faces and presets. So it predates the Pro features and proves nothing about
what ships today. Check the current backend.

If it does **not** gate them, then deleting `@require_pro` from the MCP server yields full
Pro. Be aware this is not fully fixable: the backend also runs on the user's machine, so
there is no location in a 100%-local product that the user cannot edit. See PRICING.md.
The realistic mitigations are already in play — low price, current BSL, frozen binaries.

**Do not** add cache signing, obfuscation, or a phone-home check. Each costs real time,
breaks the offline promise, annoys paying customers, and stops nobody who can delete the
verifying code.

---

## Phase 7 — Release ✅ done for the code that exists today

`v1.0.33` already shipped the license-expiry enforcement and the pricing page (commits
`7900d04`, `a903c01`). That release does **not** include a working purchase flow — that
still needs Phases 2–5. No further version bump is required purely for BSL reasons: the
Licensed Work is scoped to "`v1.0.33` and later," so every subsequent release already
qualifies without re-editing `LICENSE.md`.

When the purchase flow itself ships (Phases 3–5 done), a normal release still makes
sense for changelog/visibility reasons — just via the existing release pipeline, not as
a licensing gate:

- [ ] `python -m pytest tests/ -v`
- [ ] `python scripts/preflight_release.py`
- [ ] Run the `release-preflight` agent (it greps for hardcoded prices and dead domains)
- [ ] Commit and tag the next version

---

## Phase 8 — Ongoing

- [x] ~~Implement `expires_at` enforcement before the first subscription renews~~ — done
      in Phase 0, ahead of schedule (needed for `MONTHLY_ENABLED` to be safe to flip at
      all)
- [ ] **Watch the founding count.** Lemon Squeezy stops the code at 100, but the website
      has no idea and keeps advertising the offer. When it sells out, set
      `FOUNDING_ENDS_AT` to a past date and redeploy.
- [ ] **Watch the founding date generally**, not just the count — see the Phase 2
      guardrail. A date that already passed silently converts Lifetime to Annual and
      drops the founding banner; nothing alerts you when that happens.
