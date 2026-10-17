# FINAL PREREGISTRATION

**Fixed on: 2026-08-15 · Status: pending execution (not yet run)**

A one-shot document. Between finishing it and finishing the run, **neither this file nor the
model is changed**. It is **not changed after the run either**; results are only appended to the
experiment log.

---

## 0. What is frozen

The model = `v3_frozen/`, `MODEL_VERSION = "v3"`, `COND_RECOVER_AT = 65.0`.

```
sim.py                  256da7f66299ddd16975dcf31d4e14b31a5a38b5ed2fedba505ef32aeb697f96
scenarios.py            cfab8c5943289c26db10b351c2efcec2ea65e50249f2f9e4f0a4e5350749ba17
transplant.py           3000f324fe8a30f785933f95b770d3f19aa1a5889072732fa020cdc02234e1be
persistence_ablation.py a2630183c92a1b9d49dd1f7427dafe7bebc2825c68b4cf32cb1d6cb27669b014
```

Check `SHA256SUMS.txt` before running the final confirmation. **If it does not match, do not run.**

---

## 0.5 ⚠ The scope of this preregistration (read this section first)

**This is "the final confirmation of the current persistence architecture", not the final
confirmation of the core goal of the whole research programme.**

What it confirms:

> whether a different past leaves a persistent behavioural difference **within one common
> garden**, and which mechanisms carry that difference.

What it does **not** test, and therefore cannot claim:

> whether those past-shaped differences generalize into different decisions in a **situation
> neither side has ever experienced**.

So even if 50000–51499 passes beautifully on every count, the conclusion that may be written is
**"the foundation of persistent individuality / path dependence is now solid"**,
**not** "generalized individuality has been demonstrated".
The latter belongs to the next stage, **novel-situation generalization**, which is outside the
scope of this file.

Those two sentences must not be conflated in the paper.

## 1. Research question (RQ)

**Does an identical individual become a behaviourally different individual because it lived
through a different past; and what mechanism carries that difference?**

In falsifiable form: after a transplant into one common garden, is the behavioural difference
caused by the **developmental environment** significantly larger than the difference caused by
the **seed (initial individual variation)**; and does that difference depend on (a) the trait-floor
ratchet, (b) semantic memory.

## 2. Primary metric

**The transplant ratio**

```
ratio = mean_i TV(A_i, B_i) / mean_i b_i
```

- `A_i / B_i` = the same seed i developed for 30 days in the rich world / the barren world
  respectively, transplanted into the "baseline" world on day 30, taking the per-hour action
  distribution over the **day 30–60 window**
- `TV` = the daily mean of the per-hour total-variation distance (`transplant.window_tv`)
- `b_i` = the TV of the same world across different seeds, averaged over **K=5 repeated random
  pairings** (rule 35)
- Both numerator and denominator use **surviving pairs only**

**Secondary metrics**: the per-seed `δ_i = TV(A_i,B_i) − b_i` (carrying units, no Jensen bias),
`Cohen's dz`, and mortality.

## 3. Seeds

**seeds 50000–51499, N = 1500. Never run.**

Blocks that are contaminated and **must not** serve as the final holdout:
`0–1499` (development), `10000–11499` (the 021 holdout, inspected many times),
`20000–21499` (the 022 preregistration block, used for P1/P2 and the 023 revalidation).

**This seed block is run once.** Whatever the result, the model is not changed afterwards;
if the model is to be changed later, it must be acknowledged that the 50000 block has lost its
holdout standing, and a new block must be opened.

## 4. Exclusions and handling of death

- **The only exclusion rule**: if the agent in either world of a pair dies before day 60 → that
  pair is dropped.
- Dropping is **paired** (death of either `A_i` or `B_i` drops the whole pair).
- **Must be reported**: the effective n and the mortality (reported per world, not only the
  paired mortality).
- **Any other post-hoc filtering is forbidden.** In particular it is **forbidden** to run subset
  analyses as the main test based on simulation products such as whether `fears_hunger` fired,
  whether a `_hardship_anchor` exists, or how high condition is — that would re-create selection
  (023 §6). Such subset results may only be **secondary descriptive analysis**, and must be
  labelled as such.
- If a variant has an effective n < 1000 (mortality > 33%), it is judged **invalid** rather than
  "not significant", and this is stated plainly in the results.

## 5. Statistics

- **CI**: cluster bootstrap, resampling by agent, **3000 times**, taking the 2.5/97.5 percentiles.
- **p value**: **sign permutation** of the per-seed δ, **10000 times**, `p = (hits+1)/(n_perm+1)`.
- **Multiple comparisons**: the criteria below are **specified in advance** and no correction is
  applied; any comparison not listed in this file is marked exploratory.
- Random seeds (analysis layer): the bootstrap / permutation use a fixed seed hardcoded in the script.

## 5.5 Amendment A (2026-08-15, **before the final run**, based only on already-burned development seeds)

> **Not one word of the original is deleted; see the criteria in §6. This section adds a third
> outcome and modifies no hypothesis, no model, no estimator and no threshold of any criterion.**

### Why the change

The rehearsal (development seeds 0–1499, N=1500, `r52_precision.py`) found that R52's CI lower
bound lands at **1.0003**, and that re-running 8 times while changing only the **analysis-layer
random seed** (with data/model/estimator all unchanged) gives:

```
lower-bound range [0.99875, 1.00145]   MC SD = 0.00097
5/8 judge "pass", 3/8 judge "fail"
|median lower bound − 1.00| = 0.00032  «  jitter 0.00271
```

**At this effect size, the bright line "CI lower bound > 1.00" hands the conclusion to the random seed.**

Raising `N_BOOT` cannot rescue it: that only compresses the Monte Carlo error without changing
the limiting value of the quantile (as `N_BOOT → ∞` the lower bound converges to ≈1.0003) — it
would turn "random arbitrariness" into "deterministic arbitrariness", not into meaning.

### What changes

**Every criterion of the form "bootstrap 95% CI lower bound > 1.00"** (H1, P1, R52) goes from two
outcomes to three:

| Condition | Verdict |
|---|---|
| `lo − 1.00 ≥ +0.01` | **pass** |
| `lo − 1.00 ≤ −0.01` | **fail** |
| `\|lo − 1.00\| < 0.01` | **on the detection boundary; this criterion cannot decide** |

- The threshold **0.01 ≈ 10 × the measured MC SD (0.00097)**, fixed before the run and not adjusted again.
- The third outcome is **not** "fail" and **not** "pass". The paper states plainly "cannot decide".
- Boundary diagnostic (**affects the report only, never the verdict**): for any condition with
  `|lo − 1.00| < 0.02`, run a full bootstrap once with each of 8 analysis seeds and report the
  range of the lower bound and the MC SD.
- The main verdict still uses only the preregistered analysis seed `777`.

### Does this count as adaptive analysis

No. The basis is **only already-burned development seeds**; what changed is "allowing the
criterion to be declared undecidable", and admitting undecidability **cannot manufacture a
positive result** — it can only make a positive harder to claim. Not one tick of 50000–51499 had
been run when this amendment was made.

> ### Lesson (recorded as rule 56)
> **When preregistering a bright-line criterion, you must also preregister that it is decidable at
> the expected effect size.** Otherwise a third outcome must be allowed.

## 6. Criteria (fixed in writing before the run)

### H1 — the main effect
**Full architecture, 022 on**: the bootstrap 95% CI lower bound of the ratio is **> 1.00**.
→ Pass: the difference caused by the developmental environment is significantly larger than the
difference caused by the seed.

### P1 — does it still stand with all floors off
**022 on + −all floors ①②**: bootstrap 95% CI lower bound **> 1.00**.
- Pass → there is a persistence channel that **does not depend on the floor ratchet**.
- Fail → persistence **must** depend on the floor ratchet.
(The 023 v3 same-seed result: 1.090 [1.047, 1.128], pass.)

### P2 — is semantic memory the carrier
At the moment of transplant **delete only** `knowledge` (keeping flags / memories / the floors),
and compare against "delete nothing": **a drop of ≥ 0.05 with non-overlapping 95% CIs**.
- Pass → the knowledge channel may be claimed.
- Fail → it may **not** be claimed, and the main line becomes "discrete memory structures are not
  the long-term carrier".
(Both v2 and v3 fail. **Failure is expected.**)

### R52 — the verdict on rule 52 (the open case of 021§3)
**022 off + −all floors ①②**: bootstrap 95% CI lower bound **> 1.00**.
- Pass → the no-floor residual effect is real, and the withdrawal of rule 33 must be revisited.
- Fail → the withdrawal of rule 33 is settled: `trait_identity` is a **necessary mechanism**, not
  an amplifier.
(1.036 n.s. on the development block, 1.057 ** on the 021 holdout block; the two disagree — which
is exactly why a verdict is needed.)

### Negative control — episodic memory
At the moment of transplant delete only `memories`: this must be **bit-identical** to "delete nothing".
If it is not, the implementation has changed and the whole batch is void and must be re-checked.

## 7. Prior predictions (written before the run, copied verbatim for comparison afterwards)

| Criterion | Prediction | Basis |
|---|---|---|
| H1 | **pass**, ratio ≈ 1.12–1.16 | 023 v3: 1.124 / 1.148 / 1.172 |
| P1 | **pass**, ≈ 1.07–1.10 | 023 v3: 1.090 [1.047,1.128] |
| P2 | **fail**, drop ≈ 0.03 | 023 v3: 0.033, CIs overlap |
| R52 | **fail** (lower bound ≤ 1.00), ratio ≈ 1.03–1.06 | the two blocks give 1.036 / 1.057, straddling the detection limit |
| episodic memory | **bit-identical** | bit-identical in both v2 and v3 (rule 41) |
| mortality | ≤ 6% per world, ≤ 10% paired | 023: 4.1–4.3% |

**R52 is the only genuinely unknown item.** The other four are replications, not discoveries —
the paper must say so, and must not present a replication as a confirmation.

## 8. Execution

```powershell
cd C:\Users\yinan\Desktop\ai-sandbox
python final_confirm.py          # not yet written; once written, get it working on seeds 0+ before switching to 50000
```

⚠ **The script must first be shaken down on development seeds**, confirming there are no errors
and no version contamination (rule 55: two runs with different `--workers` give bit-identical
results), **before** pointing it at the 50000 block. The 50000 block may be executed only once.

---

## Appendix: follow-up work outside the scope of this preregistration

The following is exploratory and not bound by this file, but **must not be allowed to modify the
model before the final confirmation**:

- state transplant (transplanting a whole state)
- novel-situation generalization (behavioural differentiation in a situation never encountered)
- further dissection of the anchor mechanism (024 did a miniature version, rule 54)
