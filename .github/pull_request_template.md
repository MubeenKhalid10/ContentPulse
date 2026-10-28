## What and why

<!-- What does this change, and why? Link the issue if there is one. -->

## How it was checked

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest` (backend)
- [ ] `npm run lint && npm run typecheck && npm run build` (frontend)
- [ ] Tried it in the app, if it changes what a user sees

## Risk

- [ ] Includes a database migration (single Alembic head, downgrade does not lose data)
- [ ] Changes infrastructure code (`infra/aws`): nothing applied by this PR
- [ ] Adds or changes a setting: `.env.example` and the docs are updated
- [ ] None of the above
