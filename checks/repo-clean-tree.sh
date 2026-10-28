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
#
# v1.0.2 — comparing against HEAD:index.html, ALWAYS, made the commit trigger
# refuse every commit that touched the app. At `git commit` time HEAD is stale by
# definition: the staged bytes are not in HEAD until the commit exists, and the
# commit cannot exist if the hook fails. The check blocked its own precondition.
# Two sessions in a row worked around it by committing with --no-verify, which
# means the battery never ran -- a check that forces people to disable the
# harness is worse than no check.
#
# The property does not change: "the bytes the server serves correspond to
# something git knows about". It only learns WHICH overlap to compare:
#   pre-commit  -> the INDEX is the commit being made. index vs disk is the
#                  question ("is what I am about to commit what is live?").
#   any other   -> HEAD, as before ("is what is live committed?").
set -uo pipefail
REPO="${1:?repo}"
TRIGGER="${2:-all}"
F="$REPO/index.html"

if ! git -C "$REPO" rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "no HEAD yet — nothing to compare against"
  exit 0
fi

if [ "$TRIGGER" = "commit" ]; then
  base="index"
  base_hash=$(git -C "$REPO" rev-parse ":index.html" 2>/dev/null || echo none)
else
  base="HEAD"
  base_hash=$(git -C "$REPO" rev-parse "HEAD:index.html" 2>/dev/null || echo none)
fi
disk_hash=$(git -C "$REPO" hash-object "$F" 2>/dev/null || echo none)

if [ "$base_hash" = "none" ]; then
  echo "index.html is not in $base — nothing to compare"
  exit 0
fi

if [ "$base_hash" != "$disk_hash" ]; then
  echo "FAILURE_TYPE: ASSERTION"
  echo "the app on disk differs from $base:index.html."
  echo "  $base:index.html  $base_hash"
  echo "  working file          $disk_hash"
  echo
  if [ "$base" = "index" ]; then
    echo "The disk has bytes that this commit would NOT record. Stage them, or the"
    echo "live app is not the app git is about to know."
  else
    echo "Editing is publishing: those uncommitted bytes are already live, and no"
    echo "check has seen them. Commit them (this hook will verify them first)."
  fi
  echo "Difference:"
  if [ "$base" = "index" ]; then
    git -C "$REPO" diff --stat -- index.html | sed 's/^/  /'
  else
    git -C "$REPO" diff --stat HEAD -- index.html | sed 's/^/  /'
  fi
  exit 1
fi
echo "app on disk == $base:index.html ($disk_hash)"
