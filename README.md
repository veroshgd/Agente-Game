# LifeEngine

A **pure-Python, zero-LLM, dependency-free** artificial-life agent-based model.

It is a **minimal apparatus** built to test one question:

> **Do different experiences during a developmental period still leave a difference
> after the agent is transplanted into an identical environment?
> And if so, can those differences be put to use on an unfamiliar new problem?**

⚠ It is **not** a simulation of personality formation. Every conclusion is confined to
this apparatus.

---

## Main results

| Experiment | Question | Result |
|---|---|---|
| **v3 / 025** | Can the past **persist**? | **Yes.** After the transplant, the TV ratio of the per-hour action distribution is **1.142, 95% CI [1.098, 1.183]** (preregistered, run once) |
| **027** | Does the personality that persists **transfer automatically** to a new task? | **Extremely weakly** (0.08 trials), and it **failed to replicate** on a fresh sampling block |
| **028** | Does **widening** the interface that reads history, at equal coupling budget, rescue it? | **No gain** (G ≈ 0, and robust to the sign of the wiring) |
| **029** | Can **relational memory** grown from real experience be retrieved and used causally? | **Yes, but below the functional threshold** (see below) |

### 029 FINAL (seeds 80000–81499, N=1500)

```
ΔC = -0.8833     95% CI [-1.0160, -0.7533]     SESOI = 1.0 post-change error
→ Detectable memory-mediated transfer,
  but functional significance not established.

SHUFFLE retention  R = 0.0106   CI upper bound 0.1102 < 0.25
→ ≥75% attenuation established: the effect is carried by **relational structure**,
  not by the marginal statistics of the memory store

XSEED-DONOR retains 104.6%  →  the effect does not depend on development and test sharing a seed
All four validity gates passed
```

**Taken together this shows**: compressing a developmental history into a single personality
readout and feeding it into a new task carries almost no replicable functional transfer; but
when the developmental history is stored as **relational experience** and retrieved in a
structurally similar situation, it really does causally reduce errors on the new problem —
**only by less than one post-change error, which does not clear the functional threshold
fixed in advance.**

⛔ This repository makes **no claim** that the agent "learns / understands / becomes aware of"
anything, nor any claim of analogical reasoning or generalized individuality.
The boundary of each claim is set out in [`CLAIMS.md`](CLAIMS.md).

---

## Methodological discipline

Most of the work in this project goes into **stopping ourselves from fooling ourselves**:

- **Preregistration first.** Every confirmatory experiment fixes its hypothesis, endpoint,
  SESOI, reading rules and statistical procedure in writing beforehand, and not a word is
  changed afterwards. No key design may be modified after a group effect has been seen.
- **Seed ledger.** Every confirmatory experiment uses a block of seeds that has **never been
  used**; once a run starts, that block is permanently burned and never reused
  (`final_029_STARTED.lock` is never deleted once created, not even if the program crashes).
- **Group-blind calibration.** Every parameter is fixed **without visibility of the group
  difference**; if no passing parameters are found, the design is judged unclean and
  **the standards are never relaxed to rescue it** (experiment 026 was closed as a negative
  result on exactly these grounds).
- **Freezing and hashes.** `v2_frozen/` and `v3_frozen/` each carry SHA256 manifests;
  before starting, `final_029.py` verifies the sha256 of six modules, the task fingerprint and
  the preregistration hash, and refuses to run if any of them mismatches.
- **Failures written up as they were.** Conclusions overturned by later experiments are
  **kept verbatim** and marked as withdrawn; protocol deviations are recorded faithfully
  (see rule 98 in the log).

⚠ The `* -text` line in `.gitattributes` **must not be removed** — this project gates on the
sha256 of source files, and any line-ending conversion invalidates the frozen verification.

---

## Layout

```
sim.py, scenarios.py, behavior.py …      the model core
v2_frozen/ , v3_frozen/                  the two frozen versions (each with SHA256)
                                         the only executable v2→v3 difference is one constant
novel_task.py                            the new-task substrate shared by 027/028/029
memory_transfer_probe{,2,3}.py           029 mechanism identifiability probes (v1 one-shot →
                                         v2 stateful → v3 timing fix)
memory_acquisition_probe.py              Stable/Volatile developmental history → relational memory
memory_lambda_calibration.py             group-blind interface-capacity calibration (λ is frozen here)
memory_transfer_rehearsal.py             OWN/DELETE/SWAP/SHUFFLE rehearsal
final_029.py                             the 029 FINAL runner (seed guard + one-shot lock)
*_result.txt                             the persisted results of each experiment
tests/                                   self-checks and regressions
tools/verify_provenance.py               path-independent digest verification
tools/replay_paper_results.py            guarded replay of confirmatory numbers
docs/                                    preregistrations, design evolution, the full experiment ledger
```

### Documentation

| File | Contents |
|---|---|
| [`REPRODUCE.md`](REPRODUCE.md) | Three levels of reproduction, the **seed ledger**, and the rules on what must never be re-run |
| [`CLAIMS.md`](CLAIMS.md) | The evidence grade of each claim + **the table of forbidden wordings** |
| [`ODD.md`](ODD.md) | The standard ODD model description |
| [`docs/MEMORY_TRANSFER029_PREREGISTRATION.md`](docs/MEMORY_TRANSFER029_PREREGISTRATION.md) | The 029 preregistration (its sha256 is what `final_029.py` verifies) |
| [`docs/MEMORY_TRANSFER_DESIGN.md`](docs/MEMORY_TRANSFER_DESIGN.md) | The record of how the 029 design evolved from v1 to v7 |
| [`docs/SIMULATION_LOG.md`](docs/SIMULATION_LOG.md) | The full experiment ledger, rules 1–98 (including the original text of withdrawn ones) |
| `FINAL_PREREGISTRATION.md`, `NOVEL_TASK*_PREREGISTRATION*.md` | The preregistrations and amendments for v3 / 027 / 028 |

---

## Running

```bash
pip install -r requirements.txt   # only pytest, for the self-check
pytest                            # < 1 minute; all green means the environment is sound
```

All it needs is **Python 3.10+ and the standard library**. For a full reproduction see
[`REPRODUCE.md`](REPRODUCE.md).

⚠ **Every confirmatory seed block in this project is burned; no `final_*.py --final`
runner may be run again.** 027, 028 and 029 refuse by themselves. `final_confirm.py` (025)
does **not** — passing it `--final` silently overwrites the paper's primary result file.

To reproduce the paper's numbers, use the guarded replay harness rather than the runners:

```bash
python tools/replay_paper_results.py --list
python tools/replay_paper_results.py 025 --n 100    # quick directional check
```

It hashes every protected artifact, refuses to pass `--final`, preserves the files the
runner would overwrite, and fails loudly if a single byte moved. See
[`REPRODUCE.md`](REPRODUCE.md) for the full seed ledger and the Level ③ procedure.
Never delete a `*_STARTED.lock`: staying behind after a crash is precisely its job.

⚠ `PREREG_PATH` in `final_029.py` points at a vault path on the author's own machine, so after
cloning it reports "cannot find the preregistration". That is the historical state at the time
the FINAL run completed, and it is **deliberately left unchanged**. A reproducer can check the
hash of the copy directly:

```
sha256(docs/MEMORY_TRANSFER029_PREREGISTRATION.md)
  = 29e45930a07f2649c7958fdc0cd20a389005ca43e93287b9f69e2ccdcf867145
```

> ⚠ **Note for this English branch.** **No source file was translated, and no hash was
> regenerated.** Only Markdown documentation was translated, and no Markdown file except
> `docs/MEMORY_TRANSFER029_PREREGISTRATION.md` is referenced by any hash — that one is left in
> the original Chinese precisely because it is. Every `.py` file in this repository, in both
> frozen directories and at the root, still carries its original Chinese comments and its
> original bytes.
>
> This is verifiable without trusting the claim. `final_029_STARTED.lock` was written on the
> original machine at the instant the 029 FINAL run began, and it records the digest of each
> frozen runtime module and of the preregistration. Those recorded values equal the
> `FROZEN_MODULES` / `PREREG_SHA256` constants in `final_029.py` *and* the digests of the files
> as shipped. The same holds for `interface028_frozen.json` against `final_028_STARTED.lock`.
> See "What the integrity gates do and do not prove" below.

## Language and integrity policy

The paper is in English. This repository mixes languages **deliberately**, and the
mixture is itself part of the reproducibility argument.

| Layer | Language | Why |
|---|---|---|
| Documentation (`README`, `REPRODUCE`, `ODD`, `CLAIMS`, preregistrations except 029, `docs/*_DESIGN.md`, `docs/SIMULATION_LOG.md`) | English | Not referenced by any hash; freely translatable |
| `docs/MEMORY_TRANSFER029_PREREGISTRATION.md` | **Chinese, unmodified** | Referenced by `final_029.py` via `PREREG_SHA256`; an English rendering is provided separately as `.en.md` and is explicitly non-authoritative |
| `v2_frozen/`, `v3_frozen/` | **Chinese comments, unmodified** | Byte-frozen and verified by `SHA256SUMS.txt` |
| Root `*.py` | **Chinese comments, unmodified** | Six of them are hash-recorded in `final_029.py`; more importantly, experiment-group names such as `丰富世界` / `贫瘠世界` / `基准` are **dictionary keys**, not prose. Translating them would break interoperability with the frozen directories |

Source comments are **not** translated. Translating a comment changes the file's bytes,
which invalidates the manifests and severs the correspondence with the confirmatory runs.
This is the failure mode described in Appendix F, Rule 19 of the paper: a regenerated
manifest makes the integrity check pass silently while proving nothing.

## License

| Material | License |
|---|---|
| Source code (`*.py`) | [Apache-2.0](LICENSE) |
| Documentation, preregistrations, result records, data (`*.md`, `*.txt`, `*.csv`, `*.json`, `*.lock`) | [CC BY 4.0](LICENSE-DOCS.md) |

Copyright 2026 Yinan Qin. See [`NOTICE`](NOTICE) for the integrity conditions
that apply to the hash-gated artifacts — in short, Apache-2.0 §4(b) requires
modified files to say so, and for the frozen artifacts that requirement is the
whole point.

Machine-readable citation metadata is in [`CITATION.cff`](CITATION.cff).

## What the integrity gates do and do not prove

Not every artifact in this package is anchored the same way, and the difference matters. Two
distinct things are being checked, and only one of them is independent evidence.

**Independently anchored.** These have a digest recorded *outside* the file that carries them,
written at run time on the original machine, before this package existed. Agreement here cannot
be manufactured by regenerating a manifest.

| Artifact | Independent record | Status |
|---|---|---|
| the six frozen runtime modules | `final_029_STARTED.lock`, written before the first 029 acquisition trajectory | 6/6 identical |
| `docs/MEMORY_TRANSFER029_PREREGISTRATION.md` | same lock (`prereg_sha256`) | identical |
| `interface028_frozen.json` (content digest) | `final_028_STARTED.lock` and `final_028_result.txt` | identical |

**Self-consistent only.** `v2_frozen/SHA256SUMS.txt` and `v3_frozen/SHA256SUMS.txt` are checked
against the files they list. That proves the directories have not been disturbed *relative to
their own manifests*, but a manifest regenerated together with its files would also pass. There
is no run-time digest of those directories recorded anywhere outside them, so this is a weaker
guarantee than the table above, and it is described here as such rather than folded in with it.
The supporting circumstantial fact is that all 58 files in the two directories still carry their
original untranslated Chinese comments, so no translation event that would have required
regeneration ever took place.

This is the distinction drawn as rule 19 in Appendix F of the paper: a regenerated manifest
makes an integrity check pass silently while proving nothing. It applies to this repository too,
and the honest answer is that it applies to the frozen directories and not to the three rows
above.

To verify the chain from a fresh clone:

```bash
export PYTHONUTF8=1                  # required on Windows; see REPRODUCE.md
python3 tools/verify_provenance.py   # exit code 0 if all artifacts match
python3 -m pytest -q                 # core self-check suite
```

Both have been run from a fresh clone on Linux (Python 3.12) and Windows 11 (Python 3.13):
10/10 and 8/8 respectively. See `REPRODUCE.md` for the platform matrix.
