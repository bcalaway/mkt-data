# Phase 1: holiday calendars end to end

Platform roadmap: Milestone 22 in `nyc_pa_aws_gitops/docs/roadmap.md`.

**Goal:** before adding more sources, build one vertical slice through the whole data layer: sourcing → raw store → processed tables → Airflow schedule → monitoring and alerts → Grafana dashboard. Calendars come first because every later dataset's schedule and staleness checks depend on them ("was today a trading day for this market?").

**Scope (Bill, 2026-10-03):** SIFMA US bond market (full closes and recommended early closes), the Federal Reserve's holidays, and NYSE (full closes and early closes). CME comes later.

**Forward horizon (Bill, 2026-10-04):** calendars must reach far enough ahead to generate payment schedules for bonds and swaps. FED gives New York banking days and SIFMA-US gives U.S. Government Securities Business Days (SOFR); NYSE is for equities. No publisher lists more than five years ahead, so each calendar is projected from its rules to 2100, full closes only.

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
4. ✅ **Sourcing, one PR per calendar** (FED #2/#3, SIFMA-US #4, NYSE #5). FED is done (K.8 page, weekly DAG `mkt_data__fed_calendar`; first run 2026-10-04: 5 years, 50 closed weekdays). SIFMA-US: SIFMA's U.S. Holiday Recommendations page, weekly DAG `mkt_data__sifma_calendar`. Full closes are `closed`; recommended early closes are `early_close` with the Eastern close time (Good Friday 2026 is a 12:00 p.m. early close, not a full close). The page only lists published years (2026 as of 2026-10-04; the 2027 tab was empty), and a year counts as covered only with a full set of closes. First run 2026-10-04: the real page parsed first time, 19 days (11 full closes, 7 early closes, Jan 1, 2027). Its test fixture is now capture #3's visible text, line for line (#13). NYSE: the Holidays table on NYSE's hours-and-calendars page (current year + 2), weekly DAG `mkt_data__nyse_calendar`. Holidays are `closed` (observed days named "… (observed)"); the early closes come from the table's footnotes, which list their dates in full, and are stored with the equities close time (1:00 p.m. Eastern). As of 2026-10-04: 29 holidays over 2026–2028 (no New Year's Day holiday in 2028, since Jan 1 is a Saturday) and 5 early closes. First run 2026-10-04: the real page parsed first time, 34 days. Its test fixture is capture #2's exact bytes (#16; SHA-256 79602f7b…).
   - Fetch the publisher's page or file, store it raw, then parse it into `calendar_day`.
   - Re-fetching unchanged content records the check but adds no new capture (dedupe by hash).
   - Changes to dates already published are kept as history, not overwritten.
5. ✅ **Backfill** (done 2026-10-04: SIFMA-US from 1996, FED from 1986, NYSE from 1990, all applied on the hub). As far back as each source allows. Sources researched 2026-10-04: see [backfill.md](backfill.md) (SIFMA-US 1996+ from its archive, FED from statute checked against NY Fed circulars from 2003, NYSE 1990+ from rules plus a cited exceptions list). Approach agreed with Bill 2026-10-04: SIFMA-US back to 1996, FED to 1986 and NYSE to 1990; rule-generated years get their own source (`FED-RULES`, `NYSE-RULES`) with the rules and cited exceptions as a versioned file; where a published document and the rules disagree, the document wins and the disagreement is reported.
   Where a publisher only lists recent years, older years need a documented historical source or rule set: find this out per calendar before building, and record each calendar's coverage.
   - **SIFMA-US 2015–2025** (#10, merged 2026-10-04): the U.S. Holiday Archive page is calendar SIFMA-US's second source (calendars can have several sources, highest precedence first). Its first real capture (#4) failed to parse (422, raw kept): it lists 2015-04-03 (Good Friday) both as the holiday's date and as a "12:00 Noon" early close. **Fixed in #12 and applied on the hub (2026-10-04, capture #4 applied by the 02:35 UTC DAG run):** the whole capture was read with home-mcp `mkt_data_capture_text`, and `parse_archive` now handles its real wording:
     - under one holiday, an early close on the holiday's own date means an early close, not a full close (the same date two ways under different holidays still fails);
     - "Early Market Close: (2:00 p.m. Eastern Time): …" (Dec 30, 2016), which the old parser would have skipped silently as a note: any line starting like an early close must now parse;
     - "None" under a heading (Veterans Day 2017), and headings with no date (Presidents Day 2015 and 2016, Veterans Day 2023);
     - the "US Holiday Archives 1996-2017" PDF link ends the years, so the footer is never read.

     The test fixture is now capture #4's exact visible text (all 389 lines, in simplified markup). Parsed: 2015–2025 covered, 184 days. **Gap on SIFMA's own page:** Presidents Day 2015 (Feb 16) and 2016 (Feb 15) have no date, so 2015 has 9 full closes, exactly the minimum; the PDF should fill both.
   - **SIFMA-US 1996–2019 PDF:** source `SIFMA-US-HISTORY`, third in precedence. It was captured raw first (#15, capture #5, 2026-10-04), then parsed by `app/calendars/sifma_history.py` (#17), which reads words by position with `pdfplumber`. Result: 1996–2019 covered, 473 days.
     - It already holds Sandy (2012) and the Bush mourning day (2018). Two typos (Dec 30, 2016 printed with the wrong year or day) are corrected in `CORRECTIONS`.
     - Against the archive (2015–2019), the archive wins on Good Friday 2015 (reported as `held_by_higher_source`). The PDF fills dates the archive leaves out: Presidents Day 2015 and 2016, Jul 2, 2015 and Dec 5, 2018. It also adds Apr 2, 2015, a 2 p.m. early close the archive doesn't list: kept, Bill's call (2026-10-04). Applied on the hub 2026-10-04 (03:25 UTC run): SIFMA-US now covers 1996 onward.
   - **Rules and cited exceptions (#19):** versioned JSON files in `app/calendars/rules/`, read as `repo:` sources. The capture is the file's bytes, so a rule change becomes a new capture.
     - `SIFMA-US-EXCEPTIONS`, lowest precedence and covering no years, adds Carter (Jan 9, 2025, 2 p.m. early close; SIFMA press release of Dec 30, 2024).
     - `FED-RULES` (1986–2025) generates the federal holidays (5 U.S.C. 6103) as the Reserve Banks observe them: a Saturday holiday closes no weekday, and a Sunday holiday closes the Monday after. 382 closed weekdays. Checked against the NY Fed circulars for 2003–2009 (all seven match). The same rules reproduce K.8's 2026–2030 table exactly. Juneteenth 2021 fell on a Saturday, so no weekday closed; the Board confirmed Fed services ran normally on June 18, 2021. 1986–2002 rest on the statute alone.
   - **NYSE-RULES (#20, 1990–2025):** `rules/nyse.json`, below the hours page.
     - Holidays: Rule 7.2's list, with MLK Day from 1998, Juneteenth from 2022, and Good Friday from Easter. A Saturday holiday closes the Friday before, except New Year's Day.
     - Early closes at 1 p.m.: the day after Thanksgiving (from 1993), July 3 when it falls Monday–Thursday (from 1995), and Dec 24 when it falls Monday–Thursday (from 1996).
     - 25 cited exceptions: the 2 p.m. closes of 1990–92, July 5 instead of July 3 in 1996 and 2002, Dec 26 in 1997 and 2003, Dec 31, 1999, the 1994/1996 snow closes, the 1997 circuit-breaker halt, and the one-off full closes (Nixon, 9/11, Reagan, Ford, Sandy, Bush, Carter).
     - Result: 406 days. The same rules reproduce the hours page's 2026–2028 table exactly and match ICE's 2023–2025 announcement.
     - 1990–2010 follow NYSE's own holiday history, read through a summarizer. Aug 9, 1996 (a 3 p.m. close for a hurricane watch) is left out, unconfirmed.
   - **Step 5's agreed ranges are all in and applied on the hub (2026-10-04):** SIFMA-US from 1996, FED from 1986, NYSE from 1990.
   - **Projection to 2100 (#22):** `rules/*_projected.json`, the last source in each calendar (`projected=True`).
     - Full closes only: early closes don't move payment dates.
     - Fills only years no other source covers. Once a publisher covers a year, the projection's rows for it are retired as a whole, kept as history.
     - `business-day` answers from a projected year carry `"projected": true`.
     - FED's projection uses `fed.json`'s rules, which reproduce K.8 exactly. NYSE's uses `nyse.json`'s holidays.
     - SIFMA's rules reproduce SIFMA's published full closes for 1996–2026, except the two one-off closes (Sandy, Bush) and the jobs-report Good Fridays that became early closes. A projected Good Friday is the date most likely to change.
     - Juneteenth on a Saturday (first in 2027) is projected to the Friday before. SIFMA's published 2027 confirms it (June 18), as of #27.
     - Step 6's "next year published" check must count published sources only, so a projection can't hide a missing year.
   - Possible follow-ups: capture the NY Fed circulars and NYSE's holiday history as raw sources (today they're cited and pinned in tests). K.8's markup changes on every fetch while its text stays the same, so it compares visible text instead of bytes (`dedupe_on_text`, #23): a markup-only change is recorded as an unchanged check, not a new capture. It's on for K.8 only. SIFMA's and NYSE's pages have stayed byte-identical, and SIFMA's 2027 dates may sit in blocks the text view skips.
   - **SIFMA-US 2027 (#27):** SIFMA's page is a Next.js app. Only its first year tab is in the HTML's visible text; the others are in its embedded React data, inside scripts the text view skips. That's why 2027 read as unpublished.
     - `app/calendars/rsc.py` rebuilds that data's tree and returns its text in document order, hidden tabs included. `sifma.parse` uses it when present and falls back to the visible text.
     - Capture #3 then gives 2026–2027, 36 days. Its 2026 is identical to the visible-text parse.
     - Capture #3 was the first one fetched with the new `capture-export` workflow; its exact bytes are the fixture `sifma_us_page_capture3.html`.
     - This is also why SIFMA keeps byte-level dedupe (`dedupe_on_text` stays off): its data changes would be invisible to a text comparison.
   - ✅ Live-page fixtures are real captures: SIFMA-US from capture #3's visible text (#13), NYSE as capture #2's exact bytes (#16).
6. ✅ **Schedule** (done 2026-10-04). One Airflow DAG per calendar: a regular refresh, plus a check that next year's dates exist once the publisher normally posts them. The weekly DAGs have run since step 4. The next-year check is a gauge plus an alert rather than a DAG task (#24): `mkt_data_calendar_next_year_overdue` counts publishers only, and next year is due always for FED and NYSE and from December 20 for SIFMA-US.
7. ✅ **Monitoring** (done 2026-10-04, verified live: the `mkt-data` scrape target is up and all 11 sources read `parse_ok` 1; K.8's text dedupe held it at 3 captures. #24 here, with the scrape job and alert rules in nyc_pa_aws_gitops). `GET /metrics`; each capture and reparse records its parse outcome (migration 0003).
   - mkt-data exposes Prometheus gauges for the platform's data-quality pattern: last successful capture, rows per calendar and year, years covered, and parse failures.
   - Grafana alert rules email when a capture is stale, a parse fails, or next year is missing past its usual publish date.
8. ✅ **Dashboard** (done 2026-10-04: Grafana **Market data**, `uid: market-data`, platform #118; gauges in #32). Filterable by calendar:
   - at a glance: database reachable, parse failures, oldest successful fetch, coverage gaps, next year published;
   - each calendar's upcoming closes and early closes over the next 180 days (`mkt_data_calendar_upcoming_day`: one series per date, labelled with the holiday, status, Eastern close time and whether it's projected; the value is days until it). Prometheus drops empty labels, so a full close has no `close_time`;
   - backfill coverage per calendar and kind of source (first year, last year, years), gap years (`mkt_data_calendar_gap_years`, `_gap_year`; all 0) and stored days;
   - capture history: per-source last success, parse outcome, captures and raw bytes, over time;
   - storage and cost: database size (`pg_database_size_bytes{datname="mkt-data"}`, from postgres-exporter), raw capture bytes, calendar rows, and the whole account's AWS month-to-date and forecast from the cost-exporter.
   - Checked live 2026-10-04: 7 upcoming days for FED, 12 for SIFMA-US, 8 for NYSE; the next is Columbus Day (FED and SIFMA-US, NYSE open).
9. **home-mcp tools.** Market data status, open gaps and backfill as named tools, so they can be asked about by voice.
   - ✅ **Tools deployed and verified 2026-10-04** (platform #115, mkt-data #28). Every check below passed, after two fixes:
     - **Grafana token:** #115's hub deploy ran a minute before Terraform granted the hub role `PutParameter` on the token parameter (both workflows start on the same merge). The script made the service account and a token, couldn't save it, and wrote `none` as designed. A hub-only redeploy (13:55 UTC) stored a fresh token, and `grafana_alerts("mkt-data")` shows the three rules inactive and healthy. The first token is orphaned on the `home-mcp` account (Viewer only).
     - **SIFMA-US 2027 lost its full closes** (Good Friday, MLK Day, Labor Day, Thanksgiving read as open). Each day SIFMA published exactly as the projection already had it stayed owned by the projection, which then retired it as the publisher's year. A second run re-adds them, so the hub was repaired by triggering `mkt_data__sifma_calendar` (13:46 UTC). The code fix is #30: the publisher takes over identical days from a lower source (`taken_from_lower_source`). FED and NYSE would hit the same when K.8 and the hours page roll forward.
   - New tools:
     - `grafana_alerts`: alert rules and state, read through a Viewer service account. The hub deploy creates its token at `/home-platform/grafana/home-mcp-token`.
     - `airflow_runs` and `airflow_task_log`: read-only.
     - `airflow_trigger`: only for `mkt_data__*` DAGs.
     - `mkt_data_business_day`: says whether a day's answer is projected.
     - `mkt_data_checks`: `GET /jobs/checks`.
     - `mkt_data_capture_text` gains `embedded=true`, the Next.js embedded data (`rsc.lines`).
   - **Checks run 2026-10-04, all passing** (rerun them after a home-mcp change):
     1. ✅ `grafana_alerts("mkt-data")`: three rules, inactive and healthy. If it says access isn't set up or Grafana answers 401, the token step failed: the deploy writes `none` on failure; check the hub deploy log and `grafana_home_mcp_token()` in `scripts/hub/deploy-hub-stack.sh`.
     2. ✅ `airflow_trigger("mkt_data__nyse_calendar")`, then `airflow_runs` shows it succeed, and `mkt_data_checks(calendar="NYSE")` shows fresh checks, unchanged and parsed OK.
     3. ✅ `mkt_data_business_day("SIFMA-US", "2027-03-26")`: closed (Good Friday), not projected. `mkt_data_business_day("FED", "2040-07-04")`: closed, projected.
     4. ✅ `mkt_data_capture_text(3, embedded=true, contains="2027")` finds the 2027 tab.
   - Still to do for this step: voice-friendly status answers (coverage per calendar, open gaps), if the tools above don't already cover them.

## Open questions

These are settled in the step that needs them.

- **SIFMA backfill:** SIFMA keeps a U.S. holiday archive (linked from the schedule page as "View Archive") for earlier years.
- **Exact sources for each calendar.** For each one, check its official page's format and how many years back it goes before writing the parser.
- **NYSE early closes:** half-day close times differ by venue and asset class (options 1:15 p.m., late trading sessions 5:00 p.m.). Settled for now: calendar NYSE stores the equities close (1:00 p.m.); add others when a dataset needs them.
- **NYSE backfill:** the page lists the current year and the next two. Earlier years need NYSE's published history or the exchange's holiday rules (including one-off closures such as national days of mourning).
- **The Fed's holiday list vs FedWire / Fedwire Securities operating days:** they normally match; confirm, then model them as one calendar or two. For now FED is the Reserve Banks' calendar: when a holiday falls on a Saturday, the Banks stay open the Friday before, and only the Board of Governors closes.
- **FED backfill:** K.8 only lists the current year and the next four. Earlier years need the federal holiday rules (Juneteenth from 2021) or archived copies of the page.
- **Backup capture path** (Lambda + S3, independent of the hub) is a platform roadmap item. Calendars change rarely, so phase 1 doesn't depend on it.
