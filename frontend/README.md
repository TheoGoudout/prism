# Prism frontend

React 19 + TypeScript single-page app, built with Vite, TanStack Router and
Query, Tailwind CSS, shadcn/ui and Recharts. Managed with [Bun](https://bun.sh/).

## Getting started

```bash
cp .env.example .env    # VITE_API_URL: where the API is
bun install
bun run dev             # http://localhost:5173
```

The API must be running (see [development.md](../development.md)).

| Command | |
|---------|---|
| `bun run dev` | Dev server with hot reload |
| `bun run build` | Type-check and build to `dist/` |
| `bun run lint` | Biome lint and format (fixes what it can) |
| `bun run test` | Playwright end-to-end tests |

## Layout

```
src/
├── routes/        # pages (file-based routing; routeTree.gen.ts is generated)
├── components/
│   ├── Analytics/     # KPI table, trend chart, AI insights
│   ├── Integrations/  # connect menu, account rows, sync button, platform icons
│   ├── Workspaces/    # onboarding, workspace settings, members
│   ├── Common/        # shared building blocks (layouts, KPI cards, …)
│   └── ui/            # shadcn/ui primitives
├── contexts/      # WorkspaceContext: the selected workspace
├── hooks/         # data hooks (useIntegrations, useMetrics, useAuth, …)
├── lib/           # formatting and platform helpers
└── client/        # generated API client (do not edit)
```

Pages read the current workspace with `useCurrentWorkspace()` and fetch data
through the hooks in `hooks/`, which wrap the generated client in TanStack
Query.

## API client

`src/client/` is generated from the backend's OpenAPI schema. After changing
the API, regenerate it from the repository root:

```bash
bash scripts/generate-client.sh
```

A pre-commit hook does the same and fails if the committed client is out of
date.

## End-to-end tests

The Playwright tests in `tests/` run against the real API, and the
password-reset tests read emails from MailCatcher, so start the stack first:

```bash
docker compose up -d --wait backend mailcatcher
bunx playwright test          # or: bunx playwright test --ui
docker compose down -v        # removes the data the tests created
```

## Connection guides

The Integrations page has a step-by-step guide per platform
(`src/components/Integrations/guideContent.tsx`). The platforms change their
login screens often: re-check each guide against the live flow from time to
time and update `GUIDES_REVIEWED_ON`.

The Prism screenshots in `public/assets/images/tutorials/` are generated
against a mocked API, so no backend is needed. Re-run this after changing the
Integrations page:

```bash
bun run tutorial-screenshots
# If Playwright's own browser isn't installed, point it at another Chromium:
PLAYWRIGHT_CHROMIUM=/path/to/chromium bun run tutorial-screenshots
```
