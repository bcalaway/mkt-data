# Phase 3: Treasury securities by CUSIP

**Status: planning (2026-10-06).** Phase 2 (calendars on the golden-copy layering, Treasury CMT yields end to end) is complete: see [phase-2.md](phase-2.md). Bill's decisions are under "Decisions"; what's still open is under "Open questions".

**Goal:** every marketable Treasury bill, note, bond, TIPS and FRN as a real instrument in secmaster-svc (terms, auctions, reopenings, identifiers), with every term needed to price it, and Treasury's end-of-day prices for each in quote-svc. That is the data a curve fitter, bond analytics and on-the-run views need, and the first instruments that come from a feed rather than a seed file.

**Scope (Bill, 2026-10-06):** Treasury securities by CUSIP, including TIPS and FRNs, through the same layers as phase 2: sourcing → raw → near-raw → secmaster-svc and quote-svc → schedule → monitoring → screens → voice. Not in this phase: yields computed from prices and the curve fitter (analytics, later), SOFR/EFFR, real-yield curves, futures.

## What changes from phase 2

- **Instruments come from a feed.** The 14 CMTs are a seed file; securities arrive through mkt-data's near-raw like any data, and secmaster-svc builds them in a load job on an Airflow Asset, like quote-svc.
- **Effective-dated terms.** Phase 2 deferred `valid_from`/`valid_to`/`recorded_at` on terms to the first instrument that has terms. A security's terms are fixed at its first auction, but what we *know* changes: an announcement precedes the auction (the coupon is unknown until the auction sets it), and reopenings add to the amount outstanding. Terms carry both when they were true and when we recorded them.
- **Not a time series.** Auction and security records don't fit the generic `observation` table, so near-raw gets a second generic shape for records (below). Prices are a time series and use `observation` as is.
- **Many instruments.** About 400–500 marketable securities outstanding at any time, and tens of thousands since the late 1970s. Screens need search and lists, not one picker.

## Sources

| Source | What | Where | History | Role |
|---|---|---|---|---|
| `TD-SECURITIES` | TreasuryDirect's securities web API: every announced and auctioned marketable security (CUSIP, type, term, dates, coupon, auction results, reopening flag, TIPS and FRN details) | `https://www.treasurydirect.gov/TA_WS/securities/search?format=json&startDate=…&endDate=…&dateFieldName=auctionDate` (also `/announced`, `/auctioned`, and `/{cusip}/{issueDate}`) | Expected from about 1979 (checked in step 1) | Primary for terms and auctions |
| `TD-PRICES` | FedInvest's *Prices for Treasury Securities*: a daily file of every marketable CUSIP's buy, sell and end-of-day price | `https://www.treasurydirect.gov/GA-FI/FedInvest/selectSecurityPriceDate` (a form post by date; CSV) | Depth unknown (checked in step 1) | Primary for prices |
| `BLS-CPI` | CPI-U, not seasonally adjusted (`CUUR0000SA0`), monthly, for TIPS reference CPIs and index ratios | BLS public data API v2 (no key for small requests) | 1913 on | TIPS indexation; checked against TreasuryDirect's published reference CPIs |
| `FD-AUCTIONS` | Fiscal Data's *Treasury Securities Auctions Data*, the same auction records through a documented, paged JSON API | `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query` | Checked in step 1 | Cross-check, and fallback if TreasuryDirect's API misbehaves |

Notes:

- **Read on the hub, not by Claude.** TreasuryDirect's robots.txt turns away Claude's web tools, and the sandbox can't reach either host, so every format detail here is checked in step 1 against captures on the hub, read with `mkt_data_capture_text`. The capture jobs are ordinary scheduled API clients of a published government API, at a few requests a day.
- **What FedInvest prices are** (to confirm in step 1): Treasury's prices for the Federal Investments Program, indicative and one per security per day, not traded prices. Fine for end-of-day marks and history; a curve fitter may want them flagged as indicative. The file's time of day sets the schedule.
- **Terms:** U.S. Government works, as in phase 2. Step 1 records each source's terms page.
- **Lookback risk:** if FedInvest keeps only a short history, this is the first source where backup capture (NUC, or Lambda + S3) earns its keep, and the daily capture should start before the parsers, as in phase 2.

## Near-raw (mkt-data)

- **Prices:** `observation` as in phase 2. `source_key` is the CUSIP, `field` is `buy`, `sell` and `eod`, `unit` is `price_per_100` (Treasury quotes decimals per 100 of face). Capture unit: one capture per price date (`capture.period` = `2026-10-06`).
- **Records** (new, generic): `record` (`source`, `record_type` such as `security`, `source_key` such as `CUSIP/issue date`, `fields` as `jsonb` exactly as published, `capture_id`, `valid_from`/`valid_to`). A changed field is a revision: the old row closes, a new one opens, the same rule as `observation`. The parser keeps the source's own field names and values (strings as printed) so nothing is interpreted in ingestion; secmaster-svc does the typing. Capture unit: one capture per month of auction date, refetched while the month can still change.
- **gRPC:** `Records.ListPeriods` / `GetPeriod` mirroring `Observations`, so secmaster-svc reads by watermark exactly as quote-svc does.

## Security master (`secmaster-svc`)

- **`instrument`** gains types `ust_bill`, `ust_note`, `ust_bond`, `ust_tips` and `ust_frn`, all priced and charted this phase (Bill, 2026-10-06).
- **`instrument_terms`** (effective-dated): every term in "Terms for pricing" below. `valid_from`/`valid_to` for when a term holds, `recorded_at` for when we learned it, and each term marked **published** (from a source, with its record) or **derived** (computed here, with the rule).
- **`cash_flow`:** the full schedule for each security, generated from its terms: every coupon's accrual start and end, unadjusted pay date, pay date adjusted to the next SIFMA-US business day (from calendar-svc), and amount per 100 where it's known in advance (nominal coupons, principal). TIPS and FRN amounts depend on CPI and bill auctions, so their rows carry the rule and get amounts as those fix. Regenerated when terms or the calendar change, with history.
- **`auction`:** one row per auction (original issue or reopening): announcement, auction and issue dates, offering amount, high yield / discount rate, price, bid-to-cover and the other published results, linked to the security record it came from.
- **Identifiers** (as many as we can, Bill 2026-10-06): CUSIP from TreasuryDirect's announcement and auction records, which carry it from announcement day; ISIN, `US` + CUSIP + a check digit, computed (an ISIN for a U.S. security is defined that way, so there's nothing better to pull) and checked against any source that prints one; FIGI (and composite FIGI and Bloomberg-style ticker) from OpenFIGI's mapping API by CUSIP; for TIPS, Treasury's CPI series name; for FRNs, the index (13-week bill high rate). Each with its scheme, source and validity.
- **Short names (Bill, 2026-10-06),** readable and stable: notes and bonds `UST-4.25-2035-08-15`, bills `UST-B-2026-12-24`, TIPS `UST-TII-1.875-2035-07-15`, FRNs `UST-FRN-2028-07-31`. A reopening keeps the name (same CUSIP).
- **On-the-run (Bill, 2026-10-06):** rolling aliases such as `UST-10Y-OTR`, `UST-5Y-TII-OTR`, `UST-2Y-FRN-OTR` pointing at the most recently auctioned security of each original term, as identifiers with validity, so "the 10-year" on a past date resolves to that day's security. The switch is on the new issue's issue date (to confirm: auction date is the other common convention).
- **Load job** (`POST /jobs/load`), on the Asset `mkt_data_treasury_securities` plus nightly: reads new records, types and validates them, upserts instruments, terms and auctions, reports anything it can't type (counted like quote-svc's unmapped keys).
- The CMT seed file stays as it is; seeded and feed-built instruments live side by side.

## Terms for pricing

Everything needed to price each security and generate its cash flows (Bill, 2026-10-06). **P** = published by TreasuryDirect (field names confirmed in step 1), **D** = derived here from published terms, with the rule recorded.

**All securities**

| Term | Source | Notes |
|---|---|---|
| CUSIP, security type, security term, original term | P | Original term is what an on-the-run alias follows (a reopened 10-year is still a 10-year) |
| Announcement date | P | Per auction; the first auction's is the security's |
| Auction date | P | Per auction |
| Issue date (original) and each reopening's issue date | P | |
| Dated date (accrual start) | P | Differs from issue date for reopenings and some originals |
| Maturity date | P | |
| Redemption | D | 100 (TIPS: 100 × max(index ratio, 1) at maturity, the deflation floor) |
| Settlement convention | D | T+1 |
| Calendar | D | `SIFMA-US`, from calendar-svc |
| Pay-date adjustment | D | Unadjusted schedule; a payment on a non-business day moves to the next business day with no extra interest |
| Callable date and call price | P | Only the pre-1985 callable bonds (all matured); kept for history |
| Amount offered, accepted, outstanding after each auction | P | |

**Notes, bonds and TIPS (fixed coupon)**

| Term | Source | Notes |
|---|---|---|
| Coupon rate | P | Decimal, `0.0425`; set at the first auction, unchanged on reopenings |
| Coupon frequency | D | Semiannual |
| Day count | D | Actual/actual (ICMA) |
| First coupon (interest payment) date | P | |
| First coupon period type | P | Normal, short or long |
| Regular coupon dates | D | Maturity's day of month, every six months back from maturity (end-of-month rule for month-end maturities) |
| Penultimate coupon date | D | Six months before maturity under that rule; checked against every published schedule |
| Accrued interest per 1,000 at issue (reopenings) | P | Checked against our own accrual calculation |

**Bills**

| Term | Source | Notes |
|---|---|---|
| Discount rate and investment rate at auction, price per 100 | P | |
| Day count | D | Actual/360 discount; money-market and bond-equivalent yields computed later (analytics) |
| Cash management bill flag | P | |

**TIPS (in addition)**

| Term | Source | Notes |
|---|---|---|
| Reference CPI on dated date (base CPI) | P | |
| Reference CPI on issue date, index ratio on issue date | P | |
| Daily reference CPI and index ratio | D | From `BLS-CPI`, interpolated per Treasury's rule (the CPI three months and two months before, linearly by day); checked against TreasuryDirect's published values |
| Deflation floor | D | At maturity only |

**FRNs (in addition)**

| Term | Source | Notes |
|---|---|---|
| Index | D | 13-week bill high rate from the weekly auction (already in our auction records) |
| Spread | P | Set at the first auction, fixed for life |
| Interest payment dates | P | Quarterly; first payment date published |
| Daily accrual rule | D | Index + spread (floored at zero), accrued daily, Actual/360; the index takes effect the day after the bill auction's issue date |
| Lockout | D | Two business days before each payment, the rate stays fixed |

## Quote store (`quote-svc`)

- **Prices** as quotes: field `price` (golden from `eod`), with `buy` and `sell` kept by source; values in price per 100, Decimal.
- **Mapping** by CUSIP through secmaster-svc's `Resolve`, as for CMTs.
- **Freshness:** prices due for every outstanding security on each SIFMA-US business day; a security missing a price while outstanding is counted (matured and not-yet-issued ones are not due).
- **Size:** about 450 securities × ~250 days a year ≈ 110,000 prices a year per field, so tens of millions of rows only if FedInvest's history goes back decades. To be sized in step 1; Postgres partitioning by year if it does.
- TIPS prices are real (unadjusted for inflation, as FedInvest prints them; to confirm in step 1); FRN prices clean.
- **Not here:** yields from prices, accrued interest computed per day, analytics (a later phase, on top of these terms and cash flows).

## Custom UI and voice

- **mkt-api:** securities search (short name, CUSIP, coupon, maturity), a security's terms and auctions, lists of outstanding securities by type and maturity, and prices through the existing `/api/bars` series request (a CUSIP or short name is just another instrument).
- **mkt-ui:** a **Securities** screen (outstanding issues by maturity, filterable by type, with the on-the-runs marked) and a **Security** page (terms, auction history, price over time).
- **home-mcp:** `mkt_data_security` ("what's the 10-year on-the-run?", "when does the 4¼ of 2035 mature?") and the auction calendar ("what's auctioning this week?").

## Monitoring and alerts

- **mkt-data:** phase 1's capture stale and parse failed cover both new sources.
- **secmaster-svc:** records it couldn't type (warn), securities load stale or failed (warn), an auction whose results are overdue after its auction date (info).
- **quote-svc:** prices missing for outstanding securities on the last business day by 9:00 a.m. Eastern (warn), prices outside a sanity band or repeating (info).
- **Grafana:** a Treasury securities row on Market data: counts by type, outstanding, last load, untyped records, price coverage; storage.

## Steps

1. **Raw capture first** (mkt-data). Sources `TD-SECURITIES`, `TD-PRICES` and `FD-AUCTIONS`, fetched and kept raw with no parser yet. A daily DAG captures from today on. Read the first captures on the hub: formats, field names, history depth of each, FedInvest's time of day and whether past dates can still be fetched. Fixtures via `capture-export.yml`. Settle the open source questions above.
2. **Near-raw:** `record` table and parser for securities; `observation` parser for prices; gRPC `Records`; rebuild jobs.
3. **secmaster-svc:** types, effective-dated terms (published and derived), auctions, identifiers (CUSIP, ISIN, FIGI), short names, on-the-run aliases, load job on the Asset. Then the cash-flow schedule and the TIPS index ratios (needs `BLS-CPI` through near-raw), each checked against TreasuryDirect's published figures.
4. **quote-svc:** prices by CUSIP, golden `price`, freshness against outstanding securities.
5. **Backfill** as far back as each source allows, a year at a time; cross-check TreasuryDirect's auctions against Fiscal Data's.
6. **Schedule** on SIFMA-US, with retries until the day's file is in.
7. **Monitoring** as above.
8. **mkt-api and mkt-ui:** Securities and Security screens.
9. **home-mcp tools.**

## Decisions (Bill, 2026-10-06)

- **Scope:** Treasury securities by CUSIP, with TIPS and FRNs priced and charted too.
- **Short names** as proposed: `UST-4.25-2035-08-15`, `UST-B-2026-12-24`, `UST-TII-…`, `UST-FRN-…`.
- **On-the-run aliases** with history.
- **Identifiers:** as many as we can (CUSIP, ISIN, FIGI and the rest).
- **Terms:** everything needed to price each security, at least issue, announcement, accrual start, first and penultimate coupon, maturity and coupon.

## Open questions

- **STRIPS:** separately traded principal and coupon strips have their own CUSIPs (hundreds outstanding, mapped to their source securities). Include them as instruments, or leave them for later?
- **OpenFIGI key:** without one, mapping tens of thousands of historical CUSIPs takes a few hours once (then a handful a week); with a free key in SSM it takes minutes. Register a key, or run without?
- **On-the-run switch day:** the new issue takes over on its issue date (proposed) or its auction date?

## Later (not this phase)

- Yields, accrued interest and risk from prices; the curve fitter.
- Amount outstanding by holder and stripping, from the Monthly Statement of the Public Debt.
- Carried over from phase 2: fixings (SOFR, EFFR), real yields, backup capture, the near-live macro dashboard, the shared chart layer, calendar closes as chart events.
