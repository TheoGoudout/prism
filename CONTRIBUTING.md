# Contributing

1. Set up the stack as described in [development.md](development.md) and
   install the git hooks (`uv run prek install`).
2. Create a branch and keep each pull request focused on one change.
3. Add or update tests:
   - backend: `backend/tests`, run with `uv run pytest`
   - end-to-end: `frontend/tests`, run with Playwright
4. Make sure lint and type checks pass:
   - `uv run ruff check`, `uv run ruff format`, `uv run mypy app`
   - `bun run lint`
5. If you change the API, regenerate the frontend client with
   `./scripts/generate-client.sh`.
6. Pull requests need one of these labels: `breaking`, `security`,
   `feature`, `bug`, `refactor`, `upgrade`, `docs` or `internal`. CI checks
   for it.
