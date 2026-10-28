#!/usr/bin/env bash
# illo.harness.self @ 1.0.0
# predicate: every check script is executable and none can pass unconditionally
# "A check that cannot fail is not a check" (kin P09E092, two real incidents).
# Cheap structural read: any script whose body has no exit 1 path cannot fail.
set -uo pipefail
REPO="${1:?repo}"
DIR="$REPO/checks"
bad=""
for f in "$DIR"/*.sh; do
  b=$(basename "$f")
  [ "$b" = "run.sh" ] && continue
  [ -x "$f" ] || bad="$bad\n  $b: not executable"
  # "has exit 1" is a shallow test: the python-backed checks exit 1 from inside
  # sys.exit(1). Look for either form, and for a FAILURE_TYPE declaration, which
  # is the anatomy's hard requirement for any FAIL.
  if ! grep -q "exit 1" "$f" && ! grep -qF "exit(1)" "$f"; then
    bad="$bad\n  $b: no failure path (a check that cannot fail is not a check)"
  fi
  if ! grep -q "FAILURE_TYPE" "$f"; then
    bad="$bad\n  $b: no FAILURE_TYPE — a FAIL without an error class is a guess"
  fi
done
if [ -n "$bad" ]; then
  echo "FAILURE_TYPE: ASSERTION"
  printf "$bad\n"
  exit 1
fi
n=$(ls -1 "$DIR"/*.sh | grep -v run.sh | wc -l | tr -d ' ')
echo "$n check scripts, all executable, all have a failure path"
