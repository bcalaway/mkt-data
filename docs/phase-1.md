# Phase 1: holiday calendars end to end

Platform roadmap: Milestone 22 in `nyc_pa_aws_gitops/docs/roadmap.md`.

**Goal:** before adding more sources, build one vertical slice through the whole data layer: sourcing → raw store → processed tables → Airflow schedule → monitoring and alerts → Grafana dashboard. Calendars come first because every later dataset's schedule and staleness checks depend on them ("was today a trading day for this market?").

**Scope (Bill, 2026-10-03):** SIFMA US bond market (full closes and recommended early closes), the Federal Reserve's holidays, and NYSE (full closes and early closes). CME comes later.

## Steps

Each step is its own PR.

1. ✅ **Template in place** (#1, 2026-10-03). The repo builds, passes CI and deploys to the hub as an internal-only container.
2. ✅ **Airflow integration (platform side, `nyc_pa_aws_gitops`)**: ADR-0031, PR #96 (2026-10-03). DAGs call mkt-data's token-protected `/jobs` API, and `dags/` ships with each deploy. This settles ADR-0027's three open points:
   - how an app's DAGs reach Airflow's `dags/mkt-data/`;
   - how mkt-data's secrets reach its tasks;
   - whether tasks run inside Airflow's workers or in mkt-data's own image (DockerOperator), and how the Docker socket is isolated if so.
3. ✅ **Schema** (migration 0002, with the Fed calendar). Alembic migrations replace the template's `Item` table:
   - `source` and `capture` (raw: what was fetched, when, from where, a content hash and the payload, kept forever);
   - `calendar` (integer ID plus a short name such as `SIFMA-US`, `FED`, `NYSE`);
   - `calendar_day` (calendar, date, status `closed` / `early_close`, close time when early, and the capture it came from).
4. ✅ **Sourcing, one PR per calendar** (FED #2/#3, SIFMA-US #4, NYSE #5). FED is done (K.8 page, weekly DAG `mkt_data__fed_calendar`; first run 2026-10-04: 5 years, 50 closed weekdays). SIFMA-US: SIFMA's U.S. Holiday Recommendations page, weekly DAG `mkt_data__sifma_calendar`. Full closes are `closed`; recommended early closes are `early_close` with the Eastern close time (Good Friday 2026 is a 12:00 p.m. early close, not a full close). The page only lists published years (2026 as of 2026-10-04; the 2027 tab was empty), and a year counts as covered only with a full set of closes. First run 2026-10-04: the real page parsed first time, 19 days (11 full closes, 7 early closes, Jan 1, 2027). Its test fixture is now capture #3's visible text, line for line (#13). NYSE: the Holidays table on NYSE's hours-and-calendars page (current year + 2), weekly DAG `mkt_data__nyse_calendar`. Holidays are `closed` (observed days named "… (observed)"); the early closes come from the table's footnotes, which list their dates in full, and are stored with the equities close time (1:00 p.m. Eastern). As of 2026-10-04: 29 holidays over 2026–2028 (no New Year's Day holiday in 2028, since Jan 1 is a Saturday) and 5 early closes. First run 2026-10-04: the real page parsed first time, 34 days. Same fixture follow-up as SIFMA-US.
   - Fetch the publisher's page or file, store it raw, then parse it into `calendar_day`.
   - Re-fetching unchanged content records the check but adds no new capture (dedupe by hash).
   - Changes to dates already published are kept as history, not overwritten.
5. **Backfill.** As far back as each source allows. Sources researched 2026-10-04: see [backfill.md](backfill.md) (SIFMA-US 1996+ from its archive, FED from statute checked against NY Fed circulars from 2003, NYSE 1990+ from rules plus a cited exceptions list). Approach agreed with Bill 2026-10-04: SIFMA-US back to 1996, FED to 1986 and NYSE to 1990; rule-generated years get their own source (`FED-RULES`, `NYSE-RULES`) with the rules and cited exceptions as a versioned file; where a published document and the rules disagree, the document wins and the disagreement is reported.
   Where a publisher only lists recent years, older years need a documented historical source or rule set: find this out per calendar before building, and record each calendar's coverage.
   - **SIFMA-US 2015–2025** (#10, merged 2026-10-04): the U.S. Holiday Archive page is calendar SIFMA-US's second source (calendars can have several sources, highest precedence first). Its first real capture (#4) failed to parse (422, raw kept): it lists 2015-04-03 (Good Friday) both as the holiday's date and as a "12:00 Noon" early close. **Fixed in #12 and applied on the hub (2026-10-04, capture #4 applied by the 02:35 UTC DAG run):** the whole capture was read with home-mcp `mkt_data_capture_text`, and `parse_archive` now handles its real wording:
     - under one holiday, an early close on the holiday's own date means an early close, not a full close (the same date two ways under different holidays still fails);
     - "Early Market Close: (2:00 p.m. Eastern Time): …" (Dec 30, 2016), which the old parser would have skipped silently as a note: any line starting like an early close must now parse;
     - "None" under a heading (Veterans Day 2017), and headings with no date (Presidents Day 2015 and 2016, Veterans Day 2023);
     - the "US Holiday Archives 1996-2017" PDF link ends the years, so the footer is never read.

     The test fixture is now capture #4's exact visible text (all 389 lines, in simplified markup). Parsed: 2015–2025 covered, 184 days. **Gap on SIFMA's own page:** Presidents Day 2015 (Feb 16) and 2016 (Feb 15) have no date, so 2015 has 9 full closes, exactly the minimum; the PDF should fill both.
   - Next for SIFMA-US: the 1996–2019 PDF, then the unscheduled closes (Sandy 2012, Bush 2018, Carter 2025) as a cited exceptions list. **PDF, part 1 (#15):** source `SIFMA-US-HISTORY`, third in SIFMA-US's precedence, with no parser yet: capture jobs fetch and keep the PDF raw and apply nothing. Part 2, once the hub has a capture: pull its bytes with the README one-liner, then build the cell-position table parser and its fixture against them, and check the result by hand.
   - Then FED (`FED-RULES`, 1986+, checked against NY Fed circulars 2003+), then NYSE (`NYSE-RULES` + cited exceptions, 1990+).
   - Small follow-up: replace the SIFMA-US and NYSE live-page stand-in fixtures with their real captures (NYSE capture 2, SIFMA-US capture 3) via `GET /jobs/captures/{id}` (README one-liner), or from their visible text via `mkt_data_capture_text` as for the archive.
6. **Schedule.** One Airflow DAG per calendar: a regular refresh, plus a check that next year's dates exist once the publisher normally posts them.
7. **Monitoring.**
   - mkt-data exposes Prometheus gauges for the platform's data-quality pattern: last successful capture, rows per calendar and year, years covered, and parse failures.
   - Grafana alert rules email when a capture is stale, a parse fails, or next year is missing past its usual publish date.
8. **Dashboard.** A Grafana dashboard covering:
   - each calendar's upcoming closes and early closes;
   - backfill coverage per calendar (first year, last year, gaps);
   - capture history;
   - storage (raw bytes and rows). Monthly AWS cost comes from the platform's cost-exporter.
9. **home-mcp tools.** Market data status, open gaps and backfill as named tools, so they can be asked about by voice.

## Open questions

These are settled in the step that needs them.

- **SIFMA backfill:** SIFMA keeps a U.S. holiday archive (linked from the schedule page as "View Archive") for earlier years.
- **Exact sources for each calendar.** For each one, check its official page's format and how many years back it goes before writing the parser.
- **NYSE early closes:** half-day close times differ by venue and asset class (options 1:15 p.m., late trading sessions 5:00 p.m.). Settled for now: calendar NYSE stores the equities close (1:00 p.m.); add others when a dataset needs them.
- **NYSE backfill:** the page lists the current year and the next two. Earlier years need NYSE's published history or the exchange's holiday rules (including one-off closures such as national days of mourning).
- **The Fed's holiday list vs FedWire / Fedwire Securities operating days:** they normally match; confirm, then model them as one calendar or two. For now FED is the Reserve Banks' calendar: when a holiday falls on a Saturday, the Banks stay open the Friday before, and only the Board of Governors closes.
- **FED backfill:** K.8 only lists the current year and the next four. Earlier years need the federal holiday rules (Juneteenth from 2021) or archived copies of the page.
- **Backup capture path** (Lambda + S3, independent of the hub) is a platform roadmap item. Calendars change rarely, so phase 1 doesn't depend on it.
