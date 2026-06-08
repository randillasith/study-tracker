#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

REMOTE="${1:-origin}"
BRANCH="${2:-main}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not inside a git repository" >&2
  exit 1
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "Remote '$REMOTE' not found" >&2
  exit 1
fi

# Never upload ignored runtime files such as .env, .venv, data/, or *.db.
git add -A

if ! git diff --cached --quiet; then
  git commit -m "Update Study Tracker implementation"
else
  echo "No local changes to commit."
fi

git push -u "$REMOTE" "$BRANCH"
