#!/usr/bin/env python3
"""illo checkpoint runner — the Kin P09E092 pattern, implemented for Illo.

Kin's chain, adopted whole (epics/P09E092: anatomy → check → checkpoint → evidence → trigger):

  checks/definitions/**/*.yaml   the CHECK      a versioned property, reusable, no epic, no round
  checks/run.sh <trigger>        the TRIGGER    why verify now? writes one CHECKPOINT
  epics/P22E021/checkpoints/     the EXECUTION  manifest.yaml + results.json + evidence/<check-id>/

Two names for two things, never interchanged (Backstage N001):
  status  — one check, one execution:  PASS | FAIL | NOT RUN | ENVIRONMENT BLOCKED
  verdict — the aggregate:             RELEASEABLE | BLOCKED | INCOMPLETE | ENVIRONMENT_UNAVAILABLE

Invariants enforced here, not documented and hoped for:
  · NOT RUN and ENVIRONMENT BLOCKED never become PASS
  · FAIL iff failure_type is present (no failure_type → ERROR, never FAIL)
  · a checkpoint records WHICH checks and WHICH versions ran — never "the battery passed"
  · an execution is never overwritten; a re-run is a new checkpoint

Usage:
  checks/run.sh commit      the git pre-commit trigger (applicable set only)
  checks/run.sh all         every check regardless of applicability
  checks/run.sh status      print the last checkpoint (read-only; creates nothing)
Exit: 0 RELEASEABLE · 1 BLOCKED · 2 INCOMPLETE · 3 ENVIRONMENT_UNAVAILABLE
"""
import json, os, re, subprocess, sys, time, pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
CHECKS = REPO / "checks"
DEFS = CHECKS / "definitions"
# Kin checkpoint-contract §7: definitions in the codebase, executions in the epic.
EPIC = pathlib.Path.home() / ".openclaw/agents/illo/epics/P22E021"
CKPTS = EPIC / "checkpoints"

TRIGGER = sys.argv[1] if len(sys.argv) > 1 else "all"


# --------------------------------------------------------------------------- status
def last_checkpoint():
    if not CKPTS.exists():
        return None
    runs = sorted([p for p in CKPTS.iterdir() if p.is_dir()], key=lambda p: p.name)
    return runs[-1] if runs else None


if TRIGGER == "status":
    c = last_checkpoint()
    if not c:
        print("no checkpoint yet")
        sys.exit(0)
    m = c / "manifest.yaml"
    print(m.read_text() if m.exists() else "checkpoint has no manifest")
    sys.exit(0)


# --------------------------------------------------------------------------- yaml
def read_yaml(path):
    """A deliberately small reader: these definitions use only top-level scalars, a
    `required:` list, and a `failure_classification:` block. A real YAML parser would be
    a dependency, and the repo's promise is "no dependencies, put it on a USB stick".
    If a definition ever needs more than this, that is a signal to reconsider the shape."""
    out, section = {}, None
    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")) and ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if v == "":
                section = k
                out.setdefault(k, [] if k in ("preconditions", "depends_on") else {})
            else:
                out[k] = v.strip('"\'')
                section = None
        elif line.startswith("  ") and section:
            # nested keys (context.requires handled via its own list form)
            s = line.strip()
            if ":" in s:
                k, _, v = s.partition(":")
                out[section][k.strip()] = v.strip().strip('"\'')
            elif s.startswith("- "):
                out[section].append(s[2:].strip().strip('"\'') if isinstance(out[section], list) else {})
    return out


def load_checks():
    checks = []
    for f in sorted(DEFS.rglob("*.yaml")):
        d = read_yaml(f)
        d["_file"] = str(f)
        checks.append(d)
    return checks


# --------------------------------------------------------------------------- verdict
STATUSES = ("PASS", "FAIL", "NOT RUN", "ENVIRONMENT BLOCKED")


def run_check(c):
    """Execute one check. Returns (status, failure_type, reason, stdout, elapsed_ms)."""
    runner = c.get("runner")
    script = REPO / runner if runner else None
    if not script or not script.exists():
        return ("NOT RUN", "", "runner %s not found" % runner, "", 0)
    t0 = time.time()
    try:
        # THE RUNNER MUST KNOW WHY IT IS RUNNING. repo-clean-tree compares against the
        # INDEX on a commit and against HEAD otherwise; it asks for the trigger as $2.
        # run.py never passed it, so the check always took the HEAD branch -- and at
        # pre-commit HEAD is stale by definition, so it failed every honest commit. Two
        # sessions then committed with --no-verify to get past it, which means the battery
        # did not run at all. A harness that forces itself to be disabled is not a harness;
        # the argument was missing, and one word fixes it.
        p = subprocess.run(["bash", str(script), str(REPO), TRIGGER],
                           capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return ("FAIL", "INFRASTRUCTURE", "timed out after 180s", "", 180000)
    ms = int((time.time() - t0) * 1000)
    out = (p.stdout or "") + (p.stderr or "")
    # Kin: FAIL iff failure_type is present. No failure_type → ERROR, never FAIL.
    ft = ""
    for line in out.splitlines():
        if line.startswith("FAILURE_TYPE:"):
            ft = line.split(":", 1)[1].strip()
            break
    if p.returncode == 0:
        return ("PASS", "", (out.strip().splitlines() or ["ok"])[-1][:160], out, ms)
    if ft == "ENVIRONMENT":
        return ("ENVIRONMENT BLOCKED", ft, "environment could not be established: " + out.strip()[-160:], out, ms)
    if ft:
        return ("FAIL", ft, out.strip().splitlines()[-1][:160] if out.strip() else "assertion failed", out, ms)
    return ("FAIL", "INFRASTRUCTURE", "no failure_type emitted (INCOMPLETE evidence)", out, ms)


# --------------------------------------------------------------------------- applicability
def changed_files():
    if TRIGGER == "commit":
        p = subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--name-only"],
                           capture_output=True, text=True)
        return [f for f in p.stdout.split() if f]
    p = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True)
    return [f for f in p.stdout.split() if f]


def applicable_sets(files):
    """Context from the change, never from cost. Kin Anatomy §1."""
    app, pwa, probe, harness = False, False, False, False
    for f in files:
        if f == "index.html":
            app = True
        elif f.startswith("checks/") or f == ".erase-test.mjs":
            harness = True
        elif f.startswith("icon-") or f in ("manifest.webmanifest", "apple-touch-icon.png"):
            pwa = True
        elif f == "probe.html":
            probe = True
    if harness:
        # a changed harness lies about every other check (Anatomy §4.1)
        app = pwa = probe = True
    surf = set()
    if app:
        surf |= {"app", "sim", "repo"}
    if pwa:
        surf |= {"pwa", "repo"}
    if probe:
        surf |= {"probe", "repo"}
    if harness:
        surf.add("harness")
    return surf


def relevant(c, surfaces, all_mode):
    # A retired check is history, not an obligation (Kin lifecycle: disabled).
    if c.get("lifecycle") == "disabled":
        return False
    if all_mode:
        return True
    ns = (c.get("id") or "").split(".")
    surface = ns[1] if len(ns) > 1 else ""
    return surface in surfaces


# --------------------------------------------------------------------------- main
def main():
    all_mode = TRIGGER in ("all",)
    files = changed_files()
    surfaces = applicable_sets(files)
    checks = load_checks()
    applicable = [c for c in checks if relevant(c, surfaces, all_mode)]

    stamp = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
    ckpt_id = "P22E021-" + stamp + "-" + TRIGGER
    cdir = CKPTS / ckpt_id
    (cdir / "evidence").mkdir(parents=True, exist_ok=True)

    results, executed = [], []
    blocked = incomplete = env_blocked = False

    for c in applicable:
        cid = c.get("id", "unknown")
        status, ft, reason, out, ms = run_check(c)
        results.append({"id": cid, "version": c.get("version", "0.0.0"),
                        "status": status, "failure_type": ft, "reason": reason,
                        "elapsed_ms": ms})
        executed.append((cid, c.get("version", "0.0.0"), status))
        # Kin check-contract §8.3: an unexercised property is not a proven property.
        if status == "FAIL":
            blocked = True
        elif status == "ENVIRONMENT BLOCKED":
            env_blocked = True
        elif status == "NOT RUN":
            incomplete = True
        # evidence, first-class output (§10)
        ev = cdir / "evidence" / cid
        ev.mkdir(parents=True, exist_ok=True)
        (ev / "stdout.log").write_text(out)
        (ev / "result.json").write_text(json.dumps(
            {"id": cid, "version": c.get("version"), "status": status,
             "failure_type": ft, "reason": reason, "elapsed_ms": ms}, indent=2))
        if "env.json" in str(c.get("evidence", "")):
            (ev / "env.json").write_text(json.dumps(
                {"trigger": TRIGGER, "python": sys.version.split()[0]}, indent=2))

    if blocked:
        verdict = "BLOCKED"
    elif incomplete:
        verdict = "INCOMPLETE"
    elif env_blocked:
        verdict = "ENVIRONMENT_UNAVAILABLE"
    else:
        verdict = "RELEASEABLE"

    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()

    (cdir / "results.json").write_text(json.dumps(
        {"checkpoint_id": ckpt_id, "checks": results}, indent=2))
    (cdir / "manifest.yaml").write_text(
        "checkpoint_id: %s\n"
        "epic: P22E021\n"
        "trigger: %s\n"
        "context: %s\n"
        "artifact: { git_commit: %s, dirty: %s }\n"
        "applicable:\n%s\n"
        "executed:\n%s\n"
        "verdict: %s\n" % (
            ckpt_id, TRIGGER, ",".join(sorted(surfaces)) or "none",
            head or "none", "true" if dirty else "false",
            "\n".join("  - { id: %s, version: %s }" % (c.get("id"), c.get("version"))
                      for c in applicable),
            "\n".join("  - { id: %s, version: %s, status: %s }" % e for e in executed),
            verdict))

    # human summary — a table is a rendering of the checkpoint, never a substitute for it
    print("checkpoint: %s" % ckpt_id)
    print("trigger:    %s   context: %s" % (TRIGGER, ",".join(sorted(surfaces)) or "none"))
    print("verdict:    %s\n" % verdict)
    print("%-34s %-8s %-18s %s" % ("check", "version", "status", "reason"))
    print("-" * 96)
    for r in results:
        print("%-34s %-8s %-18s %s" % (r["id"], r["version"], r["status"],
                                       (r["failure_type"] + " " if r["failure_type"] else "") + r["reason"][:44]))
    fails = [r for r in results if r["status"] in ("FAIL", "NOT RUN", "ENVIRONMENT BLOCKED")]
    if fails:
        print("\n## not passing — verdict %s" % verdict)
        for r in fails:
            print("- `%s` %s (%s)" % (r["id"], r["status"], r["failure_type"] or r["reason"][:60]))
    print("\ncheckpoint on disk: %s" % cdir)

    return {"RELEASEABLE": 0, "BLOCKED": 1, "INCOMPLETE": 2}.get(verdict, 3)


if __name__ == "__main__":
    sys.exit(main())
