#!/usr/bin/env bash
# illo.repo.clean-tree @ 1.0.1
# predicate: nothing is live that has not been committed
#
# v1.0.0 was wrong and blocked every honest commit. It read `git status
# --porcelain`, which during a pre-commit hook is FULL of the files being
# committed — staged additions and the staged modification itself. The check
# fired on the very act it was meant to permit.
#
# The property is not "the tree is empty". It is: "the bytes the server is
# serving correspond to something git knows about". That is what makes editing
# safe to call publishing. So compare the served bytes against the COMMITTED
# blob of index.html, ignoring the index entirely.
#
# Consequence, deliberately: a save that is not committed yet cannot make this
# check pass, because HEAD does not contain those bytes. The window between
# saving and committing is exactly the flakiness the owner named, and this is
# the only place it can be seen.
set -uo pipefail
REPO="${1:?repo}"
F="$REPO/index.html"

if ! git -C "$REPO" rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "no HEAD yet — nothing to compare against"
  exit 0
fi

# bytes git has committed for this path, and bytes the working file holds
head_hash=$(git -C "$REPO" rev-parse "HEAD:index.html" 2>/dev/null || echo none)
disk_hash=$(git -C "$REPO" hash-object "$F" 2>/dev/null || echo none)

if [ "$head_hash" = "none" ]; then
  echo "index.html is not in HEAD — first commit, nothing to compare"
  exit 0
fi

if [ "$head_hash" != "$disk_hash" ]; then
  echo "FAILURE_TYPE: ASSERTION"
  echo "the app on disk differs from the last commit."
  echo "  HEAD:index.html  $head_hash"
  echo "  working file     $disk_hash"
  echo
  echo "Editing is publishing: those uncommitted bytes are already live, and no"
  echo "check has seen them. Commit them (this hook will verify them first)."
  echo "Difference:"
  git -C "$REPO" diff --stat HEAD -- index.html | sed 's/^/  /'
  exit 1
fi
echo "app on disk == app in HEAD ($disk_hash)"
