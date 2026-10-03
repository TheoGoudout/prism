# Deploying Prism

Prism is deployed in two halves, to a single **production** environment:

- **`frontend/`** is a static site on
  [Cloudflare Workers](https://developers.cloudflare.com/workers/static-assets/),
  deployed by GitHub Actions.
- **`backend/`**, the Celery worker and beat scheduler, Postgres and Redis run on
  [Coolify](https://coolify.io), a self-hosted PaaS that deploys the root
  [`compose.yml`](compose.yml).

Publishing a GitHub release deploys both, backend first.

## Domains

| | URL | Hosted by |
|---|---|---|
| Frontend | `https://app.prism.ai` | Cloudflare Workers |
| API | `https://api.prism.ai` (docs at `/docs`) | Coolify |

To use another domain, change it in the four places that carry it:

1. `frontend/.env.production`: `VITE_API_URL`;
2. Coolify's `FRONTEND_HOST` environment variable (the `compose.yml` default
   is the `prism.ai` value). `API_BASE_URL` follows the backend's domain on its
   own;
3. the `production` GitHub Environment's **variables**: `APP_URL` and `API_URL`,
   which the deploy workflows use to verify the sites (they default to the
   `prism.ai` values);
4. the custom domains in Cloudflare and in Coolify (below).

---

## How a release reaches production

[`release.yml`](.github/workflows/release.yml) runs when a release is published:

1. **Backend**: [`deploy-coolify.yml`](.github/workflows/deploy-coolify.yml)
   resolves the tag, `PATCH`es the Coolify application's git ref to it,
   triggers a deployment, waits for the build, then waits for
   `https://api.prism.ai/api/v1/utils/health-check/` to answer.
2. **Frontend**: once the backend succeeded,
   [`deploy-cloudflare.yml`](.github/workflows/deploy-cloudflare.yml) builds the
   same tag, deploys it with wrangler and checks `https://app.prism.ai/` answers
   200.

The API is upgraded before the clients that call it, and a backend that failed to
deploy stops the frontend. Pre-releases are not deployed. In the run, **Re-run
failed jobs** retries only the target that broke.

To release: draft a release on GitHub with a new tag (`v1.2.0`), and publish it.
GitHub creates the tag on publish.

Pushes to `master` deploy nothing: they run CI only.

### Re-deploying and rolling back

| To | Run |
|---|---|
| Re-deploy a release (all, or `backend` / `frontend` only) | **Release** workflow, `tag` = the release |
| Roll the backend back | **Deploy backend to Coolify**, `ref` = the previous tag |
| Roll the frontend back | **Deploy frontend to Cloudflare**, `ref` = the previous tag |

Use `force: true` to redeploy the ref the backend is already pinned to; otherwise
Coolify may decide there is nothing to rebuild. A backend rollback does not roll
back database migrations: check the migrations between the two tags first.

### GitHub setup

Create a `production`
[environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
in the repository settings. Give it required reviewers if a release should wait
for an approval before deploying.

Secrets on the `production` environment:

| Secret | Description |
|---|---|
| `COOLIFY_URL` | Base URL of the Coolify panel, no trailing slash |
| `COOLIFY_API_TOKEN` | Coolify API token with write access to the application (**Keys & Tokens → API tokens**) |
| `COOLIFY_APP_UUID` | The application's UUID: the last path segment of its URL in the Coolify dashboard |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token, see [below](#api-token) |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

Variables on the `production` environment (optional, only to change the domain):
`APP_URL`, `API_URL`.

The deploy fails, rather than skipping, when a Coolify secret is missing: a
backend that silently did not deploy is a frontend talking to the wrong API.

---

## Coolify (backend)

### 1. Create the application

1. In Coolify, **+ New → Public/Private Repository** (with the Coolify GitHub
   App for a private repository), pick this repository, and choose the
   **Docker Compose** build pack with `/compose.yml` as the compose file.
2. Set the git branch to the tag you are about to release (e.g. `v1.0.0`): after
   that, `deploy-coolify.yml` moves it on each release.
3. **Turn auto-deploy off** (*Advanced → Auto Deploy*), so pushes to `master`
   never reach production. Releases deploy it instead.
4. Give the `backend` service the domain `https://api.prism.ai:8000`: Coolify
   proxies `api.prism.ai` to the container's port 8000 and handles HTTPS. Point
   the `api.prism.ai` DNS record at the Coolify server. No other service needs a
   domain.

Coolify 4.2 or newer is required: it made the deploy endpoint `POST`-only, which
is what the workflow sends.

The Coolify host must be reachable from GitHub-hosted runners. Behind an IP
allowlist or Cloudflare Access, the API calls fail and you need either an Access
service token or a self-hosted runner.

### 2. Configure

Coolify lists every variable `compose.yml` references in the **Environment
Variables** tab.

**Generated by Coolify** ([magic variables](https://coolify.io/docs/knowledge-base/docker/compose#coolify-magic-environment-variables)),
nothing to set. Coolify generates them on the first deploy and keeps them stable:

| Coolify variable | Becomes |
|---|---|
| `SERVICE_USER_POSTGRES` | `POSTGRES_USER` |
| `SERVICE_PASSWORD_POSTGRES` | `POSTGRES_PASSWORD` |
| `SERVICE_PASSWORD_64_SECRETKEY` | `SECRET_KEY` |
| `SERVICE_PASSWORD_FIRSTSUPERUSER` | `FIRST_SUPERUSER_PASSWORD`: read it from the tab to log in the first time |
| `SERVICE_URL_BACKEND` | `API_BASE_URL`: the backend's domain, which builds the OAuth redirect URIs. `SERVICE_URL_BACKEND_8000` declares it and routes it to port 8000; Coolify starts with a generated sslip.io domain until you set yours (step 1). |

> **Never change `SECRET_KEY`.** Besides signing sessions, it derives the key
> that encrypts the OAuth tokens stored in the database
> (`backend/app/core/encryption.py`): a new one makes every connected account
> unreadable, and they all have to be reconnected. Outside local development
> the backend refuses to start without one.

Nothing has to be set by hand: a first deploy starts with the values above and
the defaults below. Set the AI key to enable the performance analyses.

**AI analyses**:

| Variable | Description |
|---|---|
| `AI_PROVIDER` | `openai`, `anthropic` or `google` (default `openai`) |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | The key of the chosen provider |

**With defaults** (set only to change them):

| Variable | Default |
|---|---|
| `FIRST_SUPERUSER` | `admin@prism.ai`: email of the first admin user. Coolify has no magic variable for an email address; log in with it and change it from the app. |
| `FRONTEND_HOST` | `https://app.prism.ai`: links in emails, and always an allowed CORS origin |
| `ENVIRONMENT` | `production` |
| `PROJECT_NAME` | `Prism` |
| `POSTGRES_DB` | `app` |
| `AI_MODEL` | `gpt-4o-mini` |
| `CELERY_CONCURRENCY` | `4` worker processes |
| `LANGCHAIN_PROJECT` | `prism` |

**Optional**:

| Variable | Description |
|---|---|
| `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET` | Facebook Pages and Instagram (one Meta app). Each platform is only available once both its variables are set; the startup logs list which are activated. |
| `TWITTER_CLIENT_ID`, `TWITTER_CLIENT_SECRET` | Twitter / X |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | LinkedIn |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | TikTok |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Analytics 4 |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_TLS`, `SMTP_SSL`, `EMAILS_FROM_EMAIL` | Email (password resets, scheduled reports). Disabled while `SMTP_HOST` is empty. |
| `BACKEND_CORS_ORIGINS` | Extra comma-separated CORS origins |
| `SENTRY_DSN` | Sentry error tracking |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_ENDPOINT` | LangSmith tracing |

Register `https://api.prism.ai/api/v1/oauth/callback/{platform}` (the
backend's domain) as the redirect URI in each platform's developer console.

### 3. The stack

`compose.yml` runs:

| Service | Role |
|---|---|
| `db` | PostgreSQL 18 |
| `redis` | Celery broker and result backend |
| `prestart` | Waits for the database, runs `alembic upgrade head`, creates the first superuser, exits. Everything else waits for it. |
| `backend` | FastAPI, four workers |
| `celery-worker` | Syncs, token refreshes, AI analyses |
| `celery-beat` | The scheduler. Exactly one must run: never scale it. |

There is no reverse proxy (Coolify's handles routing and TLS), no frontend
(Cloudflare) and no Adminer: use Coolify's terminal on the `db` container, or
its database backups, instead. Every service has a memory cap so the OOM killer,
if it ever fires, takes the misbehaving container rather than Postgres.

`.github/workflows/test-docker-compose.yml` boots exactly this file on every pull
request, with stand-ins for the magic variables, and checks the API, worker,
beat and migrations.

---

## Cloudflare Workers (frontend)

### API token

Create it at
[dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens)
with a single account-scoped permission:

| Scope | Permission | Needed for |
|---|---|---|
| Account | Workers Scripts: Edit | Uploading the Worker and its static assets |

No zone permission is needed, and the token should not carry one. That holds
only because `frontend/wrangler.jsonc` declares no `routes`, see below.

### Custom domain

The domain is bound by hand, once, in the Cloudflare dashboard: **Workers &
Pages → prism-frontend → Settings → Domains & Routes → Add → Custom domain →
`app.prism.ai`**. Cloudflare creates the DNS record and certificate. The Worker
must exist first, so bind it after the first release has deployed.

Declaring it in `wrangler.jsonc` instead would make wrangler reconcile the zone's
routes on every deploy, which needs a CI token with `Workers Routes: Edit` and
`DNS: Edit` on the zone: enough to repoint `api.prism.ai` at anything if the
token leaked. The cost is that renaming the Worker (`name` in `wrangler.jsonc`)
silently orphans the binding: the deploy succeeds, and the site keeps serving the
old Worker.

`workers_dev` is `false`, so the Worker is not also reachable at a
`*.workers.dev` URL.

### How the site is served

| Nginx (Docker image, local) | Workers |
|---|---|
| SPA fallback (`try_files $uri /index.html`) | `assets.not_found_handling: "single-page-application"` |
| `/api`, `/docs`, `/redoc` return 404 | `frontend/worker/index.ts` |

The API URL is baked in at build time from `frontend/.env.production` (Vite
loads it for `vite build`). It holds public values only: anything in a `VITE_*`
variable ends up in the bundle.

### Deploying by hand

```bash
bun install
bun run --filter frontend build
cd frontend && bun run deploy:dry-run   # validate, upload nothing
cd frontend && bun run deploy           # needs CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID
```

`.github/workflows/test-frontend.yml` runs the build and the dry run on every
pull request that touches the frontend.

### Troubleshooting

- **`Authentication error [code: 10000]` on `/zones/<id>/workers/routes`**:
  something added a `routes` key to `frontend/wrangler.jsonc`. Remove it and
  bind the domain in the dashboard.
- **The deploy succeeded but the site is unchanged**: the domain is bound to
  another Worker, or not bound at all. Check it in the dashboard.

---

## CI secrets

- `PRE_COMMIT` (optional): a token that lets `pre-commit.yml` push its autofix
  commit to pull requests and have CI run on it. Without it, fixes go through
  pre-commit.ci lite.
- `SMOKESHOW_AUTH_KEY` (optional): publishes the backend coverage report with
  [Smokeshow](https://github.com/samuelcolvin/smokeshow). Without it, the
  upload is skipped.
