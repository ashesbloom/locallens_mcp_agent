# Launch checklist — LocalLens Pro paid tier

Work top to bottom. Later phases depend on earlier ones.
Pricing rationale lives in [PRICING.md](PRICING.md); don't re-litigate it here.

---

## Phase 0 — Already done (in code, verified)

- [x] Pricing decided and recorded in `docs/PRICING.md`
- [x] Regional bands + geo routing built on the website (`locallensmcp/`)
- [x] `/api/public/geo` endpoint — tested for IN/US/BR/PL/unknown/no-header
- [x] Seven stale "one-time purchase, no subscription" claims removed (5 Python, 2 website)
- [x] BSL Change Date bumped `2026-07-18` → `2030-08-08`; `Licensed Work` scoped to
      `v1.0.33 and later`; the `"Lemon Squeezy URL here "` placeholder replaced
- [x] `pytest` 196 passing · `tsc --noEmit` clean · `eslint` clean on changed files

**Nothing is committed.** Both repos have working-tree changes. `locallensmcp/` is a
separate nested git repo and needs its own commit.

---

## Phase 1 — Decisions only you can make (5 minutes)

- [ ] **Founding window close date.** 60 days from launch is the default. You need one
      concrete date; it goes in three places (Lemon Squeezy, `pricing.ts`, `PRICING.md`).
- [ ] **Confirm ₹249/year** for Band D, or say otherwise. Nets ~$2.24 after fees.

---

## Phase 2 — Lemon Squeezy (about an hour)

- [ ] **Reply to the onboarding email.** Draft is in the plan file / ask for it again.
      Include the two questions: can Band D charge in INR, and confirm redemption caps.
- [ ] **Create Product 1 — "LocalLens Pro"** (subscription), six variants:
      `A Monthly $4.99` · `A Annual $49` · `B Monthly $2.99` · `B Annual $29` ·
      `C Annual $19` · `D Annual ₹249`
- [ ] **Create Product 2 — "LocalLens Pro — Lifetime"** (one-time payment), four variants
      at **list** price: `A $98` · `B $58` · `C $38` · `D ₹498`
- [ ] **Enable license key generation on all ten variants.** Activation limit **3**.
- [ ] **Create the `FOUNDING100` discount:**
      - 50% off
      - `max_redemptions: 100`
      - `expires_at:` your Phase 1 date
      - limited to the four **Lifetime** variants only
- [ ] **Test the cap before trusting it.** In test mode, temporarily set
      `max_redemptions: 2`, buy twice, confirm the third attempt is rejected. Then set
      it back to 100.
- [ ] **Copy the ten variant UUIDs** from each checkout URL (`/buy/<uuid>`).

---

## Phase 3 — Wire the website (15 minutes)

In `locallensmcp/src/content/pricing.ts`:

- [ ] Paste the UUIDs into `BAND_PRICING` — `lifetimeVariant` and `annualVariant` per band.
      Until these are filled, the Buy button deliberately stays inert (`checkoutUrl()`
      returns `"#"` on an empty string), so a half-configured store cannot ship a dead link.
- [ ] Replace the `FOUNDING_OFFER_ACTIVE = true` boolean with the date form:

```ts
/** Must match expires_at on the FOUNDING100 discount in Lemon Squeezy. */
const FOUNDING_ENDS_AT = "2026-10-07T00:00:00Z";
export const FOUNDING_OFFER_ACTIVE = Date.now() < Date.parse(FOUNDING_ENDS_AT);
```

**Contact form** — never covered by this checklist before, and it is the only way a
buyer can reach you about a key. It fails *quietly*: with either variable unset the
route returns a clean `500 "Contact form is not configured."` and nothing is logged
anywhere you'd notice.

- [ ] Set `RESEND_API_KEY` and `CONTACT_TO_EMAIL` in Vercel **production** env
- [ ] Verify a sending domain in Resend, then move `from:` in
      `src/routes/api/public/contact.ts` off the shared `onboarding@resend.dev`. Until a
      domain is verified, Resend only delivers to the account owner's own address, and
      mail from the shared sender lands in spam far more often.
- [ ] Submit a real message on the live site; confirm it arrives and that **Reply** goes
      back to the sender (the route sets `reply_to`, not `from`)

- [ ] `npx tsc --noEmit` and `npm run lint`
- [ ] Commit in `locallensmcp/` (separate repo) and deploy
- [ ] **Verify live:** load `/pricing` from two countries (or two VPN exits) inside the same
      hour and confirm each sees its own price — this proves the ISR cache isn't pinning
      one band for everyone

---

## Phase 4 — End-to-end purchase test (30 minutes)

- [ ] Buy a Lifetime variant in Lemon Squeezy **test mode**
- [ ] Confirm the license key arrives by email
- [ ] `activate_pro_license(license_key="...")` in Claude Desktop
- [ ] Confirm `~/.config/LocalLens/mcp_license.json` is written
- [ ] `get_license_status` reports Pro
- [ ] Run `find_duplicates` (a `@require_pro` tool) and confirm it executes
- [ ] Refund the test order and confirm the key is revoked

---

## Phase 5 — The open question about enforcement

- [ ] **Does the shipping backend gate the Pro endpoints?**

The backend copy at `../Local Lens/ll codebase/` is dated **6 May 2026**, has **zero**
license logic, and doesn't contain `/api/find-duplicates` at all — its routes stop at
sorting, faces and presets. So it predates your Pro features and proves nothing about
what ships today. Check the current backend.

If it does **not** gate them, then deleting `@require_pro` from the MCP server yields full
Pro. Be aware this is not fully fixable: the backend also runs on the user's machine, so
there is no location in a 100%-local product that the user cannot edit. See PRICING.md.
The realistic mitigations are already in play — low price, current BSL, frozen binaries.

**Do not** add cache signing, obfuscation, or a phone-home check. Each costs real time,
breaks the offline promise, annoys paying customers, and stops nobody who can delete the
verifying code.

---

## Phase 6 — Release (the BSL date depends on this)

- [ ] **Bump `MCP_VERSION` to `1.0.33`** in `src/mcp_server/updater.py` (currently
      `1.0.32`). **This matters:** `LICENSE.md` now reads *"Licensed Work: LocalLens MCP
      Agent v1.0.33 and later"*. Until 1.0.33 ships, the new 2030 Change Date protects
      nothing — v1.0 through v1.0.32 converted to Apache 2.0 on 2026-07-18 and cannot be
      clawed back.
- [ ] `python -m pytest tests/ -v`
- [ ] `python scripts/preflight_release.py`
- [ ] Run the `release-preflight` agent (it greps for hardcoded prices and dead domains)
- [ ] Commit and tag `v1.0.33`

---

## Phase 7 — Ongoing

- [ ] **Watch the founding count.** Lemon Squeezy stops the code at 100, but the website
      has no idea and keeps advertising the offer. When it sells out, set
      `FOUNDING_ENDS_AT` to a past date and redeploy.
- [ ] **Before the first subscription renews**, implement `expires_at` enforcement —
      see the licensing section of `PRICING.md`. Lifetime-only launch does not need it.
