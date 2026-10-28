#!/usr/bin/env bash
# illo.repo.no-network @ 1.0.0
# predicate: index.html makes zero network requests
# AGENTS.md: "A pull request that adds a network call to index.html is rejected,
# however small." This check is what makes that sentence real instead of aspirational.
set -uo pipefail
REPO="${1:?repo}"
F="$REPO/index.html"
hits=$(grep -nE "fetch\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|<script[^>]+src=|navigator\.serviceWorker\.register|new Worker\(" "$F" | grep -v '^\s*//' || true)
if [ -n "$hits" ]; then
  echo "FAILURE_TYPE: ASSERTION"
  echo "index.html must make zero network requests. Found:"
  echo "$hits"
  exit 1
fi
echo "zero network calls in index.html"
