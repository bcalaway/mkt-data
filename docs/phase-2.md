# Phase 2: Treasury CMT yields end to end

**Status: planned (2026-10-04), not started.** Bill's decisions are recorded under "Decisions" below; one question is still open. Phase 1 (holiday calendars) is complete: see [phase-1.md](phase-1.md).

**Goal:** the first market data through every layer: sourcing → raw store → near-raw observations → security master and golden quotes → Airflow schedule → monitoring and alerts → the first screens of the custom UI. Phase 1 proved the pipeline on reference data. Phase 2 sets up the layering every later dataset uses, and fills it with one data family before anything else arrives.

**Scope (Bill, 2026-10-04):** US Treasury constant-maturity (CMT) yields, the security master, the quote store and a dashboard. Treasuries first, per the design ("Market Data Platform — Data Layer Architecture"). Not in this phase: individual Treasury securities (CUSIPs, auctions, terms), SOFR/EFFR, real (TIPS) yields and the NUC/Lambda backup capture; see "Later" at the end.

## Layers (Bill, 2026-10-04)

- **mkt-data is ingestion.** It captures every source raw (as in phase 1) and parses each capture into **near-raw observations**: the source's own data, in the source's own terms (Treasury's `BC_10YEAR` on a date, as printed, in percent), each linked to its capture. It knows nothing about security master IDs or which source wins.
- **Services own the golden copies**, each built from near-raw:
  - `secmaster-svc`: instrument identity, short names, and the map from a source's key (`UST-PAR` / `BC_10YEAR`) to an instrument (`UST-10Y-CMT`).
  - `quote-svc`: golden quotes per instrument, date and field, with source priority, revisions and history.
  - Calendars: today mkt-data builds both their near-raw and golden rows. Their golden copy moves to a service later (open question 1).
- **Services pull.** A service's job reads new near-raw rows from mkt-data over gRPC (internal, on the `home-platform` network, per ADR-0020), maps them through secmaster-svc and writes its own tables. Dependencies point one way, mkt-data needs no other app's database credentials, and every golden table can be rebuilt from near-raw at any time.
- **Airflow orchestrates; the services hold the logic** (ADR-0031). Each repo keeps its own DAGs, and each task calls that app's `/jobs` API. mkt-data's capture DAG marks an Airflow **Asset** (e.g. `mkt-data/ust-par-observations`) when it loads new observations, and quote-svc's DAG is scheduled on that Asset, plus a nightly catch-up run in case an event is missed.
- **Two front ends.** Grafana is operational only: capture health, coverage, alerts, storage. Yields and every other market view are rendered in the custom UI (`mkt-ui`, through the `mkt-api` gateway).

## What a CMT yield is, and where it comes from

Treasury fits a par yield curve every trading day from indicative bid-side prices of the most recently auctioned bills, notes and bonds, which the New York Fed collects at or near 3:30 p.m. Eastern. The CMT yields are read off that curve, so they are not the yield of any one security ([methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology), [FAQ](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rates-frequently-asked-questions)). The Fed's H.15 republishes the same numbers, noting that Treasury interpolates them from its daily curve ([H.15](https://www.federalreserve.gov/releases/h15/)). So there is one producer and two publishers.

Things the data model has to absorb (checked 2026-10-04):

- **The tenor set changes.** Today's columns are 1, 1.5, 2, 3, 4 and 6 months, then 1, 2, 3, 5, 7, 10, 20 and 30 years. The 1.5-month point arrived with the 6-week bill (CSV from 2025-02-14, element `BC_1_5MONTH`) and the 4-month with the 17-week bill (CSV from 2022-10-18, `BC_4MONTH`) ([developer notice](https://home.treasury.gov/developer-notice-xml-changes)). Older gaps are expected too (2-month and 1-month added later; the 30-year missing while it wasn't issued, 2002–2006). Step 6 records each series' real first date and gaps from the data rather than from this list.
- **The method changed.** Quasi-cubic Hermite spline until December 6, 2021, monotone convex since. The 20-year used composite off-the-run inputs before the bond's return on May 20, 2020. Both are notes on the series, not separate series.
- **Missing values are omitted elements** in the XML since June 2, 2022, not empty tags.
- **Units:** both publishers print percent (`4.25`). Near-raw keeps that with its unit; golden quotes are decimals (`0.0425`), like every rate.

## Sources

| Source | What | URL | History | When | Role |
|---|---|---|---|---|---|
| `UST-PAR` | Daily Treasury Par Yield Curve Rates, XML feed | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=YYYYMM` (or `field_tdr_date_value=YYYY` for a year) | 1990 on | Usually by 6:00 p.m. Eastern the same day | Primary |
| `H15-TCM` | Fed H.15 Treasury constant maturities, Data Download Program CSV (business-day series such as `RIFLGFCY10_N.B`) | `https://www.federalreserve.gov/datadownload/` (exact package URL fixed in step 1) | 1962 on for the 10-year (checked); other tenors start later, recorded in step 6 | 4:15 p.m. Eastern the next business day | History before 1990, and a cross-check |

Notes:

- **No Fiscal Data, no FRED.** The design listed Fiscal Data for the par curve, but the curve isn't one of its datasets; it lives on home.treasury.gov. FRED's `DGS*` series are H.15 again and need an API key; the H.15 Data Download Program serves the same series without one, so the FRED registration can wait until a series only FRED has.
- **XML over CSV** for Treasury: the feed is documented, takes a month or year parameter, and has named elements per tenor, so a new tenor is a new element rather than a shifted column. It pages at 300 rows (zero-based `page=`), so a year fits in one page.
- **Capture unit:** one capture per source per month (Treasury) or per series package (H.15). During a month, each day's fetch of the current month either matches the last capture (unchanged) or is a new version that adds the day. A changed value for a day already held is a **revision**: a new observation version in near-raw, and history in the quote store.
- **Terms:** Treasury and Board data are U.S. Government works. Step 1 records each source's terms page next to its URL.
- **Lookback risk is nil** for both: each serves its full history, which is why backup capture can wait.
- **Publication calendar:** Treasury publishes on U.S. Government Securities Business Days, which is calendar SIFMA-US. To verify in step 6 from the data itself: every SIFMA-US business day from 1996 has a curve, no full close has one, and what happens on SIFMA's early-close days (expected: published). Any exception becomes a cited exception in a publication calendar, like phase 1's rules files.

## Near-raw observations (mkt-data)

One generic table for every time series (Bill, 2026-10-04); calendars keep their own tables.

- **`observation`:** `source`, `source_key` (the source's own name for the series: `BC_10YEAR`, `RIFLGFCY10_N.B`), `as_of`, `field` (`yield`), `value` (`numeric`, exactly as published), `unit` (`percent`), `capture_id`, `valid_from`/`valid_to` (a revision closes the old row and opens a new one, like `calendar_day`).
- Rebuildable from raw, like every processed table.
- **gRPC read API:** observations for a source since a change watermark (what a service's job pulls), and for a source, key and date range (rebuilds and backfills).
- Metrics stay as phase 1's, plus the latest `as_of` per source and key.

## Security master (`secmaster-svc`)

A new app repo from the platform's Python template (Alembic, gRPC on 9090), registered in `apps/registry.yml` with its own database. It owns instrument identity; quote-svc and mkt-ui know instruments by `sec_id` and short name.

- **`instrument`:** hidden integer `sec_id`, `type` (`cmt_yield` in this phase; `bond`, `future`, `fixing`… later), currency, country, `curve` (`UST`), `tenor` (ISO 8601 duration: `P10Y`, `P6W`), status, the calendar it follows (by name, `SIFMA-US`), created_at.
- **`short_name`:** unique and readable, used in every view, log line, metric label and voice answer: `UST-1M-CMT`, `UST-1.5M-CMT`, `UST-2M-CMT`, `UST-3M-CMT`, `UST-4M-CMT`, `UST-6M-CMT`, `UST-1Y-CMT`, `UST-2Y-CMT`, `UST-3Y-CMT`, `UST-5Y-CMT`, `UST-7Y-CMT`, `UST-10Y-CMT`, `UST-20Y-CMT`, `UST-30Y-CMT` (14 series; Bill, 2026-10-04). A rename keeps the old name as an alias; `UST-6W-CMT` starts as an alias of `UST-1.5M-CMT`.
- **`identifier`:** `(sec_id, scheme, value, valid_from, valid_to)`. For CMTs: the `UST-PAR` element (`BC_10YEAR`), the `H15-TCM` series (`RIFLGFCY10_N.B`) and FRED (`DGS10`) for reference. This is the map quote-svc uses to turn an observation into a quote, so no code hard-codes IDs.
- **`instrument_note`:** dated notes that explain a series without splitting it (the 2021 method change, the 20-year's composite inputs before 2020-05-20).
- **Seed file (Bill, 2026-10-04):** CMTs aren't in any feed, so the 14 instruments, their identifiers and notes come from a versioned file in the repo, applied by an idempotent seed job. Adding a tenor is a reviewed PR. Instruments that do come from a feed (Treasury securities, later) arrive through mkt-data's near-raw like everything else.
- **gRPC API:** look up by `sec_id`, short name, alias or external identifier; search; list by type and curve; batch-resolve identifiers.

Effective-dated terms (`valid_from`/`valid_to`/`recorded_at`) arrive with the first instrument that has terms, the Treasury securities after this phase. CMTs have none.

## Quote store (`quote-svc`)

A new app repo, same template, its own database.

- **`quote`:** `(sec_id, source, as_of, field)` → `value` (`numeric`, decimal), plus `observation_id` and `capture_id` (lineage back through near-raw to the raw capture) and `loaded_at`. For CMTs `field` is `yield` and `as_of` is the business date.
- **`quote_history`:** a revised value moves the old row here with when it was superseded, so any past view can be rebuilt.
- **Golden value:** per `(sec_id, as_of, field)`, from a per-field source priority: `UST-PAR`, then `H15-TCM`, recording which source won. H.15 fills only the years before 1990; from 1990 it's a cross-check. A table refreshed on load, not a view, so reads stay cheap.
- **Load job** (`POST /jobs/load`, run by Airflow): pull observations since the last watermark from mkt-data, resolve `source_key` → `sec_id` through secmaster-svc, convert percent to decimal, upsert quotes, refresh golden values, report disagreements. Idempotent, so a retry or a rebuild is safe. A rebuild re-reads a date range from scratch.
- **gRPC API:** a range of values for one or more `sec_id`s and a field (golden by default, or one source); the whole curve on a date; source comparison for a range; latest `as_of` per `sec_id`. quote-svc returns `sec_id`s and never calls secmaster-svc per request; mkt-api adds the names.
- **Size:** about 14 series × ~9,000 business days since 1990, plus H.15's older years: a few hundred thousand rows. Plain Postgres.

## Custom UI (`mkt-api`, `mkt-ui`)

Yields are rendered in our own UI, not Grafana (Bill, 2026-10-04). Phase 2 starts both repos with the smallest useful screens, built the way the design's extensibility rules describe:

- **`mkt-api`** (Python template): the gateway. gRPC to secmaster-svc and quote-svc, HTTP JSON to the browser, enrichment with short names, an OpenAPI schema. Holds no data.
- **`mkt-ui`** (React template, TypeScript): a typed client generated from mkt-api's OpenAPI schema in CI, so a breaking API change fails the UI build; each screen a self-contained module registering its route.
- **Screens:**
  - **Yield curve:** the curve on a date, with comparison dates (a week, a month, a year ago).
  - **Series:** one or more CMTs over time, with spreads (2s10s, 3m10y), source shown on hover.
  - **Security master:** search by short name or identifier, an instrument's identifiers, notes and sources.
- **Ingress and auth:** `mkt.billandjessie.com` (name to confirm) with a Traefik route and Route 53 record; Authentik OIDC (Pattern A). Reached like the platform's other apps.

## Grafana (operational)

Rows added to **Market data** (`uid: market-data`):

- **Ingestion** (mkt-data): per source, last capture, parse outcome, latest `as_of` in near-raw, revisions.
- **Golden quotes** (quote-svc): per series, latest golden `as_of`, missing SIFMA-US business days, UST-PAR/H15-TCM disagreements, coverage (first and last date, expected vs present days, gaps).
- **Storage:** quote-svc's and secmaster-svc's database sizes next to mkt-data's.

## Monitoring and alerts

Each service serves its own `GET /metrics`, scraped by Prometheus, with Grafana alert rules emailing, so an alert names the layer that broke (Bill, 2026-10-04):

- **mkt-data (ingestion):** phase 1's capture and parse gauges cover the new sources; plus latest `as_of` per source and key. Alerts: capture stale, parse failed.
- **quote-svc (golden):** latest golden `as_of` per series; expected-but-missing business days against SIFMA-US (the curve isn't due on a holiday, so a holiday never alerts); source disagreements; revisions; stale values (the same yield repeated across many days). Alerts: Treasury curve missing for the last business day by 9:00 a.m. Eastern the next day (warn); any disagreement between the two publishers (warn: they should be identical); a revision (info, dashboard only).
- **secmaster-svc:** instrument counts and unmapped identifiers (an observation key with no instrument), which would otherwise surface as missing quotes.

## Steps

Each step is its own PR (or a pair, when it touches nyc_pa_aws_gitops too).

1. **Raw capture first** (mkt-data). Sources `UST-PAR` and `H15-TCM`, fetched and kept raw with no parser yet, as phase 1 did with new documents, so the parsers are written against real bytes. One schema change: CMT captures need a **period key** (`2026-10` for a month, or the H.15 package) so dedupe and revisions are per period. Migration 0004: `capture.period` (nullable for the calendar sources), dedupe on `(source, period, sha256)`. Fixtures via `capture-export.yml`.
2. **Near-raw** (mkt-data). The `observation` table, the `UST-PAR` XML and `H15-TCM` CSV parsers (`ND` and blanks are no value), revisions as new versions, and the gRPC read API.
3. **Platform onboarding** (nyc_pa_aws_gitops). `secmaster-svc`, `quote-svc`, `mkt-api` and `mkt-ui` in `apps/registry.yml` (databases for the two services; `airflow: true` for quote-svc and secmaster-svc; Authentik for mkt-ui), their `github_repo_id`s, scrape jobs, then each repo's first PR from `templates/python` or `templates/react`. mkt-ui's DNS record and Authentik client.
4. **secmaster-svc.** Schema, the CMT seed file and seed job, the gRPC API, metrics, tests.
5. **quote-svc.** Schema, golden values with the source priority, the load job, the gRPC API, metrics, tests.
6. **Backfill.** UST-PAR from 1990 (one capture per month, ~440 captures); H15-TCM from each series' start; then a full quote-svc load. Record each series' real first date, gaps and tenor changes; check the publication calendar against SIFMA-US; reconcile the overlap from 1990 (every disagreement reported, none expected).
7. **Schedule.** `mkt_data__ust_par`: weekdays from 6:30 p.m. Eastern, first task the SIFMA-US business-day check, then capture the current month (and the previous one for the first few days of a month), retrying until about 10 p.m.; marks the Asset when it loads new observations. `mkt_data__h15_tcm`: weekdays after 4:15 p.m. Eastern, same pattern. `quote_svc__load`: on the Asset, plus nightly. New DAGs start paused.
8. **Monitoring.** The gauges and alert rules above (alert rules in nyc_pa_aws_gitops, like phase 1), and the Grafana rows.
9. **mkt-api and mkt-ui.** The gateway and the three screens above.
10. **home-mcp tools.** `mkt_data_yield("UST-10Y-CMT", date)` and `mkt_data_curve(date)`, answering with short names and saying which source a value came from, so "what was the 10-year yesterday?" works by voice; plus the existing checks tools for the new sources.

## Decisions (Bill, 2026-10-04)

- **Layering:** ingestion in mkt-data (raw and near-raw); golden copies owned by services (calendars, security master, quotes to start); services pull from near-raw; Airflow orchestrates and the services hold the logic. Build secmaster-svc and quote-svc in this phase.
- **Yields are rendered in the custom UI,** not Grafana; Grafana stays operational. So mkt-api and mkt-ui start in this phase.
- **Short names** as listed, `UST-1.5M-CMT` with `UST-6W-CMT` as an alias.
- **Near-raw stores values as published, with a unit;** golden quotes convert to decimals.
- **One generic observation table** for time series; calendars keep their own.
- **Golden rebuilds run on Airflow Asset events,** plus a nightly catch-up.
- **CMT instruments come from a seed file** in secmaster-svc.
- **Each service serves its own metrics and alerts** on its own layer.

## Still open

1. **Where calendars' golden copy goes, and when.** Recommendation: leave calendars in mkt-data for phase 2, then move their golden copy into secmaster-svc (reference data that instruments point at; a separate service is a lot of overhead for one table). mkt-data keeps their raw and near-raw, and the business-day check DAGs use moves with them.
2. **Chart library for mkt-ui** (from the design): TradingView Lightweight Charts (fast canvas time series), ECharts (general, good for curves) or Plotly. Recommendation: Lightweight Charts for series, ECharts for the curve, both behind the UI's own chart components so either can be swapped.
3. **mkt-ui's hostname:** `mkt.billandjessie.com` or another name.

Settled in the steps:

- H.15's exact package URL and series list, and each series' first date (steps 1 and 6).
- Whether Treasury publishes on every SIFMA early-close day, and any day where Treasury and SIFMA-US disagree (step 6).
- How often Treasury revises a published day, which sets whether revisions stay info or become warn (after a month of daily captures).

## Later (not this phase)

- **Treasury securities:** bills, notes and bonds by CUSIP from TreasuryDirect's securities data (terms, auctions, reopenings), with effective-dated terms and OpenFIGI cross-references; Treasury's end-of-day security prices. The curve fitter needs these.
- **Fixings:** SOFR and EFFR from the NY Fed, as `fixing` instruments on the same quote store.
- **Real yields:** Treasury's par real yield curve and H.15's TIPS CMTs, as `UST-…-REAL` series.
- **Backup capture** (NUC and Lambda + S3): its value comes with sources that serve only a short history; both CMT sources serve everything.
- **The near-live macro dashboard** in mkt-ui.
