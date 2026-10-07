# Prism backend

FastAPI + SQLModel API, Celery worker for platform syncs, and LangChain
chains for AI insights. Python 3.14, managed with [uv](https://docs.astral.sh/uv/).

## Layout

```
app/
├── main.py              # FastAPI app
├── api/
│   ├── deps.py          # session, current user, workspace membership, metrics filters
│   └── routes/          # one module per resource
├── models/              # SQLModel tables and API schemas
├── crud/                # database reads and writes
├── services/            # metrics aggregation, AI analyses, migrations, sync schedule
├── integrations/
│   ├── oauth/           # one OAuth provider per platform + registry
│   ├── platforms/       # one sync module per platform
│   ├── meta.py          # Graph API helpers shared by Facebook and Instagram
│   └── tokens.py        # refresh tokens before they expire
├── migrate/             # migrating history from other tools
│   ├── files/           # CSV exports: reading, each tool's column names, parsing
│   └── sources/         # API migrations: Sprout Social, Metricool
├── worker/              # Celery app, sync tasks, nightly and follow-up schedules
├── ai/                  # LLM factory, prompts, insights and report chains
├── core/                # settings, database, security, token encryption
└── alembic/             # migrations
```

## API

Everything under `/api/v1`:

| Prefix | |
|--------|---|
| `/login`, `/password-recovery`, `/reset-password` | Authentication |
| `/users` | Own account; user administration for superusers |
| `/workspaces` | Workspaces and their members |
| `/workspaces/{id}/integrations` | Connected accounts: list, connect, sync, disconnect |
| `/workspaces/{id}/metrics` | `summary`, `timeseries` and top `posts`, filtered by `platform`, `date_from`, `date_to` |
| `/workspaces/{id}/ai` | `insights` and `report`, same filters |
| `/workspaces/{id}/migrate` | Migrate history from another tool: through its API (`{source}/profiles`, `{source}`, `runs`) or a CSV export (`upload`) |
| `/oauth/callback/{platform}` | Where providers redirect after authorization |

Workspace routes check membership from the path: non-members get a 404, and
viewers get a 403 on anything that changes data. An invalid or expired token
gets a 401: the client then logs in again. The interactive docs are at
`/docs`.

## Transactions

Each API request and each worker task is one unit of work, committed once
when it is complete:

- CRUD helpers that stand for a whole unit (creating a user, renaming a
  workspace...) commit through `crud.save` / `crud.delete`. Those that are
  steps of a larger unit (storing what a sync fetched, importing a file) only
  add to the session, and their caller commits.
- A sync stores its accounts, posts and snapshots together with the
  integration's new status, or nothing if it fails. Refreshed OAuth tokens
  are the exception: they are committed right away, since a provider that
  rotates refresh tokens has already invalidated the old one.
- A migration commits each profile's data with its progress.
- Rules checked before writing ("one analysis at a time", "a workspace keeps
  an owner") are checked under row locks (`crud.lock_workspace`,
  `crud.count_owners`), so concurrent requests can't both pass them; unique
  constraints guard the upserts.

## Setup

```bash
uv sync                          # from the repository root or backend/
source ../.venv/bin/activate     # the workspace's virtual environment
```

The API needs Postgres (and Redis for the worker): start them with
`docker compose up -d db redis`, then:

```bash
uv run alembic upgrade head
uv run python app/initial_data.py    # first superuser
uv run fastapi dev app/main.py
uv run celery -A app.worker.celery_app worker --beat --loglevel=info
```

## Adding a platform

1. Add it to the `Platform` enum (`app/models/integration.py`).
2. Write an OAuth provider in `app/integrations/oauth/` and register it in
   `registry.py`.
3. Write a sync function in `app/integrations/platforms/` that maps the
   platform's metrics onto `MetricSnapshotUpsert` / `PostUpsert`, and
   register it in `platforms/__init__.py`.
4. Add its credentials to `app/core/config.py` and `.env.example`, and its
   label in `frontend/src/lib/platforms.ts`.
5. Create a migration (the enum is a database type) and regenerate the
   frontend client.

## Tests

```bash
uv run pytest                        # needs Postgres
bash scripts/test.sh                 # same, with a coverage report in htmlcov/
uv run ruff check && uv run ruff format --check
uv run mypy app
```

External APIs and LLMs are mocked, so the tests need no credentials. To run
them in the Docker stack instead: `docker compose exec backend bash
scripts/tests-start.sh`.

## Migrations

After changing a table model:

```bash
uv run alembic revision --autogenerate -m "Describe the change"
uv run alembic upgrade head
```

Review the generated file in `app/alembic/versions/` and commit it. CI fails
if the models and the migrations disagree (`alembic check`). In Docker,
migrations run automatically on start (the `prestart` service).

## Email templates

Templates are written in [MJML](https://mjml.io) in
`app/email-templates/src/` and compiled to HTML in
`app/email-templates/build/`, which is what the app sends (e.g. with the
[VS Code MJML extension](https://github.com/mjmlio/vscode-mjml): *MJML:
Export to HTML*).
