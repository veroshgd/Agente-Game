# NOVEL-SITUATION experiment design v3 (**settled direction → entering group-blind calibration**)

Status: the design has converged. **`60000–61499` untouched, `v3_frozen/` unmodified.**
Next step: write `novel_situation.py` + `novel_calibrate.py` and calibrate on `20000+`.
Basis for v2 → v3: all numeric values settled + **rule 61** (change log in §10).

---

## 0. Architectural scope (goes into the preregistration)

v3's action selection is `score(action)` = a weighted sum of "state + traits + goal +
landmark/knowledge", with **no online causal learning mechanism**. The strongest thing this
experiment can answer is:

> whether the **existing internal structure** shaped by different pasts, when placed into an
> environmental structure that never existed in its training history, produces systematically
> different **decisions and consequences**.

It **cannot** answer "does a different past bring different **learning**" (that needs v4).
**The model is not extended at this stage.**

### Wording discipline

- **Must not write**: "adapting to the frozen ground requires understanding: gather material →
  build a house → only then forage". v3 discovers no rule whatsoever.
  **Correct**: the new environment **projects** existing internal differences onto a strategy fork
  that did not exist in the training history.
- **Must not write**: "the information carried by history is not a function of `B_familiar`".
  **The only admissible wording**: *History carries predictive information not captured by the
  preregistered familiar-behavior representation and model class.*

---

## 1. ★★ Rule 61: counterfactual sibling branches ★★

**This is the most important item in the whole design, far more so than whether the RF uses 8
layers or 12.**

### Not like this (v2's implicit approach, which is wrong)

```
agent → run W days in the familiar world, measure B_familiar → then enter the frozen ground, measure B_novel
```

**Because those W days of familiar measurement are themselves an extra stretch of experience**,
which keeps changing traits / goal / trait_floor / knowledge / hardship.
By the time it enters the frozen ground, what you are predicting is **no longer "one historical
state facing two futures"**.

### It must be like this

```
              end of development
                     ↓
                 state levelling
                     ↓
              complete snapshot (including RNG)
                  ↙        ↘
             clone F        clone N
          familiar world   novel world
                ↓              ↓
            B_familiar      B_novel
```

- At the **instant of forking**, the two clones have identical complete executable state **and
  identical RNG state**.
- **Nothing that happens in either branch afterwards may feed back into the other** (no shared
  references after `copy.deepcopy`).
- Both branches run for **the same length W**, on the same window convention, so that
  `B_familiar` and `B_novel` are comparable.

⚠ Implementation trap (hit in 024): `FrozenZero` is a `dict` subclass whose `__setitem__` is a
no-op, so `deepcopy` rebuilds it through `__setitem__` → it produces an **empty dict** →
`KeyError`. `FrozenZero()` must be rebuilt after forking (it carries no state, so rebuilding is
equivalent).

---

## 1b. ★★ Rule 62: the behaviour window and the consequence window must be separated ★★

### The problem

Calibration allows nearly 20% of the novel probe to die. But G1 predicts a **7-dimensional action
share**. If one ball dies on day 8 and another survives the whole window:

```
A: only 8 days of behaviour observed        B: 30 days of behaviour observed
```

- **Dropping the dead** → creates **survivor selection** again, which is exactly what the
  persistence stage spent a great many experiments cleaning out (rule 44).
- **Using the behaviour up to death directly** → **the observation windows have different
  lengths**, so the shares are not comparable; and death itself may be caused by the rich/poor
  history → G1 would mix **"who lives longer"** with **"how decisions are made"**.

### The structure

```
enter the novel world
      ↓
[decision window] W_dec days  ——  compute B_novel → G1 (behaviour)
      ↓
keep running
      ↓
[consequence window] run to the end  ——  survival / food / shelter / condition → G2 (consequences)
```

- **G1 uses the decision window only**, and calibration must guarantee **pooled survival ≥ 95%**
  inside that window.
- **G2 is what uses the long window** for mortality and resource consequences.
- **Defining G1 by "analysing survivors only" is forbidden.**

> G1 measures "**how it chooses when facing an unfamiliar situation**";
> G2 measures "**what consequences those choices later produce**". **These two must not be mixed.**

`B_familiar` likewise takes only the decision window (both branches equal in length, rule 61), and
both branches then run on into the consequence window — the familiar branch's consequences are the
yoked control baseline for G2.

### `W_dec` is not chosen by intuition either (it gets the same treatment as S / λ)

The candidate set `W_dec ∈ {5, 7, 10, 14}` days is fixed in writing first, then chosen
**group-blind** on `20000+`.

## 2. Two structurally orthogonal probes (fixed; adding more afterwards is forbidden)

**Both passing G1 → only then may *generalized individuality* be used;
only one passing → only *novel-context transfer* may be written.**

### Probe A — "frozen ground" (N1: a precondition gate)

`world.food` is **accessible** only while `agent.shelter ≥ S`.

> ### ★ Rule 60: it must be a non-destructive gate ★
> **`world.food = 0` must never be written.** `World.take_food` deducts from the **stock**
> (`sim.py:181-186`), so zeroing it burns the world's food store every tick and regrows it from 0
> the next — that is "destroy the food if shelter is insufficient", not "the food exists but
> cannot be reached". **They are different physics.**
>
> ```python
> class GatedWorld(sim.World):          # an experiment-layer subclass; v3 is not modified
>     def take_food(self, rng):
>         if self.agent.shelter >= self.gate_S:
>             return super().take_food(rng)
>         if self.food >= 1:            # the same sampling condition as v3, keeping the random stream aligned
>             rng.random()              # the gate changes affordance only and adds no extra perturbation to the RNG
>         return 0
> ```
>
> `self.agent` is bound when the world is swapped → `shelter` is read **at call time**, with
> **no one-tick lag**, and Probe A needs no influence at all.
>
> The general lesson: **when temporarily restricting a variable with stock semantics, do not
> rewrite the stock; change the access rule.**

Source of the strategy fork: the yield of `explore` goes through `EXPLORE_FOOD_YIELD` and
**does not pass through `world.food`** (`sim.py:886`) → both "build a house → forage normally"
and "keep exploring" are survivable routes.

### Probe B — "saline soil" (N2: zero-sum coupling)

`gather_material` additionally costs `world.food`; `gather_food` additionally costs `agent.shelter`.

**One-dimensional λ calibration** (in a two-dimensional space "minimum coupling strength" has no
unique meaning):

```
c_f = λ × k_food       k_food    = the yield of one gather_food = 1     (sim.py:185)
c_s = λ × k_shelter    k_shelter = the shelter increment of one build = 22 (sim.py:882)
```

The meaning of λ reads symmetrically: **one material gather = destroying λ foraging harvests;
one foraging = destroying λ builds' worth of progress.** Calibration looks for the **first** value
among `λ = 0.1, 0.2, 0.3 …` that satisfies the pooled criteria.

The implementation has a **one-tick lag** (influences run before `agent.tick()`) — **stated
plainly in the paper**. `explore` neither consumes material nor loses shelter → the third route is
preserved.

### Orthogonality
A = **gating / precondition** (unlocked once a threshold is met); B = **zero-sum trade-off** (one
gains as the other loses). Different causal topologies.

---

## 3. Features, target and loss (★ settled in v3 ★)

### `B_familiar` = **182 dimensions** (deliberately giving M0 the advantage)

| Dimensions | Contents |
|---|---|
| 168 | the **complete action-share matrix** of 24 hours × 7 actions (normalised within each hour) |
| 7 | the whole-window action shares |
| 7 | the change in action share, **second half − first half** |

The last 14 are **deterministic summaries** of the 168 / of the raw behaviour record and
**introduce no new information**; they merely make it easier for the RF to read information that
is already there ("what it does at what hour" + "is behaviour still drifting in a familiar
environment").

> **Why not 7 dimensions**: one reviewer sentence —
> "history is only restoring the circadian / temporal information you compressed away yourself" —
> would be unanswerable. 182 dimensions make G1 harder to pass, **but harder to dismiss once passed**.

### `B_novel` = **the 7-dimensional action-share distribution** (primary target)

That is: 182 dimensions of familiar behaviour → predicting a 7-dimensional novel strategy profile.
**M0 is deliberately given the advantage.**

### Loss = TV distance (continuing the project's usual behavioural metric)

```
L(p, p̂) = ½ Σ_{a=1..7} |p_a − p̂_a|

d_i = L(actual_novel, M0 prediction) − L(actual_novel, M1 prediction)
```

`d_i > 0` in plain terms: **how much better we predict how this agent will allocate its behaviour
in the new world once we know its past.**

**Aggregation order**: the rich/poor pair of one seed is **averaged first** in loss improvement,
**then** seed-level inference is done.

### ⚠ `entry_state` is a constant in the main analysis

After levelling, every agent's entry state is **identical by construction** → in the main analysis
`entry_state` carries no information and `M0 = f(B_familiar)`.
`entry_state` is a real variable only in the **unlevelled paired-matching secondary analysis**.
This must be stated, or it looks like an omission.

---

## 4. Models and inference

### Model class

- **Primary: Random Forest**, `n_estimators = 1000` (to suppress the forest's own randomness),
  with a fixed `random_state`.
- **Robustness: Ridge on a quadratic basis expansion** (interpretable, but covering only the
  pre-specified second-order structure). **Both are not required to be significant.**
- **No k-NN** (once the behaviour vector has many dimensions, distances stop working).

**M0 and M1 must use the same model class, the same hyperparameters, the same folds, the same
feature preprocessing and the same random_state. M1's only extra is the
`development_history` column.**

### Hyperparameter selection: group-blind, and **optimising M0 only**

Scan a small grid on `20000+`:

```
max_depth        ∈ {8, 12, None}
min_samples_leaf ∈ {5, 10, 20}
max_features     ∈ {"sqrt", 0.5, 1.0}
```

> ### ★ Iron rule ★
> The tuning script **does not receive `development_history`**, and is **still less** allowed to
> look at which model maximises M1−M0.
> Its sole objective: **which RF best predicts `B_novel` from `B_familiar`**.
> **When performance is close, it is specified in advance that the simpler / more regularised one
> is taken** (larger `min_samples_leaf`, smaller `max_depth`, smaller `max_features`), rather than
> whichever gives the prettiest result.

### Inference: `ΔOOS` + seed-cluster bootstrap

```
ΔOOS = mean_i d_i          (computed only on folds that took no part in fitting)
```

- **CI**: cluster bootstrap by **seed**, **10,000 times**, taking the 2.5/97.5 percentiles.
- **Criterion**: the 95% CI lower bound of `ΔOOS` is **> 0**.
- **Secondary**: a permutation test that swaps the rich/poor labels within twin pairs and re-runs
  the entire CV pipeline.

### ★ Rule 56, strengthened: eliminate analysis randomness rather than merely measuring it ★

The lesson of R52 was "change the analysis seed and the conclusion flips". **This time it is
blocked at the source**:

1. **Deterministic CV folds**: `fold = deterministic_hash(seed) % K`, with
   **rich/poor twins always in the same fold** (otherwise information leaks). **Not randomly
   re-split each time.**
2. **The RF `random_state` is fixed**; `n_estimators = 1000` suppresses forest randomness further.
3. **The bootstrap uses a fixed analysis seed**, with replicates raised to **10,000**
   (it only resamples the OOS `d_i`, which is cheap).

**The formal analysis is essentially deterministic.**
The 8-analysis-seed rehearsal is still run, but **only as a stability diagnostic**; it is no
longer part of the verdict. If the rehearsal shows the verdict would still be decided by
randomness → switch to a three-valued verdict **before the run**, never afterwards.

### Capacity controls — the guardrail (★ tightened in v3 ★)

Under an RF, a **monotone transform** such as `rank(explore)` has no effect (trees split on
thresholds anyway). Use instead variables that are 100% `f(B_familiar)` but **require an
interaction to recover**:

```
C1 = explore × build
C2 = 1[ (explore > median) XOR (build > median) ]
```

**Declaring "insufficient model capacity, so it cannot explain this" requires both conditions to
hold at once**:

1. that capacity control's **own `ΔOOS` CI lower bound is > 0** (it has to be genuinely useful
   itself), **and**
2. its point estimate is ≥ **50%** of the true history's

> Looking at the point estimate alone would let one noisy C1 that happens to reach 51% kill the
> experiment.
> **50% is a deliberate guardrail and is not pretended to be some theoretical constant.**
>
> ⚠ **Passing the capacity control ≠ proving there is no underfit.** All it says is
> "the two classes of interaction structure tested in advance did not break M0".

---

## 5. State identity and negative controls

① **State levelling** (main analysis): following `leveling.py` (020), equalising
`hunger / energy / shelter / condition / inventory`. After levelling, shelter **must be below S**.
② **Paired matching** (secondary analysis, no intervention): no levelling, keeping only pairs whose
entry states are close (ε fixed in advance).

### ③ Full executable-state levelling — the negative control

Not only traits/floor/knowledge/flags/memories/hardship, but **also necessarily**:
**RNG state** (`agent.rng` / `world.rng` / `life.inf_rng`, via `getstate()`),
the goal state, the landmark state, `_hardship_anchor`, and every counter and cache
(`action_log` / `action_by_hour` / `goal_by_day` / `events` …).

**Execution**: serialise both agents completely before the probe; apart from
`development_history_label`, the **hashes must be identical**. If everything matches and yet
placing them in the same environment is still not bit-identical → there is a leak → **the whole
batch is void**.

### The remaining negative controls
- deleting only memories: must be a **bit-identical** no-op
- with the novel rule switched off: must reproduce the persistence-stage numbers

---

## 6. Difficulty calibration: group-blind, algorithm frozen before the values are chosen

Run on the **already burned `20000+`**, with **the script receiving no developmental-world label**
and forbidden to compute any quantity grouped by developmental world.

Strategy classification: within the novel window, `b = the share of (gather_material + build)` and
`e = the share of explore`:
`builder if b−e ≥ m` / `explorer if e−b ≥ m` / mixed otherwise. **`m = 0.05`.**

### Pass conditions (pooled, labels hidden)

1. each of the two main strategies is ≥ 20% and ≤ 80% (classified within the **decision window**)
2. **★rule 62★ pooled survival within the decision window ≥ 95%**
3. overall survival within the consequence window ≥ 80%
4. no more than 50% meet the gate within 5 days of entry (not every ball clears it instantly)
5. **the gate really does open**: the share reaching `S` **before the consequence window ends** is
   ∈ **20–80%**
6. **not a pseudo-fork**: the pooled survival of each strategy is **≥ 80%** individually, and the
   two differ by **≤ 10pp**
7. **enough behavioural sample**: ≥ 5 observations per hourly cell (i.e. `W_dec ≥ 5`), and ≥ 120
   total actions per ball

### Selection order (★ a unique solution is required in two dimensions too ★)

`W_dec` and `S` (or `λ`) are decided **jointly**, but a unique solution is taken by
**lexicographic order**, avoiding a repeat of the `c_f/c_s` problem where "minimum in a
two-dimensional space" has no unique meaning:

```
for W_dec in (5, 7, 10, 14):          # W_dec ascending first
    for S in candidates ascending:     # then S ascending
        if all of 1–7 hold:  take it and stop
```

That is: **take the shortest decision window first, then the smallest S / λ.**

> ### ★ Iron rule ★
> When choosing `S` / `λ`, **it is forbidden to look at which value maximises the rich/poor
> difference** — that is tuning the effect size.
>
> ### ★ What if no S / λ satisfies the conditions ★
> **Then the probe's design is not clean enough, and the standards must not be relaxed just to let
> it run.** 026 is meant to measure strategy transfer, **not to restart the study of survival
> selection**. Allowing one route to lose 30% and another 10% already produces obvious filtering
> of the behavioural sample.

---

## 7. Criteria

| Criterion | Content |
|---|---|
| **G1 main criterion** | for **each** probe separately, the seed-cluster bootstrap 95% CI lower bound of `ΔOOS` is > 0, **and the capacity control is not broken**. **Decision window only** (rule 62); **defining it by analysing survivors only is forbidden** |
| **G2 consequence criterion** | within the **consequence window**, survival or terminal resources differ between the worlds, paired test `p < 0.01` |
| **G3 mechanism question** | does G1 still hold under `−all floors ①②` — **exploratory, no direction assumed** |
| **naming criterion** | both probes passing G1 → *generalized individuality*; only one → *novel-context transfer* |
| negative controls | all three of §5 pass |

### The standing of G3: a mechanism question, not a necessary condition

If persistence is carried by the floor in the first place, then
`history → floor consolidation → novel context → new divergence`
**can perfectly well be genuine generalization**. Generalization **does not require a change of
carrier**; the carrier may stay the same, and what is new is that it produces new functional
consequences on an unseen problem.

- G1 disappears with the floor off → *generalization depends on the same consolidation
  architecture*. **That is not a failure**, it is the complete story:
  **one structure both preserves the past and projects it onto a new future.**
- G1 survives with the floor off → there is a second carrier, which is more surprising, but
  **not a necessary condition**.

---

## 8. Seed plan

**The clean block reserved for the novel-situation final: `60000–61499`. Nothing may point at it
before the preregistration is fixed in writing.**
Already burned and usable for design / calibration / tuning / rehearsal: `0–1499`,
`10000–11499`, `20000–21499`, `50000–51499`. Calibration and rehearsal always use `20000+`
(rule 57).

---

## 9. Implementation constraints

1. **Do not change one line of `v3_frozen/`.** Probe A = the `GatedWorld` subclass;
   Probe B = an influence (one-tick lag, which must be disclosed). To change v3, fork v4.
2. New modules: `novel_situation.py` (GatedWorld / Probe B / levelling / forking / serialisation
   controls), `novel_calibrate.py` (**group-blind**), `novel_probe.py` (execution).
3. **Rule 55**: every subtask sets all `sim.` globals explicitly; two runs with different
   `--workers` must be byte-identical.
4. **Rule 57**: the rehearsal parameter shape matches the official run (do not use `seed0 = 0`).
5. Coverage self-check + the `n = 0` interception (025 §4) carried over verbatim.
6. Rebuild `FrozenZero()` after forking (the deepcopy trap, 024).
7. ★ **The median for C2 may only be computed on the training fold** and then applied to the
   held-out fold. Using the whole-data median causes test information leakage.
   (C1 = `explore × build` is a pure product and has no such problem.)
   Likewise: any feature standardisation / binning is fitted on the training fold only.
8. ★ **Active proof of sibling isolation** (the acceptance test for rule 61, and cheap):
   after forking, do not merely check that no references are shared — also run a
   **mutation test** on development seeds — change clone F's `inventory` / `traits` /
   `world.food` and **assert that clone N is bit-unchanged**; then do it in the reverse
   direction. If it does not pass, do not proceed.

---

## 10. v2 → v3 change log

| # | Change |
|---|---|
| 1 | ★ **Added rule 61: counterfactual sibling branches** ★ — `B_familiar` and `B_novel` must come from two parallel branches of the same entry state, not from sequential measurement |
| 2 | `B_familiar` fixed at **182 dimensions** (168 hour×action + 7 whole-window shares + 7 first/second-half changes) |
| 3 | `B_novel` fixed at **7-dimensional action shares**; **loss = TV distance**; twins averaged first, then seed-level inference |
| 4 | The capacity-control verdict gains a condition: insufficient capacity is declared only if **the control's own CI lower bound > 0 and its point estimate ≥ 50% of history's** |
| 5 | Calibration condition 5 tightened: each strategy's survival **≥ 80% individually, differing by ≤ 10pp** (was 70% / 20pp); and it is stated that "finding nothing means the probe is not clean, and standards are not relaxed" |
| 6 | RF hyperparameters: `n_estimators = 1000` fixed, a small group-blind grid **optimising M0 only**, and when performance is close **the more regularised option is specified in advance** |
| 7 | **Rule 56 strengthened into "eliminate analysis randomness"**: deterministic folds via `hash(seed) % K`, a fixed RF `random_state`, a fixed bootstrap seed with replicates raised to 10,000; the 8-seed rehearsal demoted to a stability diagnostic |
| 8 | Stated that **`entry_state` is a constant in the post-levelling main analysis** and a real variable only in the unlevelled secondary analysis |
| 9 | ★ **Added rule 62: decision window / consequence window separation** ★ — G1 uses the short window only and requires ≥95% survival within it; G2 is what uses the long window's mortality and resource consequences; defining G1 by "analysing survivors only" is forbidden |
| 10 | `W_dec` and `S`/`λ` are selected jointly by **lexicographic order** (shortest window first, then the smallest S/λ), guaranteeing a unique solution in two dimensions too |
| 11 | New implementation constraints: the C2 median is computed on the training fold only (against leakage); sibling isolation must be proven actively by a **mutation test** |

---

## 11. Next steps

The design has converged here and **will not be expanded further**. Next:

1. Write `novel_situation.py` (the mechanism layer: `GatedWorld`, the Probe B influence,
   levelling, **the forking of rule 61**, the full serialisation controls)
2. Write `novel_calibrate.py` (**group-blind**) and calibrate `S` and `λ` on `20000+`
3. Calibration produces the values → write `NOVEL_PREREGISTRATION.md` → **and only then** touch
   `60000–61499`
