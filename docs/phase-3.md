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
| `FD-MSPD-STRIPS` | Fiscal Data's *Monthly Statement of the Public Debt*, the table of securities held in stripped form: each strippable security with its principal (corpus) STRIPS CUSIP and amounts stripped and reconstituted | `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/debt/mspd/…` (table confirmed in step 1) | Checked in step 1 | STRIPS identity and amounts; interest STRIPS CUSIPs (one per payment date, shared across securities) from Treasury's STRIPS CUSIP list if MSPD doesn't carry them |
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

- **`instrument`** gains types `ust_bill`, `ust_note`, `ust_bond`, `ust_tips` and `ust_frn`, all priced and charted this phase, and `ust_strip_principal` and `ust_strip_interest` (Bill, 2026-10-06).
- **STRIPS** (Bill, 2026-10-06): a principal STRIPS is linked to its one source security and matures with it; an interest STRIPS has one CUSIP per payment date, shared by every security paying on that date, and is linked to all of them. Terms are just the maturity (payment) date and the link; amounts stripped and reconstituted come monthly from MSPD. Short names `UST-SP-2035-08-15` (principal) and `UST-SI-2035-08-15` (interest). Prices only if FedInvest or another free source carries them (checked in step 1); otherwise STRIPS have identity and terms but no quotes this phase.
- **`instrument_terms`** (effective-dated): every term in "Terms for pricing" below. `valid_from`/`valid_to` for when a term holds, `recorded_at` for when we learned it, and each term marked **published** (from a source, with its record) or **derived** (computed here, with the rule).
- **`auction`:** one row per auction (original issue or reopening): announcement, auction and issue dates, offering amount, high yield / discount rate, price, bid-to-cover and the other published results, linked to the security record it came from.
- **Identifiers** (as many as we can, Bill 2026-10-06): CUSIP from TreasuryDirect's announcement and auction records, which carry it from announcement day; ISIN, `US` + CUSIP + a check digit, computed (an ISIN for a U.S. security is defined that way, so there's nothing better to pull) and checked against any source that prints one; FIGI (and composite FIGI and Bloomberg-style ticker) from OpenFIGI's mapping API by CUSIP, with an API key in SSM (Bill, 2026-10-06; he registers it with Claude's guidance when step 3 gets there); for TIPS, Treasury's CPI series name; for FRNs, the index (13-week bill high rate). Each with its scheme, source and validity.
- **Short names (Bill, 2026-10-06),** readable and stable: notes and bonds `UST-4.25-2035-08-15`, bills `UST-B-2026-12-24`, TIPS `UST-TII-1.875-2035-07-15`, FRNs `UST-FRN-2028-07-31`, STRIPS as above. A reopening keeps the name (same CUSIP).
- **On-the-run (Bill, 2026-10-06):** rolling aliases such as `UST-10Y-OTR`, `UST-5Y-TII-OTR`, `UST-2Y-FRN-OTR` pointing at the most recently auctioned security of each original term, as identifiers with validity, so "the 10-year" on a past date resolves to that day's security. The alias switches on the new issue's auction date; an issued variant (`UST-10Y-OTR-ISSUED`) switches on its issue date, for uses that need a settled security with a price.
- **Load job** (`POST /jobs/load`), on the Asset `mkt_data_treasury_securities` plus nightly: reads new records, types and validates them, upserts instruments, terms and auctions, reports anything it can't type (counted like quote-svc's unmapped keys).
- The CMT seed file stays as it is; seeded and feed-built instruments live side by side.

## Terms for pricing

Everything needed to price each security (Bill, 2026-10-06). The terms are stored; the cash-flow schedule itself is generated later by the analytics library, not here (Bill, 2026-10-06). **P** = published by TreasuryDirect (field names confirmed in step 1), **D** = derived here from published terms, with the rule recorded.

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
- **Not here:** yields from prices, accrued interest computed per day, analytics (a later phase, on top of these terms).

## Custom UI and voice

- **mkt-api:** securities search (short name, CUSIP, coupon, maturity), a security's terms and auctions, lists of outstanding securities by type and maturity, and prices through the existing `/api/bars` series request (a CUSIP or short name is just another instrument).
- **mkt-ui:** a **Securities** screen (outstanding issues by maturity, filterable by type, with the on-the-runs marked) and a **Security** page (terms, auction history, price over time).
- **home-mcp:** `mkt_data_security` ("what's the 10-year on-the-run?", "when does the 4¼ of 2035 mature?") and the auction calendar ("what's auctioning this week?").

## Platform screens: Sources and Calendars (Bill, 2026-10-06)

Two screens in mkt-ui about the platform itself rather than one data family. They need two more upstreams for mkt-api: mkt-data (sources and captures) and calendar-svc (calendars), both over gRPC on the home-platform network like secmaster-svc and quote-svc. Grafana keeps the alerting and the operational graphs; these screens are for reading what the platform holds and where it came from.

**Sources** (one row per source, every family: calendars, CMTs, securities, and whatever comes next)

- **What it is:** name, publisher, description, link to the publisher's page, terms page, format, how it's fetched (period kind: whole, day, month, year).
- **What's pulled from it:** the datasets, series or fields taken (e.g. UST-PAR: 14 par-curve tenors; TD-SECURITIES: terms and auction results per CUSIP), which layer reads it (calendar-svc, secmaster-svc, quote-svc) and what it feeds (calendars, instruments, quotes), and its role (primary, cross-check, history before a date). Kept as a short `pulls` description in each source's spec in mkt-data, so the screen and the code can't drift apart.
- **Status:** last fetch and its outcome, last new capture, latest parse (ok, failed, or kept raw: no parser yet), schedule (the DAG and its next run), whether it's stale against that schedule, any alert firing for it.
- **Coverage and size:** first and last period, periods held, gaps, raw captures and bytes, near-raw rows.
- **Drill-down:** a source's recent checks and captures; a capture's text (the same view as home-mcp's `mkt_data_capture_text`), never rendered as the publisher's page.

**Calendars** (calendar-svc's golden calendars: FED, SIFMA-US, NYSE, and CME later)

- **List:** each calendar, its time zone, its sources in precedence order, coverage by kind (published / rules / projected) and the furthest year covered, the next close and early close.
- **Year view:** a year as twelve month grids, closes and early closes marked with holiday name, close time and the source that decided each day; projected years marked as such.
- **Upcoming:** the next closes and early closes across all calendars, side by side (where FED, SIFMA-US and NYSE differ).
- **Day lookup:** is a date a business day on each calendar, and why not.
- **Disagreements and history:** days where sources disagree (held by a higher source), the cited exceptions (e.g. SIFMA-US 2001-09-11), and how a day's status changed over time.

## Monitoring and alerts

- **mkt-data:** phase 1's capture stale and parse failed cover both new sources.
- **secmaster-svc:** records it couldn't type (warn), securities load stale or failed (warn), an auction whose results are overdue after its auction date (info).
- **quote-svc:** prices missing for outstanding securities on the last business day by 9:00 a.m. Eastern (warn), prices outside a sanity band or repeating (info).
- **Grafana:** a Treasury securities row on Market data: counts by type, outstanding, last load, untyped records, price coverage; storage.

## Steps

1. 🚧 **Raw capture first** (mkt-data; built, waiting on merge and deploy). Sources `TD-SECURITIES`, `TD-PRICES` and `FD-AUCTIONS`, fetched and kept raw with no parser yet. A daily DAG captures from today on. Read the first captures on the hub: formats, field names, history depth of each, FedInvest's time of day and whether past dates can still be fetched. Fixtures via `capture-export.yml`. Settle the open source questions above.
   - **Built:** `app/securities/sources.py` with the five sources, all kept raw (`parse` is None): TD-SECURITIES and FD-AUCTIONS by month of auction (up to a month ahead, for announcements), TD-PRICES by day (FedInvest's CSV form, posted), FD-MSPD-STRIPS by month, BLS-CPI by year (deduped on content, ignoring BLS's `responseTime`, via a new `SourceSpec.dedupe_view`). Job `POST /jobs/securities/{source}/capture?period=`. DAG `mkt_data__treasury_securities_capture` (weekdays 7:15 p.m. New York, one task per source; TD-PRICES only on SIFMA-US business days, today and the previous one) and manual `mkt_data__treasury_securities_probe` (one source, the periods typed in its form) for finding each source's first period. The capture text view (home-mcp's `mkt_data_capture_text`) now reads JSON (pretty-printed) and CSV/XML, not only HTML. Stale-capture and parse metrics label the new sources (BLS-CPI under FED, the rest SIFMA-US).
   - **First captures (2026-10-06, captures #1261–#1267):** TD-SECURITIES works with MM/DD/YYYY dates: JSON, one object per security and auction, every field documented, empty strings for blanks, plus `tintCusip1`/`tintCusip2` and their due dates (interest STRIPS CUSIPs, filled on some records). FD-AUCTIONS works: the same records in snake_case with the string `"null"` for blanks. FD-MSPD-STRIPS (`mspd_table_5`) works: per month-end, each principal STRIPS CUSIP (`cusip`) with its underlying security's CUSIP (`security_class2_desc`), coupon, maturity, and amounts outstanding, unstripped, stripped and reconstituted (in thousands). BLS-CPI works: monthly CPI-U index values for the year. TD-PRICES failed with HTTP 403: FedInvest's form posts `priceDate` (YYYY-MM-DD) with a session-bound `_csrf` token (read in the browser), so the fetch now gets the form first for the session and token, then posts, and keeps the results page (deduped on visible text, since the token changes every time).
   - **FedInvest prices (fixed in #79; captures #1268–#1271, 2026-10-06):** the results page is a table of about 470 securities: CUSIP, security type (`MARKET BASED BILL`, `MARKET BASED NOTE`, `MARKET BASED BOND`, `TIPS`, `MARKET BASED FRN`), rate, maturity date, call date, buy, sell, end of day. No CSV link on the page. A price not available is printed `0.000000`. End-of-day prices for a date appear the next day (2026-10-05 had them by the evening of the 6th; the 6th's were all zero), and buy and sell differ from end of day (taken at another time of day), so the daily capture's re-fetch of the previous business day is what brings in each day's end-of-day prices. The table's empty cells (call date) vanish in the text view, so the parser reads the table, not the text. Whether STRIPS are included: not as their own rows on 2026-10-06. History depth: the form sets no limit; the probe DAG's sampling run (below) finds it.
   - **Probe sampling:** `mkt_data__treasury_securities_probe` run with its form as it is samples one period a year per source (TD-SECURITIES and FD-AUCTIONS from 1979, FD-MSPD-STRIPS from 1985, TD-PRICES from 2000) and logs sizes; a source's first year is where the answers stop being empty.
   - **History depth (sampling run, 2026-10-06, captures #1272–#1436):** TD-SECURITIES and FD-AUCTIONS both start in 1980 (February 1979 empty, February 1980 has the same 14 auctions in each). FD-MSPD-STRIPS starts in 2001 (January 2000 empty); STRIPS before that are still identified by TreasuryDirect's `corpusCusip` and `tintCusip` fields, only without monthly stripped amounts. TD-PRICES starts between 2008-01-09 (an empty page) and 2009-01-14 (prices), so about 18 years of daily prices. Every source serves its whole history on request, so the lookback risk is low and backup capture can stay in "Later". The backfill (step 5) finds each source's exact first period. All the sampled periods are kept as raw captures.
2. ✅ **Near-raw** (mkt-data #82, deployed 2026-10-06; rebuild DAG #83):
   - **Parsers and records:** migration 0008 adds `record` (source, period, `record_type`, `source_key`, `as_of`, `fields` as JSONB exactly as published, capture, `valid_from`/`valid_to`), with the same history rules as `observation`. `app/securities/parsers.py`: TD-SECURITIES and FD-AUCTIONS give one `auction` record per security and auction, keyed `CUSIP/issue date` (a reopening has its own issue date) and placed in the period by auction date; FD-MSPD-STRIPS gives a `stripped_security` record per principal STRIPS CUSIP and month-end, plus the table's four subtotal and grand-total lines as `stripped_total` records (the lines add up to the grand total); TD-PRICES gives observations per CUSIP, fields `buy`, `sell`, `eod`, unit `per_100`, with `0.000000` (not available) left out; BLS-CPI gives monthly `index` observations dated the first of the month, the annual average (M13) and unpublished months (`-`, October 2025) left out. Fiscal Data answers with more than one page are refused rather than half-read. Observation periods can now be a day or a year as well as a month. `POST /jobs/securities/{source}/rebuild` replays every capture. Written and tested against nine real captures exported from the hub (`tests/fixtures/td_securities_*`, `fd_*`, `td_prices_*`, `bls_cpi_*`); on them, TreasuryDirect and Fiscal Data list the same 11 October auctions under the same keys.
   - **Read API:** gRPC `Records` (`proto/records.proto`, `app/securities/api.py`) mirroring `Observations`: `ListSources`, `ListPeriods` (each period's `latest_capture_id`, record count, first and last dates) and `GetPeriod` (current records, optionally superseded ones, each with its fields as a JSON object of strings), for secmaster-svc to read by watermark. `Observations` now also serves TD-PRICES (a period per day) and BLS-CPI (a period per year), for quote-svc.
   - **On the hub:** the daily capture parsed every source cleanly, and `mkt_data__treasury_securities_rebuild` (manual; one source after another) applied all 177 stored captures with no parse failures: TD-SECURITIES and FD-AUCTIONS 934 auction records each over the same 50 months (1980-02 to 2026-10, the same keys in both), FD-MSPD-STRIPS 7,665 records over 44 months (2001-01 to 2026-09), TD-PRICES 22,071 values over the sampled days (2009-01-14 to 2026-10-06), BLS-CPI 8 values (2026). The step 1 captures and the sampling probe's are now near-raw, and the parse-failed alert covers the new sources.
   - **Sizing for the backfill (step 5):** about 18 years of daily prices is roughly 4,500 price dates × about 1,400 values, some 6 million observation rows, far more than the CMTs' quarter million. The rebuild reads a capture at a time, so memory isn't the limit, but the table, its indexes and quote-svc's load get sized before the full backfill runs.
3. 🚧 **secmaster-svc:** types, effective-dated terms (published and derived), auctions, identifiers (CUSIP, ISIN, FIGI), short names, on-the-run aliases, load job on the Asset. Then the TIPS index ratios (needs `BLS-CPI` through near-raw), checked against TreasuryDirect's published figures; and STRIPS (below).
   - **3a, Treasury securities** (secmaster-svc #4 and mkt-data #85, built 2026-10-07, waiting on merge): a load job reads mkt-data's `Records` (TD-SECURITIES) by period watermark, like quote-svc reads `Observations`, and types each auction record (`app/treasuries.py`). One instrument per CUSIP (`ust_bill`, `ust_note`, `ust_bond`, `ust_tips`, `ust_frn`); a reopening is another auction of it. Migration 0003: `security_terms` (typed; one current row per security with history; `provenance` per term, "published: TD-SECURITIES <record> <field>" or "derived: <rule>"; `checks`), `auction` (every auction and reopening, results typed, fields as published, lineage to mkt-data's record and capture), watermarks, `untyped_record`, `load_run`. Terms come from the original auction, or from a reopening's `original*` fields until the original is loaded (flagged in `checks`). Derived: day count, frequency, end-of-month rule, penultimate coupon, first-period type checked against the regular schedule back from maturity, redemption, T+1, SIFMA-US. CUSIP (check digit verified) and ISIN (computed) identifiers. Short names as decided, with the CUSIP appended on a clash. Status refreshed each load: active, matured, called (the pre-1985 callable bonds carry `calledDate`), withdrawn. mkt-data marks the Asset `mkt_data_treasury_securities` when an auction is added, changed or removed (capture DAG) and after a TD-SECURITIES rebuild; `secmaster_svc__load` runs on it plus nightly. Checked on three real months (1980-02, 2026-02, 2026-10): the 2-year due 2028-02-29 pays Aug 31 and Feb 28/29, 1980's 5-year 2-month and 7-year 3-month notes have the long first coupons TreasuryDirect publishes, the 1980 30-year was called in 2005.
   - **Found in the data:** TreasuryDirect's `term` is the auction program in every record: a 13-week bill auction is a reopening of a 26- or 52-week bill (same CUSIP) with `term` "13-Week", a reopened 30-year is "30-Year", and 1980's 5-year 2-month note is "5-Year". So the on-the-run aliases (3b) follow `term`: the 13-week on-the-run is the latest 13-week auction, whichever bill it reopened.
   - **Still to do:** 3b on-the-run aliases, 3c STRIPS, 3d FIGI (OpenFIGI key), 3e TIPS index ratios.
4. **quote-svc:** prices by CUSIP, golden `price`, freshness against outstanding securities.
5. **Backfill** as far back as each source allows, a year at a time; cross-check TreasuryDirect's auctions against Fiscal Data's.
6. **Schedule** on SIFMA-US, with retries until the day's file is in.
7. **Monitoring** as above.
8. **Platform screens** (mkt-data, calendar-svc, mkt-api, mkt-ui): mkt-data and calendar-svc gRPC reads as needed (sources with their `pulls`, checks and coverage; calendars, years, upcoming closes, disagreements), mkt-api's two new upstreams, then the Sources and Calendars screens. Independent of the securities data, so they can be built any time; the Sources screen is most useful early, while the new sources are being watched.
9. **mkt-api and mkt-ui:** Securities and Security screens.
10. **home-mcp tools.**

## Decisions (Bill, 2026-10-06)

- **Scope:** Treasury securities by CUSIP, with TIPS and FRNs priced and charted too.
- **Platform screens:** a Sources screen (status and what's pulled from each source) and Calendar screens in mkt-ui.
- **Short names** as proposed: `UST-4.25-2035-08-15`, `UST-B-2026-12-24`, `UST-TII-…`, `UST-FRN-…`.
- **On-the-run aliases** with history.
- **Identifiers:** as many as we can (CUSIP, ISIN, FIGI and the rest).
- **Terms:** everything needed to price each security, at least issue, announcement, accrual start, first and penultimate coupon, maturity and coupon.
- **No cash-flow schedule** in this phase: the analytics library will generate it from the stored terms.
- **STRIPS** in scope, principal and interest.
- **OpenFIGI key:** yes, registered at step 3.
- **On-the-run switch day:** the auction date, the market convention (the new issue becomes the benchmark once the auction sets its coupon), with both auction and issue dates kept on the alias and an "issued" variant (switching on the issue date) for anything that needs a settled security with a price.

## Open questions


## Later (not this phase)

- Yields, accrued interest and risk from prices; the curve fitter.
- Amount outstanding by holder, from the Monthly Statement of the Public Debt.
- Carried over from phase 2: fixings (SOFR, EFFR), real yields, backup capture, the near-live macro dashboard, the shared chart layer, calendar closes as chart events.
