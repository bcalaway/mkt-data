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
4. ✅ **Sourcing, one PR per calendar** (FED #2/#3, SIFMA-US #4, NYSE #5). FED is done (K.8 page, weekly DAG `mkt_data__fed_calendar`; first run 2026-10-04: 5 years, 50 closed weekdays). SIFMA-US: SIFMA's U.S. Holiday Recommendations page, weekly DAG `mkt_data__sifma_calendar`. Full closes are `closed`; recommended early closes are `early_close` with the Eastern close time (Good Friday 2026 is a 12:00 p.m. early close, not a full close). The page only lists published years (2026 as of 2026-10-04; the 2027 tab was empty), and a year counts as covered only with a full set of closes. First run 2026-10-04: the real page parsed first time, 19 days (11 full closes, 7 early closes, Jan 1, 2027). Its test fixture is still the live text in stand-in markup; swapping in the first real capture's bytes is a small follow-up. NYSE: the Holidays table on NYSE's hours-and-calendars page (current year + 2), weekly DAG `mkt_data__nyse_calendar`. Holidays are `closed` (observed days named "… (observed)"); the early closes come from the table's footnotes, which list their dates in full, and are stored with the equities close time (1:00 p.m. Eastern). As of 2026-10-04: 29 holidays over 2026–2028 (no New Year's Day holiday in 2028, since Jan 1 is a Saturday) and 5 early closes. First run 2026-10-04: the real page parsed first time, 34 days. Same fixture follow-up as SIFMA-US.
   - Fetch the publisher's page or file, store it raw, then parse it into `calendar_day`.
   - Re-fetching unchanged content records the check but adds no new capture (dedupe by hash).
   - Changes to dates already published are kept as history, not overwritten.
5. **Backfill.** As far back as each source allows. Sources researched 2026-10-04: see [backfill.md](backfill.md) (SIFMA-US 1996+ from its archive, FED from statute checked against NY Fed circulars from 2003, NYSE 1990+ from rules plus a cited exceptions list). Where a publisher only lists recent years, older years need a documented historical source or rule set. Find this out per calendar before building, and record each calendar's coverage.
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
