# mkt-data

The data pipeline of Bill's market data platform: it sources market data, keeps every raw capture, turns it into processed tables keyed on internal IDs, and reports on its own health. It runs on the home platform's AWS hub (`bcalaway/nyc_pa_aws_gitops`) as a registry app (`apps/registry.yml`: own Postgres database, no Authentik client, no previews), and Airflow is the platform's shared scheduler.

Phase 1, holiday calendars end to end, is complete: see [docs/phase-1.md](docs/phase-1.md). Phase 2, golden copies in services (calendar-svc, then Treasury CMT yields through secmaster-svc, quote-svc and the custom UI), is complete: see [docs/phase-2.md](docs/phase-2.md). Phase 3 brings in Treasury securities by CUSIP (terms, auctions, reopenings and end-of-day prices): see [docs/phase-3.md](docs/phase-3.md).

## How it runs

- **Container:** one process with HTTP on 8000 and gRPC on 9090. It's internal only: no Traefik route and no DNS record. Other services reach it on the `home-platform` network as `mkt-data:8000` / `mkt-data:9090`.
- **Database:** `mkt-data` on the hub's Postgres 16. The platform created the role, the database and the password (`/home-platform/postgres/mkt-data-password`). Schema changes are Alembic migrations, applied when the container starts.
- **CI/CD:** `ci.yml` runs the platform's `app-ci.yml` on every PR (`ci / Build, test, lint` is the check `main` requires). `cd.yml` builds and pushes to ECR on merge, then deploys to the hub once Bill approves the `production` environment.
- **Secrets:** anything under `/home-platform/mkt-data/` in SSM arrives in the container's environment at deploy time (name → `UPPER_SNAKE`).

## Conventions

- Hidden integer IDs internally, short readable names in every view.
- Everything decimal. Rates are stored as decimals (`0.0425` = 4.25%). Tradable prices are in market-convention units.
- EOD means each market's local close.
- Raw captures are kept forever (for now). Processed tables can always be rebuilt from raw.

## Local development

```
pip install -r requirements.txt -r requirements-dev.txt
./gen_proto.sh
uvicorn app.main:app --reload
```

`POSTGRES_PASSWORD` is optional locally; without it the app runs with no database.

Tests and lint: `pytest` and `ruff check app/ tests/`, or `docker build --target test .` / `--target lint .`, which is what CI runs.

Migrations: change `app/models.py`, run `alembic revision --autogenerate -m "..."`, then read and fix the generated file. `tests/test_migrations.py` fails if models and migrations disagree.

gRPC: edit `proto/*.proto`, run `./gen_proto.sh`, implement the servicer in `app/grpc_server.py`. The standard `grpc.health.v1` service is always on.

`CalendarSources` (`proto/calendar_sources.proto`) serves near-raw calendar rows to calendar-svc at `mkt-data:9090`: `ListSources` (every calendar source, its calendar, whether it's parsed, its latest capture and the newest capture its near-raw rows came from) and `GetSource` (one source's years and days, optionally with superseded days). Calendars are small, so a source is read whole.

`Observations` (`proto/observations.proto`) serves near-raw observations to quote-svc, by month: `ListSources`, `ListPeriods` (each month with `latest_capture_id`, the newest capture its rows came from, so a reader re-reads only months where it moved) and `GetPeriod` (a month's current values, optionally with superseded ones; values are decimal strings, never floats).

## Jobs and DAGs

Airflow runs the schedules; the work happens here (ADR-0031 in `nyc_pa_aws_gitops`). `app/jobs.py` is the job API under `/jobs/`, and every endpoint needs `Authorization: Bearer $AIRFLOW_TOKEN`. The read-only `GET` endpoints also accept `$READ_TOKEN`, which home-mcp uses for its `mkt_data_captures` and `mkt_data_capture_text` tools. The platform generates it at `/home-platform/mkt-data/read-token`. `{name}` is a calendar in `CALENDARS` (`app/calendars/service.py`): `FED`, `SIFMA-US` or `NYSE`.

- `POST /jobs/calendars/{name}/capture` fetches each of the calendar's sources, keeps it raw if it changed, and records the parse as that source's near-raw rows, with history. "Changed" means different bytes. For K.8, whose markup changes on every request, it means different visible text (`dedupe_on_text`).
- `POST /jobs/calendars/{name}/reparse` re-records each source's latest capture, for example after a parser fix (the rebuild below replays the whole history).
- `POST /jobs/calendars/{name}/near-raw/rebuild` rebuilds the calendar's sources' near-raw rows (`source_year`, `source_day`) by replaying every stored capture, oldest first. No fetch. A capture that fails to parse is skipped and listed under `parse_failed`. The manual DAG `mkt_data__calendar_near_raw_rebuild` runs it for all three calendars.
- `POST /jobs/rates/{source}/capture?period=YYYY-MM` fetches one month of a Treasury CMT source (`UST-PAR`, Treasury's par yield curve XML; `H15-TCM`, the Fed's H.15 CSV; `app/rates/sources.py`) keeps it raw if it's new for that month, and records the month's values as near-raw `observation` rows (as printed, with history; `app/rates/parsers.py`, `app/rates/near_raw.py`). An empty response is a fetch error. `period` defaults to the current month in New York. DAGs `mkt_data__ust_par` (weekdays from 6:30 p.m. New York) and `mkt_data__h15_tcm` (from 4:30 p.m.) run it on publication days, asking calendar-svc first and retrying until the day's values are in (`dags/treasury_cmt_daily.py`; phase 2, Part B). Its answer includes `last_date`, the month's latest day with values.
- `POST /jobs/rates/{source}/rebuild` rebuilds a CMT source's observations by replaying every stored capture, oldest first. No fetch.
- `POST /jobs/swaps/{source}/capture?period=YYYY-MM-DD` fetches one publication date's file of an ISDA standard model RFR curve (`SPGMI-RFR-USD`, `-EUR`, `-GBP`, `-JPY`, `-CHF`, `-AUD`; `app/swaps/sources.py`), with the email in `SPGMI_RFR_EMAIL` (SSM `/home-platform/mkt-data/spgmi-rfr-email`) added by the fetch, keeps the zip raw if its XML is new, and records each tenor's par rate (observations) and the file's conventions and maturity dates (a `curve` record). `POST /jobs/swaps/{source}/rebuild` replays every capture. DAGs `mkt_data__swap_curves_capture` (weekdays 6:15 p.m. New York) and `mkt_data__swap_curves_backfill` (manual); ISDA's NYM and TYO calendars (`ISDA-NYM`, `ISDA-TYO`) come from cdsmodel.com weekly (`mkt_data__isda_calendars`). See docs/phase-4.md, "Swap curves".
- `GET /jobs/captures?calendar=NYSE` (or `?source=NYSE-HOURS`, or neither; `limit` defaults to 20) lists raw captures, newest first: id, source, when, size, SHA-256, `period` (the month, for sources fetched by month), `applied` (some near-raw row came from it; a newest capture that isn't applied usually failed to parse) and `parsed` (false when its source has no parser yet, so it's kept raw only).
- `GET /jobs/captures/{id}` returns one capture's body byte for byte, as a download.
- `GET /jobs/captures/{id}/text?contains=…&context=…&limit=…` returns an HTML capture's visible text, one numbered line per block element, optionally only the lines containing a phrase. It's what the SIFMA-style parsers see. Use it to turn a real capture into a test fixture or see exactly what a parser saw. Add `embedded=true` for a Next.js page's embedded React data instead (`app/calendars/rsc.py`). That's what SIFMA's page parser reads, hidden year tabs included.
- `GET /jobs/checks?calendar=SIFMA-US` (or `?source=…`; `limit` defaults to 20) lists recent fetch attempts and reparses, newest first. Each row has the outcome (`new`, `unchanged`, `error` or `reparse`), the parse outcome (`ok` or `error`) and the messages. That's what each capture job actually did, per source.

**To get a capture's exact bytes into the repo** (for a fixture), run the `capture-export.yml` workflow from `main` with its id:

```
gh workflow run capture-export.yml -f capture_id=5
```

The workflow has the hub copy the capture out (the platform's `mkt-data-capture-export` document) and commits it to an orphan branch `capture/<id>`. Fetch it with `git fetch origin capture/5` and take `captures/<SOURCE>-<id>.<ext>`. No hub session or token is involved; see "Raw captures for Claude" in nyc_pa_aws_gitops's `docs/app-platform.md`. Delete the branch once the fixture is merged.

By hand, mkt-data is internal only, so to save a capture to a file, run this on the hub (`ssh ec2-user@10.0.3.1`). The token is read inside the container and never appears on the command line:

```
docker exec mkt-data python -c 'import os,sys,urllib.request as u; r=u.Request("http://localhost:8000/jobs/captures?limit=10",headers={"Authorization":"Bearer "+os.environ["AIRFLOW_TOKEN"]}); sys.stdout.buffer.write(u.urlopen(r).read())'
docker exec mkt-data python -c 'import os,sys,urllib.request as u; r=u.Request("http://localhost:8000/jobs/captures/"+sys.argv[1],headers={"Authorization":"Bearer "+os.environ["AIRFLOW_TOKEN"]}); sys.stdout.buffer.write(u.urlopen(r).read())' 2 > nyse-capture-2.html
```

The calendar DAGs (and the near-raw rebuild) mark the Airflow Asset `mkt_data_calendar_sources` after each successful run; calendar-svc's load DAG is scheduled on it. Likewise `mkt_data__ust_par` and `mkt_data__h15_tcm` mark `mkt_data_cmt_observations` when a capture adds, changes or removes an observation, and quote-svc's load DAG is scheduled on that.

DAGs live in `dags/` (flat; the deploy puts them in Airflow's `dags/mkt-data/`). Their ids start with `mkt_data__`, and they import only Airflow, the platform's `home_platform_jobs` helper and the standard library (`tests/test_dags.py` checks both). New DAGs start paused, so unpause each one in the Airflow UI once it parses.

## Metrics

`GET /metrics` serves Prometheus gauges, computed from the database on each scrape (`app/metrics.py`). Prometheus scrapes it as `mkt-data:8000` on the `home-platform` network. It has no auth, like the platform's other scrape targets, and holds only counts, years and timestamps. Labels use the readable names (`calendar`, `source`, `kind` = published / rules / projected).

- `mkt_data_source_last_success_timestamp_seconds`, `mkt_data_source_parse_ok`: drive the platform's stale-capture and parse-failed alerts.
- `mkt_data_source_captures` / `_capture_bytes`: for the dashboard.

The calendars' own gauges (coverage by kind, gaps, upcoming closes, next year published) come from calendar-svc since phase 2, step A5 (`calendar_svc_calendar_*`).

Every capture and every reparse records its parse outcome on its `source_check` row (`parse_outcome`, `parse_detail`; a reparse is a check with outcome `reparse`). So a parser fix plus a reparse clears a parse alert without waiting for the next weekly fetch.

## Data model

See `app/models.py`. In short:

- **Raw:** `source` → `capture`, which is append-only and enforced by a trigger, plus `source_check`, which records every fetch attempt.
- **Near-raw** (phase 2, Part A): `source_year` and `source_day`, each calendar source's parse as that source states it, one set of rows per source and no precedence. Every capture job writes them; their times are the captures' fetch times, so a rebuild from raw gives the same rows. calendar-svc builds golden calendars from these.
- **Near-raw observations** (phase 2, Part B): `observation`, time-series values as each source publishes them (Treasury's `BC_10YEAR`, H.15's `RIFLGFCY10_N.B`), with history per source, key, date and field.
- **Golden calendars:** in calendar-svc since phase 2, step A5. mkt-data's `calendar`, `calendar_year` and `calendar_day` were dropped (migration 0005) after calendar-svc's matched them day for day, 1900–2100.

Each calendar is captured from several sources, listed highest precedence first in `CALENDARS` (`app/calendars/service.py`), the order calendar-svc ranks them in: SIFMA-US reads its current schedule page, then its archive, then its 1996–2019 PDF, then a file of cited exceptions; FED reads K.8, then the NY Fed's 2003–2009 circulars, then its rules for 1986–2025; NYSE reads its hours page, then its holiday history, then its rules for 1990–2025. Each calendar's last source is a projection to 2100 (`FED-PROJECTED`, `SIFMA-US-PROJECTED`, `NYSE-PROJECTED`). A `repo:` source is a rules file in `app/calendars/rules/` (`app/calendars/rules.py` explains the format): its capture is the file's bytes, so each version of the rules is kept like any other raw capture. A source can have no parser yet: it's fetched and kept raw, records nothing, and its captures list with `parsed: false`. That's how a new document is first captured, so its parser can be written against the real bytes. A capture job fetches and records each source in turn, and one failing doesn't stop the others; its summary has one entry per source under `sources`. Merging the sources into one calendar (precedence, the projection's whole-year handover) is calendar-svc's job.

Started from `templates/python` in `nyc_pa_aws_gitops`. `ExampleService.Ping` is still the template's gRPC example.
