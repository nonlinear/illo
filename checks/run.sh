#!/usr/bin/env bash
# Illo checkpoint runner — entry point. The runner is Python; this keeps the name that the
# hook and the docs already use, and makes the language explicit (a .py file executed as
# bash is exactly the kind of silent breakage this harness exists to catch).
#
#   checks/run.sh commit     the git pre-commit trigger (applicable set only)
#   checks/run.sh all        every check regardless of applicability
#   checks/run.sh status     print the last checkpoint
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/checks/run.py" "$@"
