# Deploying Prism

Prism is deployed in two halves, to three environments, **dev**, **staging**
and **production**:

- **`frontend/`** is a static site on
  [Cloudflare Workers](https://developers.cloudflare.com/workers/static-assets/),
  deployed by GitHub Actions.
- **`backend/`**, the Celery worker and beat scheduler, Postgres and Redis run on
  [Coolify](https://coolify.io), a self-hosted PaaS that deploys the root
  [`compose.yml`](compose.yml).

| Environment | Deployed by | When |
|---|---|---|
| **dev** | Coolify and Cloudflare Workers Builds, watching `master` | every push to `master` |
| **staging** (opt-in) | [`release.yml`](.github/workflows/release.yml) | every published pre-release and release, once `STAGING_ENABLED` is `true` |
| **production** | [`release.yml`](.github/workflows/release.yml) | every published release (not pre-releases) |

Staging and production run the same jobs —
[`deploy-environment.yml`](.github/workflows/deploy-environment.yml), backend
first — with a different GitHub Environment; a release deploys both side by
side. Dev never goes through Actions: see [Dev](#dev).

Every environment is optional except production. Dev exists only once its
Coolify application and Worker are set up; staging only once the
`STAGING_ENABLED` repository variable is `true` (Settings → Secrets and
variables → Actions → Variables). Without it a release deploys production
alone and a pre-release deploys nothing.

## Domains

| | Production | Staging | Dev | Hosted by |
|---|---|---|---|---|
| Frontend | `https://app.prism.ai` | `https://app.staging.prism.ai` | `https://app.dev.prism.ai` | Cloudflare Workers |
| API | `https://api.prism.ai` (docs at `/docs`) | `https://api.staging.prism.ai` | `https://api.dev.prism.ai` | Coolify |

Each environment's URLs are written down in the repository, and nowhere else:

1. `frontend/.env.<environment>`: the API URL built into that environment's
   frontend (`VITE_API_URL`). `test-frontend.yml` builds all three on every
   pull request and fails if a bundle does not reference its file's URL;
2. `.github/scripts/deploy-coolify/resolve-ref-commit-and-version.sh` and
   `.github/scripts/deploy-cloudflare/verify-the-deployed-site.sh`: the hosts
   the deploy workflows check once they have deployed;
3. Coolify's `FRONTEND_HOST` on each application (the `compose.yml` default is
   the production value, so the staging and dev applications must set it);
4. the custom domains in Cloudflare and in Coolify (below).

---

## How a release reaches staging and production

[`release.yml`](.github/workflows/release.yml) runs when a release or
pre-release is published. It builds the image once, then runs steps 2 and 3
for each environment the release targets — staging for a pre-release, staging
and production side by side for a release:

1. **Backend image**: [`images.yml`](.github/workflows/images.yml) builds
   `backend/Dockerfile` from the tag on a GitHub runner and pushes it to GHCR
   as `ghcr.io/theogoudout/prism-backend`, tagged `sha-<short commit>` and with
   the release tag.
2. **Backend**: [`deploy-coolify.yml`](.github/workflows/deploy-coolify.yml)
   resolves the tag, checks anonymously that its image is on GHCR, `PATCH`es the
   environment's Coolify application's git ref to the tag and its `TAG` variable
   to `sha-<short>`, triggers a deployment (the host pulls, it never builds),
   then waits for its `/api/v1/utils/health-check/` to answer and
   checks `/api/v1/openapi.json` reports the released version (the
   `backend/pyproject.toml` version at the tag).
3. **Frontend**: once the backend succeeded,
   [`deploy-cloudflare.yml`](.github/workflows/deploy-cloudflare.yml) builds the
   same tag for that environment, deploys it with wrangler and checks the
   environment's frontend answers 200.

The API is upgraded before the clients that call it, and a backend that failed to
deploy stops that environment's frontend. Pre-releases reach staging, never
production. The run's last job,
**Release complete**, reports each target and fails if any of them did; **Re-run
failed jobs** retries only the target that broke.

### Cutting a release

Releasing is two steps, and only the second one deploys:

1. Run **Prepare Release**
   ([`release-prepare.yml`](.github/workflows/release-prepare.yml)) from
   `master`, picking a bump (`patch`, `minor`, `major`, `rc`, or an `explicit`
   version). It refuses to run unless every version file agrees
   (`bun scripts/set-version.mjs --check`), the version is new and sorts above
   every existing tag, and master's CI is green. It then writes the version to
   every file that carries it ([`scripts/set-version.mjs`](scripts/set-version.mjs)
   has the list), writes the notes for the pull requests merged since the last
   stable release into [`release-notes.md`](release-notes.md), sorted by label
   ([`scripts/release_notes.py`](scripts/release_notes.py)), commits that to
   `master`, and opens a **draft** release with the same notes.
2. Review the draft and press **Publish release**. GitHub creates the tag at that
   moment, at the bump commit, and `release.yml` deploys it.

The tag is never pushed by a workflow, so a tag without a release cannot exist,
and nothing reaches staging or production without a person pressing Publish. A
version with an `-rcN` suffix becomes a pre-release, which deploys staging only.

Prepare Release needs a `RELEASE_TOKEN` repository secret: a fine-grained PAT
(or GitHub App token) with **Contents: read and write** on this repository. The
bump commit has to be pushed with it rather than with `GITHUB_TOKEN`, because
GitHub runs no workflows for a push made with `GITHUB_TOKEN`, and the released
commit would then have no CI. If `master` is protected, that token's owner must
be allowed to push to it.

Pushes to `master` deploy dev, through the platforms (see [Dev](#dev)), never
staging or production.

### Re-deploying and rolling back

| To | Run |
|---|---|
| Re-deploy a release (all, or `coolify` / `cloudflare` only) | **Release** workflow, `tag` = the release |
| Roll both back | **Rollback**, pick the environment, `tag` = the previous release: the frontend goes back first, then the backend — the reverse of a release, so the frontend is never ahead of the API it talks to |
| Roll the backend back on its own | **Deploy backend to Coolify**, pick the environment, `ref` = the previous tag |
| Roll the frontend back on its own | **Deploy to Cloudflare Workers**, pick the environment |

Use `force: true` to redeploy the ref the backend is already pinned to; otherwise
Coolify may decide there is nothing to redeploy. A backend rollback does not roll
back database migrations: check the migrations between the two tags first.

A tag deploys only once its image exists. Releases from before images were
published to GHCR have none: run **Backend image** (`images.yml`) with that tag
first, then roll back to it.

### GitHub setup

Create two
[environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
in the repository settings, `staging` and `production`. Give `production`
required reviewers if a release should wait for an approval before deploying.
If you restrict which refs may deploy to either, allow `v*` tags: every release
deploys from its tag. Dev needs no GitHub environment.

Secrets, set on **each** environment with that environment's values:

| Secret | Description |
|---|---|
| `COOLIFY_URL` | Base URL of the Coolify panel, no trailing slash |
| `COOLIFY_API_TOKEN` | Coolify API token with write access to the application (**Keys & Tokens → API tokens**) |
| `COOLIFY_APP_UUID` | The environment's application UUID: the last path segment of its URL in the Coolify dashboard |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token, see [below](#api-token) |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

The deploy fails, rather than skipping, when a Coolify secret is missing: a
backend that silently did not deploy is a frontend talking to the wrong API.

---

## Coolify (backend)

### 1. Create the applications

Create one application each for staging and production, the same way; they
differ only in their domain and `FRONTEND_HOST`. Dev is a third application,
set up differently — see [Dev](#dev).

1. In Coolify, **+ New → Public/Private Repository** (with the Coolify GitHub
   App for a private repository), pick this repository, and choose the
   **Docker Compose** build pack with `/compose.yml` as the compose file.
2. Set the git branch to the tag you are about to release (e.g. `v1.0.0`).
   After that, `deploy-coolify.yml` moves it on each deploy.
3. **Turn auto-deploy off** (*Advanced → Auto Deploy*) on both: `release.yml`
   deploys them, after the release's image exists.
4. Do not set `TAG`: `deploy-coolify.yml` owns it, and sets it on every
   deploy to the image of the tag being deployed.
5. Give the `backend` service the domain `https://api.prism.ai:8000`
   (staging: `https://api.staging.prism.ai:8000`): Coolify proxies it to the
   container's port 8000 and handles HTTPS. Point the DNS record at the Coolify
   server. No other service needs a domain.
6. On staging, set `ENVIRONMENT=staging` and
   `FRONTEND_HOST=https://app.staging.prism.ai`.

Coolify 4.2 or newer is required: it made the deploy endpoint `POST`-only, which
is what the workflow sends.

**Nothing is built on the Coolify host.** `compose.yml` names the GHCR image
and has no `build:` section, so Coolify only pulls it. The host pulls without
credentials, so **the GHCR package must be public**. The repository is public,
but check it once after the first release: GitHub → your profile → *Packages* →
`prism-backend` → *Package settings* → *Change visibility*. The deploy's image
check fails with that hint if it is not.

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
| `CELERY_CONCURRENCY` | `1` worker process — sized for a small shared host; raise it on a bigger one |
| `WEB_CONCURRENCY` | `1` API (uvicorn) worker process, each a full copy of the app — sized for a small shared host; raise it on a bigger one |
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
| `backend` | FastAPI, `WEB_CONCURRENCY` workers (one by default) |
| `celery-worker` | Syncs, token refreshes, AI analyses |
| `celery-beat` | The scheduler. Exactly one must run: never scale it. |

`prestart`, `backend`, `celery-worker` and `celery-beat` all run the one GHCR
image. `compose.override.yml`, which Coolify never reads, adds their `build:`
sections back for local development.

There is no reverse proxy (Coolify's handles routing and TLS), no frontend
(Cloudflare) and no Adminer: use Coolify's terminal on the `db` container, or
its database backups, instead. Every service has a memory cap so the OOM killer,
if it ever fires, takes the misbehaving container rather than Postgres.

`.github/workflows/test-docker-compose.yml` boots exactly this file on every pull
request, with stand-ins for the magic variables and the pull request's own image
built under the name the file asks for, and checks the API, worker, beat and
migrations.

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

Each domain is bound by hand, once, in the Cloudflare dashboard: **Workers &
Pages → prism-frontend → Settings → Domains & Routes → Add → Custom domain →
`app.prism.ai`**, and the same for **prism-frontend-staging** →
`app.staging.prism.ai` and **prism-frontend-dev** → `app.dev.prism.ai`. Cloudflare creates the DNS record and certificate. A
Worker must exist first, so bind each after its first deploy.

Declaring it in `wrangler.jsonc` instead would make wrangler reconcile the zone's
routes on every deploy, which needs a CI token with `Workers Routes: Edit` and
`DNS: Edit` on the zone: enough to repoint `api.prism.ai` at anything if the
token leaked. The cost is that renaming the Worker (`name` in `wrangler.jsonc`)
silently orphans the binding: the deploy succeeds, and the site keeps serving the
old Worker. `wrangler.jsonc` has one `env` block per environment; production keeps
the Worker name `prism-frontend`.

`workers_dev` is `false`, so the Worker is not also reachable at a
`*.workers.dev` URL.

### How the site is served

| Nginx (Docker image, local) | Workers |
|---|---|
| SPA fallback (`try_files $uri /index.html`) | `assets.not_found_handling: "single-page-application"` |
| `/api`, `/docs`, `/redoc` return 404 | `frontend/worker/index.ts` |

The API URL is baked in at build time from `frontend/.env.<environment>`
(`bun run build:staging` / `build:production` pass Vite the mode). Those files
hold public values only: anything in a `VITE_*` variable ends up in the bundle.

### Deploying by hand

```bash
bun install
bun run --filter frontend build:production
cd frontend && bunx wrangler deploy --dry-run --env production   # validate, upload nothing
cd frontend && bun run deploy:production   # needs CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID
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

---

## Dev

Dev follows `master` without GitHub Actions: Coolify and Cloudflare Workers
Builds each watch the repository and deploy every push themselves. Nothing
orders the two, so for a few minutes after a push the dev frontend can run
ahead of the dev API — acceptable for dev, and the reason staging and
production are deployed by `release.yml` instead.

### Backend (Coolify)

A third Coolify application, set up like the other two except:

1. **Compose file: `/compose.dev.yml`**, git branch `master`, and
   **auto-deploy on**.
2. `compose.dev.yml` is `compose.yml` with the backend image built from the
   checkout (`build:` and `pull_policy: build` on `prestart`, `backend`,
   `celery-worker` and `celery-beat`) instead of pulled from GHCR — dev is the
   one environment whose Coolify host builds. It is generated: after changing
   `compose.yml`, run `scripts/generate-compose-dev.sh` and commit the result.
   `test-docker-compose.yml` fails while it is stale.
3. Do not set `TAG`: nothing pulls by tag here.
4. Domain `https://api.dev.prism.ai:8000` on the `backend` service.
5. `FRONTEND_HOST=https://app.dev.prism.ai`. `ENVIRONMENT` needs no setting:
   `compose.dev.yml` defaults it to `dev`, which the backend treats like staging
   and production (a real `SECRET_KEY` required, no local-only routes). Register
   `https://api.dev.prism.ai/api/v1/oauth/callback/{platform}` in any platform
   console you test against.

### Frontend (Cloudflare Workers Builds)

Connect the repository to the `prism-frontend-dev` Worker in the Cloudflare
dashboard (**Workers & Pages → prism-frontend-dev → Settings → Builds →
Connect**), on branch `master`:

| Setting | Value |
|---|---|
| Root directory | `/` |
| Build command | `bun install --frozen-lockfile && bun run --filter frontend build:dev` |
| Deploy command | `cd frontend && bunx wrangler deploy --env dev` |
| Build variable | `BUN_VERSION` = the value in `.bun-version` |

The API URL comes from the committed `frontend/.env.dev`, and
`test-frontend.yml` builds the dev variant on every pull request. Turn the
builds' preview deployments for non-`master` branches off unless you want them.

A Worker has to exist before it can be connected: create it with one manual
deploy first (`bun run --filter frontend build:dev && cd frontend && bun run
deploy:dev`), then bind `app.dev.prism.ai` to it.
