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

# Browser Testing Policy

Browser testing uses my Firefox through the Firefox MCP (`mcp__firefox__*`) only.

- Never use `claude-in-chrome` or any Chrome MCP tool. If Firefox MCP is unavailable, stop and tell me; do not fall back to another browser.
- Start by calling the Firefox tabs-context tool to confirm my existing session, and reuse its tabs. Do not launch another browser or profile.
- Use Firefox for UI and responsive checks, auth flows, forms, navigation, screenshots, and console/JS error inspection.
- Interactions must actually go through the Firefox MCP tools.
- If a bug turns up, fix it in source and re-test in the same session. Report tests run, bugs found, fixes, pass/fail, and remaining issues.
