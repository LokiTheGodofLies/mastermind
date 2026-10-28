#!/usr/bin/env bash
# Commit everything and push to origin. Optionally open a PR against an upstream repo.
#   ./scripts/push_sync.sh "commit message"
# Optional env vars: UPSTREAM_REPO=owner/name  PR_HEAD=user:branch
set -euo pipefail
MSG="${1:-Update bot modules and sync deployment}"
git add -A
git commit -m "$MSG" || true
git push origin HEAD
if [ -n "${UPSTREAM_REPO:-}" ] && [ -n "${PR_HEAD:-}" ] && command -v gh >/dev/null; then
  gh pr create --repo "$UPSTREAM_REPO" --base main --head "$PR_HEAD" --title "$MSG" \
    --body "Automated sync: $MSG" || echo "PR already open - it updates automatically."
fi
