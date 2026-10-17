# MEMORY_TRANSFER_DESIGN — experiment 029 design draft

**Status: DRAFT · 2026-08-18 · version 7 — ★ promoted to a preregistration; this file becomes a historical design record ★**

> ### ✅ The preregistration has been written: `MEMORY_TRANSFER029_PREREGISTRATION.md`
> **This file is frozen at this point and becomes the historical record of "how the design grew,
> step by step".**
> From now on the preregistration governs; this file is no longer a living document.
> (The only open decision was §6.3 of the preregistration: whether the SHUFFLE criterion lands on
> the point estimate or the CI upper bound.)

> ⚠ **This is not a preregistration.**
> This file may be edited freely today, as many times as needed.
> The preregistration (`NOVEL_TASK029_PREREGISTRATION.md`) is a **different file**, written only
> once everything here is settled and the group-blind calibration has passed, after which not one
> word may be changed (following the closure rule of 027 / 028).

**What landed today**: ② ③ ④ moved from "open" to "settled draft"; the probe was run in two
versions — v1 one-shot (the SWAP dominance criterion failed → **that criterion is withdrawn**),
v2 stateful (Directional SWAP check PASS), v3 fixing the resolution timing bug (the effect shrank,
the story is unchanged);
**the hand-built memory probe stage ends here**, and `memory_acquisition_probe.py` has been opened
to build real Stable/Volatile histories — the direction is entirely correct; yield has been fixed
by **ANOMALY_AT=36** to 65.8%/73.2% and **frozen**;
the λ interface-capacity calibration has been run (group-blind), and **λ=1.00 plus four capacity
gates are formally frozen**; the OWN/DELETE/SWAP/SHUFFLE rehearsal has been completed on
development seeds (**SHUFFLE collapses, SWAP-XS retains 96%**). See §⑥–§⑨.

---

## ① What does 029 actually measure? (fixed)

> **Can structurally relevant past experience be retrieved and causally used
> to adapt to a surface-novel problem?**
>
> If past experience is related to a new problem in its **underlying structure**, can the agent
> **retrieve** and **use** that experience to adapt to a problem that is **superficially
> completely unfamiliar**?

### Division of labour with 025 / 027 / 028 (cleanly separated)

| Experiment | Question | Result |
|---|---|---|
| **025 / v3** | Can the past **persist**? | ✓ clearly (1.142, 78.3% of the parameter set in the same direction) |
| **027** | Does the personality that persists **transfer automatically**? | extremely weakly (0.08 trials, below the functional threshold) |
| **028** | Does reading more personality history rescue it? | no (G ≈ 0, no gain at equal budget) |
| **★ 029 ★** | Can past experience be **genuinely retrieved** and used **by analogy**? | ← the new question |

### Why 029 is not a sequel to 028

028 has already walked the "read more widely" route to its end (G = −0.002, CI [−0.031, +0.023],
robust to the sign of the wiring), and **027's A did not replicate on the new sampling block**
(E_A = −0.039, CI containing 0, point estimate halved).

So what 029 replaces must be the **type of pathway**, not the bandwidth:

```
027 / 028   history → one scalar we read out on its behalf → β → exploration bonus
029         history → addressable entries → the agent draws on them by similarity → decision
```

⚠ **If 029 ends up degenerating into "the experimenter picks a better readout", it is just a third
arm of 028 and should not be a separate project.**

---

## ② development history: ★ do not touch rich / poor yet ★ (settled draft)

029 **does not use** v3's rich/barren worlds. It builds a very clean small learning history from scratch.

### Stable history

Multiple problems in the past, and the rule **never reverses**:

```
Problem 1     X beats Y  →  always so
Problem 2     ○ beats △  →  always so
Problem 3     left beats right →  always so
```

### Volatile history

The number of problems, the reward magnitudes and the trial counts are **exactly the same**, but
every problem contains a change point:

```
Problem 1     X good  →  later Y good
Problem 2     ○ good  →  later △ good
Problem 3     left good →  later right good
```

### ★ Three disciplines ★

1. **stable / volatile are not personality.** They merely give the agent a **different experience
   store**. (This is exactly the boundary with 027/028: those two experiments worked on traits;
   029 works on experience.)
2. **Every concrete symbol is counterbalanced.** What is learned **must not** be
   ~~"B always becomes better later"~~ but
   **"a relation that used to work sometimes stops working"**.
   Only at the level of relations can transfer be discussed at all.
3. The two histories are **equal item by item in count, magnitude and trial number** — the only
   difference is whether there is a change point.
   (Following rule 67 / 026: the two developmental worlds must be equally novel.)

⬜ Open: the number of problems (provisionally 3), the trial count per problem, the distribution of
   change-point positions, and the exact counterbalancing layout of the symbols.

---

## ③ What memory actually is (settled draft)

The current autobiographical structure is **not reused**:

```json
{"event": ..., "day": ..., "importance": ..., "text": ...}
```

It stores "what happened", which suits autobiographical memory but is
**not enough for causal transfer** — it does not store "which relation mattered".

029 builds its own experiment-layer structure:

```
Episode:
    context               a relational context label
    previous_expectation  what was expected of the strategy in hand at the time
    observation           the return actually observed
    prediction_error      observation − previous_expectation
    action_relation       ★ "stay" / "switch" ★
    outcome               the return obtained after taking that action_relation
```

Example:

```
the old option had long been good → a run of anomalously low rewards → stay   → still failed
a run of anomalously low rewards                                     → switch → the reward recovered
```

### ★★ The single most important rule: store stay/switch, not A/B ★★

Storing A/B leaves nothing transferable once the task changes — the new task has no A or B at all.
**Only storing relations can transfer.**

✅ Already implemented as a hard constraint: `Episode.__post_init__` +
`_assert_relational_only()` in `memory_transfer_probe.py` raise immediately if any option identity
appears in a field.

---

## ④ Retrieval (first version: one relational query, deliberately minimal) (settled draft)

The first version **does not need** "genuinely intelligent" retrieval. One relational query suffices:

```
current state:  the strategy in hand has long been good  +  a recent run of prediction errors
                    ↓
retrieval:      has "previously-good strategy + persistent surprise" ever occurred before
                    ↓
memory returns: what the return was after staying, and after switching, in that situation
                    ↓
evidence:       mᵢ = E[R | switch, similar past] − E[R | stay, similar past]
                    ↓
decision:       logit(switch) = base_learning + λ·mᵢ
```

When the query does not hold, **m = 0 and memory does not enter the decision** — retrieval is
**context-triggered**, which is the whole point.

### ★ The essential difference from 027 ★

```
027    traitᵢ → βᵢ                                      we read one scalar on its behalf
029    current situation → retrieval → past outcomes → evidence → choice
```

Only the latter is really "**I am in this situation now, so I recall similar situations from before**".

### ★ (a) stateful retrieval (implemented in v2) ★

v1 was one-shot: recall the past → give this one decision a push → immediately forget what was
just recalled. That is priming, not memory-guided adaptation. It is changed into a state machine,
**without "holding for a fixed N trials"** (which would add an arbitrary parameter):

```
NORMAL →(a run of persistent surprises ≥ SURPRISE_RUN_MIN with the strategy in hand long good)
       → RETRIEVE: record the suspect strategy
       → ACTIVE: m keeps entering the working decision state
ACTIVE →① Q[the other] > Q[suspect]              "ah, it really did change"   → RESOLVED
       →② SURPRISE_RUN_MIN consecutive non-surprises on the suspect
                                                 "that was just chance"       → RESOLVED
```

Both resolution conditions **use only existing quantities** (Q, pe, `PE_THRESH`,
`SURPRISE_RUN_MIN`) and add **zero new parameters**; ② is symmetric with the entry condition
(entry needs 3 consecutive surprises, exit needs 3 consecutive non-surprises).

★ **While ACTIVE, m acts on the suspect, not on "the switch action"** ★

```
logit(switch) += λ · m · s      s=+1 if switching means **leaving** the suspect
                                s=−1 if switching means **returning** to it
```

v1 added `+λm` to switch on every trial — once that had pushed one switch through, the next trial
turned it into "switch back again", which is semantically wrong and oscillates. The new form is
what "**I suspect the rule changed**" means, and that suspicion persists until it is confirmed or
dispelled.

⚠ `suspect` is a **working variable** at decision time, not an Episode field — rule 85 is unchanged.

### ★ Iron rule (following 028) ★

> **A stronger retrieval channel ≠ giving history more weight.**
> 029 likewise needs an **equal-budget** control, and must not win by turning λ up.
> 028's quantile mapping is an off-the-shelf method to reuse.

⚠ But "equal budget" **does not mean** "equal exposure" — see rule 87 (§⑥ below).

⬜ Open: the value of λ (**today it is only swept, not chosen**), and the official values of the
   three thresholds `GOOD_THRESH` / `PE_THRESH` / `SURPRISE_RUN_MIN`
   (currently probe knobs, uncalibrated; the official values must go through a group-blind calibration).

---

## ⑤ What counts as a failure of 029? How do we know the design is clean before running it?

**(draft, pending decision)**

### Three-valued reading (following rules 56 / 79)

| Case | Verdict |
|---|---|
| the CI contains 0 | no evidence that structurally relevant experience is used causally |
| the CI > 0 but overlaps [0, SESOI] | an effect is detected, but **below the functional threshold** |
| the CI lies entirely > SESOI | functionally meaningful retrieval-conditioned adaptation |

### Failure modes admitted in advance

1. **The identifiability probe does not pass** → the mechanism has no capacity to affect the
   outcome at all, and **no group comparison may be run**.
   ← v1 got stuck here; v2 passed (see §⑥).
2. **No group-blind passing parameters are found at the calibration stage** → the design is judged
   unclean and closed as 026 was. **The standards are never relaxed to rescue it.**
3. **Neither Stable nor Volatile shows an effect** → a negative result, written up as such.
4. **There is an effect, but memory-blind cannot ablate it** → the pathway is not identified, and
   "retrieval" may not be claimed.

### ★ Fixed in writing before the run: a negative 029 is also informative ★

The core proposition is now **Persistent individuality ≠ automatically functional generalization.**
If 029 also comes out ≈ 0, the proposition is unchanged and merely strengthened into
"even when given a **genuine episodic retrieval channel**, still…".

**This paragraph is fixed now, to prevent going back and changing the design afterwards in order
to obtain a positive.**

### Wording discipline

- ⛔ Must not write *analogical reasoning* / that the agent "understood the structure"
- ⛔ Must not write *generalized individuality*
- ✅ May write: **retrieval-conditioned adaptation to a surface-novel task**

### ★ Endpoint structure (settled in v4) ★

```
primary candidate      ΔC = post-change cumulative errors (wrong choices in the 40 trials after the reversal)
                       C_i = Σ_{t=40..79} 1(choice_t ≠ correct_t)   ΔC<0 = memory helps
secondary mechanistic  restricted switch latency / retrieval exposure /
                       per-opportunity potency / ACTIVE duration / realized retrieval
```

> **Rule 89**: the primary endpoint must not overlap constructively with the mechanism's own
> active window. `ACTIVE` exits at ≈ "Q proves the new strategy is better", and latency ≈ "the new
> strategy begins to dominate stably" — they are naturally bound together, so latency is
> **demoted to secondary mechanistic**.

The advantages of ΔC: the window is fixed in advance by the task / it does not read ACTIVE or
RESOLVED / there is no never-switch censoring / every agent has it / its unit is trials, which
makes a SESOI easy to set / it measures the actual functional cost.

⬜ Open: the unit and value of the SESOI (**not fixed today**).

---

## ⑥ ★ Identifiability probe results, 2026-08-18 (v1 → v2) ★

The program is **deliberately not called** `experiment029.py` but `memory_transfer_probe.py` —
today it asks one thing only: **does this mechanism have any capacity to affect the outcome.**
Substrate = 027's task, not one number changed; seeds = the development block `0–399`;
**80000–81499 untouched**.

### v1 (one-shot retrieval) — the positive control passed, SWAP dominance did not

```
engineering self-check   relational constraint / determinism / memory-blind(λ=0)   all pass
positive control         λ=1: 17.8% of trajectories changed, Δlatency −0.125, direction correct
diagnosis                retrieval enters the decision on only 0.69/80 trials on average; the body's β is on 80/80
                         at firing, the median base p(switch) is 0.208 → the decision is not saturated and memory has room to act
```

### ⛔ The dominance criterion is formally withdrawn ⛔

> Original SWAP dominance criterion `|memory| > |body|` failed at all tested λ,
> after which inspection showed that the criterion compared an event-triggered
> channel active on ~0.69/80 trials with an always-on trait channel.
> The dominance criterion was therefore **retired before any Stable/Volatile
> outcome was observed**.

**The reason for withdrawing it is not that it failed, but that it measures the wrong thing.**
The v1 file and its results are **kept intact and not overwritten** — that failure is itself part
of the methodological record.

### The new SWAP estimand

```
M_C = L(Body C, Mem V) − L(Body C, Mem S)
M_K = L(Body K, Mem V) − L(Body K, Mem S)
M   = (M_C + M_K)/2
```

Of interest: ① whether M_C / M_K agree in direction ② whether pooled M is in the preregistered
direction ③ whether it exceeds a functional SESOI (**not fixed today**) ④ the Body×Memory interaction.
**The body effect is only a robustness diagnostic and is no longer a gate.**

### ★ Rule 87 (correcting the direction of rule 86) ★

> Memory and personality **should not have the same exposure in the first place**: personality is a
> prior that is always present, while memory should be **invoked only when a relevant situation
> arises**. Forcing memory to be online 80/80 would destroy the most important theoretical feature
> of this design — **context-dependent retrieval**.
>
> For an event-triggered mechanism, **an endpoint effect must not be compared in size directly
> against an always-on mechanism**; **exposure** and **per-opportunity influence** must be reported
> separately.

### ★ Rule 88: potential vs realized retrieval ★

> `fired` is itself affected by the preceding choice sequence (a cautious body stays three times in
> a row more easily) — the firing count is itself a product of task dynamics.
> ```
> potential   defined on the memory-blind (λ=0) trajectory → mechanism exposure
> realized    what happens on the memory-enabled trajectory → part of the outcome
> ```
> ⛔ It is absolutely forbidden to analyse only the agents that "successfully recalled a memory" —
> survivor conditioning. Written as an assertion: every summary must use all 400 seeds.

### v2 (stateful retrieval) — not one threshold, task or seed changed

```
① ② EXPOSURE        eligible seeds   potential   realized(λ=1)
   v1 one-shot          45.0%           0.75         0.69
   v2 stateful          45.0%           7.18         6.96      ← 9.6×
   still event-triggered (7.2/80), not stretched to 80/80. That is correct.

③ POTENCY (counterfactually swapping memory on decision states frozen at λ=0)
                     opportunities   median base p   saturated   mean|Δp| (λ=1)
   v1 one-shot            300           0.208          0.0%         0.2205
   v2 stateful           2873           0.400          0.0%         0.2807
   → v1's per-opportunity potency was never low. What v1 lacked was exposure, not potency.

④ new SWAP       M_C      M_K   pooled M    95% CI (descriptive)  same direction  interaction
   v1  λ=1     −0.125   −0.083    −0.104   [−0.410, +0.215]           yes          −0.042
   v2  λ=0.25  −0.875   −0.900    −0.887   [−1.343, −0.471]           yes          +0.025
   v2  λ=1     −4.058   −3.920    −3.989   [−4.785, −3.231]           yes          −0.138
   v2  λ=4     −9.607   −9.710    −9.659   [−10.815, −8.549]          yes          +0.103
   ★ Directional SWAP check: PASS ★ (both mechanisms, every λ, all the same sign)
   the interaction is tiny relative to M → memory does not depend on one particular body to work
   the CIs are descriptive (seed cluster bootstrap, n_boot=10000, analysis seed 8181);
   no SESOI is fixed today and no functional-significance reading is made.

⑤ DOWNSTREAM (consequences only)  trajectory changed   Δlatency   Δpost-reversal accuracy
   v1  λ=1                              17.8%           −0.125            +0.0029
   v2  λ=1                              43.2%           −4.058            +0.0535
   v2  λ=4                              45.0%           −9.607            +0.1688
   ⚑ at λ=4 the 45.0% exactly equals the share of eligible seeds — the ceiling is eligibility, as constructed.
```

> ### ★ Conclusion of the probe stage ★
> **v1's problem really was "the retrieved evidence never formed a persistent decision state",
> not that λ was too small.** Without changing one threshold, task or seed, and only making
> retrieval stateful, pooled M went from −0.10 to **−3.99 trials** (λ=1, a factor of 38).

### ⚠ The direction of risk has flipped (left to the calibration)

```
The mechanism may now be **too strong**: −9.7 trials at λ=4, while latency has a range of only 0–36.
The hand-built memory sits at the **maximum possible contrast** (m_S=−0.667, m_V=+0.667).
Real Stable/Volatile histories will produce a much smaller |m|.
→ −4 trials is **an upper bound at maximum memory contrast**, not an expected effect size.
```

⚠ One more thing to watch: **the ACTIVE window and the latency endpoint overlap by construction**
(the suspicion is lifted roughly when the switch succeeds). Before any strong conclusion, an
endpoint **not defined by that same window** is needed.

### Still not 029 scientific success

The memories are hand-built, λ is not frozen, and Stable/Volatile have not been run at all.

---

## ⑦ ★ The acquisition stage (from 2026-08-18) ★

**The hand-built memory probe stage is over. The next step is not calibrating λ.**
Before we know whether real Stable/Volatile histories produce m = 0.03 or 0.30, arguing over
λ = .25 versus 1 is scientifically meaningless. The formal order is:

```
fix the resolution bug → lock an independent endpoint → build real Stable/Volatile histories
→ let history generate the Episodes itself → observe the real memory-evidence distribution → and only then calibrate λ
→ wire acquisition+memory+novel task together and run the DELETE / SWAP / SHUFFLE rehearsal
→ only once everything is frozen, write the 029 preregistration, the SESOI and fresh final seeds
```

### The design: both sides experience surprise

```
t <  20     the original strategy p_high, the other p_low   ← identical in both conditions
t 20–27     ★both drop to p_low★                            ← **bit-identical** in both conditions
t ≥  28     Stable: the original recovers / Volatile: the other becomes good
```

**The anomaly alone cannot tell you which world you are in**; the difference lies only in "what
this anomaly meant". (Verified on 100 seeds × 3 problems: bit-identical for t<28.)

### The result: the direction is entirely correct

```
             n (m definable)   mean m     SD      median     share m>0
Stable            94          −0.3783   0.3410   −0.4000        8.5%
Volatile          96          +0.5257   0.2240   +0.5000      100.0%
separation +0.9040   hand-built +1.3333   → real experience reaches 67.8% of the hand-built version
```

matching: ① total trials ② total reward opportunity ④ first-good side are **bit-equal**;
③ episode count 2.88 vs 3.67 (a behavioural product; reported).

### ⚠ The bottleneck: yield is only 24%

```
episode completeness   Stable 23.5%   Volatile 24.0%
→ about 3/4 of agents finish development with **no usable memory at all**
yield diagnosis (per problem): Q≥.60 at the anomaly onset is only 57.8%; ever reaching a stay-run≥3 is 57–77%;
                        both at once, 17.2%
```

> **Rule 90**: the two halves of the entry condition undermine each other by construction — it
> requires "the strategy is still trusted (Q≥.60)" **and** "three consecutive disappointments",
> while every disappointment pushes Q down. **The binding half is the first one** → what should
> change is **the amount of experience before the anomaly**, not the surprise half.
> ⛔ Getting around it by "analysing only the agents that grew a memory" is absolutely forbidden (rule 88).

### caveat: realized reward cannot be matched

Volatile's total return is lower (73.19 vs 82.99), because it has to relearn after the change
point. Opportunity is already matched bit for bit; matching realized reward would amount to
cancelling the manipulation itself. **Record it, do not fix it.**

### Only upstream quantities may be inspected at this stage

```
✅ episode count / surprise count / stay-switch counts / reward marginals / the m distribution /
   completeness / manipulation check / matching diagnostics
⛔ novel-task latency  ⛔ post-change errors  ⛔ the Stable vs Volatile transfer effect
```
**The code does not contain those quantities either.** That is what preserves the freedom to
adjust acquisition without starting to tune the design around the final outcome.

### How λ will finally be fixed

Once the real m distribution is available, use a method that **does not look at the transfer
outcome**: take the empirical |m| of the real acquisition memory on burned development seeds,
compute only the **frozen-state counterfactual potency** `Δp_t(λ)` (probe3 already has this
pipeline), and freeze λ by **not saturated / substantial but not excessive / memory stays
event-triggered**.

> **λ is fixed by interface capacity, not by "who ends up looking better, Stable or Volatile".**

---

## ⑧ ★ Acquisition frozen + λ interface-capacity calibration (2026-08-18) ★

### The frozen acquisition candidate

```
ANOMALY_AT  = 36   (was 20; only the learning length **before** the anomaly is increased)
ANOMALY_LEN =  8   (unchanged)
T_PROBLEM   = 66   (still 22 after the anomaly, as before)
GOOD_THRESH / PE_THRESH / SURPRISE_RUN_MIN / the number of problems  ★all untouched★
```

A pure upstream sweep (with no novel task attached) shows that **increasing pre-anomaly experience
mainly fixes yield and barely changes the memory contrast** — a clean engineering correction.
36 is chosen as the **elbow** (20→36 buys +42/+49pp; 36→40 buys only another 3–4pp),
**not** as the point of maximum separation.

```
pre-anomaly   Stable comp.   Volatile comp.   complete-only separation
    20           23.5%           24.0%              +0.904
★   36 ★         65.8%           73.3%              +0.894
    40           69.5%           76.8%              +0.884
```

### ★ Rule 91: memory availability is itself a developmental outcome ★

> Memory availability is itself a developmental outcome. Do not condition
> transfer or calibration on successful memory formation. Report the extensive
> margin (P[m usable]) and intensive margin (m | usable) separately, but all
> primary analyses use the full predefined population.

```
            extensive P[m usable]   intensive mean(m|usable)   overall mean m   overall median
Stable            65.8%                    −0.4099                −0.2695          −0.2440
Volatile          73.2%                    +0.4842                +0.3546          +0.4099

population separation (m=0 included) = +0.6241  ★the true value★
complete-only separation             = +0.8940  ⚠ inflated (hand-built +1.3333)
```

- The unequal yield (65.8% vs 73.2%) is **not fixed** — forcing it to match = modifying a
  post-treatment mediator.
- In future the memory effect will be split into an **extensive margin** (whether a usable
  relational memory formed at all) and an **intensive margin** (how large its direction is once
  formed), with causality tested by SWAP / DELETE / SHUFFLE.
- Realized reward (117.24 vs 103.42) is likewise **not fixed**: equalising it = cancelling the cost
  of volatility. What should be matched is trial opportunity / the reward-schedule opportunity /
  first-good identity / pre-anomaly observations / task length — and those are already bit-equal.

### λ interface-capacity calibration (group-blind, structurally guaranteed)

```
pooled_empirical_m()  both conditions poured into one pool → ★m=0 included★ → sorted (destroying the grouping correspondence)
input n=800  mean +0.0426  median |m| 0.3571  ★m=0 share 31.2%★
the Δp convention = against the "no memory" counterfactual; the states come from the λ=0 memory-blind trajectory (2708 of them)
```

```
   λ    median|Δp|   saturated after push   P(preference flip)   exposure    three criteria
 0.25     0.0182            0.0%                   3.2%          6.80/80    ✗② (negligible)
 0.50     0.0363            0.0%                   6.6%          6.71/80    ✓✓✓
 1.00     0.0717            0.0%                  13.4%          6.73/80    ✓✓✓
 2.00     0.1354            0.6%                  24.8%          6.86/80    ✓✓✓ (flip right on the edge)
 4.00     0.2250           12.7%                  33.5%          7.35/80    ✗①✗②
```

**The passing band is λ ∈ {0.5, 1, 2}; the recommendation is λ = 1.00** (the centre of the band,
close to neither edge).
⚠ The **numeric thresholds of the three criteria are also pending a decision** (they are currently
this file's reading conventions, not preregistered values).

> **λ is fixed by interface capacity, not by "who ends up looking better, Stable or Volatile".**
> Inside the calibration module the condition label is discarded at the input, so a group
> difference is physically incomputable.

---

## ⑨ ★ λ frozen + rehearsal (2026-08-18) ★

### Frozen (never to be changed for any Stable/Volatile outcome)

```
SATURATION_MAX = 0.05   MEDIAN_ABS_DP_MIN = 0.02
PREF_FLIP_MAX  = 0.25   ACTIVE_EXPOSURE_MAX = 20 / 80
MEMORY_LAMBDA  = 1.00
the exposure gate uses ★max(E[m10],E[m50],E[m90])★, not the mean
```

These four are **engineering admissibility gates, not significance thresholds**.
The max is used because event-triggeredness must not allow "one memory sign is nearly always on
but gets averaged away by the other two" (at λ=1 the max exposure is only 6.95/80, so the verdict
is unchanged).

> ### ★ Rule 92: the selection rule must be fixed in writing, including "how it was selected" ★
> Lambda was calibrated without condition labels or downstream transfer
> outcomes. Values were required to satisfy prespecified interface-capacity
> constraints on saturation, median probability shift, preference reversal,
> and retrieval exposure. Among admissible values, the log-scale midpoint of
> the admissible range was selected.
>
> The passing band is {0.5,1,2}, and `1.0 = √(0.5×2)` is its log-scale centre —
> picking the value furthest from both failure directions, not the one with the largest potency.
> The code carries an assertion.

### The rehearsal (development seeds 0–399, not FINAL)

```
arm          ΔC = C(V) − C(S)     95% CI (descriptive)    relative to OWN
OWN               -0.927        [-1.202, -0.677]              1.00
DELETE            +0.000        [+0.000, +0.000]              0.00   ← an identity
SWAP              +0.927        [+0.680, +1.202]             -1.00   ← an identity
SHUFFLE           +0.087        [-0.068, +0.242]             -0.09   ★collapses
SWAP-XS           -0.890        [-1.140, -0.660]              0.96   ★retained
```

> ### ★ Rule 93: with only one pathway, DELETE / SWAP degenerate into assertions, not evidence ★
> With a constant body and the developmental history entering the task only through memory, the two
> conditions of one seed differ only in memory, so `DELETE ≡ 0` and `SWAP ≡ −OWN` hold
> **by construction**.
> What they prove is "**there is no second leakage pathway**", not "memory has a causal effect".
>
> **To make SWAP a non-trivial test, the developmental history would have to carry something
> besides memory** (for example 027/028's trait pathway).
> ← ★ This is the first thing 029 genuinely has to decide ★

The two genuinely informative controls both behave as expected:
**SHUFFLE** (preserving the episode count / the stay-switch counts / the outcome marginals, and
shuffling only the action↔outcome relation) → ΔC collapses to −9.4% of OWN with a CI spanning 0
→ **the effect comes from the relational structure, not from marginal statistics**;
**SWAP-XS** (re-pairing across seeds) → retains 96%
→ **the effect is carried by memory content**, not by the coupling of development and test sharing
a seed.

### ⚠ Do not mix the two definitions of the extensive margin

```
usable (m ≠ 0)            Stable 64.2%   Volatile 73.2%
complete (entries on both sides)  Stable 65.75%  Volatile 73.25%
```
The difference is 6 Stable agents (1.5%) that have entries on both sides but whose means happen to
be exactly equal → m=0. **Whichever is reported, report the same one throughout.**

### What is still missing before the preregistration can be written

```
① whether the developmental history should also carry a trait pathway (otherwise SWAP is forever an identity) — rule 93
② the SESOI (ΔC is measured in trials, and OWN is currently ≈ 0.93)
③ fresh final seeds (80000–81499 is still clean)
④ MEMORY_TRANSFER029_PREREGISTRATION.md
```

---

## Appendix: seed ledger

```
0–1499          development (★ today's probes use 0–399 ★)
10000–11499     021 holdout set / 028 transport rehearsal
20000–21499     022 preregistration block / 027 + 028 group-blind calibration
50000–51499     v3 persistence FINAL
60000–61499     027 novel-task FINAL
70000–71499     028 breadth FINAL
80000–81499     ★ reserved for 029 FINAL ★  ← verified: never appears as a seed anywhere in the repository
```

⬜ Open: which block 029's calibration / rehearsal will use (**the 80000 block must not be touched**).

---

## Appendix: things deliberately not done today (written down to prevent slips)

```
⛔ fixing 029's final seeds     ⛔ writing the preregistration
⛔ fixing the SESOI             ⛔ deciding λ's final value
⛔ using a new final block      ⛔ adding memory directly into sim.py
⛔ bringing in an LLM / embeddings   ⛔ turning on episodic + semantic + abstraction at once
⛔ looking at the formal Stable vs Volatile difference
⛔ (b) relaxing SURPRISE_RUN_MIN     ⛔ (d) a multi-change-point task
```

**Why (b) is not done**: v1 already showed the decision is not saturated when retrieval fires
(base p=0.208), so it is not "remembered too late". Going 3→2 only makes memory appear earlier and
**does not fix "cleared as soon as it appears"** — that treats the quantity, not the mechanism.
**Why (d) is not done**: turning one reversal into three naturally increases exposure, and if the
result strengthens we cannot tell "the mechanism was fixed" from "the same weak one-shot effect
repeated three times". (d) belongs after the mechanism is right on a single change point, at which
point it becomes a **dose-of-opportunity robustness test**.

What we are still asking is: **is this mechanism identifiable at all?**
As in 026, first prove that "the experiment is able to measure what it claims to measure".

---

## Appendix: to-do

- [x] ② swap the developmental history to stable / volatile (leaving rich/poor alone)
- [x] ③ 029's own Episode structure (storing stay/switch, not A/B)
- [x] ④ minimal relational retrieval + `logit(switch)=base+λm`
- [x] ⑥ positive control + SWAP test run
- [x] **(c) the SWAP reading convention** — dominance withdrawn, replaced by M_C/M_K/pooled M + directional consistency
- [x] **(a) stateful retrieval** — RETRIEVE → ACTIVE → RESOLVED, with zero new parameters
- [x] the exposure × potency decomposition (rule 87) + the potential/realized separation (rule 88)
- [ ] ②'s problem count / trial count / change-point distribution / counterbalancing layout
- [ ] a group-blind calibration scheme for the three thresholds
- [ ] ⑤ the unit and value of the SESOI
- [ ] the calibration seed block

---

## Version history

| Version | Date | What changed |
|---|---|---|
| v1 | 2026-08-18 | First draft. ① fixed; ②–⑤ drafts, all pending decision |
| v2 | 2026-08-18 | ② changed to stable/volatile (leaving rich/poor alone); ③ Episode structure fixed; ④ minimal retrieval + decision rule fixed; added ⑥ probe results: **positive control passed, SWAP did not**, diagnosed as asymmetric exposure |
| v7 | 2026-08-18 | **No trait pathway added** (rule 93 final form: a second developmental pathway must not be added merely to make a control non-trivial); `SWAP-XS` renamed **XSEED-DONOR**; the extensive margin formally set to **completeness** (rule 94: m=0 is meaningful zero evidence, not "no memory"); **SESOI = 1.0 post-change error** + the three-way reading; SHUFFLE frozen as the **retention ratio R** (criterion A/B pending, measured R=0.094, CI [0.005, 0.261]); **FINAL 80000–81499 N=1500 frozen**; the preregistration written → this file frozen |
| v6 | 2026-08-18 | **λ=1.00 and the four capacity gates formally frozen** (the exposure gate switched to max); **rule 92**, the selection rule fixed in writing (the log centre of the passing band, with an assertion); ran the OWN/DELETE/SWAP/SHUFFLE rehearsal: OWN ΔC=−0.927, **SHUFFLE collapsed to −9.4%**, **SWAP-XS retained 96%**; **rule 93** — with a single pathway, DELETE/SWAP are algebraic identities and can only serve as assertions; a non-trivial SWAP would require the developmental history to carry a second pathway |
| v5 | 2026-08-18 | Froze the acquisition candidate (ANOMALY_AT=36/LEN=8/T=66, adding only pre-anomaly learning length, yield 24%→66–73%); **rule 91**, extensive/intensive margins reported separately with the primary using the whole population (population separation +0.624, complete-only +0.894 would inflate it); the mismatches in yield and realized reward are **both left unfixed**; ran the group-blind λ interface-capacity calibration, passing band λ∈{0.5,1,2}, recommendation λ=1 |
| v4 | 2026-08-18 | Fixed the resolution timing bug (v3; the effect shrank, the story unchanged, old results kept); **rule 89**, latency demoted and ΔC set as the primary candidate; created `memory_acquisition_probe.py`: the m grown by real Stable/Volatile histories points the right way and reaches 67.8% of the hand-built separation, but **completeness is only 24% (rule 90)**; the formal order changed to "acquisition first, calibrate λ last" |
| v3 | 2026-08-18 | (c) **the dominance criterion withdrawn**, replaced by M_C/M_K/pooled M; the direction of rule 86 corrected → **rule 87** (exposure × potency reported separately); added **rule 88** (potential vs realized retrieval, survivor conditioning forbidden); (a) **stateful retrieval** implemented and working: **Directional SWAP check PASS**, pooled M −0.10 → −3.99; the direction of risk flipped to "the mechanism may be too strong" |
