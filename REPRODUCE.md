# Reproduction guide

```bash
pip install -r requirements.txt
pytest                       # < 1 minute; all green means the environment is sound
```

All it needs is **Python 3.10+ and the standard library**; `pytest` is used only for the
self-check. There are no third-party dependencies.

---

## Before you run anything: UTF-8 output is required

Several scripts print Unicode characters (`✓`, `★`) and Chinese labels. On Windows, Python
still defaults to the legacy `cp1252` console codec, which cannot encode them: the affected
scripts abort inside `print()` with `UnicodeEncodeError`, and the self-check suite then reports
failures that have nothing to do with model integrity.

Enable Python's UTF-8 mode first:

```powershell
$env:PYTHONUTF8 = "1"                                              # PowerShell, current session
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")   # or persist it, then reopen
```

```bash
export PYTHONUTF8=1          # Linux / macOS — usually already UTF-8, harmless to set
```

Verified environments:

| Environment | `tools/verify_provenance.py` | `pytest` |
|---|---|---|
| Linux, Python 3.12 (UTF-8 default) | 10/10 | 8/8 |
| Windows 11, Python 3.13, `PYTHONUTF8=1` | 10/10 | 8/8 |
| Windows 11, Python 3.13, **without** `PYTHONUTF8` | 10/10 | 6/8 |

In the last row both failures are `UnicodeEncodeError` raised by `print()` in
`novel_calibrate3.py` and `final_confirm.py`. No integrity check, hash comparison, or numerical
result is affected — `tools/verify_provenance.py` passes 10/10 in all three environments.

---

## Independent provenance verification

`final_029.py` is the historical one-shot confirmation runner and is left byte-unchanged,
including its absolute `PREREG_PATH`, which points at the machine used at confirmation time.
That path does not exist in a fresh clone, so the runner's own preflight prints "cannot find"
for the preregistration line. This is expected and is disclosed in Appendix B.9 of the paper.

To verify the chain without modifying the historical runner:

```bash
python tools/verify_provenance.py
```

It recomputes, from this repository alone, the SHA-256 of the preregistration document, the six
frozen runtime modules recorded in `final_029.py`, both frozen model directories, and the frozen
Experiment 028 interface, and compares each against the constants recorded before the
confirmatory runs. Exit code 0 means every artifact matches.

---

## Three levels of reproduction

| Level | Command | Time | What it proves |
|---|---|---|---|
| **① self-check / regression** | `pytest` | < 1 min | frozen integrity, model provenance, mechanism layer, determinism |
| **② small-scale smoke test** | see below | ~15 min | the **direction** of the core results reproduces |
| **③ full replay** | `tools/replay_paper_results.py` | 1--6 h per experiment | the **specific numbers** in the paper |

---

### ⛔ Read this before Level ③

**Every confirmatory seed block in this project is burned. None of the
`final_*.py --final` runners may be run again.** See the seed ledger below for
which blocks are burned and why that is permanent.

Three of the four runners defend themselves: `final_027.py` refuses once its
result file exists, `final_028.py` holds a one-shot lock, and `final_029.py`
creates `final_029_STARTED.lock` before the first acquisition trajectory and
refuses thereafter. **`final_confirm.py` (Experiment 025) has no such guard.**
Passing it `--final` opens `final_confirm_result.txt` in write mode and silently
overwrites the paper's primary confirmatory result. Earlier revisions of this
file listed that command under "full reproduction". It was wrong and is
withdrawn; do not run it.

Never delete a `*_STARTED.lock`. A lock is not a nuisance file to be cleared
after a crash — its whole purpose is to stay behind after a crash. Deleting one
converts a burned block back into an apparently clean holdout, which is the
single fastest way to destroy the confirmatory standing of this work.

### ① Self-check / regression

```bash
pytest
python tools/verify_provenance.py
```

`pytest` verifies the SHA-256 of `v2_frozen/` and `v3_frozen/`; asserts the model
really is imported from `v3_frozen` with `MODEL_VERSION == "v3"` and
`COND_RECOVER_AT == 65.0`; uses an **AST comparison** to confirm that the only
executable v2 → v3 difference is still that one constant; runs the 6
mechanism-layer self-checks; verifies the rule 72 window regression; and verifies
that two runs of the same seed are bit-identical.

`tools/verify_provenance.py` independently recomputes every frozen digest without
executing or modifying the historical runners.

### ② Small-scale smoke test (direction, not numbers)

```bash
python novel_situation.py                        # the 8 mechanism-layer self-checks
python final_confirm.py --check                  # the frozen-verification gate only
python final_confirm.py --seed0 0 --n 200        # development seeds, safe to repeat
python rule71_ablation.py --seeds 50 --workers 4 # causal direction of TRAIT_DRIFT
```

⚠ At small N the point estimate is biased upward (rule 34: the ratio estimator is
inflated at small N), so **read the direction only**.

Note that `--seed0 0` is used here deliberately: block `0–1499` is development
seed space and carries no confirmatory standing, so repeating it costs nothing.

### ③ Full replay of the paper's numbers

Use the replay harness. Do not invoke the runners directly.

```bash
python tools/replay_paper_results.py --list          # what can be replayed
python tools/replay_paper_results.py 025 --n 100     # quick directional check
python tools/replay_paper_results.py 025             # full block, hours
python tools/replay_paper_results.py 027
python tools/replay_paper_results.py 028
python tools/replay_paper_results.py 029
```

**How replay can be exact without re-burning anything.** In all four runners,
`--final` selects only three things: the seed block, the banner text, and the
output filename. The simulation is byte-identical either way. So the harness
passes the burned seeds *explicitly in non-final mode* — same model, same seeds,
same numbers, different output file.

Around that, the harness supplies the protection the runners lack:

1. hashes every protected artifact before starting;
2. refuses to pass `--final` to anything, unconditionally;
3. backs up the scratch output file the runner is about to overwrite;
4. runs the experiment;
5. moves the fresh output into `replay_out/` and restores the backup;
6. re-hashes everything and **fails loudly if one byte moved**.

Step 6 is the point of the tool. If it ever reports a changed artifact, treat the
working tree as contaminated and re-clone before doing anything else. The
detector has been mutation-tested: appending one line to
`final_confirm_result.txt` between the two scans makes it report the file as
CHANGED and return failure.

`replay_out/` is gitignored. Compare its contents against the recorded result
file named in the harness output.

| Replay | Seeds | Recorded result to compare against | Rough time |
|---|---|---|---|
| `025` | 50,000–51,499 | `final_confirm_result.txt` | ~1.5 h |
| `027` | 60,000–61,499 | `final_027_result.txt` | ~1 h |
| `028` | 70,000–71,499 | `final_028_result.txt` | ~1 h |
| `029` | `--rehearse`, full size on a burned development block | `final_029_result.txt` | ~1.5 h |

Experiment 029 is replayed through `final_029.py --rehearse` rather than by
re-simulating 80,000–81,499. The rehearsal is full-size and exercises the same
five arms, acquisition pipeline, interface transport and analysis path; what it
cannot do is regenerate the confirmatory block itself, because that block is
burned and its lock is permanent.

To check only the integrity scan, without running any simulation:

```bash
python tools/replay_paper_results.py --verify-only
python tools/replay_paper_results.py 025 --dry-run
```

### Other analyses reported in the paper

These are not one-shot confirmations and may be re-run freely:

```bash
# v3 parameter robustness  500 configs x 300 seeds  ~45 min
python param_sweep.py --configs 500 --seeds 300 --out sweep_results_v3.csv
python sweep_report.py sweep_results_v3.csv

# v2 -> v3 same-seed revalidation (experiment 023, paper section 7)  ~40 min
python v3_revalidate.py

# rule 71 causal ablation  ~20 min
python rule71_ablation.py --seeds 300
```

⚠ `param_sweep.py` writes `sweep_results_v3.csv` in place. That file is cited by
the paper; redirect with `--out` if you want to keep the original.

---

## Which model each result came from — read this table

| Artefact | Model | Standing |
|---|---|---|
| `final_confirm_result.txt` | **v3_frozen** | ★the preregistered final confirmation★ (seeds 50000–51499, run once) |
| `sweep_results_v3.csv` | **v3_frozen** | v3 parameter robustness (the paper uses this one) |
| output of `rule71_ablation` | **v3_frozen** | TRAIT_DRIFT causal ablation (exploratory; the directional prediction was fixed beforehand) |
| `sweep_results.csv` / `holdout.csv` | **v2** | ⚠ **development history**, header carries no version column. The paper must not cite it as v3 robustness |
| `final_confirm_result.VOID_bug.txt` | — | ⚠ **void**: the empty run caused by the chunk-indexing bug, kept as a process record |
| every number from experiments 011–022 | **v2** | development history, **kept and not overwritten** |
| experiment 026 (novel-situation) | v3_frozen | **negative result**: all four probes retired |

> Experiments 011–022 were conducted under model v2 and are retained as
> development history rather than overwritten by subsequent model correction.

---

## Seed ledger (which blocks are burned)

A block is **burned** the moment information relevant to the research question is
first generated from it — not when the primary outcome is first computed. Once
burned it can never again be described as unseen holdout or confirmatory data.

| Block | Use | Status |
|---|---|---|
| `0–1499` | model development, 21 iterations, later dry runs; 029 probes / calibration / rehearsal used `0–399` | 🔥 burned |
| `10000–11499` | 021 holdout set; 028 transport rehearsal; **029 full-shape rehearsal** | 🔥 burned |
| `20000–21499` | 022 preregistration block; 027 and 028 group-blind calibration | 🔥 burned |
| `50000–51499` | **Experiment 025 — persistence FINAL** | 🔥 burned, executed once |
| `60000–61499` | **Experiment 027 — new-task transfer through a narrow trait interface FINAL** | 🔥 burned, executed once |
| `70000–71499` | **Experiment 028 — widened trait readout at fixed coupling budget FINAL** | 🔥 burned, executed once |
| `80000–81499` | **Experiment 029 — relational-memory transfer FINAL** | 🔥 burned, executed once |

**No clean confirmatory block remains.** Any future confirmatory experiment must
open a new, previously unused block and record it here before the first run.

This table is authoritative and matches Appendix C.2 of the paper and the
`ledger:` header written into `final_029_result.txt`. If any other document in
this repository disagrees with it, this table is correct and the other document
is stale.

> **Correction.** Earlier revisions of this file listed `60000–61499` as
> "✓ clean — once reserved for the 026 final, never used", and omitted
> `70000–71499` and `80000–81499` entirely. That was wrong: 026 was closed as a
> negative result, but the block was subsequently consumed by the 027 final
> confirmation, as recorded in the header of `final_027_result.txt`. The error is
> noted rather than quietly deleted, because a ledger that silently revises its
> own history is worth nothing.

---

## Layout

```
v2_frozen/     the v2 frozen snapshot (COND_RECOVER_AT = 30) + SHA256SUMS.txt
v3_frozen/     the v3 frozen snapshot (COND_RECOVER_AT = 65) + SHA256SUMS.txt  ★the paper's model★
tests/         the pytest self-check
tools/         provenance verifier + replay harness (not part of any frozen manifest)
replay_out/    replay harness output (gitignored, created on demand)
FINAL_PREREGISTRATION.md      the full preregistration (including amendment A)
NOVEL_SITUATION_DESIGN.md     the 026 design (closed)
```

The `*.py` files in the root are **experiment scripts**, not pytest tests — running them takes
tens of minutes of simulation. `pytest.ini` restricts collection to `testpaths = tests` and
excludes the two frozen directories (which hold modules of the same name and must not be edited).

**Deprecated** (kept for history, do not use): `sweep.py`, `food_sweep.py`.
**Retired** (the calibrations of 026's four probes, kept as evidence of a negative result):
`novel_calibrate.py`, `novel_calibrate2.py`, `novel_calibrate3.py`.
