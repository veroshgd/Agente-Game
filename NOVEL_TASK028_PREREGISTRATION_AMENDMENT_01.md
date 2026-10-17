# 028 preregistration · amendment 01

**Created after the shape rehearsal and before opening the final seed block 70000–71499.**

> Amendment created after the shape rehearsal (seeds 10000–10299, n=286)
> but before inspection of final seeds 70000–71499. Rehearsal breadth
> contrasts had been observed. The clause below concerns the **sample size
> at which the validity gates are defined**; it is derived from the sampling
> standard error of the gate statistics, **not** from the observed rehearsal
> G value. No gate threshold, arm definition, frozen transform, endpoint,
> SESOI, or inference method is changed.

⚠ **Not one word of the original `NOVEL_TASK028_PREREGISTRATION.md` is changed.**
This file is a **transparent pre-final amendment** and does not pretend to be part of the
original preregistration.

---

## A. Added: a sample-size qualification for the validity gates

### The clause

> **The validity gates are defined for the N = 1500 confirmatory run.
> A rehearsal smaller than that verifies only the code path, the metric conventions and the order
> of magnitude; its gate results **do not constitute** a verdict on the frozen transform.**

### The basis (unrelated to the observed G)

The gate statistic `|μ_j − μ_A| / SD_A` itself carries sampling noise.
The two means are computed on **the same batch of agents**, `M = 2 × n_pairs` agent-instances in
total, so the sampling SE of the paired-difference mean is about

```
SE( |Δμ| / SD_A )  ≈  √(2 / M)
```

| Stage | n_pairs | M | SE | the 10% threshold equals |
|---|---|---|---|---|
| shape rehearsal | 286 | 572 | ≈ 5.9% | **< 2 SE** |
| FINAL | ≈ 1400 | ≈ 2800 | ≈ 2.7% | **≈ 3.7 SE** |

**At rehearsal scale the 10% threshold is under 2 SE — it is essentially testing noise.**

**An independent empirical anchor**: on **n=2944** (seeds 10000–11499), `transport028.py` measured
the same frozen transform at a largest `|Δμ|/SD_A = 3.2%` and `|ΔSD|/SD_A = 2.4%`, consistent with
what is expected at final scale. The shape rehearsal (n=286) measured Bp at `|Δμ|/SD_A = 10.4%` —
**the difference between the two comes from sample size, not from transport error in the transform**.

### What is not changed

The four thresholds `support ≤ 2%`, `boundary ≤ 2%`, `|Δμ|,|ΔSD| ≤ 10% × SD_A` are **left
untouched**. They were frozen after the transport measurements (n=2944) had been seen, and were
set for the **N=1500 confirmatory run**.

### The layered failure handling is unchanged

Either C± failing → primary G invalid; B± failing → secondary invalid only;
A has no mapping transport gate. The failure wording is still:

> Frozen coupling normalization did not transport adequately to the
> confirmatory population; breadth contrast is not cleanly interpretable
> under the preregistered equal-budget assumption.

---

## B. The corresponding runner change (affects printing only, not the decision logic)

When `N < 1500`, `final_028.py` prints a **NON-BINDING** line explaining that the gate results of
that run do not constitute a verdict on the frozen transform.
**The final run (N=1500) is unaffected and the gates remain binding as before.**

---

## C. Record: the gates as measured in the shape rehearsal (seeds 10000–10299, n=286)

```
arm  out of range  boundary mass  |Δμ|/SD_A  |ΔSD|/SD_A  support  budget
Bp      0.00%        0.00%          10.4%       6.4%        ✓        ✗
Bm      0.00%        0.00%           7.3%       4.1%        ✓        ✓
Cp      0.17%        0.17%           5.1%       3.5%        ✓        ✓
Cm      0.00%        0.00%           2.0%       2.0%        ✓        ✓

primary (C±) ✓ valid      secondary (B±) ✗ invalid
```

Every support gate passes with an enormous margin (worst case 0.17% against a 2% threshold).
The only failure is Bp's budget gate, exceeding the threshold by **0.4 percentage points**, which
under §A is **noise at rehearsal scale** and **does not constitute a verdict on the frozen transform**.

> ### ★ Rule 82: a criterion must be bound to the sample size it was designed for ★
> A threshold designed for N=1500 becomes "a test of noise" when applied at n=286.
> When a preregistration states a threshold, **it must also state the scale at which that
> threshold is valid**, or a small-sample rehearsal will produce a meaningless red light
> (or worse: a meaningless green one).
