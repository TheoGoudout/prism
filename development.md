# Developing Prism

## Requirements

- [Docker](https://www.docker.com/) for the full stack
- [uv](https://docs.astral.sh/uv/) for the backend (it installs the Python
  version from [`.python-version`](.python-version), currently 3.14)
- [Bun](https://bun.sh/) for the frontend

## Running the stack

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
docker compose watch
```

| URL | Service |
|-----|---------|
| <http://localhost:5173> | Frontend |
| <http://localhost:8000/docs> | API and interactive docs |
| <http://localhost:8080> | Adminer (database admin) |
| <http://localhost:1080> | MailCatcher: every email the backend sends |

`docker compose watch` syncs code changes into the containers and reloads
the API. The first start takes a minute while the database is migrated and
the first superuser is created; follow it with `docker compose logs -f`.

[`compose.yml`](compose.yml) describes the deployed stack and
[`compose.override.yml`](compose.override.yml) adds the local-only settings
(published ports, MailCatcher, live reload); Compose merges them
automatically.

### Running a service outside Docker

Every service keeps its port, so you can stop one container and run it
locally instead:

```bash
docker compose stop frontend
bun run dev                        # frontend, with hot reload

docker compose stop backend
cd backend && uv run fastapi dev app/main.py
```

### Connecting real platforms

OAuth providers redirect back to `{API_BASE_URL}/api/v1/oauth/callback/{platform}`.
Register that URI in the platform's developer console and set its
credentials in `.env` (see the [README](README.md#configuration)). Most
providers accept `http://localhost:8000` for development; those that require
HTTPS need a tunnel (e.g. `cloudflared` or `ngrok`) set as `API_BASE_URL`.

## Backend

See [backend/README.md](backend/README.md): layout, tests, migrations.

## Frontend

See [frontend/README.md](frontend/README.md): layout, API client, end-to-end
tests.

## Code quality

The hooks in [`.pre-commit-config.yaml`](.pre-commit-config.yaml) run
[prek](https://prek.j178.dev) (a faster pre-commit): file hygiene, Ruff, mypy,
Biome, a check that the generated client is up to date, and GitHub workflow
linting. CI runs them on every pull request.

```bash
uv run prek install            # run them before each commit
uv run prek run --all-files    # run them now
```

## Testing the domains locally

To try the Traefik subdomain routing used in production, set
`DOMAIN=localhost.tiangolo.com` in `.env` (that domain and all its
subdomains resolve to `127.0.0.1`) and restart the stack: the frontend is
then at <http://dashboard.localhost.tiangolo.com> and the API at
<http://api.localhost.tiangolo.com>.
