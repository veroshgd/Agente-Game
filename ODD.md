# ODD model description — AI SANDBOX Life Engine v3

Subject: `v3_frozen/sim.py` (`MODEL_VERSION = "v3"`, `COND_RECOVER_AT = 65.0`)
**All line numbers refer to `v3_frozen/sim.py`** (see the line-number note in §8).

This file is a model description written to the ODD protocol, and doubles as a **final static
code audit** — every statement of the form "why the agent does X", "when this variable changes",
"when this memory is read" has been checked back against the code. Problems found during the
audit are recorded in §8, **unvarnished**.

---

## 1. Purpose

The question: **does an identical individual become a behaviourally different individual because
it lived through a different past?**

The model does **not** attempt to simulate real personality formation. It is a minimal apparatus
for asking whether, in a system with only environmental differences and no "individual type"
input whatsoever, experience can produce a behavioural difference that **survives transplant into
an identical environment**.

⚠ The model contains **no concept of a "user type"** (the core change of v2).
"Who is feeding it" and "how diligently" are the business of the **experiment scripts**
(`scenarios.py`); the Life Engine itself does not know what a user is.

---

## 2. Entities, state variables, scales

### 2.1 Agent

| Variable | Range | When it changes | Lines |
|---|---|---|---|
| `traits{caution, curiosity, industry}` | [floor, 100] | after every action (positive feedback) | 906–912 |
| `trait_floor` | [identity, 90] | raised by landmark experiences and hardship; decays daily | 550, 973, 917 |
| `trait_identity` | [0, 90] | raised only by landmark experiences, **never falls** | 553 |
| `hunger` | [0, 100] | +2.2/tick; −20 per meal | 936, 865 |
| `energy` | [0, 100] | −1.2/tick; each action costs extra | 937 |
| `shelter` | [0, 100] | −0.35/tick; storms deduct; build +22 | 938, 943, 882 |
| `condition` | [0, 100] | −0.40 while hunger>70; +0.16 while hunger<65 | 953–961 |
| `inventory{food, material}` | ≥0 | gathering / consumption | 864–882 |
| `hardship` | ≥0 | += deficit/24 each tick | 966 |
| `_hardship_anchor` | dict or None | **written once, the first time condition<100, never changed after** | 967–968 |
| `flags` | set | triggered by landmark experiences | 541 |
| `knowledge` / `knowledge_strength` | strength (0,1] | learning/refreshing restores 1.0; −0.02 daily | 484, 499–502 |
| `memories` | list | appended by landmark experiences | — |
| `goal` | dict or None | **updated once every morning (tick 0)** | 931–933 |
| `goal_satiation` | dict | the day a goal was completed/abandoned | 740, 747 |
| `alive` | bool | **only condition ≤ 0 sets it False** | 983 |

### 2.2 World

`food` (a stock, capped at `food_cap`), `objects` (`book` / `music`),
`p` (parameters: `food_regen` / `material_yield` / `storm_chance` / …),
`weather` (`clear` / `storm`), `rng`, `events` (recording only).

### 2.3 Scales

`TICKS_PER_DAY = 24`. Experiment window: 30 days of development → transplant → 30 days of observation.

---

## 3. Process overview and scheduling

**The strict order within one tick** (the experiment loop + `Agent.tick`, 926–988):

```
1. world.tick(day, t)          resource regrowth; at tick_of_day==3 the weather is drawn by storm_chance
2. influences(...)             external interventions (feeding, experiment-layer probes) — before the agent
3. agent.tick(day, t):
   a. if not alive → return immediately
   b. if tick_of_day == 0 → update_goal(), and write the day's goal into goal_by_day
   c. hunger += 2.2 ; energy −= 1.2 ; shelter −= 0.35
   d. if weather == "storm" → shelter −= damage; damage>28 triggers a landmark experience
   e. condition: hunger>70 → −0.40 ; else hunger<65 → +0.16 ; else 0
   f. deficit>0 → hardship += deficit/24; **if the anchor is empty, write the anchor**
   g. anchor non-empty → raise trait_floor by hardship_norm; hnorm≥0.5 triggers fears_hunger
   h. **if condition ≤ 0 → alive=False, return (the only path to death)**
   i. score all 7 actions → argmax → act()
4. (at the end of each day) agent.daily(day):  trait_floor decays towards identity;
                               hardship fades when condition≥99.5; knowledge decays
```

⚠ Two points in the ordering are easy to misread, and both were checked:
- **influences run before `agent.tick`** → an experiment-layer probe can only charge for the
  action of the **previous** tick (every influence-style probe in 026 carries this one-tick lag).
- **The goal is set once a day** (tick 0), not re-picked every tick — that is where continuity comes from.

---

## 4. Design concepts

**Emergence**: individual differences are not an input; they are amplified by the positive
feedback "act → trait → more inclined to that act".

**Adaptation**: **purely reactive**. The agent scores its current state and takes the maximum,
with **no online contingency learning whatsoever** — it cannot discover by trial and error that
"in this world X causes Y". (This is the core scope limitation of 026.)

**Objectives**: `score(action)` = state terms + trait match + current-goal bonus
+ landmark/knowledge bonus. **No utility function, no planning, no lookahead.**

**Learning**: only two weak channels — trait drift (continuous) and knowledge
(discrete, restored to full on learning, decaying daily).

**Prediction**: none.

**Sensing**: the agent reads all of its own state plus `world.objects` / `world.p` /
`world.food` / `world.weather`. It **does not sense other agents** (the model has only one).

**Interaction**: no agent–agent interaction.

**Stochasticity**: **five sources only**, all verified:

| Source | Lines |
|---|---|
| trait offset at birth ±6 | 418 |
| whether a storm happens / its strength | 175, 178 |
| food-gathering success rate 0.85 | 183 |
| exploring finds food 0.28 | 886 |
| landmark experience triggers 0.30 / 0.25 | 888, 895 |
| (experiment layer) feeding timing | 200 |

**Action selection itself is a fully deterministic argmax: no softmax, no ε-greedy.**

**Collectives**: none.

**Observation**: `action_by_hour` (24×actions), `goal_by_day`,
`action_log`, `flags`, `memories`.
⚠ Of these, `action_log` and `goal_satiation` **are read back** (see §5) and are not pure logs —
a point that only surfaced during the field audit of experiment 024 (rule 63).

---

## 5. Submodels (checked one by one)

### 5.1 Action selection

```python
scored = [(self.score(a, day), a) for a in ACTIONS]
scored = [(s, a) for s, a in scored if s is not None]
self.act(max(scored)[1], day, tick_of_day)          # 986–988
```

- `score()` returning `None` = the action is **illegal** (`read` requires a `book` in the world,
  `ACTION_REQUIRES_OBJECT`, 276).
- ★**Hidden mechanism**★ `max((score, action))` breaks **exact ties** by the **alphabetical order
  of the action name** → `sleep` always wins, `build` always loses.
  **Measured across 19,200 decision ticks: exactly 0 ties.** So it exists but has never fired.
  It is recorded anyway, because it is deterministic and had never appeared in any document.

### 5.2 Positive feedback (the source of persistence)

```python
extremity = abs(traits[t] - 50)/50
pull      = max(0.12, 1 - extremity * TRAIT_SATURATION)
traits[t] = clamp(traits[t] + delta * TRAIT_DRIFT * pull, trait_floor[t], 100)
```
(906–912)

- `delta` comes from `ACTION_TRAIT_FEEDBACK` (264–272): doing something reinforces the trait that made you do it.
- `pull` is the **diminishing-returns brake**: the more extreme, the harder to grow further. Without it,
  explore's `caution −0.10` would push the ball into doing nothing but running around outside (v1 was
  protected by the permanent floor; v2's floor fades, so this brake had to replace it).
- **The lower bound is `trait_floor` — that is the ratchet.**

★ Causal evidence: taking `TRAIT_DRIFT` from 0 to 2.4 moves the transplant ratio 1.021 → 1.575;
and it is the most sensitive knob across 500 randomised parameter sets (ρ = +0.442).

### 5.3 The floor

- `trait_floor` is raised by two things: **landmark experiences** (550) and **hardship** (973)
- It decays daily towards `trait_identity` by `FLOOR_DECAY_PER_DAY` (917–919)
- `trait_identity` **only rises** (553) and is the permanent identity
- The floor takes effect as the **lower bound** of the trait update (912)

### 5.4 The hardship ratchet

```
first time condition < 100  → _hardship_anchor = a snapshot of traits then (written once, never changed)
every tick                  → hardship += (100−condition)/100/24
trait_floor[t]              ← min(anchor[t] + w × 22 × hardship_norm, 90)
hardship_norm               = 1 − exp(−hardship / 1.5)
```

⚠ `HARDSHIP_SCALE = 1.5` means roughly 5 days of accumulated deficit pins it at 1.0, while the
measured hardship is 23–48 → **hnorm is saturated at the ceiling for every ball under every
condition**. So this ratchet is **not a graded signal but a binary switch** (rule 50).
What carries the individual difference is **the snapshot inside the anchor**, not "how much
suffering there was".

★ But experiment 024 proved that **the anchor's content explains only 1.3% of the effect**
(rule 54). What matters is that a floor existed, not which snapshot it was anchored to.

### 5.5 knowledge (wired into decisions in experiment 022)

```
learn/refresh → knowledge_strength[key] = 1.0          484
daily         → strength −= 0.02, deleted at ≤0        499–502
score()       → += 12.0 × strength (× slack for discretionary actions)  835
goal priority → += 0.25 × strength                      656
```

⚠ The measured strength is nearly binary (p10 = 0.000, p50 = 0.979), so it is **not a graded
channel** (rule 73).

### 5.6 condition / death

```
hunger > 70 → condition −= 0.40
hunger < 65 → condition += 0.16          (v3; v2 used < 30)
otherwise    → 0 (the dead zone, only 5 points wide in v3)
condition ≤ 0 → death (the only path)
```

**Hunger itself is not lethal**; it kills through condition.
v2's dead zone was 40 points wide and the recovery channel almost never fired → no steady state,
120-day mortality 40.7%; v3 raises the threshold to 65, which only works **once the "sloth valley"
has been crossed** (rule 49).

### 5.7 Goals

Every morning `update_goal()`: `propose_goals()` assigns priorities to 5 goals
(reading shelter / food / condition / knowledge / flags), subtracts `_satiation` (the refractory
period) and takes the highest; there is a switching margin and a minimum commitment in days.
Goals bonus the matching actions through `GOAL_ACTIONS` (300–305).

⚠ The `learn` goal has **0.0% participation** in the baseline world (it needs books); `recover`
has only 16.6%. **In practice there are only 3 active goals.**

---

## 6. Initialization

`traits = 50 ± U(−6, 6)` (418); `hunger=30, energy=?, shelter=?, condition=100`;
`inventory` empty; `flags/knowledge/memories` empty; `trait_floor = trait_identity = 0`.
The world is constructed from the parameters in `scenarios.WORLDS`.

★ Key point: **the only difference between the two developmental worlds is the world parameters**
(`food_regen` 3.2/1.8, `material_yield` 2.0/0.5, `objects` `("book","music")`/`()`,
`storm_chance` 0.02/0.1).
**The agent's initialization is completely identical and determined by the seed alone.**

---

## 7. Input data

No external data. All randomness comes from the seed.

---

## 8. ★ Problems found during the audit (recorded plainly, unvarnished) ★

### 8.1 Line-number correspondence: pre-023 line numbers in the log do not match v3

`v2_frozen/sim.py` has 1013 lines, `v3_frozen/sim.py` has 1043. v3 added about 27 lines of
docstring at the head and another 3 lines of `MODEL_VERSION` in the middle, **so the offset is not
constant**:

```
                              v2      v3     offset
def take_food                 154     181    +27
KNOWLEDGE_WEIGHT × know       805     835    +30
hardship += deficit           936     966    +30
_hardship_anchor = dict       938     968    +30
trait_floor[t] = max(         943     973    +30
```

⚠ **Any `sim.py:NNN` cited in the experiment log at 023 or earlier uses the v2 numbering**, so in
`v3_frozen/` add **+27 (before `MODEL_VERSION`) or +30 (after)**.
Every line number in this ODD has been normalised to the **v3_frozen numbering**.

### 8.2 Tie-breaking is a hidden deterministic mechanism

`max((score, action))` breaks ties by the alphabetical order of the action name.
Measured 0/19,200 firings, **but it had never appeared in any document** — if someone changes the
scoring so that ties become common, behaviour would tilt systematically towards `sleep`.

### 8.3 Mechanisms that had been misunderstood, confirmed while writing this ODD

| Mechanism | The former misunderstanding | The truth | Recorded as |
|---|---|---|---|
| `take_food` | thought `world.food` could be zeroed to "block it temporarily" | it **deducts from the stock**, so zeroing = burning the food store | rule 60 |
| `memories` | thought it was a pure log | read back by `recall()` | rule 63 |
| `action_log` | thought it was a pure log | feeds **goal progress** | rule 63 |
| `goal_satiation` | overlooked | read back (the refractory period) | rule 63 |
| `storm_damage` | overlooked | a **dynamic attribute**, existing only after a storm | rule 63 |
| `explore` food yield | thought it could sustain life on its own | 0.14/tick against a need of 0.11/tick, negative once sleep is deducted | rule 64 |
| `knowledge_strength` | thought it was a continuous channel | nearly binary (0 or 0.98) | rule 73 |

**All seven were implicit mechanisms of the "I know it so I never wrote it down" kind, and writing
the ODD is what exposed them one by one.**
