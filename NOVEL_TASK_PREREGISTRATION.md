# Experiment 027 preregistration — Novel-Task Transfer + Reversal

**Fixed on: 2026-08-17 · Status: awaiting rehearsal → awaiting execution**

A one-shot document. Between finishing it and finishing the run, **this file, the task
parameters and the model are not changed**. They are **not changed after the run either**;
results are only appended to the experiment log.

---

## 0. The model and what is frozen

**v4 = the core of `v3_frozen/` (byte-for-byte untouched) + `novel_task.py`**

`novel_task.py` **modifies no line of `v3_frozen/`** and **does not touch agent state within the
first 60 days**, so "with NovelTask off, v4 is tick-for-tick identical to v3" holds **by
construction** (it is still written as a regression test, see control one in §5).

### Task configuration (frozen by the group-blind calibration)

```
α (learning rate)         = 0.05     identical for every agent
β (uncertainty bonus)     = 0.05     ★the only knob through which history enters★
τ (softmax temperature)   = 0.20     identical for every agent; not a history channel
TRIALS = 80   REVERSAL_AT = 40   P_HIGH/P_LOW = 0.80/0.20   Q_INIT = 0.5

configuration fingerprint config_fingerprint() = 26778f672e9e7009
```

`assert_frozen()` is a hard stop before every official run, and the fingerprint is persisted
alongside the results. **The defaults already equal the frozen values** — so even if the runner
forgets to pass them explicitly, it cannot run the wrong version.

---

## 1. Research question

> Two agents with identical starting points, different pasts, and an already-established
> persistent difference: when facing for the first time a **new task neither has ever seen**,
> will their different pasts make them **learn differently / choose differently / adapt along
> different paths**?

### The procedure

```
30 days of development (rich / barren) → 30 days of common garden → level the body state
→ enter the new task: two options A / B that never existed before, 80 trials
   trials 1–40   good option 80% / bad option 20% (which is good first is randomised by seed)
   trial 41      ★the rule suddenly reverses★
   trials 41–80  the other way round
```

### The single entrance for history

```
novelty_style = (curiosity − caution + 100) / 200 ∈ [0,1]
beta_i        = β × novelty_style_i
value(x)      = Q_x + beta_i / sqrt(1 + N_x)
choice        ~ softmax(value / τ), decided by the shared u_t
```

**The past is not allowed to decide whether A or B is good.** The learning rate α, the
temperature τ and the reward table are exactly the same for every agent.

---

## 2. ★ Primary hypothesis H2 — Reversal adaptation ★

> **H2: developmental history alters adaptation to reversal in a jointly novel task.**

**Primary endpoint = restricted switch latency.**

```
switch latency = the first trial t after the reversal such that within [t, t+5) the new correct
                 option is chosen ≥4 times
maximum detectable value = 35
never switching within the whole observation period → censored to 36
```

⚠ **36 does not mean "it switched on trial 36"; it means "it never switched within the window".**
This censoring rule is fixed in writing before the run, because:

- **dropping never-switchers** → creates selection (if one arm has more never-switchers, the
  effect would be quietly erased)
- **treating them as 0** → mistakes "never switched" for "switched immediately", the exact
  opposite direction
- **switching to a survival model afterwards** → that is choosing the statistical method after
  seeing the result

(Calibration measured never-switch at only **2.0%**, so the censoring will not dominate the
result, but it is fixed in advance anyway.)

### Statistics

```
per seed    d_i = L_rich,i − L_poor,i        (same-seed twin pairing)
primary     mean(d_i)
CI          cluster bootstrap by seed, 10,000 times, 95%
p           same-seed paired sign permutation, 10,000 times
```

**H2 is two-sided**: a 95% CI excluding 0 → developmental history alters reversal adaptation
latency. **rich faster, poor faster, or no difference — all three outcomes are accepted.**
⛔ **No direction is assumed.**

---

## 3. Secondary confirmatory H1 — Novel-task transfer

> **H1: developmental history already alters behavior during initial acquisition of the novel task.**

**Endpoint = the exploration rate on trials 1–10**
("exploration" = choosing the option with the lower current Q). The first 10 trials are chosen
because that is the moment the agent is **genuinely facing unfamiliar options for the first time**.

Same-seed pairing + cluster bootstrap + sign permutation, two-sided, as above.

> ### ⛔ H1 is secondary and must not substitute for the primary ⛔
> **This must not happen**: "H2 not significant → H1 significant → declare 027 a success".
> H2 is the sole primary endpoint.

---

## 4. Criteria

| Criterion | Content |
|---|---|
| **H2 (primary)** | the paired difference in restricted switch latency, 95% CI excluding 0 |
| **H1 (secondary)** | the paired difference in the trial 1–10 exploration rate, 95% CI excluding 0 |
| **validity gate** | see §6; failing it means validity compromised and no strong conclusion |
| **four controls** | see §5; failing any one voids the whole batch |

### ⚠ Applying rule 56 (decidability) in advance

`CI excluding 0` is another bright line. **At the rehearsal stage** (on burned seeds) it must be
re-run with 8 analysis random seeds, and if the verdict turns out to be decided by the random
seed, it must be changed **before the final run** into a three-valued verdict (pass / fail /
on the detection boundary, undecidable), with the boundary width set to ≥10 × the measured MC SD.
**Never changed afterwards.**

---

## 5. The four controls (failing any one = the whole batch is void)

1. **v3 equivalence control** — with NovelTask off, the first 60 days are bit-identical to frozen
   v3; the task must not write back any existing agent state.
2. **identical-agent control** — two clones of the same day-60 snapshot + the same reward table
   → must be **identical trial by trial**. Otherwise there is an RNG / shared-reference leak.
3. **history-blind control** — switch off the influence of curiosity/caution on β (beta fixed at
   its median) while learning proceeds as usual.
   **If the task trajectories of the two histories still differ systematically → there is an
   undiscovered channel.**
4. **trait-levelling control** — at the task entrance, make rich/poor curiosity and caution equal
   while **keeping everything else about their history**.
   - the main effect **disappears** → confirms the mechanism `past → trait → new-task behaviour`
   - the main effect **remains** → there is another carrier of history (a finding, not a failure)

---

## 6. ★ Validity gate: pre-task paired attrition ★

NovelTask itself never touches survival, but the agents entering the task have still been
filtered by the first 60 days of v3. So:

- **only seeds where both rich and poor survive to task entry enter the primary paired analysis**
  (the same-seed twin intersection)
- **must be reported separately**: rich pre-task mortality, poor pre-task mortality, and the
  number of paired exclusions
- **the gate**: if fewer than **90% of the 1500 final seeds yield valid twins**, the verdict is
  **validity compromised, and no strong conclusion is drawn**

(At the calibration stage 600 → 589, a loss of about 1.8%, so 10% is not expected to be
approached. Locked in advance.)

---

## 7. Seeds

```
development / calibration / rehearsal   20000–21499 and other burned blocks
★ FINAL ★                               60000–61499 (N=1500) — never used, run once
```

Blocks that are contaminated and must not serve as the final: `0–1499`, `10000–11499`,
`20000–21499`, `50000–51499`.

---

## 8. ★★ Closure rule ★★

> **Once the rich/poor result of 60000–61499 has been seen, none of the following may be changed:**
> reward probabilities, reversal time, learning rate α, softmax temperature τ, trait coupling β,
> the primary metric, task length, the censoring rule, the statistical procedure.
>
> **If the primary test fails, it fails.**

Exploratory analysis after a failure is allowed, but it **may only be labelled exploratory** and
must not be packaged as a new confirmation.

---

## 9. Prior predictions (written before the run, copied verbatim for comparison afterwards)

| Criterion | Prediction |
|---|---|
| H2 direction | **not assumed** (two-sided) |
| Is H2 significant | **unknown** — the only genuinely unknown item in this experiment |
| H1 | leaning towards a difference (novelty_style enters β directly), but two-sided as well |
| controls 1/2 | must pass (already passing in the self-check) |
| control 3 | with beta fixed, the two arms should show no systematic difference |
| control 4 | if the mechanism is as designed, the main effect should **weaken substantially** |
| valid-twin rate | > 95% |

---

## 10. Wording discipline (the line holds even on success)

- ✅ May be written: **developmental history transferred to learning and adaptation in a jointly
  novel task**
- ⛔ **Must not be written**: *generalized individuality* —
  this task **deliberately builds in** the interface `curiosity/caution → exploration bonus`, and
  what it measures is "whether one pre-specified general exploration interface can carry a
  historical difference into a new task", **not** "individuality generalizes automatically to any
  unknown problem you care to pose".
  Upgrading the wording requires a **second, structurally different task** to replicate it (028).
- ⛔ **Must not be written**: that the agent "understood / learned the causal structure of the
  world" — what it learns is **the value of a 2-armed bandit**.
- **The Methods section must state proactively**: the rich/poor twins share one reward table and
  one softmax draw `u_t`, which is a **common random numbers / counterfactual pairing variance
  reduction design**, **not** a pretence that two agents share random numbers in reality.
  (An independent-choice-noise secondary robustness analysis may be preregistered, but it is
  **not** a necessary condition for the primary to hold.)
