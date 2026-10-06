# Phase 3: Treasury securities by CUSIP

**Status: planning (2026-10-06).** Phase 2 (calendars on the golden-copy layering, Treasury CMT yields end to end) is complete: see [phase-2.md](phase-2.md). The proposals marked **(to decide)** below wait for Bill; once decided they move to "Decisions".

**Goal:** every marketable Treasury bill, note and bond as a real instrument in secmaster-svc (terms, auctions, reopenings, identifiers), with Treasury's end-of-day prices for each in quote-svc. That is the data a curve fitter, bond analytics and on-the-run views need, and the first instruments that come from a feed rather than a seed file.

**Scope (Bill, 2026-10-06):** Treasury securities by CUSIP, through the same layers as phase 2: sourcing → raw → near-raw → secmaster-svc and quote-svc → schedule → monitoring → screens → voice. Not in this phase: yields computed from prices and the curve fitter (analytics, later), SOFR/EFFR, real-yield curves, futures.

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

- **`instrument`** gains types `ust_bill`, `ust_note`, `ust_bond`, and **(to decide)** `ust_tips` and `ust_frn`. Proposed: record TIPS and FRNs as instruments now (their terms come in the same records) but price and chart only nominal bills, notes and bonds this phase.
- **`instrument_terms`** (effective-dated): issue date, maturity date, coupon (decimal, `0.0425`), coupon frequency, day count, first coupon date, dated date, original term and security term, face outstanding after each auction, the calendar it follows (`SIFMA-US`). `valid_from`/`valid_to` for when a term holds, `recorded_at` for when we learned it.
- **`auction`:** one row per auction (original issue or reopening): announcement, auction and issue dates, offering amount, high yield / discount rate, price, bid-to-cover and the other published results, linked to the security record it came from.
- **Identifiers:** CUSIP (from the feed), ISIN (`US` + CUSIP + check digit, computed and checked), and **(to decide)** FIGI from OpenFIGI's mapping API (free, rate-limited without a key; a key would be one more secret).
- **Short names (to decide).** Proposed, readable and stable, matching how traders say them: notes and bonds `UST-4.25-2035-08-15`, bills `UST-B-2026-12-24`, TIPS `UST-TII-1.875-2035-07-15`. A reopening keeps the name (same CUSIP).
- **On-the-run (to decide):** rolling aliases such as `UST-10Y-OTR` that point at the most recently auctioned security of each original term, with the history of which CUSIP held it when. Proposed: yes, as identifiers with validity, so "the 10-year" on a past date resolves to that day's security.
- **Load job** (`POST /jobs/load`), on the Asset `mkt_data_treasury_securities` plus nightly: reads new records, types and validates them, upserts instruments, terms and auctions, reports anything it can't type (counted like quote-svc's unmapped keys).
- The CMT seed file stays as it is; seeded and feed-built instruments live side by side.

## Quote store (`quote-svc`)

- **Prices** as quotes: field `price` (golden from `eod`), with `buy` and `sell` kept by source; values in price per 100, Decimal.
- **Mapping** by CUSIP through secmaster-svc's `Resolve`, as for CMTs.
- **Freshness:** prices due for every outstanding security on each SIFMA-US business day; a security missing a price while outstanding is counted (matured and not-yet-issued ones are not due).
- **Size:** about 450 securities × ~250 days a year ≈ 110,000 prices a year per field, so tens of millions of rows only if FedInvest's history goes back decades. To be sized in step 1; Postgres partitioning by year if it does.
- **Not here:** yields from prices, accrued interest, analytics (later phase, on top of these).

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
3. **secmaster-svc:** types, effective-dated terms, auctions, identifiers (ISIN, maybe FIGI), short names, on-the-run aliases, load job on the Asset.
4. **quote-svc:** prices by CUSIP, golden `price`, freshness against outstanding securities.
5. **Backfill** as far back as each source allows, a year at a time; cross-check TreasuryDirect's auctions against Fiscal Data's.
6. **Schedule** on SIFMA-US, with retries until the day's file is in.
7. **Monitoring** as above.
8. **mkt-api and mkt-ui:** Securities and Security screens.
9. **home-mcp tools.**

## Decisions (to make)

- TIPS and FRNs: instruments now, priced later (proposed), or out of scope entirely.
- Short-name format (proposed above).
- On-the-run aliases with history (proposed yes).
- FIGI through OpenFIGI: now, later, or never.

## Later (not this phase)

- Yields, accrued interest and risk from prices; the curve fitter.
- Amount outstanding by holder and stripping, from the Monthly Statement of the Public Debt.
- Carried over from phase 2: fixings (SOFR, EFFR), real yields, backup capture, the near-live macro dashboard, the shared chart layer, calendar closes as chart events.
