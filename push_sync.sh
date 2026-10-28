#!/data/data/com.termux/files/usr/bin/bash
MSG="${1:-Update bot modules and sync deployment}"
git add -A
git commit -m "$MSG" || true
git fetch https://github.com/LokiTheGodofLies/mastermind.git main
git merge FETCH_HEAD --strategy-option=ours --no-edit || true
git push -f origin main
gh pr create --repo LokiTheGodofLies/mastermind \
  --base main \
  --head mastermindmayankofficial:main \
  --title "$MSG" \
  --body "Automated sync from Termux: $MSG" || echo "ℹ️ PR already open and updated automatically with new commits!"
