# Deploying Prism

Prism runs as a Docker Compose stack (API, Celery worker and beat, frontend,
Postgres, Redis, Adminer) behind a shared [Traefik](https://traefik.io) proxy
that routes subdomains and handles HTTPS certificates. With `DOMAIN=example.com`:

| URL | Service |
|-----|---------|
| `https://dashboard.example.com` | Frontend |
| `https://api.example.com` | API (docs at `/docs`) |
| `https://adminer.example.com` | Database admin |
| `https://traefik.example.com` | Traefik dashboard |

## 1. Prepare the server

- A server with [Docker Engine](https://docs.docker.com/engine/install/).
- DNS records for your domain **and a wildcard** (`*.example.com`) pointing to
  it. For a staging stack on the same server, use e.g. `staging.example.com`
  and `*.staging.example.com`.

## 2. Start Traefik (once per server)

Traefik lives in its own stack, shared by every Prism deployment on the
server, and reaches them over a Docker network called `traefik-public`:

```bash
# On your machine
rsync -a compose.traefik.yml root@your-server:/root/code/traefik-public/

# On the server
docker network create traefik-public
cd /root/code/traefik-public/
export USERNAME=admin                         # Traefik dashboard login
export PASSWORD=<a strong password>
export HASHED_PASSWORD=$(openssl passwd -apr1 "$PASSWORD")
export DOMAIN=example.com
export EMAIL=you@example.com                  # for Let's Encrypt; not @example.com
docker compose -f compose.traefik.yml up -d
```

## 3. Configure Prism

Create a `.env` from [`.env.example`](.env.example). The variables are
described in the [README](README.md#configuration); for a deployment, also:

- set `ENVIRONMENT` to `staging` or `production`, and `DOMAIN` to your domain;
- set `FRONTEND_HOST=https://dashboard.<DOMAIN>`,
  `API_BASE_URL=https://api.<DOMAIN>` and
  `BACKEND_CORS_ORIGINS=https://dashboard.<DOMAIN>`;
- give each deployment on the server its own `STACK_NAME` and
  `COMPOSE_PROJECT_NAME` (e.g. `prism-staging`, `prism-production`);
- replace every `changethis`. Generate secrets with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`;
- register `{API_BASE_URL}/api/v1/oauth/callback/{platform}` as the redirect
  URI in each platform's developer console.

## 4. Deploy

### Manually

```bash
rsync -av --filter=":- .gitignore" ./ root@your-server:/root/code/prism/
scp .env root@your-server:/root/code/prism/.env

# On the server
cd /root/code/prism/
docker compose -f compose.yml build
docker compose -f compose.yml up -d
```

`-f compose.yml` leaves out `compose.override.yml`, which only holds
local-development settings. Database migrations run automatically (the
`prestart` service) before the API starts.

### With GitHub Actions

Two workflows deploy on a [self-hosted
runner](https://docs.github.com/en/actions/hosting-your-own-runners) on your
server:

| Workflow | Trigger | Runner label | GitHub environment |
|----------|---------|--------------|--------------------|
| `deploy-staging.yml` | push to `master` | `staging` | `staging` |
| `deploy-production.yml` | release published | `production` | `production` |

To set them up:

1. On the server, create a user for the runner and let it use Docker:

   ```bash
   sudo adduser github
   sudo usermod -aG docker github
   ```

2. As that user, [add a self-hosted
   runner](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners)
   to the repository with the label `staging` or `production`, then, as root,
   [install it as a
   service](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service)
   (`./svc.sh install github && ./svc.sh start` in `actions-runner/`).

3. In the repository settings, create the `staging` and `production`
   [environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
   and give each a `DOTENV` secret holding the whole `.env` file for that
   deployment. The workflow writes it to `.env` before running Compose.

## CI secrets

- `SMOKESHOW_AUTH_KEY` (optional): publishes the backend coverage report with
  [Smokeshow](https://github.com/samuelcolvin/smokeshow). Without it, the
  coverage step is skipped.
