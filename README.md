# mkt-data

The data pipeline of Bill's market data platform: it sources market data, keeps every raw capture, turns it into processed tables keyed on internal IDs, and reports on its own health. It runs on the home platform's AWS hub (`bcalaway/nyc_pa_aws_gitops`) as a registry app (`apps/registry.yml`: own Postgres database, no Authentik client, no previews), and Airflow is the platform's shared scheduler.

Phase 1 is holiday calendars end to end. See [docs/phase-1.md](docs/phase-1.md).

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

## Jobs and DAGs

Airflow runs the schedules; the work happens here (ADR-0031 in `nyc_pa_aws_gitops`). `app/jobs.py` is the job API under `/jobs/`, and every endpoint needs `Authorization: Bearer $AIRFLOW_TOKEN`. The read-only `GET` endpoints also accept `$READ_TOKEN`, which home-mcp uses for its `mkt_data_captures` and `mkt_data_capture_text` tools. The platform generates it at `/home-platform/mkt-data/read-token`. `{name}` is a calendar in `CALENDARS` (`app/calendars/service.py`): `FED`, `SIFMA-US` or `NYSE`.

- `POST /jobs/calendars/{name}/capture` fetches the source, keeps it raw if it changed, and applies the parse with history. "Changed" means different bytes. For K.8, whose markup changes on every request, it means different visible text (`dedupe_on_text`).
- `POST /jobs/calendars/{name}/reparse` re-applies the latest capture, for example after a parser fix.
- `GET /jobs/calendars/{name}/business-day?on=YYYY-MM-DD` answers whether that date is a business day. It's meant for DAGs' short-circuit first task. For a year no publisher covers yet, the answer comes from the calendar's projection and includes `"projected": true`: a best guess from the rules, not a published date.
- `GET /jobs/captures?calendar=NYSE` (or `?source=NYSE-HOURS`, or neither; `limit` defaults to 20) lists raw captures, newest first: id, source, when, size, SHA-256, `applied` (some calendar row came from it; a newest capture that isn't applied usually failed to parse) and `parsed` (false when its source has no parser yet, so it's kept raw only).
- `GET /jobs/captures/{id}` returns one capture's body byte for byte, as a download.
- `GET /jobs/captures/{id}/text?contains=…&context=…&limit=…` returns an HTML capture's visible text, one numbered line per block element, optionally only the lines containing a phrase. It's what the SIFMA-style parsers see. Use it to turn a real capture into a test fixture or see exactly what a parser saw.

mkt-data is internal only, so to save a capture to a file, run this on the hub (`ssh ec2-user@10.0.3.1`). The token is read inside the container and never appears on the command line:

```
docker exec mkt-data python -c 'import os,sys,urllib.request as u; r=u.Request("http://localhost:8000/jobs/captures?limit=10",headers={"Authorization":"Bearer "+os.environ["AIRFLOW_TOKEN"]}); sys.stdout.buffer.write(u.urlopen(r).read())'
docker exec mkt-data python -c 'import os,sys,urllib.request as u; r=u.Request("http://localhost:8000/jobs/captures/"+sys.argv[1],headers={"Authorization":"Bearer "+os.environ["AIRFLOW_TOKEN"]}); sys.stdout.buffer.write(u.urlopen(r).read())' 2 > nyse-capture-2.html
```

DAGs live in `dags/` (flat; the deploy puts them in Airflow's `dags/mkt-data/`). Their ids start with `mkt_data__`, and they import only Airflow, the platform's `home_platform_jobs` helper and the standard library (`tests/test_dags.py` checks both). New DAGs start paused, so unpause each one in the Airflow UI once it parses.

## Data model

See `app/models.py`. In short:

- **Raw:** `source` → `capture`, which is append-only and enforced by a trigger, plus `source_check`, which records every fetch attempt.
- **Processed:** `calendar` → `calendar_year` (coverage) and `calendar_day` (closed or early-close weekdays, with `valid_from`/`valid_to` history).

A calendar can have several sources, highest precedence first (`CALENDARS` in `app/calendars/service.py`): SIFMA-US reads its current schedule page, then its archive, then its 1996–2019 PDF, then a file of cited exceptions; FED reads K.8, then its rules for 1986–2025; NYSE reads its hours page, then its rules for 1990–2025. Each calendar's last source is a projection to 2100 (`FED-PROJECTED`, `SIFMA-US-PROJECTED`, `NYSE-PROJECTED`). It covers only years no other source covers, and gives a year up whole once a publisher covers it. A `repo:` source is a rules file in `app/calendars/rules/` (`app/calendars/rules.py` explains the format): its capture is the file's bytes, so each version of the rules is kept like any other raw capture. A source can have no parser yet: it's fetched and kept raw, applies nothing, and its captures list with `parsed: false`. That's how a new document is first captured, so its parser can be written against the real bytes. A capture job fetches and applies each source in turn. A source never overrides a date a higher one holds (it reports the disagreement as `held_by_higher_source`), and only closes off rows it wrote itself. The job's summary has one entry per source under `sources`.

Started from `templates/python` in `nyc_pa_aws_gitops`. `ExampleService.Ping` is still the template's gRPC example.
