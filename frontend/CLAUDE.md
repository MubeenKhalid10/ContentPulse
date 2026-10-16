@AGENTS.md

## Token-efficient repository workflow

- Start with the user's requested task and inspect only the relevant files.
- Read `git status --short` and inspect targeted files before making changes.
- Never scan the entire repository or dump large files unless explicitly necessary.
- Exclude dependencies, build output, caches, logs, generated artifacts, local databases, backups, and environment files from routine exploration.
- Never read or print `.env` files, credentials, private keys, or secret values. Use variable names and redacted diagnostics instead.
- For backend changes, prioritize relevant `backend/app/` modules, migrations, and targeted `backend/tests/`.
- For frontend changes, prioritize relevant frontend source files and tests.
- Read `docs/production-readiness.md` and `docs/production-verification.sql` only for database/security/deployment tasks.
- Run targeted tests first, then the broader suite when appropriate.
- Do not modify or deploy production infrastructure unless explicitly authorized.
- Before reading additional files, explain briefly why they are needed if the scope is expanding significantly.