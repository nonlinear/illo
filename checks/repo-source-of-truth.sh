#!/usr/bin/env bash
# illo.repo.source-of-truth @ 1.0.0
# predicate: the file the server returns is byte-identical to the file on disk
# This is the check that catches the lie: "the folder is the product". If the
# server serves a cached/different copy, editing the folder is NOT publishing,
# and every other conclusion in this repo is built on sand.
set -uo pipefail
REPO="${1:?repo}"
disk="$REPO/index.html"
live=$(curl -s --max-time 5 http://127.0.0.1:3003/ 2>/dev/null)
if [ -z "$live" ]; then
  echo "FAILURE_TYPE: ENVIRONMENT"
  echo "could not fetch the served app"
  exit 1
fi
# Compare a hash of the CONTENT, not a byte count. `$(...)` strips trailing
# newlines, so a byte count is off by one on any file ending in a newline — a
# check that fails on a correct repo is worse than no check (kin P09E092 §3.3).
h_disk=$(shasum -a 256 < "$disk" | cut -d' ' -f1)
h_live=$(printf '%s' "$live" | shasum -a 256 | cut -d' ' -f1)
# normalise: hash the served text without its trailing newline too
if [ "$h_disk" != "$h_live" ]; then
  # tolerate exactly one trailing newline difference, nothing else
  h_disk2=$(printf '%s' "$(cat "$disk")" | shasum -a 256 | cut -d' ' -f1)
  if [ "$h_disk2" != "$h_live" ]; then
    echo "FAILURE_TYPE: ASSERTION"
    echo "served content != disk content (disk $h_disk2, live $h_live)"
    echo "— the folder is not what the site serves"
    exit 1
  fi
fi
# strong identity: a signature line that only exists in the current file
sig=$(grep -c "PEN ONLY (owner, 2026-10-27)" "$disk" || true)
if [ "$sig" -gt 0 ]; then
  printf '%s' "$live" | grep -q "PEN ONLY (owner, 2026-10-27)" || {
    echo "FAILURE_TYPE: ASSERTION"
    echo "disk has the pen-only gate, the served copy does not — serving a stale file"
    exit 1
  }
fi
echo "served copy == disk copy ($h_disk bytes)"
