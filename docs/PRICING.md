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

**Status as of 2026-08-12: not armed.** Lemon Squeezy rejected the store application (no
live public site/social/customer base yet — see `LAUNCH_CHECKLIST.md` Phase 2). The
`2026-10-07T00:00:00Z` currently in `FOUNDING_ENDS_AT` is a leftover placeholder, not a
real deadline — there is no store for it to correspond to. Don't set the real date until
Lemon Squeezy approves; that's the first step of `LAUNCH_CHECKLIST.md` Phase 3.

**Rejected alternatives:** manually unpublishing the variant at 100 (races past the cap);
a webhook + API integration to disable variants (needs a server and an API key to solve
what a coupon field already solves).

---

## Free preview — grandfathering

**The promise: nobody who used LocalLens during the free preview ever pays.** They keep
every Pro feature, permanently, at no cost. This is a commitment made publicly on the
site, not a marketing hedge — it must be honored even where honoring it costs a sale.

It also supersedes Founding-100 for anyone who arrived during the preview: they are not
one of the hundred, they are simply free. Founding-100 begins at paid launch, for people
arriving after it.

The reasoning is not only ethical. The preview exists because Lemon Squeezy asked to see a
real user base before approving the store — so these are the exact people whose adoption
unblocks the business. Charging them for having shown up early would be both a bad trade
and the kind of thing that gets written up.

### How eligibility is established

There is **no user registry, by design.** LocalLens makes no network calls, so there is no
list of who joined and no way to build one without breaking the product's central promise.
Eligibility is therefore established locally, two ways, and generously:

**1. Automatic — local install date.** Every install carries
`~/.config/LocalLens/mcp_onboarded.json` with an `onboarded_at` timestamp. If it predates
`_PREVIEW_CUTOFF` (`src/mcp_server/license.py`, the paid-launch date), Pro stays unlocked
forever. No key, no activation, no network call — the privacy claim stays literally true
for these users, as it does for lifetime buyers.

Absent or unparseable markers resolve to **eligible**. That is deliberate and matches
`_parse_expiry()`'s permissive reading of a bad `expires_at`: erring the other way locks
out someone we promised not to charge, which is a far worse failure than granting Pro to
someone who reinstalled. Note the marker is written by the desktop app's setup page
(`"source": "setup_page"`), which lives in the backend repo — so an install path that
skips that page leaves no marker at all. The MCP stamps one itself when it finds none.

**2. Manual claim.** Anyone who reinstalled, switched machines, or lost the marker can
say so through the contact form and be issued a free key. No proof required; the honest
majority costs less than the alternative.

**Forgeability is not a new problem.** A local date check is exactly as editable as the
license cache sitting next to it — see *Licensing code* below and the note that there is
no location in a 100%-local product the user cannot edit. It costs nothing new, and the
realistic mitigations (low price, current BSL, frozen binaries) are unchanged.

**Rejected:** requiring an email signup to qualify (a registry, which is the thing the
product exists to not have); telemetry to count installs (same problem, worse); and
silently letting the promise lapse for users who never wrote in (the failure mode that
makes the promise worthless).

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

  **While `FREE_PREVIEW` is on, the second line is empty too, and that is correct.**
  `resolveOffer()` returns the free offer before it reads `country`, and because the
  flag is a `const true` the bundler proves the band map unreachable and drops it from
  the server bundle as well. Nothing about regional pricing exists in the deployed
  artifact at all right now. Re-apply the check as written once the preview ends.

  Use `grep -F`. Without it, `$49` is read as a regex meaning "end of line, then 49" and
  silently matches nothing, which looks like a passing test.

**There is no technical defence against a VPN.** Lemon Squeezy discount codes cannot be
restricted by country — product scoping and redemption caps only. The defence is
informational: don't advertise the scheme, give no affordance to switch, keep the map off
the client, and accept the residual leakage. Someone who runs a VPN to save $46 was never
going to pay $49. If you ever want to measure it, the Lemon Squeezy `order_created` webhook
carries the billing country — observe, don't block.

---

## Licensing code — shipped

**The MCP server enforces both lifetime and subscription licenses.**
`is_pro_active()` (`src/mcp_server/license.py`) returns true when `expires_at is None`
(lifetime — unlocked permanently and offline, exactly one network call ever) or when
`now` is still inside `expires_at` plus a 14-day offline grace. Within 7 days of expiry,
`refresh_license_if_stale()` attempts one re-validation and rewrites the cache; on
network failure the grace window covers it. `README.md`'s privacy claim is worded to
match: one request ever for lifetime, periodic re-checks (key only, no photos/paths) for
subscriptions. 9 tests in `tests/test_license_expiry.py` cover all four behaviours,
mutation-tested against the old always-true `is_pro_active()`.

This was necessary groundwork, not launch-blocking scope creep: without it, a monthly
subscriber could pay once, cancel immediately, and keep Pro forever. It shipped in
`7900d04`/`a903c01` (`v1.0.33`) ahead of `MONTHLY_ENABLED` being flipped on, so the gate
already exists by the time it's needed.

---

## Changelog

- **2026-08-08** — initial decision. Four bands; $4.99/mo and ₹249/yr anchors; C and D
  annual-only on transaction-fee grounds; Founding-100 via a capped 50% discount code.
