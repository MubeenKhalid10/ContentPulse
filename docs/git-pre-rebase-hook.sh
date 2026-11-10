#!/bin/sh
# Optional local guard: refuse to rebase commits that already exist on a remote.
#
# Install (once per clone):
#   cp docs/git-pre-rebase-hook.sh .git/hooks/pre-rebase && chmod +x .git/hooks/pre-rebase
#
# Rebasing gives commits new hashes. If the old ones were pushed, the next push is
# rejected as "non-fast-forward". Use `git merge` instead (see CONTRIBUTING.md).
# Override on purpose, for a branch nobody else uses:
#   ALLOW_REBASE_PUBLISHED=1 git rebase ...   (then push with --force-with-lease)

[ -n "$ALLOW_REBASE_PUBLISHED" ] && exit 0

upstream="$1"
branch="$2"
[ -z "$branch" ] && branch="$(git symbolic-ref -q --short HEAD)"
[ -z "$branch" ] && exit 0

for commit in $(git rev-list "$upstream..$branch" 2>/dev/null); do
  remotes="$(git branch -r --contains "$commit" 2>/dev/null)"
  if [ -n "$remotes" ]; then
    echo "" >&2
    echo "Refusing to rebase: commit $(git rev-parse --short "$commit") is already on a remote:" >&2
    echo "$remotes" | head -3 | sed 's/^/    /' >&2
    echo "Bring changes in with:   git merge $upstream" >&2
    echo "(Only if you really mean it: ALLOW_REBASE_PUBLISHED=1 git rebase ...)" >&2
    exit 1
  fi
done
exit 0
