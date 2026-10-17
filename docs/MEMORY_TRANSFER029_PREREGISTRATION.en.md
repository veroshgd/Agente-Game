> **NON-AUTHORITATIVE TRANSLATION — NOT HASH-VERIFIED**
>
> The authoritative preregistration for Experiment 029 is the Chinese original
> `MEMORY_TRANSFER029_PREREGISTRATION.md` in this directory. Its SHA-256
>
> ```
> 29e45930a07f2649c7958fdc0cd20a389005ca43e93287b9f69e2ccdcf867145
> ```
>
> is the value recorded in `final_029.py` (`PREREG_SHA256`) before the confirmatory
> run on seed block 80,000–81,499, and is the value cited in Appendix B.9 of the paper.
>
> This file is an English rendering provided for readability only. It is **not** referenced
> by any hash check and must **not** be used in place of the original for verification.
> If the two ever disagree, the Chinese original governs.

---

# Experiment 029 preregistration — Memory-Mediated Transfer

**Fixed on: 2026-08-18 · Status: ★ fully frozen ★ → awaiting the pre-launch check → awaiting execution**

A one-shot document. Between finishing it and finishing the run, **this file, the architecture,
the acquisition parameters, retrieval, λ, the capacity gates, the primary endpoint, the SESOI,
the reading rules, the statistical procedure and the seed block are not changed.**
They are **not changed after the run either**; results are only appended to the experiment log.

> ✅ **§6.3 is settled: CI upper bound < 0.25 (option B)**, with the conditional reading (§6.3.2)
> and the pilot-informed transparent disclosure (§6.3.1).
> **This file is fully frozen from here.** Not one seed of 80000–81499 is touched before the
> pre-launch check passes.

---

## 0. Research question

> **Can the same anomalous experience, because it later turned out differently in different
> worlds, form different relational memories; and can that memory reduce actual errors on a
> future problem that is superficially unfamiliar but structurally similar?**

Formally:

```
Can structurally relevant past experience be retrieved and causally used
to adapt to a surface-novel problem?
```

### Division of labour with 025 / 027 / 028

| Experiment | Question | Result |
|---|---|---|
| 025 / v3 | Can the past **persist**? | ✓ clearly |
| 027 | Does the personality that persists **transfer automatically**? | extremely weakly (0.08 trials) |
| 028 | Does **widening** the personality readout at equal budget rescue it? | no (G ≈ 0) |
| **029** | Can past **experience** be **retrieved** and **used causally**? | ← this experiment |

⚠ What 029 replaces is the **type of pathway**, not the bandwidth:

```
027 / 028   history → one scalar we read out on its behalf → β → exploration bonus
029         history → addressable relational entries → the agent draws on them by context → decision
```

---

## 1. ★ What is frozen (all of it frozen before this experiment runs) ★

```
architecture   memory-only. The developmental history enters the test task **only** through memory.
               body = NeutralBody (curiosity=caution=50), identical in both conditions.
               ⛔ No trait pathway is added (reasoning in §8, rule 93 final form)

acquisition    3 problems × 66 trials; ANOMALY_AT=36, ANOMALY_LEN=8, 22 trials after the anomaly
               α=0.05  τ=0.20  Q_INIT=0.5  P_HIGH/P_LOW=0.80/0.20

retrieval      stateful context window: RETRIEVE → ACTIVE → RESOLVED
               entry: Q[cur] ≥ 0.60 and a run of surprises ≥ 3 (PE < −0.30)
               exit:  Q[the other] > Q[suspect]  or  3 consecutive non-surprises on the suspect
               ★ RESOLVED is judged **after** the Q update ★ (the timing bug fixed in probe3)

interface      logit(switch) += λ · m · s     s=+1 leaving the suspect / s=−1 returning to it
               ★ MEMORY_LAMBDA = 1.00 ★ (frozen by the group-blind capacity calibration)

capacity gates SATURATION_MAX=0.05  MEDIAN_ABS_DP_MIN=0.02
               PREF_FLIP_MAX=0.25   ACTIVE_EXPOSURE_MAX=20/80 (★max, not mean★)

novel task     027's novel_task.py, not one number changed. Fingerprint 26778f672e9e7009
               80 trials, reversal at trial 41, P=0.80/0.20, which is good first randomised by seed
```

### The selection rule for λ (copy verbatim into the paper)

> Lambda was calibrated without condition labels or downstream transfer
> outcomes. Values were required to satisfy prespecified interface-capacity
> constraints on saturation, median probability shift, preference reversal,
> and retrieval exposure. Among admissible values, the log-scale midpoint of
> the admissible range was selected.

The passing band is {0.5, 1.0, 2.0}, and `1.0 = √(0.5×2)` is its log-scale centre —
**picking the value furthest from both failure directions, not the one with the largest potency**.
The code carries an assertion: if λ ceases to equal the log centre of the band, it raises.

⚠ **λ was frozen before any group transfer outcome had been seen.**
So the answer to "would a different λ have made it positive?" is: **unknown, and changing it
afterwards is not allowed.**

---

## 2. Developmental history: Stable vs Volatile (★ both sides experience surprise ★)

⛔ **The wrong approach**: "Stable never has a surprise, Volatile has many" — that would degenerate
the memory difference into "one has data, the other does not".

✅ **This design**: **the same surface phenomenon means different things.**

```
trials  0 .. 35     the original strategy p_high, the other p_low   ← identical in both conditions
trials 36 .. 43     ★both drop to p_low★                            ← **bit-identical** in both conditions
trials 44 .. 65     Stable  : the original strategy returns to p_high
                    Volatile: the other one becomes p_high
```

- The reward draws **share one random stream** across the two conditions → **bit-identical** for
  `trial < 44`. **The anomaly alone cannot tell you which world you are in**; the difference lies
  only in "what this anomaly meant".
- The first-good side of each problem is counterbalanced by seed.
- The relations learned are:
  - **Stable**: persistent surprise is sometimes just noise, **staying pays better**
  - **Volatile**: persistent surprise usually means the rule changed, **switching pays better**

### What must match (constructively, bit-equal)

```
① total trials      ② total reward opportunity      ③ first-good identity
④ pre-anomaly observations                          ⑤ task length structure
```

### ★ What explicitly does **not** match, and must not be equalised afterwards ★

- **realized reward**: lower for Volatile (it has to relearn after the change point).
  Equalising it ≈ compensating Volatile and **cancelling the cost of volatility itself**.
- **memory completeness**: unequal between the sides (see §9). Forcing it to match =
  **modifying a post-treatment mediator**.
- **episode count**: a behavioural product; simply report it.

---

## 3. Memory structure (★ rule 85: store relations, not identities ★)

```
Episode:
    context               a relational context label ("previously_good_strategy")
    previous_expectation  Q[suspect] at the start of the window
    observation           the mean return over the run of anomalies that triggered the window
    prediction_error      observation − previous_expectation
    action_relation       ★ "stay" / "switch" ★
    outcome               the return this decision obtained
```

**Storing A/B leaves nothing transferable once the task changes** — the new task has no A or B at
all. This is implemented as a **hard constraint**: `Episode.__post_init__` +
`_assert_relational_only()` raise immediately if any option identity appears in a field.

Read-out:

```
m = E[R | switch, similar past] − E[R | stay, similar past]
no entries on either side → m = 0 (no evidence, not "evidence of zero difference")
```

⚠ `suspect` is a **working variable** at decision time, not an Episode field.

---

## 4. ★ Primary endpoint: ΔC ★

```
C_i = Σ_{t=40..79} 1( choice_t ≠ correct_option_t )     how many wrong choices after the rule changes
ΔC  = C(Volatile-history) − C(Stable-history)           same-seed paired
ΔC < 0  ⇔  a Volatile-type memory helps more
```

`C = 40 × (1 − post-reversal accuracy)`; the identity is written as an assertion.

### Why not switch latency (★ rule 89 ★)

The exit condition of `ACTIVE` ≈ "Q proves the new strategy is better", while restricted switch
latency ≈ "the new strategy begins to dominate stably" — **they overlap by construction**.
**The primary endpoint must not overlap with the mechanism's own active window.**
Latency is retained as a secondary mechanistic measure.

The advantages of ΔC: the window is fixed in advance by the task / it does not read ACTIVE or
RESOLVED / there is no never-switch censoring / **every agent has it** / its unit is trials / it
measures the actual functional cost.

### ★ SESOI = 1.0 post-change error ★

That is: **one fewer mistake** within the fixed 40 post-change trials, equivalent to
`1/40 = 2.5%` of post-change accuracy.

Reasons:
- consistent with the **1-trial functional unit** used in 027 / 028, rather than inventing a 0.5
  or 0.75 on the spot;
- the development rehearsal **has already shown ΔC = −0.927**, so setting the threshold at 1.0
  **does not** retro-package the development result as a "functional success" — quite the
  opposite: under this threshold the development result counts only as
  *statistically detectable / directionally strong, with functional significance not established*.

### ★ Three-way reading (95% CI, two-sided) ★

| Case | Verdict |
|---|---|
| the CI **contains 0** | **No evidence of memory-mediated transfer.** |
| the CI lies entirely **< 0** but has not cleared **−1** | **Detectable memory-mediated transfer, but functional significance not established.** |
| the CI lies **entirely < −1** | **Functionally meaningful memory-mediated transfer established.** |
| the CI lies entirely **> 0** | clearly transfer in the **opposite / harmful** direction; write it as such |

(The development rehearsal's `[−1.202, −0.677]` falls into the second row.)

---

## 5. Secondary mechanistic

```
restricted switch latency (censoring as in 027: 0–35 real values, 36 = never switched within the window)
retrieval exposure (potential defined on the λ=0 trajectory / realized on the official trajectory)
per-opportunity potency Δp
ACTIVE duration
```

⚠ **Rule 88**: `potential` and `realized` must be reported separately, and it is **never**
permitted to analyse only the agents that "successfully recalled a memory".

---

## 6. ★ Confirmatory mechanistic control: SHUFFLE ★

### 6.1 Definition

Shuffle `action_relation` **within each agent's own entries**:

```
preserved: the episode count, the counts of stay and switch, the marginal distribution of outcome
destroyed: the **relation** between action and outcome
```

The question: **is what works the relational structure, or the marginal statistics of the memory store?**

### ★ The permutation rule and salt are frozen (fixed in writing before FINAL) ★

```
rng = random.Random( SHUFFLE_SALT ^ seed ^ (len(episodes) << 8) )
rng.shuffle(relations)                     SHUFFLE_SALT = 0x29C10
```

⛔ Generating a new shuffle scheme on the spot during the FINAL run is **forbidden**.
The same `(seed, len(episodes))` must always produce the same permutation (written as a
deterministic self-check in the runner).

### 6.2 The statistic: retention ratio

```
R = |ΔC_SHUFFLE| / |ΔC_OWN|
```

**joint same-seed bootstrap**: each replicate resamples **one** set of seed indices shared by both
arms, and **abs and division are applied per replicate** (the lesson of 028: taking the means
separately and then applying the non-linearity, or dividing the endpoints of two marginal CIs, are
both wrong).

⚠ **Rule 84**: `R` is always ≥ 0, so "the CI excludes 0" carries no information.
The criterion looks **only at the upper bound** against 0.25.

### 6.3 ★ Criterion: CI upper bound < 0.25 (option B, settled) ★

```
criterion:  CI_97.5%( R )  <  0.25
```

⛔ "point estimate < 0.25" is **not used**. Requiring only the point estimate would let the
sentence "**at least 75% of the transfer is destroyed**" be stated **more strongly than the
evidence**. Since what we really want to claim is "once the relational structure is destroyed,
most of the transfer disappears", **the uncertainty itself must support that sentence too**.

### 6.3.1 ⚠ Transparent disclosure (must go into the results and the paper) ⚠

Measured in the development rehearsal (n=400):

```
R = 0.094      95% CI [0.005, 0.261]
```

Under this criterion, the honest way to write the development data is:

> **point estimate strongly supports collapse, but the rehearsal sample is
> insufficient to establish ≥75% attenuation with 95% confidence.**

It is **not** "we just missed it, so we switch to option A".

The following must be written alongside the results:

> **The CI-upper interpretation in §6.3 was finalized after observing the
> development rehearsal retention estimate R = 0.094, 95% CI [0.005, 0.261],
> but before any observation from the confirmatory seed block.**

That is: 029 remains **prospective** with respect to FINAL, but **this mechanistic criterion is
explicitly pilot-informed**, and must not be presented as if it predated the rehearsal.

(A power-scale check: scaling the same 400-seed joint per-seed empirical distribution up to
N=1500, the ratio CI is expected to shrink to about `[0.014, 0.182]`. **This is not a guarantee
about FINAL**; it only shows that at N=1500, option B is not an absurdly strict gate doomed to
fail.)

### 6.3.2 ★★ Conditional reading (no SHUFFLE verdict when the denominator is unidentifiable) ★★

If FINAL's `ΔC_OWN ≈ 0`, then the denominator of `R` approaches 0 and the ratio becomes unstable
or explodes. **In that case "SHUFFLE control failed" must not be said** — there is simply no OWN
transfer to ask "how much was retained" about.

> **The SHUFFLE retention criterion is interpreted only if the OWN primary
> effect shows evidence of transfer (its 95% CI excludes 0 in the preregistered
> direction). If OWN does not establish transfer, the retention ratio is
> reported descriptively but no relational-mediation claim is evaluated.**

```
OWN CI contains 0 (or points the other way)
    → the primary does not hold
    → R is reported descriptively only
    → ⛔ no verdict of "relation retained / destroyed"

OWN CI lies entirely < 0
    → only then does the SHUFFLE mechanism gate apply
    → CI_97.5%(R) < 0.25 is required to support "≥75% attenuation"
```

**This clause is fixed in writing before FINAL is seen.**

## 7. Seed-coupling control: XSEED-DONOR

Seed s uses the **same-condition** memory of **another seed**.

The question: **is the effect caused by the coupling of "development and test sharing one seed"?**

### ★ The donor mapping is frozen (fixed before FINAL, never decided on the spot) ★

```
donor_index(i) = (i + N // 2) % N          deterministic half-block rotation
FINAL: N = 1500  →  donor_index(i) = (i + 750) % 1500
rehearsal: N = 400 →  (i + 200) % 400      (the same rule)
```

It must satisfy (written as assertions in the runner):

```
① no self-donor: ∀i, donor_index(i) ≠ i
② a bijection
③ Stable and Volatile use **the same** donor permutation
④ ⛔ donors must not be chosen on the basis of any memory / outcome
```

Expectation: largely retained (the development rehearsal retained **96.0%** of OWN).

⚠ Naming discipline: **it is not called SWAP-XS**. It asks a different question from SWAP.

---

## 8. ★ Integrity assertions: DELETE and within-seed SWAP ★

```
DELETE   both conditions use an empty store → identical trial by trial → ΔC ≡ 0
SWAP     the two conditions' memories are exchanged → ΔC ≡ −ΔC(OWN)
```

Under a memory-only architecture both hold **by construction**.
They are run **as assertions** (a mismatch voids the whole batch) and are **not reported as
scientific evidence**.

> ### ★ Rule 93 (final form) ★
> When memory is the sole developmental pathway into the test task, DELETE and
> within-seed SWAP are **algebraic integrity checks rather than independent
> causal evidence**. A second developmental pathway should **not** be introduced
> merely to make these controls non-trivial; causal support should instead come
> from **interventions on memory structure** such as relational shuffling and
> cross-seed donor tests.

⛔ The trait pathway **must not** be added back just to make SWAP "non-trivial". That would turn
the clean `history → relational memory → novel adaptation` back into
`history → memory + traits → …`, bringing back memory/trait competition, interaction and budget —
i.e. the whole 027/028 apparatus.
**029's goal is not to prove that "memory matters more than personality".**

---

## 9. ★ The convention for the extensive margin (frozen) ★

```
primary extensive margin  =  P( relational memory COMPLETE )
                             complete := at least one stay entry and at least one switch entry
```

Measured on the development block: **Stable 65.75% / Volatile 73.25%**

Also reported (**reportable, but must not be called extensive / availability**):

```
non-zero evidence rate     Stable 64.25% / Volatile 73.25%
```

The difference comes from **6 Stable agents (1.5%) that have entries on both sides but whose two
means happen to be exactly equal → m = 0**.

> ⚠ They have **not "failed to form a memory"**. They formed a **complete** relational memory
> which simply tells them "**switching and staying made no difference in the past**" —
> that is **meaningful zero evidence**. Calling `m ≠ 0` memory availability would misclassify
> "formed a neutral experience" as "has no memory".

### ★ Rule 91 (unchanged) ★

> Memory availability is itself a developmental outcome. Do not condition
> transfer or calibration on successful memory formation. Report the extensive
> margin (P[m usable]) and intensive margin (m | usable) separately, but all
> primary analyses use the full predefined population.

**Every primary transfer analysis uses all predefined agents, including incomplete ones and m = 0.**

---

## 10. Statistical procedure

```
pairing        per seed d_i = C_Volatile,i − C_Stable,i (same-seed twins)
primary        mean(d_i)
CI             cluster bootstrap by seed, 10,000 times, 95%
R              joint same-seed bootstrap 10,000 times, abs and division applied per replicate
analysis seed  8181 (fixed, persisted)
```

⚠ The twins share the novel task's reward table and the softmax draw `u_t` — this is a
**common random numbers / counterfactual pairing variance reduction design**, **not** a pretence
that two agents share random numbers in reality. It must be stated in the Methods.

### Applying rule 56 (decidability) in advance

"Does the CI clear −1" is another bright line. **At the rehearsal stage** (on burned seeds) it must
be re-run with 8 analysis random seeds; if the verdict would be decided by the analysis random
seed, a three-valued verdict with a boundary width of ≥10 × the measured MC SD must be written in
**before FINAL is run**. **Never afterwards.**

---

## 11. ★ Validity gates (reading order: before the outcome) ★

Executed in order; **ΔC may only be computed once all of them pass**:

### G1 acquisition manipulation check (constructive)

```
bit-identical across the two conditions for trial < 44          must hold
total trials / total reward opportunity / first-good side       must be bit-equal
```

### G2 interface capacity transport (★ group-blind ★)

Recompute the empirical m distribution on the **FINAL block** (**pooled, m=0 included, sorted,
label discarded**), and recompute the four capacity readings on the λ=0 frozen decision states:

```
P(saturated after push) ≤ 0.05     median|Δp| ≥ 0.02
P(preference flip) ≤ 0.25          max(realized exposure @ m10/m50/m90) ≤ 20/80
```

⚠ This step **cannot** leak the grouping: the label is discarded at the input.

**The fixed wording on failure:**

> Interface capacity calibrated on the development block did not transport to
> the confirmatory population; the memory channel is not cleanly interpretable
> under the preregistered capacity constraints.

⛔ A gate failure **must not** lead to re-estimating λ.

### G3 integrity assertions

```
DELETE ΔC ≡ 0 (per seed)        SWAP ΔC ≡ −ΔC(OWN) (per seed)
```

Either failing → **the whole batch is void** (it would mean the developmental history has a
leakage path besides memory).

---

## 12. ★ Seed ledger and the FINAL block ★

```
0–1499          development (every 029 probe, calibration and rehearsal lives in 0–399)
10000–11499     021 holdout set / 028 transport rehearsal
20000–21499     022 preregistration block / 027 + 028 group-blind calibration
50000–51499     v3 / 025 persistence FINAL
60000–61499     027 novel-task FINAL
70000–71499     028 breadth FINAL
80000–81499     ★ 029 FINAL ★
```

### The 029 FINAL CONFIRMATORY BLOCK

```
seed0 = 80000     N = 1500     seeds = 80000–81499
```

- **for Experiment 029 FINAL only**
- **forbidden** for calibration / transport / rehearsal / parameter selection
- **once any agent trajectory has been officially generated, the block counts as burned**

Verified: throughout the repository and the experiment log, `80000` appears only in notes of the
"untouched / do not touch / reserved" kind, and **no simulation path has ever used this block**.

### Engineering protections (the runner must implement these, following 028's set)

1. **Seed guard** — `--final` accepts only `seed0=80000, N=1500` and rejects anything else outright
2. **One-shot lock** — once `final_029_STARTED.lock` is created, **that seed block is permanently
   burned even if the run subsequently crashes**; if `final_029_result.txt` already exists, refuse
   to run again
3. **Preflight ledger print** — print and persist the full seed ledger before starting
4. the task fingerprint `26778f672e9e7009` + the frozen-constant check, refusing to run on any mismatch
5. persist `MEMORY_LAMBDA`, the four gate values, the analysis seed, and the sha256 of each module

---

## 13. ★★ Closure rule ★★

> **Once the Stable/Volatile result of 80000–81499 has been seen, none of the following may be changed:**
> the architecture (memory-only / NeutralBody), the acquisition parameters, the retrieval rules,
> λ, the capacity gates, the primary endpoint, the SESOI, the three-way reading, the SHUFFLE
> criterion, the XSEED-DONOR definition, the extensive-margin convention, the statistical
> procedure, the seed block.
>
> **If the primary fails, it fails.**

Exploratory analysis after a failure is allowed, but **may only be labelled exploratory**.

---

## 14. Prior predictions (written before the run, copied verbatim for comparison afterwards)

| Item | Prediction |
|---|---|
| ΔC direction | predicted **< 0** (a Volatile-type memory helps more) — a **directional** prediction, unlike the two-sided ones of 027/028 |
| Does ΔC clear SESOI = 1.0 | **unknown** — the only genuinely unknown item in this experiment. The development block's −0.927 sits just under the threshold |
| G1 / G3 | must pass (constructive + already passing on the development block) |
| G2 capacity transport | expected to pass (all four items have margin on the development block) |
| SHUFFLE R | point estimate expected ≈ 0.1; whether the CI upper bound clears 0.25 is **not assumed** (the power-scale check suggests about `[0.014, 0.182]` at N=1500, but that is no guarantee) |
| the case ΔC_OWN ≈ 0 | then, per §6.3.2, **no SHUFFLE verdict** is given and R is reported descriptively |
| XSEED-DONOR | expected to retain ≥ 80% of OWN |
| memory completeness | expected Stable ≈ 66%, Volatile ≈ 73% |

---

## 15. Wording discipline

- ⛔ **Must not write** *analogical reasoning* / that the agent "understood the structure / understood the causality"
- ⛔ **Must not write** *generalized individuality*
- ⛔ **Must not** present DELETE / within-seed SWAP as causal evidence (rule 93)
- ⛔ **Must not** call `m ≠ 0` memory availability (§9)
- ⛔ **Must not** report the complete-only separation alone (rule 91)
- ✅ May write: **retrieval-conditioned adaptation to a surface-novel task**
- ✅ May write: **memory-mediated transfer** (if the primary is met)
- ✅ The Methods section must explain the common-random-numbers variance reduction design
- ✅ It must be stated that λ was frozen by a group-blind capacity calibration, with the selection
  rule quoted verbatim

---

## Appendix: how 029 relates to 027/028 (goes into the Discussion)

027 + 028 have already established:

> **Persistent individuality ≠ automatically functional generalization.**

029 **does not overturn** that; it replaces the question. Instead of asking "will the personality
shaped by the past magically help with any new problem", it rigorously tests one specific
mechanism —

> whether the same anomalous experience, because it later turned out differently in different
> worlds, can form different **relational memories**; and whether that memory can **reduce actual
> errors** on a future problem that is **superficially unfamiliar but structurally similar**.

If 029 also comes out ≈ 0, the core proposition is **strengthened** into "even when given a
genuine episodic retrieval channel whose interface capacity has been independently calibrated as
sufficient, persistent individual differences still carry almost no replicable functional
transfer". **Both directions are informative** — this paragraph is fixed in writing before the
numbers are run, to prevent going back and changing the design in order to obtain a positive.
