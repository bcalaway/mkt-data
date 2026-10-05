# Phase 2: the golden-copy layering, calendars first, then Treasury CMT yields

**Status: in progress (2026-10-04).** Part A done: calendars run on the new layering (calendar-svc owns the golden copy). Part B (Treasury CMT yields) next. Bill's decisions are recorded under "Decisions" below. Phase 1 (holiday calendars) is complete: see [phase-1.md](phase-1.md).

**Goal:** set up the layering every dataset uses from now on (ingestion and near-raw in mkt-data, golden copies in services) and take two data families through it:

- **Part A, calendars** (Bill, 2026-10-04): move phase 1's calendars onto the new layering first, with their golden copy in a new `calendar-svc`. The data, fixtures and expected answers already exist, so a flaw in the pattern shows up on known data, and the result can be checked against today's tables day for day before anything switches over.
- **Part B, Treasury CMT yields:** sourcing → raw store → near-raw observations → security master and golden quotes → Airflow schedule → monitoring and alerts → the first screens of the custom UI.

**Scope (Bill, 2026-10-04):** calendars on the new layering, then US Treasury constant-maturity (CMT) yields, the security master, the quote store and a dashboard. Treasuries first, per the design ("Market Data Platform — Data Layer Architecture"). Not in this phase: individual Treasury securities (CUSIPs, auctions, terms), SOFR/EFFR, real (TIPS) yields and the NUC/Lambda backup capture; see "Later" at the end.

## Layers (Bill, 2026-10-04)

- **mkt-data is ingestion.** It captures every source raw (as in phase 1) and parses each capture into **near-raw observations**: the source's own data, in the source's own terms (Treasury's `BC_10YEAR` on a date, as printed, in percent), each linked to its capture. It knows nothing about security master IDs or which source wins.
- **Services own the golden copies**, each built from near-raw:
  - `calendar-svc` (Bill, 2026-10-04): one calendar per market from its sources, with precedence, projection, coverage and the business-day answer. Its own service, not part of the security master, so anything that needs dates (a payment-schedule generator, every DAG) can use it without the rest.
  - `secmaster-svc`: instrument identity, short names, and the map from a source's key (`UST-PAR` / `BC_10YEAR`) to an instrument (`UST-10Y-CMT`). An instrument names the calendar it follows; calendar-svc serves it.
  - `quote-svc`: golden quotes per instrument, date and field, with source priority, revisions and history.
- **Services pull.** A service's job reads new near-raw rows from mkt-data over gRPC (internal, on the `home-platform` network, per ADR-0020), maps them where needed (quote-svc through secmaster-svc) and writes its own tables. Dependencies point one way, mkt-data needs no other app's database credentials, and every golden table can be rebuilt from near-raw at any time.
- **Airflow orchestrates; the services hold the logic** (ADR-0031). Each repo keeps its own DAGs, and each task calls that app's `/jobs` API. mkt-data's capture DAG marks an Airflow **Asset** (e.g. `mkt-data/ust-par-observations`) when it loads new observations, and quote-svc's DAG is scheduled on that Asset, plus a nightly catch-up run in case an event is missed.
- **Two front ends.** Grafana is operational only: capture health, coverage, alerts, storage. Yields and every other market view are rendered in the custom UI (`mkt-ui`, through the `mkt-api` gateway).

## Part A: calendars on the new layering

Today mkt-data does both jobs for calendars: it captures and parses each source, and it merges them into one calendar (`calendar_day`, `calendar_year`) with precedence, projection retirement and history (phase 1, steps 4–5). Part A splits that along the layer line.

**Stays in mkt-data (ingestion):**

- Every calendar source, captured raw exactly as now, including the `repo:` rules and projection files (each version of the rules is still a raw capture).
- **Near-raw calendar tables** (calendars keep their own shape, not the generic `observation`): `source_year` (the years a source covers, from which capture) and `source_day` (a source's closed and early-close weekdays as that source states them: date, status, close time, holiday name, capture, `valid_from`/`valid_to`). One set per source, with no precedence applied: two sources listing the same date both keep their row.
- Parse outcomes, captures, checks and their metrics and alerts (capture stale, parse failed), and home-mcp's capture and checks tools.
- A gRPC read API: a source's years and days (current and superseded). Calendars are small, so calendar-svc reads a source whole rather than by watermark.

**Moves to calendar-svc (golden):**

- The calendar definitions: each calendar's sources in precedence order, its time zone and its `next_year_due`.
- The merge: a higher source wins a date and a disagreement is reported (`held_by_higher_source`); a publisher takes over identical days from a lower source (`taken_from_lower_source`, phase 1's #30); a projected source fills only years no other source covers and gives a year up whole once a publisher covers it; history with `valid_from`/`valid_to`.
- Coverage by kind (published / rules / projected), gap years and the "next year published" check, with their metrics and alert.
- The business-day answer (`projected: true` from a projected year), for DAGs' short-circuit tasks, home-mcp's `mkt_data_business_day` and quote-svc's missing-day checks; plus upcoming closes for the Grafana panel.
- A load job (`POST /jobs/load`), run by Airflow on an Asset that mkt-data's calendar DAGs mark, plus nightly; a rebuild re-reads everything from near-raw.

**Proof before switching:** calendar-svc's golden calendar must match mkt-data's current `calendar_day` exactly (every date, status, close time and holiday name, and the projected flag) for FED, SIFMA-US and NYSE over their whole range, 1986–2100. A comparison job reports any difference; the switch waits for zero.

**The switch:** DAGs' business-day checks, home-mcp's `mkt_data_business_day` (renamed or repointed), the Grafana coverage and upcoming-closes panels, and the next-year alert move to calendar-svc. Then mkt-data's `calendar_day` and `calendar_year` are retired by a migration, and its calendar-shaped metrics and `/jobs/calendars/{name}/business-day` with them.

## Part B: Treasury CMT yields

## What a CMT yield is, and where it comes from

Treasury fits a par yield curve every trading day from indicative bid-side prices of the most recently auctioned bills, notes and bonds, which the New York Fed collects at or near 3:30 p.m. Eastern. The CMT yields are read off that curve, so they are not the yield of any one security ([methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology), [FAQ](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rates-frequently-asked-questions)). The Fed's H.15 republishes the same numbers, noting that Treasury interpolates them from its daily curve ([H.15](https://www.federalreserve.gov/releases/h15/)). So there is one producer and two publishers.

Things the data model has to absorb (checked 2026-10-04):

- **The tenor set changes.** Today's columns are 1, 1.5, 2, 3, 4 and 6 months, then 1, 2, 3, 5, 7, 10, 20 and 30 years. The 1.5-month point arrived with the 6-week bill (CSV from 2025-02-14, element `BC_1_5MONTH`) and the 4-month with the 17-week bill (CSV from 2022-10-18, `BC_4MONTH`) ([developer notice](https://home.treasury.gov/developer-notice-xml-changes)). Older gaps are expected too (2-month and 1-month added later; the 30-year missing while it wasn't issued, 2002–2006). Step B6 records each series' real first date and gaps from the data rather than from this list.
- **The method changed.** Quasi-cubic Hermite spline until December 6, 2021, monotone convex since. The 20-year used composite off-the-run inputs before the bond's return on May 20, 2020. Both are notes on the series, not separate series.
- **Missing values are omitted elements** in the XML since June 2, 2022, not empty tags.
- **Units:** both publishers print percent (`4.25`). Near-raw keeps that with its unit; golden quotes are decimals (`0.0425`), like every rate.

## Sources

| Source | What | URL | History | When | Role |
|---|---|---|---|---|---|
| `UST-PAR` | Daily Treasury Par Yield Curve Rates, XML feed | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=YYYYMM` (or `field_tdr_date_value=YYYY` for a year) | 1990 on | Usually by 6:00 p.m. Eastern the same day | Primary |
| `H15-TCM` | Fed H.15 Treasury constant maturities, nominal, business day: the Data Download Program's package of 11 series (`RIFLGFCM01_N.B` … `RIFLGFCY30_N.B`), CSV, by month (`&from=MM/01/YYYY&to=…`) | `https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78&…` | 1962 on for 1, 3, 5, 10 and 20 years; 7-year from 1969, 2-year 1976, 30-year 1977, 3- and 6-month 1981, 1-month 2001 (checked 2026-10-04). **No 1.5-, 2- or 4-month series.** Holidays are rows of `ND` | 4:15 p.m. Eastern the next business day | History before 1990, and a cross-check |

Notes:

- **No Fiscal Data, no FRED.** The design listed Fiscal Data for the par curve, but the curve isn't one of its datasets; it lives on home.treasury.gov. FRED's `DGS*` series are H.15 again and need an API key; the H.15 Data Download Program serves the same series without one, so the FRED registration can wait until a series only FRED has.
- **XML over CSV** for Treasury: the feed is documented, takes a month or year parameter, and has named elements per tenor, so a new tenor is a new element rather than a shifted column. It pages at 300 rows (zero-based `page=`), so a year fits in one page.
- **Capture unit:** one capture per source per month (`capture.period`, `2026-10`), for both sources. During a month, each day's fetch of the current month either matches the last capture (unchanged) or is a new version that adds the day. A changed value for a day already held is a **revision**: a new observation version in near-raw, and history in the quote store.
- **Terms:** Treasury and Board data are U.S. Government works. Step 1 records each source's terms page next to its URL.
- **Lookback risk is nil** for both: each serves its full history, which is why backup capture can wait.
- **Publication calendar:** Treasury publishes on U.S. Government Securities Business Days, which is calendar SIFMA-US. To verify in step B6 from the data itself: every SIFMA-US business day from 1996 has a curve, no full close has one, and what happens on SIFMA's early-close days (expected: published). Any exception becomes a cited exception in a publication calendar, like phase 1's rules files.

## Near-raw observations (mkt-data)

One generic table for every time series (Bill, 2026-10-04); calendars keep their own tables.

- **`observation`:** `source`, `source_key` (the source's own name for the series: `BC_10YEAR`, `RIFLGFCY10_N.B`), `as_of`, `field` (`yield`), `value` (`numeric`, exactly as published), `unit` (`percent`), `capture_id`, `valid_from`/`valid_to` (a revision closes the old row and opens a new one, like `calendar_day`).
- Rebuildable from raw, like every processed table.
- **gRPC read API:** observations for a source since a change watermark (what a service's job pulls), and for a source, key and date range (rebuilds and backfills).
- Metrics stay as phase 1's, plus the latest `as_of` per source and key.

## Security master (`secmaster-svc`)

A new app repo from the platform's Python template (Alembic, gRPC on 9090), registered in `apps/registry.yml` with its own database. It owns instrument identity; quote-svc and mkt-ui know instruments by `sec_id` and short name.

- **`instrument`:** hidden integer `sec_id`, `type` (`cmt_yield` in this phase; `bond`, `future`, `fixing`… later), currency, country, `curve` (`UST`), `tenor` (ISO 8601 duration: `P10Y`, `P6W`), status, the calendar it follows (by name, `SIFMA-US`, served by calendar-svc), created_at.
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
- **Ingress and auth:** `mkt.billandjessie.com` (Bill, 2026-10-04) with a Traefik route and Route 53 record; Authentik OIDC (Pattern A). Reached like the platform's other apps.

## Grafana (operational)

Rows added to **Market data** (`uid: market-data`):

- **Ingestion** (mkt-data): per source, last capture, parse outcome, latest `as_of` in near-raw, revisions.
- **Golden quotes** (quote-svc): per series, latest golden `as_of`, missing SIFMA-US business days, UST-PAR/H15-TCM disagreements, coverage (first and last date, expected vs present days, gaps).
- **Storage:** quote-svc's and secmaster-svc's database sizes next to mkt-data's.

## Monitoring and alerts

Each service serves its own `GET /metrics`, scraped by Prometheus, with Grafana alert rules emailing, so an alert names the layer that broke (Bill, 2026-10-04):

- **mkt-data (ingestion):** phase 1's capture and parse gauges cover the new sources; plus latest `as_of` per source and key. Alerts: capture stale, parse failed.
- **quote-svc (golden):** latest golden `as_of` per series; expected-but-missing business days against SIFMA-US, asked of calendar-svc (the curve isn't due on a holiday, so a holiday never alerts); source disagreements; revisions; stale values (the same yield repeated across many days). Alerts: Treasury curve missing for the last business day by 9:00 a.m. Eastern the next day (warn); any disagreement between the two publishers (warn: they should be identical); a revision (info, dashboard only).
- **secmaster-svc:** instrument counts and unmapped identifiers (an observation key with no instrument), which would otherwise surface as missing quotes.

## Steps

Each step is its own PR (or a pair, when it touches nyc_pa_aws_gitops too). Part A comes first; Part B starts once calendar-svc serves the business-day answer.

### Part A: calendars

1. ✅ **Calendar near-raw** (mkt-data). Two PRs:
   - ✅ **Tables and rebuild** (#45, migration 0004, deployed 2026-10-04): `source_year` and `source_day`; every capture job writes the source's parse there (no precedence) in the same transaction as the calendar; `POST /jobs/calendars/{name}/near-raw/rebuild` replays every stored capture, oldest first, with the captures' fetch times as `valid_from`/`valid_to`, so a rebuild gives the same rows; the manual DAG `mkt_data__calendar_near_raw_rebuild` fills near-raw on the hub from the captures taken before it existed. `calendar_day` and everything that reads it are untouched.
   - ✅ **Read API** (#46, deployed 2026-10-04; near-raw filled on the hub by `mkt_data__calendar_near_raw_rebuild`: every capture applied, counts as in phase 1): gRPC `CalendarSources` for calendar-svc (`ListSources`; `GetSource`, a source's years and days, current and optionally superseded, read whole since calendars are a few thousand rows), and the calendar DAGs and the rebuild marking the Asset `mkt_data_calendar_sources` after each successful run.
2. ✅ **Platform onboarding** (2026-10-04): nyc_pa_aws_gitops #126 (registry entry, scrape job, Milestone 23), #128 (`github_repo_id`), calendar-svc #1 (template, internal only). #126's first AWS apply raced the CI role's own `ecr:CreateRepository` grant (re-run passed; the wait is now 60s, #127). Along the way the platform's applies became one `platform-release.yml` behind one approval, and app deploys stopped needing approval (#129, ADR-0032).
3. ✅ **calendar-svc golden calendars** (2026-10-04, calendar-svc #2–#5): the schema and the merge ported from `apply` with its rules' tests (#2); `POST /jobs/load`, reading `CalendarSources` over gRPC, with DAG `calendar_svc__load` on the Asset `mkt_data_calendar_sources` or nightly, and `/metrics` (#3); the business-day answer at the same path as mkt-data's, `closes`, gRPC `calendar_svc.Calendars` and mkt-data's calendar gauges as `calendar_svc_calendar_*` (#4); gRPC `Coverage` for the comparison (#5). On the hub, a FED capture's Asset event started the load within seconds, and every count matches mkt-data's: days by status, years by kind, upcoming closes, no gap years.
4. ✅ **Prove it.** A comparison of calendar-svc's calendars against mkt-data's `calendar_day` for FED, SIFMA-US and NYSE, 1986–2100: every date, status, close time, holiday name and projected flag. Zero differences, or each one explained and fixed, before step 5.
   - **The comparison** (#47; calendar-svc #5 added `Coverage`): `POST /jobs/calendars/compare-with-calendar-svc` reads calendar-svc's `Closes` (1900–2100) and `Coverage` over gRPC (`proto/calendars.proto`, a copy of calendar-svc's) and compares them with `calendar_day` and `calendar_year`: every day's status, close time and holiday name, and every year's kind of source. DAG `mkt_data__calendar_svc_compare` runs it daily after calendar-svc's nightly load and fails when they differ. Both go away in step 5.
   - **Result (2026-10-04, 20:53 UTC): identical.** FED 1,151 days / 115 years, SIFMA-US 1,465 / 105, NYSE 1,151 / 111; no day or year differed, and every year's kind of source matched.
5. ✅ **Switch over** (2026-10-04, Bill: finish now, nobody uses it yet).
   - **Platform** (nyc_pa_aws_gitops #130): home-mcp's `mkt_data_business_day` asks calendar-svc with its own read token (`/home-platform/calendar-svc/read-token`); the Market data dashboard's calendar panels and the next-year alert read `calendar_svc_calendar_*`; new alerts for a stale or failed calendar-svc load. No DAG asked the business-day question yet, so none needed changing.
   - **mkt-data** (this PR, migration 0005): `calendar`, `calendar_year` and `calendar_day` dropped, with `apply`, the business-day endpoint, the calendar gauges, and the comparison job, its DAG and its proto copy. mkt-data keeps capturing every source, its near-raw rows, the source gauges and alerts, and `CalendarSources`. Its tests now check each source's near-raw rows; the precedence and projection rules are tested in calendar-svc.

### Part B: Treasury CMT yields

1. ✅ **Raw capture first** (mkt-data #49, deployed 2026-10-04). Sources `UST-PAR` and `H15-TCM` (`app/rates/sources.py`), fetched a month at a time and kept raw with no parser yet, so the parsers are written against real bytes. Migration 0006: `capture.period` and `source_check.period`, with dedupe per source and period (calendar sources keep an empty period and dedupe as before). `POST /jobs/rates/{source}/capture?period=YYYY-MM` (default: the current month in New York). DAG `mkt_data__treasury_cmt_capture`, weekdays 23:37 UTC, captures the current month of each (and the previous one in a month's first five days) from now on, so the raw history starts accumulating before the parsers exist; the existing stale-capture and parse alerts cover both sources (labelled `calendar="SIFMA-US"`, their publication calendar). Fixtures via `capture-export.yml`. First run on the hub: September and October of both sources, captures #30–#34; fixtures `tests/fixtures/ust_par_2026_0{9,10}_capture3{1,2}.xml` and `h15_tcm_2026_{09,10}_capture{30,34}.csv`. H.15 once answered 200 with an empty body (capture #33); an empty response is now a fetch error, not a capture.
2. ✅ **Near-raw** (mkt-data). Two PRs:
   - ✅ **Parsers and observations** (#50, deployed 2026-10-04, migration 0007): `observation` (source, series key, date, field, value as printed in `numeric`, unit `percent`, capture, period, `valid_from`/`valid_to`), filled by every capture job: within the capture's month a new value is added, a changed one is a revision (old row closed, new row added), a dropped one is closed. `app/rates/parsers.py`: Treasury's XML (any `BC_<n>MONTH/YEAR` element, so a new tenor needs no change; `BC_30YEARDISPLAY` skipped; omitted elements are no value) and H.15's CSV (`ND` rows skipped). `POST /jobs/rates/{source}/rebuild` replays every capture. On the fixtures, every H.15 value for September 2026 equals Treasury's (231 of 231). On the hub: UST-PAR September 294 values (21 days × 14 tenors), October 28; H15-TCM September 231, October 11; all added, nothing revised.
   - ✅ **Read API** (#51, deployed 2026-10-04; on the hub calendar-svc's next load read mkt-data's gRPC server cleanly after the restart): gRPC `Observations` (`proto/observations.proto`, `app/rates/api.py`) for quote-svc, read by period. `ListSources` (each source, its calendar, first period and how many periods it has); `ListPeriods` (a source's months, optionally from `since_period`, each with `latest_capture_id`, the newest capture any of its rows came from, plus its current value count and first and last dates); `GetPeriod` (one month's current values, optionally with superseded ones). Values are decimal strings as stored, never floats. quote-svc keeps `latest_capture_id` per period and re-reads a month only when it moves: a revision or a dropped value can only come from a newer capture of that month, so it always does.
3. ✅ **Platform onboarding** (2026-10-04). nyc_pa_aws_gitops #132 put `secmaster-svc`, `quote-svc`, `mkt-api` and `mkt-ui` in `apps/registry.yml` (databases and Airflow for the two services; Authentik for mkt-ui; mkt-api internal with no route, called by mkt-ui's server as `mkt-api:8000` for the signed-in user), mkt-ui's DNS record `mkt.billandjessie.com` and OIDC client (id and secret generated by the hub deploy), and the services' scrape jobs; #135 their `github_repo_id`s. Each repo's first PR (#1 in each) copied `templates/python` or `templates/react`; all four deployed and run on the hub, and signing in at https://mkt.billandjessie.com works through Authentik.
   - Fixed on the way: the hub role's inline policies passed IAM's 10,240-character limit, so its per-app grants are now a managed policy (#134); a Terraform apply retries once on an IAM propagation race (#133); plan comments list every resource's action first (#132).
   - The React template had been broken by a Dependabot bump (ESLint 10, Express 5), found by mkt-ui's first CI run, fixed in #136 with a CI workflow for the template; then two login bugs: the OIDC issuer needs Authentik's trailing slash (mkt-ui #3, template #137), and an Authentik provider created since 2026.2 needs its `grant_types` listed (#138). All three are in nyc_pa_aws_gitops's `docs/gotchas.md` or template.
   - The template's React page, `/db-check` and Python `Item` and `ExampleService` examples stay until steps B4, B5 and B9 replace them.
4. ✅ **secmaster-svc** (secmaster-svc#2, deployed 2026-10-05).
   - **Schema** (migration 0002): `instrument`, `instrument_name` (one short name plus aliases), `identifier` (scheme, value, validity), `instrument_note` and `seed_run`. Nothing is deleted; dropped rows get `removed_at`.
   - **Seed:** `seeds/cmt.toml` holds the 14 CMTs with 36 identifiers: UST-PAR elements, H.15 series and FRED series, keys checked against mkt-data's fixtures. Identifier schemes are mkt-data source names, so quote-svc resolves `(source, source_key)` directly. The file is applied idempotently at every start, on `POST /jobs/seed`, and from the manual DAG `secmaster_svc__seed`.
   - **gRPC** `secmaster_svc.Securities`: `GetInstrument`, `ListInstruments` (tenor order), `Resolve` (quote-svc's batch lookup) and `Search`, with the same lookups as job-API GETs. Metrics cover instruments, identifiers, aliases and seed runs.
   - **On the hub:** the migration ran, and the seed created 14 instruments, 15 names, 36 identifiers and 21 notes; Prometheus scrapes `secmaster_svc_*`.
   - **Left for later:** the notes' dates (first publication, the 20- and 30-year gaps, the 2021 method change) are from published notes and get checked against the data in B6. Unmapped source keys are counted in quote-svc (B5), which sees them.
5. ✅ **quote-svc** (quote-svc#2 and mkt-data#55, deployed 2026-10-05).
   - **Schema** (migration 0002): `quote` (per source, with lineage to mkt-data's observation and capture), `quote_history` (revised and removed values), `golden` (with the winning source), `source_period` watermarks, `unmapped_key`, `instrument_ref` (secmaster-svc's short names) and `load_run`.
   - **Load** (`POST /jobs/load`): re-reads only months whose `latest_capture_id` moved, resolves keys through secmaster-svc, converts percent to decimal exactly, keeps history, and recomputes golden values (UST-PAR, then H15-TCM) in batches of dates. `POST /jobs/rebuild` clears the watermarks and reloads.
   - **gRPC** `quote_svc.Quotes`: `GetSeries`, `GetCurve`, `CompareSources` and `GetLatest`, with values as canonical decimal strings (`"0.041"`), plus the same reads on the job API by short name.
   - **Metrics:** load health, quotes by source, golden values and first and last dates per instrument, source disagreements and unmapped keys.
   - **Trigger:** `quote_svc__load` runs on the Asset `mkt_data_cmt_observations`, which `mkt_data__treasury_cmt_capture` now marks, plus nightly at 07:13 UTC.
   - **On the hub:** a capture fired the load within a second. UST-PAR 322 quotes (September 294, October 28), H15-TCM 242 (231, 11), no unmapped keys, zero disagreements, and 322 golden yields for all 14 instruments, 2026-09-01 to 2026-10-02, all from UST-PAR.
6. **Backfill.** UST-PAR from 1990 (one capture per month, ~440 captures); H15-TCM from each series' start; then a full quote-svc load. Record each series' real first date, gaps and tenor changes; check the publication calendar against SIFMA-US; reconcile the overlap from 1990 (every disagreement reported, none expected).
7. **Schedule.** `mkt_data__ust_par`: weekdays from 6:30 p.m. Eastern, first task the SIFMA-US business-day check (asked of calendar-svc), then capture the current month (and the previous one for the first few days of a month), retrying until about 10 p.m.; marks the Asset when it loads new observations. `mkt_data__h15_tcm`: weekdays after 4:15 p.m. Eastern, same pattern. `quote_svc__load`: on the Asset, plus nightly. New DAGs start paused.
8. **Monitoring.** The gauges and alert rules above (alert rules in nyc_pa_aws_gitops, like phase 1), and the Grafana rows.
9. **mkt-api and mkt-ui.** The gateway and the three screens above.
10. **home-mcp tools.** `mkt_data_yield("UST-10Y-CMT", date)` and `mkt_data_curve(date)`, answering with short names and saying which source a value came from, so "what was the 10-year yesterday?" works by voice; plus the existing checks tools for the new sources.

## Decisions (Bill, 2026-10-04)

- **Calendars first:** move calendars onto the new layering (Part A) before Treasury quotes.
- **calendar-svc** owns calendars' golden copy, as its own service rather than part of secmaster-svc.
- **Layering:** ingestion in mkt-data (raw and near-raw); golden copies owned by services (calendars, security master, quotes to start); services pull from near-raw; Airflow orchestrates and the services hold the logic. Build secmaster-svc and quote-svc in this phase.
- **Yields are rendered in the custom UI,** not Grafana; Grafana stays operational. So mkt-api and mkt-ui start in this phase.
- **mkt-ui's hostname:** `mkt.billandjessie.com`.
- **Short names** as listed, `UST-1.5M-CMT` with `UST-6W-CMT` as an alias.
- **Near-raw stores values as published, with a unit;** golden quotes convert to decimals.
- **One generic observation table** for time series; calendars keep their own.
- **Golden rebuilds run on Airflow Asset events,** plus a nightly catch-up.
- **CMT instruments come from a seed file** in secmaster-svc.
- **Each service serves its own metrics and alerts** on its own layer.

## Still open

1. **Chart library for mkt-ui** (from the design): TradingView Lightweight Charts (fast canvas time series), ECharts (general, good for curves) or Plotly. Recommendation: Lightweight Charts for series, ECharts for the curve, both behind the UI's own chart components so either can be swapped.

Settled in the steps:

- H.15's exact package URL and series list, and each series' first date (steps B1 and B6).
- Whether Treasury publishes on every SIFMA early-close day, and any day where Treasury and SIFMA-US disagree (step B6).
- How often Treasury revises a published day, which sets whether revisions stay info or become warn (after a month of daily captures).

## Later (not this phase)

- **Treasury securities:** bills, notes and bonds by CUSIP from TreasuryDirect's securities data (terms, auctions, reopenings), with effective-dated terms and OpenFIGI cross-references; Treasury's end-of-day security prices. The curve fitter needs these.
- **Fixings:** SOFR and EFFR from the NY Fed, as `fixing` instruments on the same quote store.
- **Real yields:** Treasury's par real yield curve and H.15's TIPS CMTs, as `UST-…-REAL` series.
- **Backup capture** (NUC and Lambda + S3): its value comes with sources that serve only a short history; both CMT sources serve everything.
- **The near-live macro dashboard** in mkt-ui.
