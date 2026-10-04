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

Airflow runs the schedules; the work happens here (ADR-0031 in `nyc_pa_aws_gitops`). `app/jobs.py` is the job API under `/jobs/`, and every endpoint needs `Authorization: Bearer $AIRFLOW_TOKEN`:

- `POST /jobs/calendars/{FED}/capture` fetches the source, keeps it raw if it changed, and applies the parse with history.
- `POST /jobs/calendars/{FED}/reparse` re-applies the latest capture, for example after a parser fix.
- `GET /jobs/calendars/{FED}/business-day?on=YYYY-MM-DD` answers whether that date is a business day. It's meant for DAGs' short-circuit first task.

DAGs live in `dags/` (flat; the deploy puts them in Airflow's `dags/mkt-data/`). Their ids start with `mkt_data__`, and they import only Airflow, the platform's `home_platform_jobs` helper and the standard library (`tests/test_dags.py` checks both). New DAGs start paused, so unpause each one in the Airflow UI once it parses.

## Data model

See `app/models.py`. In short:

- **Raw:** `source` → `capture`, which is append-only and enforced by a trigger, plus `source_check`, which records every fetch attempt.
- **Processed:** `calendar` → `calendar_year` (coverage) and `calendar_day` (closed or early-close weekdays, with `valid_from`/`valid_to` history).

Started from `templates/python` in `nyc_pa_aws_gitops`. `ExampleService.Ping` is still the template's gRPC example.
