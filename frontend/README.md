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
│   ├── Common/        # shared building blocks: form fields, page header,
│   │                  # auth form, dialogs' cancel button, KPI cards, …
│   └── ui/            # shadcn/ui primitives
├── contexts/      # WorkspaceContext: the selected workspace
├── hooks/         # data hooks (useIntegrations, useMetrics, useAuth, …)
├── lib/           # formatting, dates, validation rules, access token,
│                  # route helpers, background job polling, platforms
└── client/        # generated API client (do not edit)
```

Pages read the current workspace with `useCurrentWorkspace()` and fetch data
through the hooks in `hooks/`, which wrap the generated client in TanStack
Query. Forms use the fields of `components/Common/FormFields.tsx` with the
rules of `lib/validation.ts`; buttons running an action are `LoadingButton`s.

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
screens often: re-check each guide from time to time and update
`GUIDES_REVIEWED_ON`. Its screenshots live in
`public/assets/images/tutorials/` and come from two scripts.

**Prism's own screens** are generated against a mocked API, so no backend is
needed. Re-run this after changing the Integrations page:

```bash
bun run tutorial-screenshots
# If Playwright's own browser isn't installed, point it at another Chromium:
PLAYWRIGHT_CHROMIUM=/path/to/chromium bun run tutorial-screenshots
```

**The platforms' screens** (Facebook, Google, X, ...) come from real
connections made on a running Prism with test accounts. Run this on your own
computer: platforms block scripted logins, so you log in by hand once and the
script reuses those sessions (stored in `.tutorial-browser-profile/`, which is
git-ignored because it holds login cookies).

```bash
# Once, or when a session has expired: log in on every tab, then close the browser
PRISM_URL=https://prism.example.com bun run tutorial-screenshots:login

# Every few months: connect and disconnect each platform, saving its screens
PRISM_URL=https://prism.example.com MASK_TEXT=test@acme.com bun run tutorial-screenshots:platforms
# or only some platforms
PRISM_URL=https://prism.example.com bun run tutorial-screenshots:platforms facebook google_analytics
```

- Use dedicated test accounts with brand-like names: their names appear in
  the screenshots. `MASK_TEXT` blacks out the given texts (e.g. email
  addresses).
- Disconnecting revokes Prism's access on the platform, so each run sees the
  first-time screens. LinkedIn has no revocation API: remove Prism under
  LinkedIn's settings (*Data privacy → Permitted services*) between runs.
- When a platform shows a screen the script doesn't recognise, it saves it in
  `public/assets/images/tutorials/_debug/` and moves on. Update `SCREENS` in
  `scripts/platform-screenshots.ts` to match it.
