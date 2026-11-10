# Contributing to ContentPulse

## Workflow

1. Branch from `main`: `git switch -c <type>/<short-description>`, for example
   `fix/approval-double-submit` or `feat/trend-export`.
2. Make small, focused commits.
3. Run the checks locally (the same ones CI runs):

   ```bash
   cd backend  && uv run ruff check . && uv run ruff format --check . && uv run pytest
   cd frontend && npm run lint && npm run typecheck && npm run build
   ```

4. Push the branch and open a pull request. CI must be green before it is merged.
5. Merge with a squash or a merge commit, then delete the branch.

Nothing is pushed straight to `main`.

## Never rewrite pushed commits

This is what causes `! [rejected] ... (non-fast-forward)` on `git push`.

- **Don't `git rebase` (or `commit --amend`, or `reset`) commits that are already on GitHub.**
  A rebase gives them new hashes; GitHub still has the old ones, so the branch has
  diverged and every push is rejected until someone force-pushes or merges the two
  histories. To bring in `main`, use `git merge origin/main`.
- **One branch per pull request.** Once a PR is merged, delete the branch (turn on
  *Settings → General → Automatically delete head branches* in GitHub) and start the
  next piece of work from a fresh `main`: `git switch main && git pull && git switch -c <name>`.
  Reusing a merged branch name is how the same commits end up on two histories.
- If a push is rejected anyway: `git fetch`, then `git merge origin/<branch>` and push
  again. Never `git push --force`; if you truly must rewrite a branch only you use,
  use `git push --force-with-lease`.
- Optional local guard: copy the `pre-rebase` hook from `docs/git-pre-rebase-hook.sh` to
  `.git/hooks/pre-rebase` (it refuses to rebase commits that are already on a remote).

## Branch names

`feat/…` a new capability, `fix/…` a bug fix, `chore/…` tooling, cleanup or dependencies,
`docs/…` documentation only, `refactor/…` a change that keeps behaviour the same.

## Commit messages

Say what changed and why, in the imperative, with a short subject (about 70 characters):

```
Refuse to approve a post twice when two admins click at once

Lock the post before the approval row so the second request waits, then
sees the round was already decided and gets a 409.
```

Avoid titles like "Updated version" or "Updated for deployment": they make `git log`,
`git blame` and rollbacks useless. Use the body for the reason, not for a list of files.

## Database changes

- Every schema change is an Alembic migration in `backend/app/db/migrations/versions/`.
  Keep a single head (`uv run alembic heads`).
- A downgrade that would destroy data must raise rather than silently drop it.
- Tests run migrations against a throwaway database named `*test*` on a local host and
  refuse to run anywhere else.

## Secrets and local files

- Never commit `.env` files, keys, Terraform state or `*.tfvars` (they are git-ignored).
  Add new settings to `.env.example` with a blank value.
- Personal notes, tool caches and generated reports are git-ignored; keep them out of the
  repository.

## Infrastructure

`infra/aws` is code only until someone applies it. Do not run `terraform apply` or
`deploy.sh` against a real environment from a pull request branch. See
[infra/aws/README.md](infra/aws/README.md).

## Protecting `main` (repository admins)

In GitHub: **Settings → Branches → Add branch ruleset** for `main`:

- Require a pull request before merging.
- Require status checks to pass: select `Backend (lint + tests)`,
  `Frontend (lint + types + build)` and `Terraform (format + validate)` (they appear after
  the first CI run).
- Block force pushes and deletion.
