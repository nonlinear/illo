#!/usr/bin/env bash
# Illo check harness — Trigger → Checks → Evidence → Verdict
#
# Model imported from kin/epics/P09E092/anatomy-of-checks.md (frozen 2026-10-07).
# Nouns: Check (versioned property) · Trigger (what summons) · Checkpoint (dated
# execution) · Evidence (what it left). Fields: applicable · executed · verdict.
#
# Usage:
#   checks/run.sh commit     the git pre-commit trigger
#   checks/run.sh all        every check, regardless of applicability
#   checks/run.sh status     print the last checkpoint
#
# Exit: 0 = RELEASEABLE, 1 = BLOCKED, 2 = INCOMPLETE, 3 = ENVIRONMENT_UNAVAILABLE
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKS="$REPO/checks"
OUT="$CHECKS/checkpoints"
TRIGGER="${1:-all}"

# `status` must not create a checkpoint — it only reads. Before this guard it made
# its own empty directory and then found it, so it always reported "no checkpoint".
if [ "$TRIGGER" = "status" ]; then
  last=$(ls -1d "$OUT"/*/ 2>/dev/null | grep -v -- '-status/$' | tail -1)
  if [ -n "$last" ] && [ -f "$last/checkpoint.md" ]; then
    cat "$last/checkpoint.md"
  else
    echo "no checkpoint yet"
  fi
  exit 0
fi

STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
CKPT="$OUT/$STAMP-$TRIGGER"
mkdir -p "$CKPT/evidence"

# ---------------------------------------------------------------- applicable
# Applicability by context, never by cost (anatomy §1, invariant).
changed=""
if [ "$TRIGGER" = "commit" ]; then
  changed=$(git -C "$REPO" diff --cached --name-only 2>/dev/null)
else
  changed=$(git -C "$REPO" ls-files 2>/dev/null)
fi

APP_LIST=""
harness_changed=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    index.html|vault.html)
      case " $APP_LIST " in *" app "*) ;; *) APP_LIST="$APP_LIST app" ;; esac ;;
    manifest.webmanifest|icon-*.png|apple-touch-icon.png|illo-icon.svg|illo-icon.png)
      case " $APP_LIST " in *" pwa "*) ;; *) APP_LIST="$APP_LIST pwa" ;; esac ;;
    probe.html)
      case " $APP_LIST " in *" probe "*) ;; *) APP_LIST="$APP_LIST probe" ;; esac ;;
    checks/*) harness_changed=1 ;;
  esac
done <<< "$changed"

# A changed harness lies about every other check (anatomy §4.1). If checks/ moved,
# the whole battery must re-prove itself against the current code, not just the
# harness's own shape.
if [ "$harness_changed" = "1" ]; then
  APP_LIST=" app pwa probe"
fi
APP_UNIQ="${APP_LIST# }"

# ------------------------------------------------------------------- runner
declare -a EXEC=()
declare -a FAILED=()
declare -a NOTRUN=()
BLOCKED=0
INCOMPLETE=0

# run_check <id> <applicable:0|1> <cmd...>
run_check() {
  local id="$1"; shift
  local app="$1"; shift
  if [ "$app" != "1" ]; then
    NOTRUN+=("$id|not applicable to this context")
    EXEC+=("| $id | NOT RUN | — | não aplicável (mudança não toca esta superfície) |")
    return 0
  fi
  local log="$CKPT/evidence/${id}.log"
  if "$@" > "$log" 2>&1; then
    EXEC+=("| $id | PASS | $(wc -c < "$log" | tr -d ' ')B | $(tail -1 "$log" | cut -c1-70) |")
  else
    local rc=$?
    # A FAIL must carry a failure_type (§3.3). Absent one -> ERROR, never FAIL.
    local ftype="ASSERTION"
    if grep -q "^FAILURE_TYPE:" "$log" 2>/dev/null; then
      ftype=$(grep "^FAILURE_TYPE:" "$log" | head -1 | cut -d: -f2- | tr -d ' ')
    fi
    if [ "$ftype" = "ENVIRONMENT" ]; then
      EXEC+=("| $id | ENVIRONMENT_BLOCKED | $(wc -c < "$log" | tr -d ' ')B | $ftype |")
    else
      EXEC+=("| $id | FAIL | $(wc -c < "$log" | tr -d ' ')B | failure_type=$ftype · rc=$rc |")
      FAILED+=("$id ($ftype)")
      BLOCKED=1
    fi
  fi
}

has() { case " $APP_UNIQ " in *" $1 "*) echo 1;; *) echo 0;; esac; }

# illo.repo.* — ALWAYS applicable: the contract invariants
run_check illo.repo.clean-tree 1 bash "$CHECKS/repo-clean-tree.sh" "$REPO"
run_check illo.repo.no-network 1 bash "$CHECKS/repo-no-network.sh" "$REPO"
run_check illo.repo.serving    1 bash "$CHECKS/repo-serving.sh"
run_check illo.repo.source     1 bash "$CHECKS/repo-source-of-truth.sh" "$REPO"

# illo.app.* — the surface the user touches
run_check illo.app.syntax        "$(has app)" bash "$CHECKS/app-syntax.sh" "$REPO"
run_check illo.app.erase         "$(has app)" bash "$CHECKS/app-erase.sh" "$REPO"
run_check illo.app.erasers       "$(has app)" bash "$CHECKS/app-erasers.sh" "$REPO"
run_check illo.app.pen-only      "$(has app)" bash "$CHECKS/app-pen-only.sh" "$REPO"
run_check illo.app.no-phantom-writes "$(has app)" bash "$CHECKS/app-no-phantom-writes.sh" "$REPO"

# illo.pwa.* — the surface the operating system touches
run_check illo.pwa.icons         "$(has pwa)" bash "$CHECKS/pwa-icons.sh" "$REPO"
run_check illo.pwa.manifest      "$(has pwa)" bash "$CHECKS/pwa-manifest.sh" "$REPO"

# illo.probe.* — an instrument that lies is worse than none
run_check illo.probe.verdict     "$(has probe)" bash "$CHECKS/probe-verdict.sh" "$REPO"

# illo.harness.* — a broken check lies about every other check
run_check illo.harness.self     "$harness_changed" bash "$CHECKS/harness-self.sh" "$REPO"

# ------------------------------------------------------------------- verdict
# Computed over mandatory ∩ applicable. "No FAIL" alone is NOT a verdict (§4.2).
if   [ "$BLOCKED" = "1" ]; then VERDICT="BLOCKED"
elif [ "$INCOMPLETE" = "1" ]; then VERDICT="INCOMPLETE"
else VERDICT="RELEASEABLE"; fi

GIT_COMMIT=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo none)
DIRTY=$(git -C "$REPO" status --porcelain 2>/dev/null | wc -l | tr -d ' ')

{
  echo "# Checkpoint — $STAMP UTC"
  echo
  echo "| | |"
  echo "|---|---|"
  echo "| trigger | \`$TRIGGER\` |"
  echo "| repo | \`$REPO\` |"
  echo "| git_commit | \`$GIT_COMMIT\` |"
  echo "| working_tree | \`$([ "$DIRTY" = "0" ] && echo clean || echo "$DIRTY files dirty")\` |"
  appl="${APP_UNIQ:-none}"; [ "$harness_changed" = "1" ] && appl="$appl harness"
  echo "| applicable | \`$appl\` + illo.repo.* |"
  echo "| verdict | **$VERDICT** |"
  echo
  echo "## executed"
  echo
  echo "| check | status | evidence | note |"
  echo "|---|---|---|---|"
  printf '%s\n' "${EXEC[@]}"
  echo
  if [ ${#FAILED[@]} -gt 0 ]; then
    echo "## failed"
    echo
    printf -- '- `%s`\n' "${FAILED[@]}"
    echo
  fi
  if [ ${#NOTRUN[@]} -gt 0 ]; then
    echo "## not applicable"
    echo
    echo "> Not applicable ≠ not executed. These do not count against RELEASEABLE (§4.2)."
    echo
    for n in "${NOTRUN[@]}"; do
      echo "- \`${n%%|*}\` — ${n#*|}"
    done
  fi
} > "$CKPT/checkpoint.md"

cat "$CKPT/checkpoint.md"

case "$VERDICT" in
  RELEASEABLE) exit 0 ;;
  BLOCKED) exit 1 ;;
  INCOMPLETE) exit 2 ;;
  *) exit 3 ;;
esac
