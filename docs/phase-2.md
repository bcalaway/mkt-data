# Phase 2: Treasury CMT yields end to end

**Status: draft (2026-10-04), not started.** Steps 1 and 2 wait on the decisions marked **Decision** below. Phase 1 (holiday calendars) is complete: see [phase-1.md](phase-1.md).

**Goal:** the first market data through every layer: sourcing → raw store → security master → quote store → Airflow schedule → monitoring and alerts → dashboard. Phase 1 proved the pipeline on reference data; phase 2 adds the two services the design puts under all market data, `secmaster-svc` and `quote-svc`, and fills them with one data family before anything else arrives.

**Scope (Bill, 2026-10-04):** US Treasury constant-maturity (CMT) yields, the security master, the quote store and a dashboard. Treasuries first, per the design ("Market Data Platform — Data Layer Architecture"). Individual Treasury securities (CUSIPs, auctions, terms from TreasuryDirect), SOFR/EFFR, real (TIPS) yields and the NUC/Lambda backup capture are not in this phase; see "Later" at the end.

## What a CMT yield is, and where it comes from

Treasury fits a par yield curve every trading day from indicative bid-side prices of the most recently auctioned bills, notes and bonds, which the New York Fed collects at or near 3:30 p.m. Eastern. The CMT yields are read off that curve, so they are not the yield of any one security ([methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology), [FAQ](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rates-frequently-asked-questions)). The Fed's H.15 republishes the same numbers, noting that Treasury interpolates them from its daily curve ([H.15](https://www.federalreserve.gov/releases/h15/)). So there is one producer and two publishers.

Things the data model has to absorb (checked 2026-10-04):

- **The tenor set changes.** Today's columns are 1, 1.5, 2, 3, 4 and 6 months, then 1, 2, 3, 5, 7, 10, 20 and 30 years. The 1.5-month point arrived with the 6-week bill (CSV from 2025-02-14, element `BC_1_5MONTH`) and the 4-month with the 17-week bill (CSV from 2022-10-18, `BC_4MONTH`) ([developer notice](https://home.treasury.gov/developer-notice-xml-changes)). Older gaps are expected too (2-month and 1-month added later; the 30-year missing while it wasn't issued, 2002–2006); step 5 records each series' real first date and gaps from the data rather than from this list.
- **The method changed.** Quasi-cubic Hermite spline until December 6, 2021, monotone convex since. The 20-year used composite off-the-run inputs before the bond's return on May 20, 2020. Both are worth a note on the series, not separate series.
- **Missing values are omitted elements** in the XML since June 2, 2022, not empty tags.
- **Units:** both publishers print percent (`4.25`). Stored as decimals (`0.0425`), like every rate.

## Sources

| Source (proposed name) | What | URL | History | When | Role |
|---|---|---|---|---|---|
| `UST-PAR` | Daily Treasury Par Yield Curve Rates, XML feed | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=YYYYMM` (or `field_tdr_date_value=YYYY` for a year) | 1990 on | Usually by 6:00 p.m. Eastern the same day | Primary |
| `H15-TCM` | Fed H.15 Treasury constant maturities, Data Download Program CSV (business-day series such as `RIFLGFCY10_N.B`) | `https://www.federalreserve.gov/datadownload/` (exact package URL fixed in step 1) | 1962 on for the 10-year (checked); other tenors start later, recorded in step 5 | 4:15 p.m. Eastern the next business day | History before 1990, and a cross-check |

Notes:

- **No Fiscal Data, no FRED.** The design listed Fiscal Data for the par curve, but the curve isn't one of its datasets; it lives on home.treasury.gov. FRED's `DGS*` series are H.15 again and need an API key; the H.15 Data Download Program serves the same series without one, so Bill's FRED registration can wait until a series only FRED has.
- **XML over CSV** for Treasury: the feed is documented, takes a month or year parameter, and has named elements per tenor, so a new tenor is a new element rather than a shifted column. The feed pages at 300 rows (zero-based `page=`), so a year request fits in one page.
- **Capture unit:** one capture per source per month (Treasury) or per series package (H.15). During a month, each day's fetch of the current month either matches the last capture (unchanged) or is a new version that adds the day. A changed value for a day already held is a **revision**: kept as history in the quote store and reported (see Monitoring).
- **Terms:** Treasury and Board data are U.S. Government works. Step 1 records the terms page for each source next to its URL.
- **Lookback risk is nil** for both: each serves its full history, which is why backup capture can wait.
- **Publication calendar:** Treasury publishes on U.S. Government Securities Business Days, which is calendar SIFMA-US. To verify in step 5 from the data itself: every SIFMA-US business day from 1996 has a curve, no full close has one, and what happens on SIFMA's early-close days (expected: published). Any exception becomes a cited exception in a publication calendar, like phase 1's rules files.

## Security master (`secmaster-svc`)

A new app repo from the platform's Python template (Alembic, gRPC on 9090), registered in `apps/registry.yml` with its own database. It owns the instrument identity for everything; mkt-data and quote-svc know instruments only by `sec_id`.

- **`instrument`:** hidden integer `sec_id`, `type` (`cmt_yield` in this phase; `bond`, `future`, `fixing`… later), currency, country, `curve` (e.g. `UST`), `tenor` (ISO 8601 duration, e.g. `P10Y`, `P6W`), status, the calendar it follows (by name, `SIFMA-US`; see Decision 3), created_at.
- **`short_name`:** unique, readable, used in every view, log line, metric label and voice answer. Proposed: `UST-1M-CMT`, `UST-1.5M-CMT`, `UST-2M-CMT`, `UST-3M-CMT`, `UST-4M-CMT`, `UST-6M-CMT`, `UST-1Y-CMT` … `UST-30Y-CMT` (14 series). A rename keeps the old name as an alias.
- **`identifier`:** `(sec_id, scheme, value, valid_from, valid_to)`. For CMTs: `UST-PAR` element (`BC_10YEAR`), H.15 series (`RIFLGFCY10_N.B`) and FRED (`DGS10`) for reference. This is also how a parser maps a column to a `sec_id`: it never hard-codes IDs.
- **`instrument_note`:** dated notes that explain a series without splitting it (the 2021 method change, the 20-year's composite inputs before 2020-05-20).
- **API (gRPC):** look up by `sec_id`, short name, alias or external identifier; search; list by type and curve. A batch "resolve these identifiers" call for parsers.
- **Seeding:** the 14 CMT instruments come from a versioned file in the repo, applied by a migration or an idempotent seed job, so adding a tenor is a reviewed PR.

Effective-dated terms (`valid_from`/`valid_to`/`recorded_at`) arrive with the first instrument that has terms, the Treasury securities after this phase. CMTs have none.

## Quote store (`quote-svc`)

A new app repo, same template, its own database. Keyed exactly as the design says:

- **`quote`:** `(sec_id, source, as_of, field)` → `value` (`numeric`, decimal), plus `capture_id` (lineage back to mkt-data's raw capture) and `loaded_at`. `source` is a short name (`UST-PAR`, `H15-TCM`). For CMTs `field` is `yield` and `as_of` is the business date.
- **`quote_history`:** a revised value moves the old row here with when it was superseded, so any past view can be rebuilt.
- **Golden value:** per `(sec_id, as_of, field)`, from a per-field source priority: `UST-PAR`, then `H15-TCM`. It records which source won. In practice H.15 fills only the years before 1990 and the rest is a cross-check. Stored as a table refreshed on load, not a view, so reads stay cheap.
- **API (gRPC):** a range of values for one or more `sec_id`s and a field (golden by default, or one source); the whole curve on a date (every CMT `sec_id` on that `as_of`); source comparison for a range; latest `as_of` per `sec_id`. quote-svc returns `sec_id`s only and never calls secmaster-svc; whoever displays names enriches them.
- **Writes:** see Decision 2.
- **Size:** about 14 series × ~9,000 business days since 1990, plus H.15's older years: a few hundred thousand rows. Plain Postgres.

## Dashboard

Grafana stays the operational view; phase 2 adds rows to **Market data** (`uid: market-data`):

- **Health:** per source, last capture, last parse outcome, latest `as_of` loaded, missing business days against SIFMA-US, revisions in the last 30 days, UST-PAR/H15-TCM disagreements.
- **Coverage:** per series, first and last date, expected vs present days, gaps.
- **Market data:** the curve on a date (latest, a week ago, a year ago), and selected series over time (2Y, 10Y, 30Y; 2s10s and 3m10y spreads), with the readable short names. How Grafana reads the values is Decision 4.
- **Storage:** quote-svc's and secmaster-svc's database sizes next to mkt-data's.

The React front end (`mkt-api`, `mkt-ui`) starts in its own phase; Decision 4 explains why not here.

## Monitoring and alerts

Same pattern as phase 1: gauges on `GET /metrics`, scraped by Prometheus, Grafana alert rules emailing.

- `mkt_data_source_last_success_timestamp_seconds` and `_parse_ok` already cover the new sources once they are in `source`.
- New, labelled by short name: latest `as_of` loaded per series; **expected-but-missing business days** per source (a SIFMA-US business day with no value by the next morning; the curve isn't due on a holiday, so a holiday never alerts); revisions; UST-PAR vs H15-TCM disagreements; stale values (the same yield repeated across many days).
- Alerts: Treasury curve missing for the last business day by 9:00 a.m. Eastern the next day (warn); any disagreement between the two publishers (warn: they should be identical); a revision (info, on the dashboard).

## Steps

Each step is its own PR (or a pair, when a step touches nyc_pa_aws_gitops too).

1. **Raw capture first** (mkt-data). Sources `UST-PAR` and `H15-TCM`, fetched and kept raw with no parser yet, as phase 1 did with new documents, so the parsers are written against real bytes. Needs one schema change: a capture is today one version of one URL; CMT captures need a **period key** (`2026-10` for a month, or the H.15 package) so dedupe and revisions are per period. Migration 0004: `capture.period` (nullable for the calendar sources), and dedupe on `(source, period, sha256)`. Fixtures via `capture-export.yml`.
2. **Platform onboarding** (nyc_pa_aws_gitops). `secmaster-svc` and `quote-svc` in `apps/registry.yml` (`database: true`, no Authentik, no previews), then their `github_repo_id`s, then each repo's first PR from `templates/python`, internal only like mkt-data. Whatever Decision 2 needs on the platform side (a write grant or nothing) lands here.
3. **secmaster-svc schema and API.** `instrument`, `short_name`, `identifier`, `instrument_note`; the CMT seed; gRPC lookup, search and batch resolve; tests.
4. **quote-svc schema and API.** `quote`, `quote_history`, golden values with the source priority; gRPC range, curve-on-date, comparison and latest; the write path; tests.
5. **Parsers and load** (mkt-data). `UST-PAR` XML → one value per tenor element per day; `H15-TCM` CSV → one value per series per day (`ND` and blanks are no value). Each resolves identifiers through secmaster-svc, converts percent to decimals and writes through quote-svc with the capture's ID. Records each series' real first date, gaps and tenor changes here, and checks the publication calendar against SIFMA-US.
6. **Backfill.** UST-PAR from 1990 (one capture per month, ~440 captures); H15-TCM from each series' start. Reconcile the overlap (1990 on): every disagreement reported, none expected.
7. **Schedule** (mkt-data DAGs). `mkt_data__ust_par`: weekdays, starting 6:30 p.m. Eastern, first task the SIFMA-US business-day check, then capture the current month (and the previous one for the first few days of a month), retrying until about 10 p.m. `mkt_data__h15_tcm`: weekdays after 4:15 p.m. Eastern, same check. Both new DAGs start paused.
8. **Monitoring.** The gauges and alert rules above (alert rules in nyc_pa_aws_gitops, like phase 1).
9. **Dashboard.** The Market data rows above, once Decision 4 is settled.
10. **home-mcp tools.** `mkt_data_yield("UST-10Y-CMT", date)` and `mkt_data_curve(date)`, answering with short names and saying which source a value came from, so "what was the 10-year yesterday?" works by voice. Plus the existing checks tools for the new sources.

## Decisions for Bill

1. **Services now, or tables in mkt-data first?** The design puts secmaster-svc in phase 1 and quote-svc in phase 2, and you wanted the security master and quotes as microservices. Phase 1 kept calendars inside mkt-data, which worked well and was quicker. Recommendation: build both services now. CMTs are the first data with an identity and quotes, and retrofitting the boundary after more datasets arrive costs more. The price is two more repos and a slower start to the first numbers.
2. **How mkt-data writes to quote-svc.** The design says each service ships a Python write library that writes straight into its database. On this platform that means mkt-data's job holding a second database role (a writer on quote-svc's database), which the onboarding script doesn't create, and installing the library from a pinned Git tag of another repo. Recommendation: a batched gRPC write call instead (`WriteQuotes`, a few thousand rows per call; the whole backfill is a few hundred thousand rows). One role per app stays true and only quote-svc knows its schema, which was the point of the write library. The library can come back if bulk volumes ever need it.
3. **Where calendars live.** The design makes calendars secmaster-svc reference data; today they're in mkt-data, with their own API, DAGs, metrics and home-mcp tools. Recommendation: leave them in mkt-data this phase, with instruments naming their calendar (`SIFMA-US`). Moving them is a contained follow-up once secmaster-svc exists, and nothing here depends on it.
4. **How the dashboard reads yields.** The design says no other code reads a service's database. Options: (a) Grafana's Infinity data source calling a small read-only HTTP JSON endpoint on quote-svc, enriched with short names (keeps the rule, one plugin to add); (b) a read-only Postgres role for Grafana on a quote-svc view (simplest, bends the rule); (c) start mkt-api and mkt-ui now (the eventual front end, but two more repos and Authentik in a phase already adding two services). Recommendation: (a), with mkt-api/mkt-ui as their own phase, where the near-live dashboard you want also lands.
5. **The 1.5-month name.** `UST-1.5M-CMT` matches Treasury's "1.5 Mo" label; `UST-6W-CMT` matches the bill behind it. Recommendation: `UST-1.5M-CMT`, with `UST-6W-CMT` as an alias.

## Open questions (settled in the steps)

- H.15's exact package URL and series list, and each series' first date (step 1 and step 5).
- Whether Treasury publishes on every SIFMA early-close day, and any day where Treasury and SIFMA-US disagree (step 5).
- How often Treasury revises a published day, which sets whether revisions stay info or become warn (after a month of daily captures).

## Later (not this phase)

- **Treasury securities:** bills, notes and bonds by CUSIP from TreasuryDirect's securities data (terms, auctions, reopenings), with effective-dated terms and OpenFIGI cross-references; Treasury's end-of-day security prices. The curve fitter needs these.
- **Fixings:** SOFR and EFFR from the NY Fed, as `fixing` instruments on the same quote store.
- **Real yields:** Treasury's par real yield curve and H.15's TIPS CMTs, as `UST-…-REAL` series.
- **Backup capture** (NUC and Lambda + S3): its value comes with sources that serve only a short history; both CMT sources serve everything.
- **mkt-api and mkt-ui**, and the near-live macro dashboard.
