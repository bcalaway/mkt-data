# Phase 4: Treasury analytics from prices

**Status: draft for Bill's decisions (2026-10-07).** Nothing is built. Phase 3 (Treasury securities by CUSIP: terms, auctions, STRIPS, FIGIs, TIPS index ratios, 18 years of FedInvest prices) closes once step 3's BLS history is in: see [phase-3.md](phase-3.md). The choices that shape this phase are under "Decisions to make", each with a recommendation; nothing here is settled until Bill says so.

**Goal:** turn phase 3's terms and prices into analytics: every outstanding Treasury's yield, accrued interest and risk each day since 2008, and a fitted Treasury curve each day, each checked against an independent published answer before anything is shown.

## What changes from phase 3

- Phase 3 stored everything needed to price a security, but nothing computes with it: no cash-flow schedule, no yield, no curve (Bill, 2026-10-06: "the analytics library will generate it from the stored terms").
- This phase adds that library and the place its results live, and first uses them on the screens: a security's yield over time, the curve as fitted from every bond, and how rich or cheap each bond is to it.
- The data layer is unchanged: no new sources, unless validation shows a gap.

## The analytics library

A Python package with no I/O: it takes terms and prices and returns schedules, numbers and fits. Services and DAGs call it; it never reads a database or a service itself, so every function is testable on its own.

| Area | What it does |
|---|---|
| Schedules | Coupon dates from the stored terms: regular dates back from maturity (end-of-month rule), the first period (short, long, normal) and the penultimate date as published; pay dates adjusted on SIFMA-US (calendar-svc's closes, passed in); TIPS principal indexed; FRN periods with the lockout |
| Accrual | Actual/actual (ICMA) for notes, bonds and TIPS; Actual/360 for FRNs (index plus spread, floored at zero, daily); none for bills |
| Price and yield | Notes and bonds: Treasury's street convention (semiannual, the formula in 31 CFR 356 Appendix B), price from yield and yield from price. Bills: discount rate, money-market yield and bond-equivalent (investment) rate, Treasury's formulas including the over-half-a-year case. TIPS: real yield from the real clean price, with the index ratio for the inflation-adjusted price. FRNs: discount margin |
| Risk | Modified and Macaulay duration, convexity, DV01 per 100; TIPS real-yield duration |
| Curve | The fitter (method under "Decisions to make"), and from a fit: par, zero and forward curves at standard tenors, and each bond's fitted yield and residual (rich or cheap, in basis points) |

**Decimal where it's shown, floats where it's solved.** Conventions (accrual, the price formulas) in `Decimal`, so a published price reproduces to its last digit. Yield-from-price and the curve fit in floats (numpy and scipy), rounded to Decimal at the boundary, like everything else the platform stores.

**Testing:** pure-Python parts run in the sandbox like every other repo. numpy and scipy are compiled, so the sandbox's PyPI-free test script can't install them; the fitter's tests run in CI only, as the gRPC tests do now.

## Validation: three independent answers

Every number is checked against something published before it's trusted, and the checks keep running as data arrives (as the TIPS reference CPI check does now).

1. **Auctions, price from yield** (every auction since 1980 in secmaster-svc): the high yield (or discount rate) and the issue date as settlement must give TreasuryDirect's published price per 100, and a reopening's published accrued interest per 1,000. Bills: discount rate to price and to the published investment rate. TIPS: the adjusted price and index ratio at issue. FRNs: the high discount margin to price. Expected: exact to the published rounding, with exceptions explained like phase 3's TIPS ones.
2. **FedInvest prices, yield from price and back** (4,593 days): price to yield to price again must reproduce the price to its six decimals, every security, every day; a check on the solver.
3. **The curve against Treasury's own** (UST-PAR, the par curve the CMTs come from): the fitted par yields at Treasury's tenors against Treasury's published par curve each day. Not expected to match exactly (Treasury fits indicative bid-side quotes of the on-the-run issues near 3:30 p.m.; FedInvest's end-of-day prices are another snapshot), but the difference should be a few basis points and steady; a jump is a problem in the fit or the data.

## Results: what's stored, where

**Per security per day** (outstanding, priced): yield, accrued interest, dirty price, modified duration, convexity, DV01; TIPS real yield; FRN discount margin. About 400 securities a day since 2008: some 2 million rows per field, the size of the FedInvest prices themselves.

**Per day:** the curve fit's parameters and fit quality, the par, zero and forward curves at standard tenors, and each bond's residual.

**Where:** see "Decisions to make". Either way the results are derived, never golden source data: rebuildable from terms, prices and the library's version, with that version recorded on each run, so a convention fix is a rebuild.

## Screens and voice

- **A security's page:** yield over time beside price (lines or OHLC, the same chart), accrued and risk today, and its residual to the curve.
- **The curve screen:** the fitted curve beside the CMTs, each bond plotted as a dot at its maturity and yield, coloured rich or cheap; the on-the-runs marked.
- **Over time:** fitted par yields as series beside the CMTs, and the difference (the validation, visible).
- **home-mcp:** `mkt_data_security` adds yield and DV01; "how rich is the 10-year to the curve?".

## Monitoring and alerts

- Validation 1 as a metric and an alert (auctions whose published price we don't reproduce), like the TIPS CPI check.
- Validation 3 as a daily gauge: the fitted curve's largest difference from Treasury's par curve; an alert above a threshold set from history, the way the price sanity limits were.
- The fit's quality (RMSE of residuals) per day, with an alert on a jump.
- Results stale: the analytics for the latest priced day not in by the morning after prices are due.

## Decisions to make

1. **Where the library lives:** (a) a new repo, `mkt-analytics`, a Python package installed by whatever uses it (recommended: it's the one piece the services, DAGs and later notebooks all want, and pure functions version cleanly); (b) a module inside quote-svc.
2. **Where results live and what computes them:** (a) a new service, `analytics-svc`, with its own database, running the library after quote-svc's load (on an Airflow Asset, like every other build) and serving results over gRPC to mkt-api (recommended: results are derived and rebuilt on a library change without touching golden quotes); (b) quote-svc stores yields and risk as more fields from a "CALC" source, next to the prices (simpler: one store, one API; but computed numbers mixed into the golden quote store, and a library change means re-deriving inside it).
3. **Yield convention for notes and bonds:** street convention (recommended: Treasury's own for auction yields, so validation 1 checks it directly); true yield (adjusting for payments moved off weekends) as a second field later if wanted.
4. **Settlement for daily analytics:** T+1 on SIFMA-US (recommended: the market's convention for cash Treasuries); or the price date itself. Which one FedInvest's prices assume is an open question below; validation 2 doesn't depend on it, validation 3 does a little.
5. **The curve method:**
   - (a) **Svensson on off-the-run notes and bonds**, leaving out bills, the on-the-run and first off-the-run issues and the shortest maturities, in the spirit of the Fed's Gürkaynak–Sack–Wright curve (the exact filters to be read from their paper in step 5) (recommended first: a smooth zero curve with every bond's residual, and a published method to compare against);
   - (b) **monotone convex on the on-the-runs**, Treasury's own method since December 2021, the closest reproduction of the par curve (validation 3 then tests the method rather than the data);
   - (c) a **smoothing spline** (Fisher–Nychka–Zervos or variable roughness): more flexible, more parameters to choose.
   Recommended: (a) then (b), both stored, so rich/cheap comes from (a) and the check against Treasury from (b).
6. **History:** compute everything back to 2008 in the first build (recommended: about 4,600 days; a few minutes per pass vectorized), or from a recent start date first.
7. **STRIPS:** priced from the fitted zero curve (they aren't in FedInvest's prices), or left for later (recommended: later).

## Steps (once the decisions are made)

1. **The library, conventions first:** schedules, accrual, price and yield for each type, with validation 1 against every auction as its test suite (real captures, as phase 3's parsers were tested).
2. **Validation 1 on the hub:** run over every auction; explain every miss before going on.
3. **Daily analytics:** results store, the build on quote-svc's Asset, validation 2, the backfill to 2008.
4. **mkt-api and mkt-ui:** yield and risk on a security's page.
5. **The curve:** the fitter, validation 3 against UST-PAR, the backfill.
6. **Curve screens:** fitted curve, residuals, rich and cheap.
7. **Monitoring** as above.
8. **home-mcp tools.**

## Open questions

- Does FedInvest's end-of-day price for a TIPS mean the real clean price per 100 of original principal (most likely, as Treasury quotes TIPS), and for an FRN a clean price? Validation 2 and a few hand checks answer this in step 1.
- What settlement and time of day FedInvest's end-of-day prices assume (FedInvest prices securities for federal agencies' investments; its documentation should say). It matters for comparing with Treasury's par curve, not for the conventions.
- Do FedInvest's prices for bills about to mature, and for securities just auctioned but not yet issued, behave well enough to fit? The fitter's exclusions will say.

## Later (not this phase)

- Interest-rate futures (STIR and bond futures), which this phase's curve and risk feed: the next asset class on Bill's list.
- Carried over: amount outstanding by holder (MSPD), fixings (SOFR, EFFR), real yields as series, backup capture, the near-live macro dashboard, the shared chart layer, calendar closes as chart events.
- Swaps and G4 government bonds, on the same library.
