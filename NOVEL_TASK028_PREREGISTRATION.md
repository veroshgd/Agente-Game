# Experiment 028 preregistration — Interface Breadth and Component Transfer

**Fixed on: 2026-08-17 · Status: awaiting rehearsal → awaiting execution**

A one-shot document. Between finishing it and finishing the run, **this file, the frozen
transform, the five-arm definition, the gates, G/R_B, the SESOI and the joint-bootstrap method
are not changed.**

---

## 0. Research question

027 forced a conceptual distinction into the open:

```
whether historical information exists                ← v3 proved it does
whether the new task can **access** that information  ← 027: through one narrow interface it read only a minuscule functional influence (0.08 trials)
```

**028 exists specifically to separate those two things.**

> **At the same total coupling budget, does a broader historical readout produce a larger
> novel-task transfer magnitude than the narrow interface of 027?**

⚠ **The name deliberately avoids "generalization"**, and also avoids "interface width":
C is still compressed into **one** `beta_i` entering the same softmax; what is widened is the
**range of history being read**, **not the number of decision channels**.

---

## 1. What is frozen

```
model      v4 = the v3_frozen core (byte-for-byte untouched) + novel_task.py
task       α=0.05  β=0.05  τ=0.20  TRIALS=80  REVERSAL_AT=40  P=0.80/0.20
           fingerprint 26778f672e9e7009
interface  interface028_frozen.json   sha256 f82497fb5b1ff535… (n_cal=2936)
```

### The five arms

| Arm | historical readout | Note |
|---|---|---|
| **A** | `curiosity − caution` | **the original 027 interface, not one line changed**. Passes through none of 028's mappings |
| **B+** | `+industry⊥` | component assay |
| **B−** | `−industry⊥` | component assay |
| **C+** | `A_std + industry⊥` | broader readout |
| **C−** | `A_std − industry⊥` | broader readout |

`industry⊥` = the **OLS residual** of industry against **`curiosity − caution` (A's true ordering
variable)**; on calibration, Pearson = 0.000000 and **Spearman = −0.0080**.

⚠ The orthogonalisation basis must be the **raw difference**, not `z(cur) − z(cau)` —
A's beta is a monotone function of the raw difference, and since σ_cur=20.87 ≠ σ_cau=29.55 the
two **order differently** (Spearman 0.9999). Quantile mapping is entirely ordering-based.

### Equal budget: quantile mapping

The readout of every non-A arm is **monotonically rank-normalised onto A's frozen beta marginal
distribution**, so support / mean / SD / skew / tails are **all identical to A's**, and
**the only difference is "which agents receive the larger beta" (the ordering)**.

> All historical readouts were monotonically rank-normalized to the frozen
> marginal coupling distribution of the original 027 interface, so arms
> differed in historical ordering rather than overall coupling magnitude.

⚠ **B− is not `0.05 − b(B+)`** — A's distribution is asymmetric ([0.012139, 0.048427],
μ=0.036948), so a **reverse percentile** is required.

⚠ **The adapter must cancel the internal multiplication**: `NT.run_task(..., beta=X)` internally
computes `b = X × novelty_style(agent)`. Passing the mapped `b_i` straight in as `beta=` would
give `b_i × novelty_style_i` — **secretly multiplying the A axis back in and destroying the
five-arm design**. That error was measured at 0.0107 ≈ the same order as arm A's entire SD (0.0122).

---

## 2. ★ Primary: G = min(|E_C+|, |E_C−|) − |E_A| ★

`E_arm` = the **same-seed paired difference** in restricted switch latency under that arm
(`d_i = L_rich,i − L_poor,i`, censoring None → 36, following 027).

**What taking the min means**: **whatever sign this semantically undirected historical component
is wired in with, the broader readout must produce stronger transfer than the narrow interface**
for it to count as a robust breadth gain. If only C+ or only C− wins →
**sign-dependent, and explicitly not counted as primary success**.

### Statistics: joint same-seed bootstrap

```
for each replicate b:
    idx = resample the seed indices once        ★shared by all five arms★
    E_A^(b), E_Cp^(b), E_Cm^(b)                 ← all using that idx
    G^(b) = min(|E_Cp^(b)|, |E_Cm^(b)|) − |E_A^(b)|
the CI is taken directly from {G^(b)}     n_boot = 10,000   analysis seed fixed
```

⛔ **Two forbidden approaches** (`stats028.py` carries adversarial tests that make them fail explicitly):
① computing marginal CIs per arm and subtracting the endpoints — measured 29.2× too wide
② taking the bootstrap mean of each arm first and then applying `abs()`/`min()` — `G` is
   non-linear and must be applied **per replicate**

### Three-valued verdict (SESOI = 1.0 trial, the same unit as 027)

| Case | Verdict |
|---|---|
| the 95% CI **contains 0** | **no evidence that the broader readout beats A** |
| the CI lies entirely **> 0** but still overlaps **[0, 1]** | **a breadth gain is detected, but below the functional threshold** |
| the CI lies **entirely > 1 trial** | **functionally meaningful breadth gain established** |

**C+ and C− are each additionally reported once against the ±1 trial equivalence region** —
"C beats A" and "C is functionally meaningful in itself" are **two different claims**.

---

## 3. Secondary: R_B = min(|E_B+|, |E_B−|)

Likewise computed **inside each joint replicate**. The raw values of B+ and B− are all reported.

⚠ What B asks is **not** "can industry transfer at all", but:
**how much transfer the part of industry's historical information that the exploration axis does
not explain can produce when wired into the same standardised decision interface as 027.**
This is an **information-pathway experiment**, not a psychological semantic assertion.

**Structural fact recorded in advance**: `corr(A axis, raw industry) = −0.8823` — most of the
variance of raw industry overlaps with the exploration axis.

---

## 4. ★ Validity gates (reading order: before the outcome) ★

```
support gate            raw out-of-range ≤ 2.0%   and   boundary mass ≤ 2.0%
budget-transport gate   |μ_j − μ_A|/SD_A ≤ 10%    and   |SD_j − SD_A|/SD_A ≤ 10%
```

⚠ `μ_A / SD_A` must be **arm A as actually run on the same confirmatory population**, not
calibration's A — that way any population shift cancels automatically.
(Measured in the transport rehearsal: A itself drifted from 0.036948 to 0.036663, i.e. 2.3% of SD_A.)

⚠ **out-of-support is checked on the input-side raw readout, not on the beta output** — beta is
already pinned inside A's support by the frozen mapping and can show no extrapolation by itself.

### Layered failure handling

| Failure | Consequence |
|---|---|
| either the C+ or C− gate fails | **primary G invalid / not cleanly interpretable** — neither a breadth gain nor a no-gain may be claimed |
| the B+ or B− gate fails | R_B secondary invalid; **if both C± pass, G is unaffected** |
| A | **has no mapping transport gate** (it is the contemporaneous reference itself) |

The fixed wording on failure:

> Frozen coupling normalization did not transport adequately to the
> confirmatory population; breadth contrast is not cleanly interpretable
> under the preregistered equal-budget assumption.

⚠ A gate failure **must not** lead to re-estimating the mapping.

### Transport rehearsal measurements (seeds 10000–11499, n=2944, group-blind)

```
largest out-of-range total 0.10%   largest boundary mass 0.20%
largest |Δμ| = 3.2% × SD_A     largest |ΔSD| = 2.4% × SD_A
```

---

## 5. ★ Arm A's dual role (which must be judged separately) ★

`70000–71499` is a **genuinely new sampling block for A too**, so 028 produces results at two
levels at once:

| | |
|---|---|
| **Arm A** | a **sampling-level replication** of the 027 effect (as distinct from 027's internal analysis-level MC stability, rule 80) |
| **G** | the fixed-budget breadth contrast of the broader readout against A |

**The two must be judged separately:**

- Even if A fails to reproduce 027's −0.08 trials, **G can still be computed**, but the paper must
  state: *027 narrow-interface effect did not replicate on the new sampling block.*
- Even if A does reproduce it, **A's success must not be counted as success for 028's breadth
  hypothesis.** G is still judged by its own CI + the 1-trial SESOI.

---

## 6. ★ Four dilution reading modes (fixed in advance) ★

| Mode | Conclusion |
|---|---|
| **C > A, and B shows transfer** | adding readable historical components **increased** transfer at a fixed coupling budget |
| **C ≈ A** | the broader historical readout **did not increase** transfer; the extra dimension provided no net gain |
| **C < A, and B is very weak** | consistent with **information dilution** from adding a low-transferability component at a fixed budget |
| **B is strong but C < A** | this may **not** be called dilution-by-noise; it suggests **cancellation, correlation structure or non-linear interaction** within the combined readout, and calls for follow-up mechanistic study |

⛔ The result **must not** be reduced to "C>A → wide interfaces work / C≤A → wide interfaces don't".

---

## 7. Seed ledger

```
0–1499          development
10000–11499     021 holdout set / 028 transport rehearsal
20000–21499     022 preregistration block / 027 + 028 group-blind calibration
50000–51499     v3 persistence FINAL
60000–61499     027 novel-task FINAL
70000–71499     ★028 breadth FINAL★   ← new, never used
```

### The 028 FINAL CONFIRMATORY BLOCK

```
seed0 = 70000     N = 1500     seeds = 70000–71499
```

- **for Experiment 028 FINAL only**
- **forbidden** for calibration / transport / rehearsal / parameter selection
- **once any agent trajectory has been officially generated, the block counts as burned**

Verified: `70000` appears **0 times** in the code, the experiment log and the result files.

---

## 8. Engineering protections (the runner must implement these)

1. **Seed guard** — `--final` accepts only `seed0=70000, N=1500` and rejects anything else outright
2. **One-shot lock** — refuse to run again if `final_028_result.txt` already exists
3. **Preflight ledger print** — before the final starts, print and persist the full seed ledger (§7),
   so the data role of all four stages is obvious at a glance
4. frozen JSON sha256 + task fingerprint verification, refusing to run on any mismatch

---

## 9. ★★ Closure rule ★★

> **Once the rich/poor result of 70000–71499 has been seen, none of the following may be changed:**
> the frozen transform, the five-arm definition, the quantile mapping, the transport gates,
> the definitions of G / R_B, the SESOI, the joint-bootstrap method, the task parameters, the seed block.
>
> **If the primary fails, it fails.**

Exploratory analysis after a failure is allowed, but **may only be labelled exploratory**.

---

## 10. Prior predictions (written before the run, copied verbatim for comparison afterwards)

| Item | Prediction |
|---|---|
| G direction | **not assumed** (two-sided) |
| Does G clear the SESOI | **unknown** — the only genuinely unknown item in 028 |
| arm A replication | leaning towards another minuscule effect, but **whether it replicates is not assumed** |
| R_B | unknown; `corr(A axis, raw industry) = −0.88` suggests the residual component may carry very little historical information |
| transport gates | expected to pass throughout (worst rehearsal values 3.2% / 0.20%) |
| C+ / C− individually | both expected to land inside the ±1 equivalence region |

---

## 11. Wording discipline

- ⛔ **Must not write** *generalized individuality*
- ⛔ **Must not write** that the agent "understood / learned the causal structure" — what it learns is the value of a 2-armed bandit
- ⛔ **Must not write** "we searched every carrier of history" — the task offered only one readout
- ✅ The Methods section must state: the twins share the reward table and the softmax draw `u_t`,
  which is a **common random numbers / counterfactual pairing variance reduction design**
- ✅ B must be worded as a **residual component**, never as "industry"
