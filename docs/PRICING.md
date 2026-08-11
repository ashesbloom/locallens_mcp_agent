# Pricing — LocalLens Pro

**Status:** canonical. Decided 2026-08-08.
**Authority:** Lemon Squeezy is the source of truth for what a customer is actually charged.
This document is the reference the store and the website are built from; if they disagree,
Lemon Squeezy wins and this file is stale.

## The rule that governs this file

`docs/LICENSE_PLANS_SPEC.md` Rule 1: **never state a price in code.** It exists because an
assistant, asked about Pro licensing, found no price in `get_license_status`, fell back to a
URL in shipped prose, and described a different company's product to a user as fact
(commit `2f45c36`). `tests/test_bundle_and_pricing.py::test_upsell_never_quotes_a_price`
now fails the build on any `$ € £ ₹ USD INR` token reaching the upsell string.

Prices are allowed **here** (`docs/`) and in the website's `src/content/`. They are never
allowed in `src/mcp_server/`, `src/tray/`, or any user-facing string the MCP server emits.
The server links to `PRICING_URL`; the website renders the number.

---

## Bands

Four coarse bands, not per-country pricing. Anchors are **$4.99/mo** high-income and
**₹249/yr** India — those two choices imply the ~5× spread, and B and C are even steps
inside it.

| Band | Monthly | Annual | Founding lifetime | Lifetime list |
|---|---|---|---|---|
| **A** High income | $4.99 | **$49** | **$49** | $98 |
| **B** Upper-mid | $2.99 | **$29** | **$29** | $58 |
| **C** Mid | — | **$19** | **$19** | $38 |
| **D** Emerging | — | **₹249** | **₹249** | ₹498 |

Annual is 10× monthly — two months free.

### Country → band

Anything not listed falls back to **Band A**. Keep this list coarse; resist the urge to
tune individual countries.

| Band | ISO codes |
|---|---|
| **A** | `US CA GB IE DE FR NL BE AT CH LU DK SE NO FI IS IT ES AU NZ JP SG HK KR TW IL AE QA KW SA` |
| **B** | `PL CZ SK HU PT GR HR RO SI EE LV LT BG-adjacent upper-mid, CL UY MY CR PA` |
| **C** | `BR MX TR TH ZA AR CO CN RS BG PE DO EC` |
| **D** | `IN ID VN PH PK BD LK NP NG KE EG MA GH TZ UG` |

> The authoritative machine-readable copy lives in the website repo at
> **`locallensmcp/src/server/pricing.ts`** — server-only, never client code. Update both
> together. See *Discretion* below for why the location is enforced.

---

## Why C and D are annual-only

Lemon Squeezy charges **5% + $0.50** per transaction, **+1.5%** international, **+0.5%**
subscription. The flat $0.50 does not scale down with the price:

| Charge | Fees | You keep | Fee share |
|---|---|---|---|
| ₹79/mo (≈$0.95) | $0.57 | **$0.38** | 60% |
| ₹249/yr (≈$2.93) | $0.69 | **$2.24** | 23% |
| $1.99/mo | $0.64 | **$1.35** | 32% |
| $4.99/mo | $0.77 | **$4.22** | 15% |
| $49/yr | $2.95 | **$46.05** | 6% |

Twelve $0.50 tolls a year against a sub-$2 charge is not viable. India monthly is
separately constrained by RBI e-mandate rules on recurring card payments; a single annual
charge sidesteps both problems.

**Annual is materially better margin in every band** (6% vs 15% even in Band A). Present
annual as the default everywhere and monthly as the alternative, not the headline.

### Band D is distribution, not revenue

₹249/yr nets about **$2.24**, or ~$1.74 in the worst case (Lemon Squeezy pricing
GST-inclusive *and* the rupee at ₹88). One Band A customer is worth roughly twenty Band D
customers. Band D exists to buy reviews, word-of-mouth, and bug reports. Do not build
revenue forecasts on it.

---

## Founding 100

**Offer:** the first 100 customers worldwide pay once and keep Pro forever — one year's
price for permanent access.

**Mechanism:** Lemon Squeezy has no inventory limit on digital products, but discount codes
do have redemption limits. Lifetime *list* prices are set at exactly 2× the founding price
so a single global code produces the right number in every band:

```
code                    FOUNDING100
type                    50% off
is_limited_redemptions  true
max_redemptions         100
is_limited_to_products  true  → scoped to the four Lifetime variants only
```

$98→$49 · $58→$29 · $38→$19 · ₹498→₹249

Lemon Squeezy rejects the 101st redemption itself, atomically, with one counter shared
across all bands. That is the intended semantics — first 100 *worldwide*, not per region.
The strike-through price is genuine, so the discount is honest.

**Window closes at 100 sales OR `<SET DATE AT LAUNCH — 60 days is a sane default>`,
whichever comes first.** Lemon Squeezy enforces **both**: `max_redemptions` caps the count
and the discount object's `expires_at` field caps the date. Set the same date in
`FOUNDING_ENDS_AT` (`locallensmcp/src/server/pricing.ts`) so the page stops advertising an
offer that checkout would refuse.

The **count** is the one thing that does not sync — Lemon Squeezy stops the code at 100 but
cannot tell the website, so it keeps advertising. When it sells out, set `FOUNDING_ENDS_AT`
to a past date and redeploy.

**Rejected alternatives:** manually unpublishing the variant at 100 (races past the cap);
a webhook + API integration to disable variants (needs a server and an API key to solve
what a coupon field already solves).

---

## Lemon Squeezy store inventory

Enable license key generation on every variant. Activation limit **3** per key — laptop,
desktop, and one reinstall. The local cache is machine-locked by SHA-256 of hostname+MAC
(`src/mcp_server/license.py`), so activations are genuinely per-machine.

**Product 1 — "LocalLens Pro"** (subscription)

| Variant | Price | Checkout UUID |
|---|---|---|
| A Monthly | $4.99 | `<fill in>` |
| A Annual | $49 | `<fill in>` |
| B Monthly | $2.99 | `<fill in>` |
| B Annual | $29 | `<fill in>` |
| C Annual | $19 | `<fill in>` |
| D Annual | ₹249 | `<fill in>` |

**Product 2 — "LocalLens Pro — Lifetime"** (one-time payment)

| Variant | List | Founding | Checkout UUID |
|---|---|---|---|
| A Lifetime | $98 | $49 | `<fill in>` |
| B Lifetime | $58 | $29 | `<fill in>` |
| C Lifetime | $38 | $19 | `<fill in>` |
| D Lifetime | ₹498 | ₹249 | `<fill in>` |

**Refund policy:** 14 days, no questions asked; the license key is revoked on refund.

---

## How a price reaches a customer

```
locallensmcp.vercel.app/pricing
  │  /pricing is ISR-cached (3600s) — server-side geo would bake one
  │  country into the shared cache, so band resolution is client-side.
  ▼
GET /api/public/offer        ← dynamic route, NOT in routeRules
  │  reads x-vercel-ip-country (or cf-ipcountry), resolves server-side,
  │  returns ONE offer: { price, note, checkoutUrl, founding, claimed }
  │  — no band letter, no country list, no other band's prices
  ▼
Lemon Squeezy checkout overlay
  │  payment · tax/VAT/GST · merchant-of-record · license key email
  ▼
activate_pro_license(license_key=...)   ← src/mcp_server/license.py, unchanged
```

## Discretion: where the map is allowed to live

The country→band map, the per-band prices and the checkout URLs live in
**`locallensmcp/src/server/pricing.ts` and nowhere else.** They must never appear in
client code.

This is enforced, not merely agreed: `vite.config.ts` sets `importProtection` with
`behavior: "error"` on `**/server/**`, so a client import of that module fails the build.

**Why.** An earlier version kept the map in `src/content/pricing.ts` and rendered a visible
region dropdown. Both were mistakes. The map shipped inside the JavaScript bundle where
anyone could read every band in devtools, and the dropdown was a self-serve discount menu —
it taught every visitor that a cheaper price existed and handed them the control to pick it.

**The rules that follow:**

- No band letters, country lists, or other bands' prices in any client-visible string.
- No region selector in the UI. A genuine traveller or expat uses the "wrong currency?"
  link, which routes to a human who can hand out an undocumented `?country=XX` link.
- The ISR-cached HTML renders Band A. That is the list price, so caching it discloses nothing.
- Verify after any change to pricing code:

```bash
cd locallensmcp && npm run build
grep -raF -- '₹249' .output/public/    # must be empty — client bundle
grep -raF -- '₹249' .output/server/    # must NOT be empty — server bundle
```

  Use `grep -F`. Without it, `$49` is read as a regex meaning "end of line, then 49" and
  silently matches nothing, which looks like a passing test.

**There is no technical defence against a VPN.** Lemon Squeezy discount codes cannot be
restricted by country — product scoping and redemption caps only. The defence is
informational: don't advertise the scheme, give no affordance to switch, keep the map off
the client, and accept the residual leakage. Someone who runs a VPN to save $46 was never
going to pay $49. If you ever want to measure it, the Lemon Squeezy `order_created` webhook
carries the billing country — observe, don't block.

---

## Licensing code: what still needs building

**Today the MCP server can only enforce lifetime licenses.** `is_pro_active()`
(`src/mcp_server/license.py`) checks `tier` and `machine_id` and nothing else; the cache
stores no expiry, and no network call is ever made after activation. Once a key activates,
Pro is unlocked permanently and offline.

That is exactly correct for the Founding-100 launch — lifetime keys return
`expires_at: null` — so **the founding launch needs no licensing changes at all.**

**Before the first subscription is sold**, `src/mcp_server/license.py` needs:

1. `activate_license()` to read `license_key.expires_at` from the validate response (it
   currently receives the whole body in `body` and discards everything but `valid`).
2. `_write_cache()` to persist `expires_at`, nullable — `None` means lifetime.
3. `is_pro_active()` to return true if `expires_at is None` **or** `now < expires_at`.
4. An auto-refresh: within 7 days of expiry or past it, attempt one `/validate` and rewrite
   the cache; on network failure allow a **14-day offline grace** before locking.
5. **The privacy claim to be corrected.** `README.md` promises *"the only network request is
   license activation."* Periodic revalidation makes that false for subscribers. Keep the
   `expires_at is None` fast path explicit so it stays literally true for lifetime buyers,
   and reword for everyone else.

---

## Changelog

- **2026-08-08** — initial decision. Four bands; $4.99/mo and ₹249/yr anchors; C and D
  annual-only on transaction-fee grounds; Founding-100 via a capped 50% discount code.
