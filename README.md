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

Started from `templates/python` in `nyc_pa_aws_gitops`. The `Item` model, its `0001` migration and `ExampleService.Ping` are template examples and will be replaced by the calendar schema.
