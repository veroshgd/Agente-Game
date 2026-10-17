# 027 preregistration · amendment 01

**Created after the rehearsal and before inspecting the final seed block 60000–61499.**

> Amendment created after rehearsal but before inspection of final seeds
> 60000–61499. Rehearsal rich/poor contrasts had been observed. The SESOI
> was determined from the pooled latency scale and task-native unit, not
> from the between-history rehearsal contrast. The original statistical H2
> criterion is retained; this amendment adds a separate practical-
> significance interpretation using a ±1 trial equivalence region.

⚠ **Not one word of the original `NOVEL_TASK_PREREGISTRATION.md` is changed** (it states that it
is a one-shot document). This file is a **transparent pre-final amendment** and **does not
pretend to be part of the original preregistration**.

---

## A. Added: SESOI = 1.0 trial, as a ±1 practical-equivalence region

### Why it is needed

§4 of the original preregistration wrote only "the 95% CI excludes 0". At N=1500:

```
pooled restricted latency (range 0–36): mean 18.04   SD 8.15
SE of the paired difference ≈ 0.30  →  on precision alone, |Δ| ≈ 0.58 trials already comes out "significant"
```

**0.58 trials is only 1.6% of the 0–36 range.** Reading only "the CI excludes 0" could declare a
statistically significant but functionally meaningless difference to be a success for 027.

### The basis for SESOI = 1.0 trial (**unrelated to the rich/poor contrast**)

- **1 trial is the smallest natural unit of latency** (the task's own scale)
- relative to the pooled mean of 18.04 it is ≈ **5.5%**
- relative to the pooled SD of 8.15 it is ≈ **0.12 SD**
- clearly above the ~0.58 trial detection capability that precision alone gives at N=1500

### Three-valued verdict (★replacing the original two-valued verdict★)

| Case | Verdict |
|---|---|
| the 95% CI **contains 0** | **H2 unsupported** |
| the CI **excludes 0** but still overlaps **[−1, +1]** | **a history effect exists statistically, but functional significance is not established** |
| the CI lies **entirely > +1** or **entirely < −1** | **functionally meaningful reversal-transfer established** |

⚠ The formulation "the CI excludes 0 **and** the point estimate \|Δ\| ≥ 1.0" is **not used**.
Counterexample: `Δ = 1.05, CI = [0.20, 1.90]` — the point estimate crosses the line, but the CI
allows a true value of only 0.2 trials, so **there is no confidence that it exceeds the functional
threshold**. An equivalence region is the clean way to say it.

**The original statistical criterion (CI excludes 0) is retained**; this amendment only **adds** a
layer of functional-significance interpretation.

---

## B. Requalification of controls three / four

### The original wording is withdrawn

> ~~Control four: if the main effect remains → there is another carrier of history~~ ★withdrawn★

**Under the current task that is impossible by construction.** The only path by which history
enters the task is

```
history → curiosity / caution → novelty_style → beta_i
```

so "history-blind switches that entrance off" and "trait-levelling equalises both ends of the
entrance" are **equivalent by construction** on the question of whether rich/poor can still
produce a difference. The rehearsal measured **both as exactly zero**, for exactly that reason —
not because "we searched every carrier and found only traits".

### The new qualification: pathway-isolation / leakage controls

Both tests are **kept**, because they check **different implementation layers**:

| Control | What it checks |
|---|---|
| history-blind | whether any signal still leaks once the history channel is switched off **inside** NovelTask |
| trait-levelling | whether the task result goes to zero once the sole input difference is removed **on the agent-state side** |

As engineering they are not duplicate tests; **as scientific evidence they cannot count as two
independent negative controls.**

### What may / may not be said

- ✅ If main is effective and both pathway-isolation controls go to zero:
  **the history effect observed in 027 entered the new task, as designed, via the novelty style
  defined by curiosity/caution.**
- ⛔ **Must not be said**: "we searched every carrier of history and found only traits."
  The experiment **never gave any other carrier a chance to enter the task**.

---

## C. Correction to the record: the rehearsal attrition figures

`final_027_rehearsal.txt` is the sole authoritative record:

```
attrition rich=0.0000  poor=0.0367  keep=0.9633   n=289/300
```

⚠ At one point in conversation these were reported as "rich 3.33% / poor 4.00%" — **those two
numbers are wrong**, written while the output was truncated by `tail` and that line had not
actually been seen.
**There are not two conventions**: the file is right, the spoken figures were wrong, and there is
no supersede relationship.

> ### ★ Rule 78: not a single number may go into a report unless it was seen with one's own eyes ★
> When output is truncated by `tail` / `head`, **go back and fetch that line** rather than filling
> in a plausible-looking value. Errors of this kind are almost undetectable elsewhere — this one
> was caught only by reconciling against the log.

---

## D. What this amendment does **not** change

`α = 0.05`, `β = 0.05`, `τ = 0.20`, the reward probabilities, the number of trials, the reversal
point, the H1/H2 endpoints, the censoring rule (None → 36), the validity gate (90%), the
statistical procedure (cluster bootstrap 10,000 + paired sign permutation 10,000), and the
closure rule (§8) — **all left untouched.**
