#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Isolated replay harness for the paper's confirmatory numbers.

WHY THIS EXISTS
---------------
The confirmatory runners are one-shot by design. Their seed blocks are burned,
their locks must never be deleted, and their result files are the paper's
primary evidence. A reproducer who simply runs them can destroy exactly the
artifacts that make the results checkable.

The hazard is not hypothetical. `final_confirm.py` (Experiment 025) has **no**
one-shot guard: `--final` opens `final_confirm_result.txt` in write mode and
silently overwrites the paper's primary result. `final_027.py`, `final_028.py`
and `final_029.py` do guard themselves; 025 does not.

WHAT MAKES REPLAY POSSIBLE
--------------------------
In every runner, `--final` controls only three things: which seed block is used,
the banner text, and which filename the output goes to. The simulation itself is
identical. So the burned block can be re-simulated by passing its seeds
explicitly in non-final mode -- same model, same seeds, same numbers, different
output file.

This harness does that, and adds the protection the runners lack:

  1. hashes every protected artifact before running
  2. refuses to pass --final to anything, ever
  3. backs up the scratch output file the runner is about to clobber
  4. runs the experiment
  5. moves the fresh output into replay_out/ and restores the backup
  6. re-hashes everything and hard-fails if a single byte moved

Step 6 is the point. If this harness ever reports a changed artifact, treat the
working tree as contaminated and re-clone.

WHAT IT DOES NOT DO
-------------------
It does not shorten anything. Replaying Experiment 025 at full size means
simulating 1500 seeds and takes hours. Use --n to replay a prefix of the block
for a faster directional check, but note rule 34: the ratio estimator is biased
upward at small N, so a small-N replay reproduces direction, not the number.

USAGE
-----
    python tools/replay_paper_results.py --list
    python tools/replay_paper_results.py 025 --n 100      # quick, direction only
    python tools/replay_paper_results.py 025              # full, hours
    python tools/replay_paper_results.py 029
    python tools/replay_paper_results.py --verify-only    # just the integrity scan
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPLAY_DIR = os.path.join(ROOT, "replay_out")


# --------------------------------------------------------------------------
# Experiment registry
# --------------------------------------------------------------------------
# scratch: the file the runner writes in non-final mode (will be preserved)
# recorded: the historical result this replay should be compared against

EXPERIMENTS = {
    "025": dict(
        name="Persistence final confirmation",
        runner="final_confirm.py",
        args=["--seed0", "50000", "--n", "{n}"],
        default_n=1500,
        scratch="final_confirm_debug.txt",
        recorded="final_confirm_result.txt",
        note="Seeds 50000-51499. The runner has NO one-shot guard; never pass --final.",
        hours="~1.5 h at full N",
    ),
    "027": dict(
        name="Narrow trait interface, new-task transfer",
        runner="final_027.py",
        args=["--seed0", "60000", "--n", "{n}"],
        default_n=1500,
        scratch="final_027_rehearsal.txt",
        recorded="final_027_result.txt",
        note="Seeds 60000-61499, burned. The runner refuses --final once the result exists.",
        hours="~1 h at full N",
    ),
    "028": dict(
        name="Widened trait readout at fixed coupling budget",
        runner="final_028.py",
        args=["--seed0", "70000", "--n", "{n}"],
        default_n=1500,
        scratch="final_028_rehearsal.txt",
        recorded="final_028_result.txt",
        note="Seeds 70000-71499, burned. Lock file present; --final is refused.",
        hours="~1 h at full N",
    ),
    "029": dict(
        name="Relational-memory transfer",
        runner="final_029.py",
        args=["--rehearse"],
        default_n=None,                     # --rehearse fixes its own size
        scratch="final_029_rehearsal_result.txt",
        recorded="final_029_result.txt",
        note=("Seeds 80000-81499, burned; STARTED.lock present and must never be "
              "deleted. --rehearse replays at full size on an already-burned "
              "development block, which is the only supported mode."),
        hours="~1.5 h",
    ),
}


# --------------------------------------------------------------------------
# Integrity scanning
# --------------------------------------------------------------------------

PROTECTED_DIRS = ["v2_frozen", "v3_frozen", "docs"]
PROTECTED_SUFFIXES = (".lock",)
PROTECTED_NAMES = {
    "final_confirm_result.txt", "final_confirm_result.VOID_bug.txt",
    "final_027_result.txt", "final_028_result.txt", "final_029_result.txt",
    "final_027_rehearsal.txt", "final_028_rehearsal.txt",
    "final_029_rehearsal_result.txt", "final_confirm_debug.txt",
    "interface028_frozen.json",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def protected_files():
    out = []
    for name in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, name)
        if os.path.isfile(p) and (name in PROTECTED_NAMES
                                  or name.endswith(PROTECTED_SUFFIXES)
                                  or name.endswith("_console.txt")
                                  or name.endswith("_console_rehearsal.txt")):
            out.append(p)
    for d in PROTECTED_DIRS:
        dp = os.path.join(ROOT, d)
        if not os.path.isdir(dp):
            continue
        for name in sorted(os.listdir(dp)):
            p = os.path.join(dp, name)
            if os.path.isfile(p):
                out.append(p)
    return out


def snapshot():
    return {p: sha256(p) for p in protected_files()}


def diff_snapshot(before, after):
    changed, removed, added = [], [], []
    for p, h in before.items():
        if p not in after:
            removed.append(p)
        elif after[p] != h:
            changed.append(p)
    for p in after:
        if p not in before:
            added.append(p)
    return changed, removed, added


def report_integrity(before, after):
    changed, removed, added = diff_snapshot(before, after)
    rel = lambda p: os.path.relpath(p, ROOT)
    if not (changed or removed):
        print(f"  [OK] {len(before)} protected artifacts unchanged")
        if added:
            print(f"  [note] {len(added)} new file(s): "
                  + ", ".join(rel(p) for p in added[:4]))
        return True
    print("\n" + "!" * 74)
    print("  PROTECTED ARTIFACT MODIFIED -- the working tree is contaminated.")
    print("  Do not publish anything from this tree. Re-clone before continuing.")
    print("!" * 74)
    for p in changed:
        print(f"    CHANGED  {rel(p)}")
    for p in removed:
        print(f"    REMOVED  {rel(p)}")
    return False


# --------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------

def run_experiment(key, n, workers, dry_run):
    spec = EXPERIMENTS[key]
    runner = os.path.join(ROOT, spec["runner"])
    if not os.path.isfile(runner):
        print(f"missing runner: {spec['runner']}")
        return 2

    args = [a.format(n=n) for a in spec["args"] if not (a == "{n}" and n is None)]
    if spec["default_n"] is None:
        args = list(spec["args"])
    if workers and spec["default_n"] is not None:
        args += ["--workers", str(workers)]

    cmd = [sys.executable, runner] + args
    if "--final" in cmd:
        raise SystemExit("refusing to run: --final must never be passed by this harness")

    print(f"Experiment {key}  --  {spec['name']}")
    print(f"  {spec['note']}")
    print(f"  command : {' '.join(os.path.basename(c) for c in cmd)}")
    print(f"  estimate: {spec['hours']}")
    if n is not None and spec["default_n"] and n < spec["default_n"]:
        print(f"  ⚠ N={n} < {spec['default_n']}: rule 34 -- the ratio estimator is biased")
        print(f"    upward at small N. This replay shows DIRECTION, not the paper's number.")
    print()

    if dry_run:
        print("  [dry run] nothing executed")
        return 0

    os.makedirs(REPLAY_DIR, exist_ok=True)
    scratch = os.path.join(ROOT, spec["scratch"])
    backup = scratch + ".replay-backup"
    had_scratch = os.path.isfile(scratch)
    if had_scratch:
        shutil.copy2(scratch, backup)
        print(f"  preserved existing {spec['scratch']}")

    before = snapshot()
    print(f"  hashed {len(before)} protected artifacts\n")

    t0 = time.time()
    env = dict(os.environ, PYTHONUTF8="1")
    rc = subprocess.call(cmd, cwd=ROOT, env=env)
    mins = (time.time() - t0) / 60
    print(f"\n  runner exit={rc}  ({mins:.1f} min)")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    saved = None
    if os.path.isfile(scratch):
        saved = os.path.join(REPLAY_DIR, f"{key}_replay_{stamp}_{spec['scratch']}")
        shutil.copy2(scratch, saved)
    if had_scratch:
        shutil.copy2(backup, scratch)
        os.remove(backup)
        print(f"  restored original {spec['scratch']}")
    elif os.path.isfile(scratch):
        os.remove(scratch)

    print("\nIntegrity re-scan:")
    ok = report_integrity(before, snapshot())

    if saved:
        print(f"\n  replay output: {os.path.relpath(saved, ROOT)}")
        print(f"  compare against: {spec['recorded']}")
    return 0 if (ok and rc == 0) else 1


def main():
    ap = argparse.ArgumentParser(
        description="Replay confirmatory experiments without touching burned artifacts.")
    ap.add_argument("experiment", nargs="?", choices=sorted(EXPERIMENTS),
                    help="which experiment to replay")
    ap.add_argument("--n", type=int, default=None,
                    help="replay only the first N seeds of the block (direction only)")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--list", action="store_true", help="list experiments and exit")
    ap.add_argument("--verify-only", action="store_true",
                    help="scan protected artifacts and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would run without running it")
    a = ap.parse_args()

    if a.list:
        print(f"{'key':<6} {'runner':<20} {'seeds / mode':<22} experiment")
        for k, s in sorted(EXPERIMENTS.items()):
            mode = " ".join(x for x in s["args"] if not x.startswith("--n"))
            mode = mode.replace("--seed0 ", "").replace(" {n}", "")
            print(f"{k:<6} {s['runner']:<20} {mode:<22} {s['name']}")
        return 0

    if a.verify_only:
        files = protected_files()
        print(f"protected artifacts: {len(files)}")
        for p in files:
            print(f"  {sha256(p)[:16]}  {os.path.relpath(p, ROOT)}")
        return 0

    if not a.experiment:
        ap.print_help()
        return 2

    n = a.n if a.n is not None else EXPERIMENTS[a.experiment]["default_n"]
    return run_experiment(a.experiment, n, a.workers, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
