# Simulation experiment log

> The experiment log of a pure-code simulator. The code lives in `C:\Users\yinan\Desktop\ai-sandbox\`
> Related: [[Design points and risks]] · [[Vida artificial]]
> Date: 2026-08-06

---

## Experiment 001 — initial parameters: **convergence**

```
PERSONALITY_WEIGHT=8  TRAIT_DRIFT=0.55  HUNGER_RATE=2.2
999 balls × 30 days
```

| Metric | Result | Verdict |
|---|---|---|
| personality gap between user types | **1.1 points** | ❌ essentially zero |
| caution distribution | unimodal, concentrated in 55–80 | ❌ |
| σ | 11.3 | ❌ too small |
| mortality | 0% | ✓ |
| personality types | 559/999 are all "workhorses" | ❌ |

**Conclusion: the core selling point does not hold.** Three completely different users raise balls that are almost identical.

---

## Experiment 002 — parameter sweep: **not a tuning problem**

Swept 24 parameter sets (PW ∈ {8,18,30,45} × drift ∈ {0.55,1.2} × hunger ∈ {2.2,1.2,0.7}).

**Not one set satisfies** spread>8 + peaks≥3 + death<10% simultaneously.

The key observation: the only combination that pushes spread to 10+ (PW=45, drift=1.2) has a mortality of **38%–62%**.

> In other words: to give the balls a personality, you have to let them starve to death.
> **This is a structural problem, not a parameter problem.**

---

## Experiment 003 — a structural fix: one line of code

### Diagnosis

The original food-gathering score:

```python
s += self.hunger * 0.55 + 12      # ← that constant +12 is the culprit
```

That `+12` means **it wants to gather whether it is hungry or not**. The consequence:

```
the user feeds it → hunger falls → but the ball keeps gathering → the time saved is eaten by gathering again
        → the user's actions leave no trace at all → convergence
```

### The fix

```python
s += max(0.0, self.hunger - 35) * 0.85
if self.inventory["food"] <= 1:
    s += 20                        # anxiety only once the food store runs out
```

### Result

| Metric | Before | After |
|---|---|---|
| usable parameter sets | **0 / 24** | **6 / 24** |
| best spread | 13.1 (but mortality 55%) | 10.4 (mortality 0.3%) |
| σ | 11.3 | 36.2 |
| distribution shape | unimodal | **bimodal** |

---

## ★ The design rule obtained

This rule deserves a place in the formal design document:

> ### Personality needs slack in order to express itself
>
> If survival pressure permanently fills the action budget, every individual's behaviour is driven by need,
> and no amount of personality weight can squeeze into the decision → convergence is inevitable.
>
> **Corollary: the user's actions must change **what choices the ball has**, not merely change its numbers.**
>
> Feeding that only fills a number which climbs back by itself is the same as nothing happening.
> Feeding must free up time, and that time must flow into personality-determined behaviour (exploring / building)
> before differentiation can occur.

This rule holds for **any** need-driven agent, not just this project.

---

## Current configuration (already written into sim.py)

```python
PERSONALITY_WEIGHT = 30.0   # 45 also works, but sits far too close to the mortality cliff
TRAIT_DRIFT        = 1.20
LANDMARK_BONUS     = 25.0
HUNGER_RATE        = 2.2
```

The result of 999 balls × 30 days:

```
mortality 0%        σ = 36.2        bimodal distribution

adventurer  362  ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇
nest-builder 356  ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇
workhorse   234  ▇▇▇▇▇▇▇▇▇▇
cautious     47  ▇▇
```

---

## ⚠ Two problems still unsolved

### 1. The user's influence is still too weak

```
overall difference between balls        σ = 36.2
difference caused by user type          6.0 points
```

**Differentiation does hold, but it comes mainly from the internal positive feedback loop (difference source #4)
and the initial seed (#1), not from the user (#3).**

Whether a ball ends up an adventurer or a nest-builder is currently decided mainly by the random seed, not by the user.

That is a problem for the product — the user cannot feel "I raised it", so no emotional bond forms.

**Directions to try next:**
- let the user's actions directly trigger irreversible events (a ratchet) rather than merely changing numbers
- widen the gap between feeding intervals (currently 1 / 3 / 8 days, which may not be extreme enough)
- add more inputs that **only the user can provide** (conversation, giving specific objects, taking it somewhere)

### 2. The "nearly starved to death" ratchet has never fired (0%)

The balls are far too good at finding food themselves and never get hungrier than 92.

This irreversible event was meant to be the best story material ("my ball nearly starved, and hoarded food ever after"),
but it is currently dead code. Balls under a hands-off user need to face a genuine crisis.

---

---

# Round two: solving the "user influence" problem

The starting point: **a storm is an act of god, the user cannot prevent it, so it is useless for attribution.**
Hunger is the opposite — it is the one channel the user actually operates (feeding), which makes it the best carrier for attribution.

So why did it not work before? The numbers make it obvious:

```
hunger rises per day   2.2 × 24 = 52.8
one portion of food removes        55
```

**One gather = a whole day's ration. The ball is fully self-sufficient → whatever the user gives is redundant.**

> ### The user's influence exists only in the part the ball cannot solve by itself
> If the ball can feed itself, the user is an ornament.

---

## Experiment 004 — manufacturing a deficit: spread 6 → 37, but 26% died

Changes: food nutrition 55 → 20, and local food is finite and regrows slowly (2.0/day against a demand of 2.64/day).

| | Result |
|---|---|
| spread | **6.0 → 37.3** |
| doting | caution 62 / curiosity 65, house integrity 98 |
| hands-off | caution 25 / curiosity 95, house integrity 0 |
| mortality | **26.1%** ❌ |

The doted-on ball becomes a stay-at-home architect and the hands-off ball a wandering adventurer — **because it has to go out to find food**.
The story is beautiful, but 66% of the hands-off balls died.

## Experiment 005 — sweeping the food supply: it is a cliff, not a slope

```
regen 2.0 → spread 34.7   hands-off mortality 66%
regen 2.2 → spread 11.2   hands-off mortality 45%
regen 2.4 → spread  6.2   hands-off mortality  5%    ← once life is comfortable there is no difference
```

**Survival and differentiation have become the same variable**: the balls can only show a difference by nearly dying.

## Experiment 006 — adding a "condition" layer: giving failure a grade milder than death

Hunger used to have only two states: **fine** or **dead**. There was no chronic state in between,
and personality is formed precisely in that middle stretch.

Added `condition`: chronically underfed → condition falls → sleep recovery efficiency drops → fewer things become possible.
Death is redefined as "condition reaching zero" rather than "one missed meal kills".

Result: mortality fell (hands-off 45% → 17%), but spread also fell back to around 6.

## Experiment 007 — adding seasons: turning the cliff into a slope

Diagnosis: local regrowth and user feeding are **both flat rates**; added together they are either enough or not enough, with no middle state.

> **What produces a gradient is fluctuation, not the mean.**
> The user's food is not filling a constant deficit; it is **helping the ball through the lean season**.
> That is also closer to what a carer really does.

After adding a 12-day cycle of plenty and lean (amplitude 0.55): hands-off mortality 33% → 6.7%,
and the ratchet trigger rate rose to 11%. But spread is still 6.6.

## Experiment 008 — a one-way valve for personality

Diagnosis: **personality drifts back.** Forced to explore in the lean season → curiosity spikes → the season of plenty arrives and it drifts back to the middle.
Irreversible events only gave a bonus to behaviour and left no trace on **personality**.

Added `trait_floor`: a landmark experience raises the floor of some trait, which can never fall back below it again.

```python
def mark(self, day, text, flag, floors):
    self.flags.add(flag)
    self.landmarks.append((day, text))
    for t, boost in floors.items():
        self.trait_floor[t] = max(self.trait_floor[t],
                                  min(self.traits[t] + boost, 90.0))
```

What makes formative experience formative is precisely that it is irreversible.

---

## ⚠ Experiment 009 — a methodological correction: I have been tuning against noise

The sweep said spread=9.4 at regen=2.2 (450 balls), but 999 balls gave only 4.7.
That gap looked wrong, so a **permutation test** was run (shuffle the user-type labels 400 times and see what pure chance produces).

```
observed spread          :  4.66
null median (pure noise)  :  3.10
null 95th percentile      :  6.41
p value                  :  0.188   ← not significant
```

**The spread metric takes the maximum over 9 combinations of 3 user types × 3 dimensions,
and taking a maximum inflates noise by itself.** The "✓" threshold I had set at 5 points was below the noise floor.

> Conclusion: every spread of 6–9 in experiments 006–008 was **an illusion**.
> The only real signal is the 37.3 of experiment 004, and that configuration kills 26% of the balls.
>
> **Lesson: any metric that takes a maximum must have its noise floor measured first.**

## Experiment 010 — locating it: the mechanism is right, the transmission is too weak

The key diagnosis (`diagnose.py`):

```
              hunger-scarred  storm-fearing  exploration-loving  industry  condition
doting              0.0%          37.8%            35.4%           66.3      100.0
balanced            2.7%          33.9%            38.1%           66.4       97.9
hands-off          25.6%          42.0%            35.9%           71.0       79.3
```

- **"hunger-scarred" 0% / 2.7% / 25.6%** — perfect separation, the mechanism is entirely correct
- **"storm-fearing" is almost identical across the three rows** — the control arm, unrelated to the user as expected ✓ (which in turn validates the design logic)
- **"condition" 100 / 97.9 / 79.3** — strong separation

**The user's actions really do produce a clear, measurable difference — it just shows up in "state" and "events"
and never reaches "personality".** Because only 25.6% of hands-off balls fired the ratchet, the other 74% are
indistinguishable from the doted-on ones and the group mean is diluted away.

## Experiment 011 — strengthening the transmission: ✓ passes

Raised the condition threshold from 55 to 72 (so more balls fire it) and the ratchet floor from +10 to +22.

```
              hunger-scarred   industry
doting              0.0%          66.3
balanced            4.8%          67.1
hands-off          36.2%          75.3

permutation test:  spread = 8.96   p = 0.000   ✓ significant
          industry diff/SE = 7.2
mortality:    total 2.1%   doting 0%   balanced 0%   hands-off 6.3%
```

**For the first time both are satisfied at once: statistically significant user attribution + acceptable mortality.**

---

## Current configuration

```python
PERSONALITY_WEIGHT = 30.0
TRAIT_DRIFT        = 1.20
LANDMARK_BONUS     = 25.0
HUNGER_RATE        = 2.2
FOOD_NUTRITION     = 20.0    # one gather ≠ one day's ration
LOCAL_FOOD_REGEN   = 2.2     # demand is 2.64, a natural deficit
SEASON_DAYS        = 12      # the lean season is what the user is for
SEASON_AMPLITUDE   = 0.55
condition threshold = 72     # the trigger rate must be high enough or the group mean is diluted
```

---

## ★ The four design rules from this round

1. **The user's influence = the part the ball cannot solve by itself.**
   With a self-sufficient pet, the user is an ornament.

2. **Acts of god are useless for attribution.** Nobody can stop a storm, so the user feels no responsibility for it.
   Attribution must hang on a channel the user operates (feeding).

3. **Give failure a grade milder than death.** With only "fine / dead",
   survival and differentiation are the same variable, and tuning is necessarily zero-sum between them.

4. **What produces a gradient is fluctuation, not the mean.**
   A flat supply only produces a cliff. The user's value is helping through the lean season, not filling a constant deficit.

Plus one methodological rule:

5. **Any metric that takes a maximum must have its noise floor measured first.**
   Otherwise you spend hours tuning parameters against random numbers (as I did).

---

## ⚠ Still unsolved

**The effect size is small.** Industry differs by 9 points with σ≈19, an effect size ≈ 0.47 SD.
Statistically real, but **a user comparing two balls side by side may not see it**.

An investor demo needs a difference visible within 30 seconds, and we are not there yet.

There is a more practical finding, though: **attribution does not have to run through personality.**

| Carrier | Current state | Can the user perceive it immediately |
|---|---|---|
| state (condition 100 vs 79) | ✓ already strong | **immediately, visibly** |
| events (0% vs 36% went hungry) | ✓ already strong | **there is a story to tell** |
| personality (industry 66 vs 75) | weak | needs long observation |

"Your ball looks thin" is **immediately perceivable** attribution, far more direct than a personality number.
Perhaps the first demo should lead with the first two carriers and keep personality as a long-term reward.

---

---

---

# Round three: from "group means" to "pairing"

> Date: 2026-08-09

The last round ended on "the effect size is small". This round first explored everything outside the 30-day
configuration, found problems far worse than "small", and then changed the measurement method.

## ⚠ Stocktake: four blind spots in the experiment 011 configuration

### 1. The user explains only 4% of the variance

`spread=8.96, p=0.000` is real, but the variance explained (eta²) is:

```
industry    3.82%
caution     0.24%
curiosity   0.07%
```

**96% of the personality difference comes from the random seed and random world events.**
At a sample size of 999 balls, even a 4% effect can produce p=0.000.
**A large sample makes a tiny effect "statistically significant", but the product experience has nothing to do with a p value.**

### 2. 30 days is a time window; the configuration collapses at 60 days

```
 days   mortality   gap   gap/SE   σ(caution)  caution pinned at 100   hands-off hunger-scarred
   15    0.0%    6.41     7.3      21.2         0.0%          21.3%
   30    2.1%    8.96     7.2      33.9        15.8%          36.2%
   60   15.8%    9.31     5.1      42.2        57.3%          27.3%
   90   20.7%   23.67    14.4      41.5        54.9%          29.7%
```

- mortality is already 15.8% at 60 days, violating the <10% I set myself
- 57% of balls have caution pinned at 100 → that dimension can no longer differentiate (the clamp destroys information)
- the trigger rate falls at 60 days = **survivorship bias**; the balls that would have fired it died
- gap=23.67 at 90 days is not stronger differentiation, it is the weak being eliminated

### 3. The current configuration is a peak, not a plateau

Perturbing `LOCAL_FOOD_REGEN` by ±0.15 (±7%):

```
 regen   total dead   hands-off dead   hands-off scarred   gap   gap/SE
  1.90   15.2%     42.0%      38.9%     3.33     2.0
  2.05    8.6%     25.5%      41.9%     6.99     4.8
  2.20      2.1%           6.3%             36.2%          8.96     7.2   ← the current configuration
  2.35    0.2%      0.6%      17.2%     6.60     5.8
  2.50    0.0%      0.0%      10.8%     5.76     5.2
```

The peak of the gap sits exactly where mortality starts to become non-negligible.

> **Rule four (fluctuation produces a gradient) eased the cliff of experiment 005, but did not remove it.**
> Survival and differentiation are still coupled, only more loosely. A configuration sitting on a peak is most likely overfitted to the seed.

### 4. The daily routines of balls raised by the three users almost coincide

```
              eat     sleep   gather_food  gather_material   build   explore
doting        11.7%    52.4%       3.3%          11.5%         3.4%    17.7%
balanced      11.5%    50.1%       6.8%           9.8%         2.9%    19.0%
hands-off     11.2%    48.7%       7.8%          11.2%         3.3%    17.8%
```

- the three rows essentially coincide, and the one that does differ, gather_food, is exactly the behaviour the user cannot see
- **the ball spends half its life asleep**; eat+sleep account for 62%
- **building is only 3.3%**, while "builds its own home" is the headline selling point

(The sampled comparison in `sim.py` looks very different because `next()` grabs the first ball, not a representative one.)

### Root cause: all attribution rests on one binary switch

```
feeding frequency → condition → crossing the line at 72 → fears_hunger → industry jumps to the floor at 90
```

Splitting each group by whether it fired makes it obvious:

```
             CON flag    SIN flag    trigger rate
doting          —          66.34       0.0%
hands-off     95.06        64.08      36.2%

Among balls that did not fire the ratchet, spread is only 2.26   ← noise level
```

**Those 9 points come entirely from 36% of balls jumping from 64 to 95.** That is not personality growing, it is a switch.
So "spread 8.96" and "hunger-scarred 36.2%" are the same thing measured twice.

| Phenomenon | Because |
|---|---|
| bimodality within a group (a cluster at 64 and one at 95) | the switch has only on/off |
| only industry carries a signal | this chain is wired only to industry |
| extreme sensitivity to regen ±0.15 | the trigger rate depends on the tail of the distribution |

### ⚠ Tooling: the lesson of experiment 009 was never applied retroactively

`sweep.py` / `food_sweep.py` still use `spread > 8`, but the noise floor is tied to the population size:

```
pop=300 (sweep.py)       noise 95th percentile = 10.48   ← the threshold is below the noise
pop=450 (food_sweep.py)  noise 95th percentile =  9.18   ← the threshold is below the noise
pop=999 (sim.py)         noise 95th percentile =  6.47      ok
```

**Those two scripts currently award ★ to pure noise.** The same mistake replaying at a smaller scale.

---

## Experiment 012 — changing the measurement method: the paired experiment (`paired.py`)

### Starting point

`significance.py` asks "do the means of the three groups of balls differ much".
But the question in the user's mind is **"if someone else had raised it, would it be different?"**

A group comparison cannot answer that, because the balls in each group carry different seeds,
and the difference caused by the seed (σ≈34) is far larger than the difference caused by the user, so the signal drowns.

**The method: run the same seed twice, changing only the user.** Identical initial personality → the largest noise source is cancelled.

Sensitivity: paired gives 11.6× the standard error against grouped 7.2×. And it asks exactly the question the product has to answer.

Limitation (already in the docstring): the same seed only guarantees the same **initial state**,
and once the actions diverge the rng streams fall out of step. Pairing cancels seed noise, not world-luck noise.
So the null-hypothesis test uses **sign permutation** (flipping the signs of the differences 2000 times) —
following the lesson of experiment 009, a new method also needs its noise floor measured first.

### Results (400 seeds × 30 days, doting → hands-off, 374 valid pairs)

```
  carrier          mean diff   median     dz   share increased   |d|≥5       p
  caution           +1.53     +0.00   +0.13     48.9%    24.1%   0.009
  curiosity          -0.58     +0.00   -0.08        0.8%          2.1%   0.076  ← noise
  industry          +9.03     +1.34   +0.60     68.7%    47.6%   0.000
  condition        -20.66     +0.00   -0.71      0.8%    41.2%   0.000
  shelter           +9.74     +0.00   +0.42     40.4%    34.8%   0.000
```

The control arm's self-check passes: "storm-fearing" fires for hands-off only in 57 pairs and for doting only in 47, roughly balanced ✓
("hunger-scarred" is 137 pairs to 0.)

### Finding 1 ★ The median of every carrier is 0

```
condition:  p10 = -67.8    median = 0    p90 = 0
industry:   median = +1.34               p90 = +32.8
shelter:    median = 0                   p90 = +43.4
```

**For the median ball, changing the user changed nothing.** 30.2% of pairs show no change on **any** carrier.

> ### An effect with a median of 0 is the same as no effect
> The problem is not "the effect is small" but **"the effect is zero for most balls and drastic for a few"**.
> The mean writes those two situations as the same number. Any paired metric must be read alongside its median.

### Finding 2 State is the strongest carrier, not personality

`condition` has dz = −0.71, stronger than industry's +0.60,
and its directional consistency is **99.2%** (industry only 68.7%).

The guess at the end of the last round (that state and events are more direct than personality) now has numbers behind it,
and **state is the only carrier whose direction almost never reverses**.

### Finding 3 ⚠ The direction of shelter is inverted: hands-off balls have better houses

```
population:  doting 48.5   balanced 48.1   hands-off 56.6 (median 80.4)

hands-off WITH the hunger-scarred flag (n=113):  shelter 96.0   industry 95.1
hands-off WITHOUT it              (n=199):  shelter 34.2   industry 64.1
```

The cause is that the ratchet pours +22 into industry, and industry scores `gather_material` and `build`.

**The narrative has become: "I neglected it, so it fixed its house up better."**

The beautiful story of experiment 004 (doting→stay-at-home architect, shelter 98 / hands-off→wandering adventurer, shelter 0)
has not weakened in the current configuration, it has **inverted**. The paired curiosity difference of −0.58 confirms this.

### Finding 4 The dose response is a step, not a slope

```
                    industry   condition
doting→balanced          +3.15       -1.84
balanced→hands-off       +6.37      -19.58
```

**Feeding once every three days and feeding once a day raise almost the same ball.**
The only user who raises a different ball is the one who is about to churn.

---

## ★ New design rules from this round

6. **An effect with a median of 0 is the same as no effect.** The mean writes "a few balls changed drastically" as "every ball changed a little".

7. **To measure "what if someone else raised it", you have to actually change the person and run it again.**
   In a group comparison, seed noise always buries the user signal. Pairing cancels it.

8. **Priority of attribution carriers: state > events > personality.**
   `condition` has 99.2% directional consistency, personality only 68.7%. The demo should lead with state.

9. **A new metric means measuring the noise floor again.** (A corollary of rule 5 — this time the sign permutation was done from the start.)

---

## Baseline (as of experiment 012; the latest numbers are in experiment 013)

```
industry effect size dz   +0.600    target > 0.8
pairs with no change       30.2%    target < 20%
personality-label flip     12.8%    target > 50%
hands-off mortality         6.5%    target < 10%
```

(The third row depends on `dominant_style()`, whose criterion ordering is wrong: caution=100 gets labelled a workhorse.
The most common transition, "cautious→workhorse" with 24 cases, is largely a product of that bug.)

---

## Next steps

No more parameter tuning — there is no room on a peak. In this order:

1. ✅ Turn the paired experiment into a standard measurement script (`paired.py`)
2. ✅ Make the binary switch continuous → see experiment 013 (**conclusion: this is not the bottleneck**)
3. Open a second and third channel for the user, so that all attribution does not rest on feeding
4. Deal with the ceiling in time (personality topping out, 60-day mortality)

---

## Experiment 013 — the hypothesis is falsified: the bottleneck is not the switch but a leak upstream

### First attempt: making the ratchet continuous (failed)

Done as planned: add a `hardship` accumulator (condition deficit × duration),
raise `trait_floor` continuously along a saturating curve, anchored to "the personality at the moment the crisis began"
(anchoring to the current personality runs away — the floor rises along with the personality). No threshold anywhere.
`fears_hunger` is kept only as a narrative marker.

```
                    experiment 011   after going continuous
industry median          +1.34            +0.96
industry dz             +0.600           +0.524     ← it went down instead
pairs with no change      30.2%            29.9%
```

**Nothing moved.**

> If smoothing the transfer function has no effect, that means **the input itself is binary**.

### Diagnosis: the input really is binary

```
hands-off:  hardship ≈ 0 (never went hungry):  49.1%
        condition == 100 exactly:              53.2%
        hardship quantiles: p50=0.04 → p60=1.38    ← nothing in between
```

### ★ Root cause: explore is an infinite food tap

```
                 explore share   gather_food share   hardship
hit a crisis         0.0%             12.0%           4.66
never in crisis     36.5%              3.4%           0.00
```

**A ball that explores never goes hungry, and a ball that does not explore inevitably does. Zero overlap.**

The code for `explore` is `if rng.random() < 0.28: food += 2`, which is **bounded by no resource cap at all**.
An exploring ball accumulates about 147 portions over 30 days while needing only 79.

The scarcity so carefully manufactured in experiment 004 **had a leak, and half the balls escaped through it**.

> **This was predicted by rule one:**
> "the user's influence = the part the ball cannot solve by itself."
> Exploring is exactly a way the ball solves the problem by itself.
> The rule was right; nobody went back to audit whether the code violated it.

### Incidental finding: what the positive feedback amplifies is the seed, and it happens before the user intervenes

Comparing the **initial** personality (reconstructed from the seed) and the **final** personality of the "hit a crisis" and "never in crisis" groups:

```
                initial                    final
           crisis   no crisis        crisis   no crisis
curiosity  47.1     54.3            47.1     86.7
caution    52.8     46.6            91.6     45.0
```

**A 7-point initial difference is amplified into 40 points.** An amplification factor of about 6.

That is difference source #4 (positive feedback) working as designed — but what it amplifies is **the noise of the seed**,
and it locks the ball into one of two attractors before the user's feeding can have any effect.

### The fix

```python
EXPLORE_FOOD_YIELD  = 0.5   # was hardcoded at 2.0. Exploring is now a subsidy, not a substitute
LOCAL_FOOD_REGEN    = 2.4   # 2.2 → 2.4. With the leak plugged the balls have no fallback, so local supply is loosened
```

(The two magic numbers `0.28` and `2` were promoted to named parameters along the way. The magic numbers hid this bug for an entire round.)

### Results

```
                        exp 011   continuous only    final     target
industry median          +1.34        +0.96         +14.38      ≠ 0
industry dz              +0.600     +0.524     +0.884    > 0.8   ✓
pairs with no change      30.2%        29.9%           6.5%    < 20%   ✓
condition median           0.00         0.00          -6.72      ≠ 0     ✓
hands-off mortality        6.5%         6.5%           7.8%    < 10%   ✓
```

**The dose response went from a step to a slope:**

```
                     industry   condition
doting→balanced      before   +3.15      -1.84       now   +6.60   -12.45
balanced→hands-off   before   +6.37     -19.58       now   +5.92   -13.76
```

The two segments are now nearly equal — **feeding every 3 days and feeding every day finally raise different balls**.

At the population level (`diagnose.py`) all three carriers show a gradient while the control arm stays flat:

```
          hunger-scarred  storm-fearing  industry  condition
doting          0.0%          37.8%        66.3      100.0
balanced       23.4%          37.2%        71.1       87.3
hands-off      49.5%          42.4%        79.7       76.4
```

spread 8.96 → 13.43; the industry signal-to-noise ratio 7.2 → 12.7;
caution goes from 2.1 → 5.4, so it is no longer a single carrier carrying the signal.

---

## ★ New design rules from this round

10. **If one link in the transmission chain is binary, the whole chain is binary.**
    Changing the far end achieves nothing. Walk up the chain until you find the first binary point.
    How to tell: smooth the transfer function, and if the output does not change, the problem is in the input.

11. **Audit the bypasses through which "the ball solves the problem itself" regularly.**
    Rule one had the direction right, but the code can quietly grow something that violates it
    (this time it was the food yield of exploring, hidden inside two magic numbers).
    **Every time an action that produces a resource is added, ask: does this make the user optional?**

12. **Positive feedback amplifies whichever difference entered the loop first.**
    The seed's noise enters on day 0, while the user's feeding takes days to show
    → the loop locks the ball into an attractor and the user can never catch up.
    **The user's input must enter the system before the positive feedback locks in.**

Plus one methodological rule:

13. **A hypothesis being falsified on the spot by your own tool is evidence the tool works.**
    The first thing `paired.py` did once it existed was refute the very hypothesis it was built for.
    Looking only at spread, "going continuous" would have been recorded as a small improvement rather than a falsification.

---

## Still unsolved (after experiment 013)

- **The direction of `shelter` is still inverted** (+9.09). Hands-off balls still fix their houses up better.
  The root cause is unchanged: the ratchet pours into `industry`, and `industry` scores `build`.
- **The paired medians of `caution` / `curiosity` are still ≈ 0.** The user's channel converges on the single dimension `industry`.
- **The personality-label flip rate is 17.1%** (target 50%), and a substantial part of it is the `dominant_style()` bug.
- **Balanced now dies at 2.5%** (previously 0%).
- ⚠ **The new configuration has not been re-tested for 60-day durability or ±7% parameter robustness** (problems 2 and 3 in the stocktake).

---

## Experiment 014 — ablation: how much does each mechanism actually contribute (`ablation.py`)

The method is taken from §6 of [[Generative Agents notes]]: switch off each component of the architecture in turn and see how far the metric drops.
They proved "every component is necessary"; what we want to prove is **that differentiation is not the doing of one knob, and is not random**.

300 seeds × 30 days, paired doting → hands-off:

```
condition                       ind dz   ind median   cond dz   no change   hands-off dead   vs full
full architecture                0.861     12.08      -0.826       6.5%          8.0%       baseline
− personality weight             0.823     13.31      -1.290       5.3%          0.0%          -4%
− positive feedback loop         1.439     14.75      -0.767      16.7%          0.0%         +67%
− ratchet (no mark left)         1.484      6.55      -0.633       5.8%         13.3%         +72%
− seasonal fluctuation           0.732      9.70      -0.713       7.4%          9.3%         -15%
− food deficit                   0.401      0.94      -0.413      32.3%          0.0%         -53%
− user difference (null)         0.000      0.00       0.000     100.0%          3.0%        -100%
```

**The null row is exactly 0** — when the feeding intervals of the three users are made equal,
two runs of the same seed are deterministically identical. The measurement pipeline does not leak.

### The results are uncomfortable but informative

**1. The food deficit is the overwhelming top contributor (−53%).**
Switching it off (= restoring the exploration food leak) takes the median straight down to 0.94, with a third of pairs unchanged.
The judgement of experiment 013 is independently confirmed.

**2. Positive feedback and the ratchet contribute negatively to the "user attribution" metric.**

That looks like bad news, but it actually quantifies the tension of [[Design points and risks]] §5.2:

> Positive feedback (difference source #4) amplifies **the seed**,
> and the seed is **noise** for the user's signal.
> It makes the balls differ from one another (large σ) while making "was this caused by the user" harder to see.

**Difference sources #1/#4 and #3 are competing for the same variance budget.** That is a genuine trade-off, not a bug.

The ratchet is the same: switching it off raises dz to 1.484, **but halves the median (12.08 → 6.55) and takes mortality from 8.0% to 13.3%.**
The ratchet's real contribution is **raising the median and keeping them alive**, not raising dz.

**3. ⚠ Switching off the personality weight barely changes dz (−4%) and takes mortality to zero.**

This one deserves the most caution, because what it exposes is **a problem with our metric**:

> At `PERSONALITY_WEIGHT = 0` the personality numbers **have no effect on behaviour at all**.
> And yet industry dz is still 0.823.
> So dz measures **a difference in a number**, not **a difference in behaviour**.

This is exactly what [[Design points and risks]] §5.5 warned about: "the difference must be visible".
**Every current metric measures numbers, and not one measures behaviour.**

Incidentally: the personality weight is what kills the balls (mortality 8.0% → 0% once it is off), consistent with the observation of experiment 002.

---

## ★ The rules from experiment 014

14. **Positive feedback amplifies whichever difference entered the loop first — it serves "individual diversity", not "user attribution".**
    Those two goals compete for the same variance. Which one you want depends on what the product is selling.

15. **An ablation table exposes the blind spots of the metric, not only the contributions of the mechanisms.**
    dz staying put when the personality weight is switched off means the metric is measuring the wrong thing.
    **What should come next is a behaviour-layer metric** (how far apart the daily action distributions of two paired balls are),
    rather than further optimisation of a numeric-layer dz.

---

## Experiment 015 — filling in the behaviour layer: at which layer does the selling point hold (`behavior.py`)

Rule 15 of experiment 014 put it bluntly: every metric measures numbers and none measures behaviour.
This round fills that in. `action_by_hour` was added to `Agent` along the way (recorded per hour),
and the criterion-ordering bug in `dominant_style()` was fixed.

### Three metrics and their noise floors

TV (total variation distance) is always positive, so sign permutation cannot be used. **The correct control is to change the comparison object:**

```
TV_user  = same seed, different user     ← the behavioural difference caused by the user
TV_base  = same user, different seed     ← the difference two balls have anyway
```

**TV_user must clearly exceed TV_base**, or "my ball is different from yours"
cannot be told apart from "balls differ anyway", and the user still will not feel they raised it.

### ✗ Conclusion one: the behaviour layer does not hold

```
caused by the user (same seed, different user)    TV 0.160
baseline (same user, different seed)              TV 0.286 / 0.223

user / baseline = 0.63×      p = 0.000   ← significant, but in the wrong direction
```

The routine metric puts it even more harshly:

```
hours whose routine differs:   caused by the user 5.05/24 (median 0)   baseline 9.35/24 (median 13)
```

**The median is 0 — in more than half the pairs the two balls have exactly the same daily routine.**
And the entire displacement is concentrated on one action: `gather_food +7.5%`,
which is precisely the behaviour the user cannot see.

### ✓ Conclusion two: the state layer does hold

```
feature                only hands-off   only doting   discordance rate
still looks healthy            0             169          56.3%   ← direction perfect
has a food store              81              79          53.3%
has a decent home             39               0          13.0%   ← direction inverted
often goes out                 0              15           5.0%

★ at least one feature differs: 78.7%     target > 60%   ✓
```

**78.7% of pairs can be told apart at a glance, without looking at any number.**

### Rule 8 needs revising

It used to be "state > events > personality". A fourth must be added, and it comes last:

> ### ★ state > events > personality > **behaviour**
> Behaviour is not only the weakest but **below baseline** — the user's influence on "what the ball does each day"
> is smaller than the seed's influence on it.

### Experiment 015b — a direct test of rule 12, and a false dawn

Rule 12 says the seed competes with the user's signal. So try turning the initial noise down
(`INITIAL_TRAIT_SPREAD`, previously hardcoded at ±15):

```
spread   TV user   TV baseline   ratio   ind dz   visibly distinct   hands-off dead
  15.0   0.146    0.277    0.53     0.86     72.5%      8.0%
   6.0   0.160    0.255    0.63     0.91     78.7%      0.0%
   0.0   0.167    0.138    1.20     0.68     67.0%      0.0%
```

The ratio goes from 0.53 to 1.20, which looks like a solution. **But look at the `TV user` column: it barely moves.**

> ### ★ Rule 16: a better ratio is not a stronger effect
> The numerator did not change; the denominator was cut away.
> In a world with spread=0 every ball is the same, so this trades "abolishing individual diversity"
> for "a larger user share" — throwing away the other half of the product's value.
>
> **The user's behavioural influence has a ceiling, stuck at TV≈0.16, and no amount of seed tuning moves it.**

That said, `spread 15 → 6` is better on every metric and comes free, so it has been adopted.

---

## Experiment 016 — fixing "caring for it actually harms it"

> ### ⚠⚠ The conclusion of this section was overturned by experiment 017, and the weight 1.2 was reverted to 0.6
> Every 30-day number below is real, but **this parameter set does not survive 40 days**:
> at 60 days even the doted-on balls die at 45%. The cause is the caution weight added here.
> **The original text is kept, because this crash is itself the most valuable record.**

### Diagnosis (visible directly in the demo material)

```
hour      0 1 2 3 4 5 6 7 8 91011121314151617181920212223
doting    sl ex ex sl ex ex sl ex sl ex ex sl ex sl ex ex sl ex ex sl ex sl ex ex    shelter  0
hands-off ga ga sl sl ga ga ga sl ga ga ga sl ga sl sl ga ga sl sl sl ga sl sl sl    shelter 99
```

The doted-on ball **explores all day and builds nothing**.

Checking `ACTION_TRAIT_MATCH` makes it clear: `build` does respond to `caution`,
but **`gather_material` responds only to `industry`**, and `industry` only rises through the hunger ratchet.
Without material there is no way to build a house.

> **Taking good care of your ball removes the only motivation it had to build a house.**
> That is a one-line design flaw, not a parameter problem.

### The fix

```python
"gather_material": {"industry": 1.0, "caution": 1.2}   # previously industry only
```

**Wanting safety** should also drive gathering material, not industry alone.
(Adding positive feedback on `caution` at the same time was tried, and "visibly distinct" fell to 52–60% instead —
the positive feedback amplified the seed again. Rule 14 applies once more, so it is not added.)

A weight sweep (re-verified on 700 seeds; 1.2 is a sharp peak and both 1.1 and 1.3 are worse ⚠ robustness test pending):

```
c_match   mean shelter   has a home hands-off/doting    TV ratio   ind dz   visibly distinct
   0.0        +14.07      89/0          0.64     0.91      76.0%
   1.1         -0.08      63/56         0.53     0.69      76.1%
   1.2         -0.78           75/171                     0.53      0.64        82.5%   ← adopted
   1.3         -0.28      52/116        0.52     0.60      73.7%
```

### Results: much better than the sweep suggested

Watching `ind dz` alone would suggest a bad trade (0.91 → 0.67). Across all metrics it is not:

```
                        exp 015     exp 016
condition dz            -0.83      -1.04
condition median          -6.72      -26.40   ← the median finally moves substantially
condition |d|≥5         50.4%      79.7%
caution dz                +0.37       +0.48   (directional consistency 81.7%)
industry dz               +0.88       +0.67   ← the price
shelter                   +9.09       -0.74   (p=0.383, the inversion is gone)
visibly distinct           78.7%       82.9%
"has a decent home" direction   39/0 inverted    30/76 correct
hours whose routine differs   5.05(median 0)  10.58(median 11)
pairs with no change            6.5%        3.8%
hands-off mortality             7.8%        0.2%
```

**0.24 of industry bought: the condition median rising from 6.7 to 26.4,
caution going from no signal to a signal, the inversion disappearing, mortality falling to zero, and 82.9% visibly distinct.**

⚠ But `TV ratio` is still 0.53 — **the behaviour-layer conclusion has not changed.**
(The routine metric rose to 10.58/24 with a median of 11, which fights the TV; two behaviour metrics disagreeing
means TV measures "the overall mix of actions" while routine measures "what it is doing right now",
and the latter is closer to what the user perceives. This is not yet fully understood.)

---

## ★ The rules from experiments 015–016

16. **A better ratio is not a stronger effect.** Check whether the numerator moved before reading the ratio.

17. **Making a trade-off while watching one metric leads you the wrong way.**
    Experiment 016 is a loss viewed through `ind dz` and a large gain viewed across all metrics.
    **Once there are layered metrics, a trade-off must be read off the whole table at once.**

18. **Every time a new behaviour is added, ask which traits drive it.**
    `gather_material` hanging on industry alone accidentally produced "caring for it harms it".
    Every behaviour needs at least two personality pathways, or it becomes the exclusive outlet of one mechanism.

---

## Current state: at which layer does the selling point hold

| Layer | Conclusion | Evidence |
|---|---|---|
| **state** (condition, food store, whether it has a home) | ✓ **holds** | visibly distinct 66% (30 days) to 86% (90 days), robust to ±7% perturbation |
| **events** (the story of nearly starving) | ✓ **holds** | 187/0 discordant pairs, there is a story to tell |
| **personality** (the numbers) | ✓ holds statistically, weak perceptually | condition dz ≈ 1.0 |
| **behaviour** (what it does each day) | ✗ **does not hold** | per-hour TV user/baseline = 0.68–0.80, **three metrics agree, and it is insensitive to both parameters and time scale** |

> **The original selling point, "two users raise balls with different personalities",
> holds at the state and story layers and fails at the personality and behaviour layers.**
>
> This is still a product, but the pitch is different:
> lead with "your ball looks thin" and "it remembers nearly starving",
> and do not lead with "its personality/behaviour differs from everyone else's".

---

---

# Experiment 017 — settling both outstanding debts (both went wrong)

## 17a The two behaviour metrics disagree: I read them wrong

TV fell from 0.160 to 0.113 while the routine difference rose from 5.05 to 10.58. At the time I guessed "routine is closer
to what the user perceives, so the conclusion may not be so bad". **The guess was wrong.**

The key is the **mode margin of the dominant action**:

```
experiment 015:  margin = 0.40
experiment 016:  margin = 0.16    ← collapsed
```

After adding caution the ball starts alternating between gathering material and sleeping,
and the top action leads the second by only 16 percentage points — **the tiniest perturbation flips the "dominant action"**.

What `rhythm_diff` measures the rise of is the fragility of the mode, not a difference in behaviour. The proof: **the baseline
rose in step from 7.73 to 13.88**, leaving the ratio almost unchanged. I looked at the numerator and not the denominator (breaking rule 16 again).

### The correct routine metric: compare distributions per hour

`hourly_tv()` — compare the action distributions hour by hour and average. By convexity it is strictly more sensitive
than an aggregate TV (aggregation only shrinks the distance), and it has no mode-flipping problem.

```
                        user    baseline   ratio
experiment 015  TV aggregate   0.160   0.255   0.63
                TV per-hour    0.244   0.324   0.75
                routine (mode) 5.053   7.733   0.65
experiment 016  TV aggregate   0.113   0.216   0.53
                TV per-hour    0.212   0.307   0.69
                routine (mode)10.582  13.880   0.76
```

**All three metrics agree: the ratio is 0.53–0.76 and not one of them reaches 1.**
`behavior.py` has been switched to `hourly_tv`, and the mode version is kept only as a control with a warning attached.

> ### ★ Rule 19: when metrics disagree, go and check the one more easily pushed by noise first
> Do not pick whichever favours your own conclusion.

## 17b Durability: the experiment 016 parameters wipe the population out

```
days    visibly distinct   cond dz   routine ratio   doting dead   hands-off dead   caution saturated
 15      50.7%    -0.70     0.73      0.0%      0.0%       0.0%
 30      82.9%    -1.02     0.69      0.0%      0.3%       0.0%
 60      91.4%    -1.35     0.52     43.7%     59.3%       7.5%
 90      87.9%    -1.99     0.57     56.3%     75.3%      18.1%
```

**At 60 days even the doted-on balls die at 43.7%.** A simulator that kills half of the best-cared-for balls
is not a valid instrument, whatever the product pitch says.

The attribution is clean:

```
caution weight   60-day doting dead   60-day hands-off dead   material share of the action budget
    0.0          0.0%          16.0%           14.6%
    0.6          0.0%          15.6%           21.7%
    1.2               45.2%                 60.4%              25.3% (as high as 29.7% at 30 days)
```

**It is the weight added in experiment 016.** The balls spend three tenths of their action budget gathering material,
leaving food chronically underinvested; at 30 days the initial stock and the seasons hold it up, and at 60 days it collapses.

### A structural conjecture that was falsified (recorded so it is not walked again)

I thought it was "the need is satisfied but the personality term keeps pushing": the need term of `gather_material` is
`(100-shelter)*0.30`, which is zero at shelter=100; but the personality term `caution` contributes a constant ~36 points
at caution=100, **bounded by no measure of how far the need is satisfied**.

So a gate was added: `shelter > 90 and material ≥ 6 → this action is illegal`.
Result: 60-day mortality 60.4% → 57.6%, **almost no effect**.

The cause: the house decays by 8.4 a day, so shelter can rarely stay above 90 — the ball is not hoarding,
**it is on a treadmill endlessly repairing its house**. The conjecture is falsified.

### Disposition: revert to 0.6

```
days    visibly distinct   cond dz   routine ratio   doting dead   hands-off dead   caution saturated
 15      50.7%    -0.78     0.80      0.0%      0.0%       0.0%
 30      66.0%    -0.91     0.78      0.0%      0.0%       2.0%
 60      73.1%    -1.05     0.70      0.0%     15.7%      78.1%
 90      86.3%    -1.21     0.68      0.0%     27.0%      75.6%
```

- ✓ the wipeout is solved (doting: 0% mortality at 90 days)
- ✗ **the inversion is back** (has a home, doting/hands-off = 1/18; still only hands-off balls have homes)
- ✗ 30-day visibly distinct 82.9% → 66.0% (still above the 60% target, but clearly worse)
- ⚠ **a new problem: at 60 days, 78.1% of balls have caution pinned at 100** (the old configuration gave 57.3%)

> **The inversion is a narrative problem and the wipeout is a validity problem; protect the latter first.**

## 17c Robustness (30 days, ±7%)

```
                        visibly distinct   cond dz   routine ratio   hands-off dead
baseline                     82.9%          -1.02        0.69            0.3%
LOCAL_FOOD_REGEN -7%     90.3%     -1.55     0.67     11.0%   ⚠
LOCAL_FOOD_REGEN +7%     74.2%     -0.70     0.69      0.3%
HUNGER_RATE      +7%     89.3%     -1.70     0.70      9.7%   ⚠
PERSONALITY_W    ±7%     76-79%    -0.8~-1.0 0.70    0~1.7%
caution(material)    -7%     74.2%          -0.97        0.70            0.3%   ← has-a-home direction 32/38, the direction is gone
caution(material)    +7%     72.1%          -0.95        0.68            1.0%
```

- **visibly distinct stays between 71.7% and 90.3% and never falls below target.** That metric is stable.
- **the routine ratio stays between 0.62 and 0.80, completely unmoved.** The behaviour-layer conclusion is entirely insensitive to parameters.
- ⚠ either −7% food supply or +7% hunger rate pushes hands-off mortality to around 10%.
- ⚠ **a ±7% change in the `caution(material)` weight is enough to make the "has a home" direction vanish** — what 016 fixed
  was sitting on a knife edge all along, and this should have been seen before reverting to 0.6.

---

## ★ The rules from experiment 017

19. **When metrics disagree, check the one more easily pushed by noise first, and do not pick whichever favours you.**

20. **Tuning at only one time scale is the same as not tuning.**
    Every 30-day metric of experiment 016 improved, and at 60 days the population was wiped out.
    **Any parameter change must be looked at on at least two time scales.**

21. **"Wipeout" and "the narrative is wrong" are not problems of the same order.**
    The first invalidates the instrument; the second only makes the product story less appealing. When they conflict, protect the instrument's validity first.

---

## Still to do

- ✗ **The shelter inversion is still unsolved** (experiment 016's fix was rejected by 017).
  Next time it must be changed **structurally**: let "wanting safety" drive building in a way that does not consume the long-term action budget,
  rather than tuning a weight yet again.
- ⚠ **78% of balls have caution pinned at 100 at 60 days**; the ceiling problem of the personality system is worse than before
- ⚠ mortality is still sensitive to food supply and hunger rate (±7% → 10%)
- the paired median of `curiosity` is still 0
- `sweep.py` / `food_sweep.py` have been superseded and should be marked deprecated

---

---

---

# Experiment 018 — the v2 refactor: taking the "user" out of the model

> Date: 2026-08-10
> ⚠ **A numeric dividing line**: v2 splits the world and the individual into two independent random streams,
> changing the consumption order, so numbers after 018 **cannot be compared directly with 011–017**.

## 0. First, a reported bug was checked — it does not exist

Someone pointed out that `s += max(0.0, self.hunger - 35) * 0.85` appears twice inside `gather_food`,
so the model actually run would be ×1.7. **Checked: `grep -c` = 1, it appears once (sim.py:220).**
Nothing needs re-running. Recorded here so the same thing does not trip anyone up again.

## 1. Structure: the three layers Agent / World / Influence

The model used to contain:

```python
USER_ARCHETYPES = {"doting": {"feed_every_days": 1.0}, ...}   # difference source #3
```

and the Agent constructor took `archetype` directly. That writes the product philosophy backwards:

```
User type → Feeding → Personality        (before)
World → Experience → Memory → Personality → Goals → Behavior   (now)
```

Split into:

```
sim.py                          scenarios.py
├─ World      resources/weather/objects/events   FEEDING  three feeding frequencies (the old control arm)
├─ Influence  give_food / add_book               WORLDS   11 worlds (the new main line)
│             play_music / change_env
├─ Agent      personality/needs/memory/goals
└─ Life       binds the three together and runs them
```

**The word "user" no longer appears in `sim.py`.** The Agent only sees "two extra portions of food in the world today"
and does not know who gave them. The three archetypes are kept as experiment groups but moved to `scenarios.py`.

`scenarios.run()` attaches a `.scenario` label to the agent it returns —
that is the **experiment ledger**, used by analysis scripts for grouping, and the model never reads it while running.

## 2. The temporal structure of personality (note ⑤): forms fast, fades slow

The old `trait_floor` was a permanent one-way valve. It becomes two layers:

```
soft floor  fades by 0.35 a day; a "medium-term habit"
perm floor  40% of what a landmark raises becomes a permanent bias; an "identity"
                soft is never below perm
```

Plus: on well-fed, sheltered days `hardship` fades by 0.015 a day.

## 3. The Goal layer (note ③): from a reactive agent to an autonomous life

It used to be `tick → score → take the highest`, a perfectly good **Reactive Agent**.
What the user saw was "this tick, build happens to score highest", not "it has been building a home these last few days".

```python
goal = {"type": "improve_home", "priority": 0.72,
        "created_from": "storm_memory", "progress": 0.35}
```

It thinks once every morning (not every tick, which would destroy continuity), and the goal biases the action scores.

### ★ Four traps hit, each worth recording ★

**Trap 1: a count-based progress measure with no baseline stored.**
The progress of `see_the_world` was computed from the cumulative explore count, so it was "complete" the moment it was raised →
completed daily, re-raised daily → re-raising refreshes `created_day` → permanently inside the minimum commitment period
→ **the ball is locked onto this goal and starves to death.**
The same class of error as experiment 009: **a count-based metric must store a baseline.**

**Trap 2: intention overrides survival.**
In the first version the goal bonus applied unconditionally, and the ball starved chasing "go and see distant places".
A suppression term was added: when hunger/condition are critical, the goal bonus decays proportionally to 0.
→ This is the rule "personality needs slack to express itself" restated at the intention layer.

**Trap 3: adding a bonus is not enough; it must also become distractible.**
A ball drifted to curiosity 100 / caution 18 has a +44 personality bonus on explore,
which a +22 goal bonus alone cannot cover — measured, it "wanted to fix its house" for 13 days straight while running around outside,
and the house rotted to 0. `GOAL_OFF_TASK` was added: pastime actions (explore/read) are suppressed while a goal is active.
> **Focus is not only "wanting A more", it is also "wanting B less for now".**

**Trap 4: a refractory period forces out intentions it cannot act on.**
Just after completing see_the_world → the refractory period suppresses it → improve_home is pushed up →
but its personality does not support it at all → it wanted to fix the house for 8 days straight and never picked up a single log.
A stall-abandon rule was added (abandon after 4 days without progress, leaving a memory of "wanted to but never did").
> People are the same: "I have been meaning to fix the roof but never have" — that intention eventually fades by itself.

Result: **each goal is held for 3.7 days on average and 8 things are completed in a lifetime**,
and `storm_memory` and `hunger_memory` appear among the sources — memory really is generating intentions.

## 4. Memory (note ④): from flags+landmarks to structured objects

```python
{"event": "storm_destroyed_roof", "day": 12, "importance": 0.9,
 "emotional_weight": 0.82, "consequence": "shelter_damage",
 "related_traits": ("caution",), "tags": (...)}
```

Split into two kinds:

```
episodic   on day 12 there was a storm and the roof broke       grows without bound, needs forgetting
semantic   without solid shelter, rain is dangerous              capped at a few dozen, what behaviour really depends on
```

`recall(tags, k)` retrieves by **structured tags**, not vector similarity
([[Design points and risks]] §3.4; the most common failure in [[Generative Agents notes]] §6.5.2
is vector retrieval fetching the wrong thing).

`context_packet(day)` is the bundle that will later be fed to an LLM:
**current state + current goal + relevant memories + world knowledge + personality**.
Measured, it produces "goal: stock_food, created_from: hunger_memory" +
"day 25, lived through a stretch of not having enough to eat" — language and behaviour now line up.
Note that traits are read-only: the LLM never owns the personality.

---

## 5. ★ The main result of experiment 018: the environment beat the seed, and feeding never did ★

> ### ⚠ The baseline of the table below has a bug, corrected in experiment 019; the right numbers are there
> The baseline paired survivors within each cohort. The survivors of the barren world are filtered
> (the weak all died) → within-group variance too small → baseline too small → **the ratio is inflated**.
> After correction: rich↔barren 1.56 → **1.51** (conclusion unchanged),
> has-books 1.02 → **0.87 (★ gone)**.
> **"Books alone can clear 1" was an illusion.**

Same seed, same initial personality, same feeding frequency; only the world differs:

```
comparison                    routine TV  base  ratio   goal TV  base  ratio   visibly distinct   dead
rich world↔barren world           0.381  0.245  1.56     0.416  0.247  1.68        68.5%          6.0% ★
has books↔baseline                0.266  0.260  1.02     0.311  0.211  1.47        56.4%          0.0% ★
has music↔baseline                0.203  0.322  0.63     0.099  0.257  0.39        38.0%          0.0%
food-rich↔food-poor               0.162  0.286  0.57     0.182  0.292  0.62        41.7%          3.2%
material-rich↔material-scarce     0.205  0.285  0.72     0.127  0.240  0.53        41.2%          0.0%
rainy↔stable weather              0.253  0.273  0.93     0.228  0.245  0.93        68.4%          0.0%
doting↔hands-off                  0.195  0.279  0.70     0.349  0.228  1.53        71.6%          0.0%  ← the old axis
```

**A ratio of 1.56 is the first time this project has exceeded 1 at the behaviour layer.**
The ceiling on the feeding axis across every experiment from 011–017 was 0.80, and it never reached 1.

Three observations:

1. **Single factors mostly cannot win; the combination can.** Music 0.63, food 0.57, material 0.72
   and rain 0.93 are each below baseline; stacked together they give 1.56.
   The environment's effect is **cumulative**, not one switch.

2. **Goal is a strong carrier.** The goal-TV ratio is generally higher than the routine-TV ratio
   (1.68 vs 1.56 for the world pair; even the old feeding axis gives 1.53 vs 0.70).
   **Adding the goal layer incidentally opened an attribution channel stronger than the action distribution.**

3. **Weather alone changes personality a great deal but not the routine** (caution differs by 27.3 points, routine ratio 0.93).
   Personality and behaviour can decouple — another instance of the finding from the ablation experiment (014).

### Demo material (same seed, two worlds; this is the pair with the largest TV, so it is cherry-picked)

```
▸ rich world   caution 28 | curiosity 100 | industry  70   adventurer
             shelter  0   condition 53   food store 2
             spent its life pursuing: see the world (40%), read a little more (23%)
             completed 14 things, abandoned 1
             learned: books hold worlds I have not seen; there are places with more food far away

▸ barren world   caution 80 | curiosity  45 | industry 100   nest-builder
             shelter 99   condition 76   food store 4
             spent its life pursuing: store more food (90%), make the home sturdier (10%)
             completed 0 things, abandoned 4
             learned: without solid shelter, rain is dangerous
             day 2, a storm tore the roof off
```

> **The same seed. The same initial personality. Only the world differs.**
> This is the direct evidence for "the user changes the world like a god, and life grows into different shapes by itself".

⚠ "rich world vs barren world" changes four variables at once and is **not single-factor attribution**;
all that can be said is "the environment as a whole can produce different lives", not which factor did it.

---

## ★ The rules from experiment 018

22. **Count-based progress must store a baseline.** Same root as rule 5: before using any "cumulative quantity" as a metric,
    be clear about where its zero is.

23. **The intention layer needs slack too.** When survival is critical the goal must give way, or the agent will
    starve chasing an ideal. This is "personality needs slack" restated at the goal layer.

24. **Focus = a bonus + a cost to distraction.** Bonusing the goal action alone cannot cover a personality that has already drifted.

25. **An intention that cannot produce action must be able to fade.** Otherwise "wanting to" and "doing" decouple and the goal layer was added for nothing.

26. **The environment's effect is cumulative.** Single factors are mostly below baseline, and only the combination clears 1.
    → Product implication: **giving the user one prop achieves nothing; give them a whole modifiable world.**

---

## Still to do (after v2)

- ⚠ **No v2 configuration has had a 60/90-day durability test** (the lesson of experiment 017: tuning at one
  time scale is the same as not tuning). The goal layer is new and its long-term behaviour is entirely unknown.
- ⚠ **No ±7% robustness test**; the four new goal parameters (BONUS / OFF_TASK / REFRACTORY /
  STALL_DAYS) were all hand-tuned and have never been swept once.
- **The shelter inversion** has not been re-tested under v2.
- "rich world vs barren world" needs splitting into single factors before we know which one deserves the credit.
- The conclusions of `paired.py` / `ablation.py` / `behavior.py` all need re-running under v2
  (so far only a smoke test has been done, confirming they run and that the null is still 0).

---

---

---

# Experiment 019 — persistence becomes the main metric

> Date: 2026-08-10

Four things: fixing the instrument's validity, fixing the baseline, establishing "persistence" as the main metric, and promoting Goal to the main carrier.

## 1. Fixing validity first (rule 21: a wipeout beats a narrative)

The 60/90-day mortality of v2:

```
             30d     60d     90d
baseline        0.0%   11.5%   43.0%
barren world    5.5%   27.5%   54.0%
```

Diagnosis (90 days, baseline) — the balls that died all fit one profile:

```
          eat  sleep  gather food  gather material  build  explore     caution  curiosity  industry
muertos   11%   40%    2%    1%   0%  46%       18   100    78
vivos     11%   41%    6%   13%   4%  25%       59    83    88
```

**The balls that ran off drifted to "caution 18 / curiosity 100", spending 46% of their time outside and only 2% gathering food.**
Switching the goal layer off takes 90-day baseline mortality from 43.0% down to 7.0% — **it is that intention that kills them**.

### Root cause: note ⑤ incidentally removed the only brake

Positive feedback has no brake of its own (explore → curiosity↑ caution↓ → wants to explore more).
In v1 the **permanent trait_floor happened to serve as the brake**; v2 lets the floor fade, and the brake is gone.

### Two fixes

**Fix A: `TRAIT_SATURATION = 0.90`** — the more extreme the personality, the harder it is to grow more extreme.

```
 SAT     30d    60d    90d   caution pinned   environment ratio   visibly distinct
0.00    0.0%  11.5%  43.0%      44.6%      1.56     68.3%
0.90    0.0%   0.0%  28.5%       0.0%      1.55     79.9%
```

**Everything improves and not a scrap of the environment signal is lost.** It also incidentally cures the ceiling problem of
experiment 017, "78% of balls have caution pinned at 100 at 60 days".

**Fix B: pastime goals must have slack before they can be raised at all.**
The suppression inside `goal_bonus` acts **at execution time**, which is too late. The real problem is
**raising the ambition of "go and see distant places" while there is nothing to eat**.
The priority of `see_the_world` / `learn` is multiplied by
`slack = f(food store) × f(condition)`.

```
             30d    60d    90d
baseline        0.0%   0.0%   2.5%      (was 0.0 / 11.5 / 43.0)
rich world      0.0%   0.0%   4.5%
balanced        0.0%   0.0%   2.5%
hands-off       0.0%   3.0%   6.0%
doting          0.0%   0.0%   0.0%
barren world    6.0%  23.0%  37.5%      ← this world is deliberately extreme
```

> ### ★ Rule 27: the suppression of needs must act on **intention formation**, not **intention execution**
> Waiting until condition has fallen before suppressing the goal means the deficit is already done.
> "Slack" must take part in the judgement at the moment the ambition is raised.

## 2. Fixing the baseline (survivorship)

`environment.py` built its baseline by pairing survivors within each cohort.
The survivors of the barren world are a filtered batch → within-group variance too small → baseline too small → **the ratio is inflated**.
The treatment group uses the intersection of "alive on both sides", so the baseline must use the same batch of seeds.

### The corrected full 018 table (including the validity fix)

```
comparison                    routine TV  base  ratio   goal TV  base  ratio   visibly distinct   dead
rich world↔barren world          0.361  0.239  1.51     0.355  0.274  1.30        82.9%          6.4% ★
has books↔baseline               0.225  0.258  0.87     0.276  0.256  1.08        63.6%          0.0%
has music↔baseline               0.197  0.310  0.64     0.116  0.296  0.39        46.4%          0.0%
food-rich↔food-poor              0.156  0.281  0.56     0.171  0.332  0.51        51.7%          3.2%
material-rich↔material-scarce    0.207  0.276  0.75     0.137  0.285  0.48        53.2%          0.0%
rainy↔stable weather             0.255  0.273  0.94     0.277  0.269  1.03        78.0%          0.0%
doting↔hands-off                 0.190  0.265  0.72     0.417  0.233  1.79        82.4%          0.0% ← the old axis
```

**"Books alone clear 1" was an illusion created by the baseline bug** (1.02 → 0.87).
The conclusion about the combined world is unchanged (1.56 → 1.51).

## 3. ★ The transplant experiment: the difference is personality, not a thermometer ★ (`transplant.py`)

That 1.51 from 018 carries a fatal ambiguity: **at the time the two balls were still in different worlds.**
So it cannot distinguish:

```
(A) experience shaped it    → it survives a return to the same world
(B) only the current conditions differ → it vanishes once the environment matches
```

Method: 30 days of divergence, then **both sides switched to the "baseline" world for the second 30 days**, with measurement only in that second half.

```
condition   window TV   base   ratio   visibly distinct   dead    personality diff
stay          0.303    0.238   1.27         74.6%        24.4%    ca +23.9
move          0.300    0.259   1.16         76.8%         6.8%    ca +27.4

stay 1.27 → move 1.16   retained 91%
★ the ratio is still > 1 after the transplant
```

**With the cause removed the difference remains, and 91% of it is retained. It is (A).**
The product-document line "there was a heavy rain once… ever since then I have not liked being unprepared"
now has empirical support.

## 4. Single-factor persistence (`persistence.py`) — the conjecture was only half right

```
factor          stay routine  move routine  retained   stay goal  move goal  retained
books                0.92          0.87        94%        1.04       0.80       76%
music                0.64          0.62        97%        0.52       0.53      103%
weather              1.00          0.88        88%        0.97       0.94       97%
material             0.67          0.57        85%        0.58       0.53       91%
food rate            0.67          0.58        87%        0.55       0.57      103%
combination (ref)    1.27          1.18        93%        1.16       1.07       92% ★
```

### ⚠ Finding one: the retention rate distinguishes nothing

**Every factor's retention rate is between 85% and 103%.** Food rate retains 87%, books retain 94% — much the same.

> ### ★ Rule 28: persistence is not "how much was retained" but "how much was created in the first place"
> Practically any difference that gets created survives. The real difference is in **magnitude**, not in retention.
> So the main metric should be **the absolute post-transplant ratio**, not the retention percentage.

### Finding two: the conjecture was half right

| Conjecture | Result |
|---|---|
| food rate is weakest (written into no persistent structure) | ✓ **confirmed**. 0.58 after the transplant, the lowest; the personality residue is only +3.0 |
| books are strongest (written into knowledge and goal) | ✗ **merely tied**. Books 0.87, **weather 0.88** |

The mechanism columns (a difference = the second minus the first; a negative sign means the first has more):

```
factor        routine after move   semantic memory diff   permanent identity diff   personality residue after move
books                0.87                -1.01                    +0.04               caution +9.2
weather              0.88                -0.06                    -0.28               caution -26.8  ← nine times
food rate            0.58                +0.08                    -0.05               caution  +3.0
```

**The mechanistic direction is right, but the strongest persistent-write channel is weather, not books.**
Weather writes through storm → landmark → `trait_identity` into a **permanent identity**,
leaving a 26.8-point caution difference 30 days after the transplant. Books write only into `knowledge` and leave 9.2 points.

### ★ Finding three: `knowledge` is write-only — that is why books are weak

Checked the code: `self.knowledge` is written only by `learn()` and read only by `context_packet()`,
and **`score()` has never read it.**

> **Semantic memory is currently an ornament.** It can be recited but changes no behaviour.
> Books lose to weather not because they write less, but because the drawer they write into
> is not wired to behaviour.

That explains another number: **books' goal retention is only 76%, the lowest in the table** —
the `learn` goal needs books in the world, and once transplanted to the baseline world the books are gone and that channel is cut.
Weather is different: what it writes is on the ball itself, and travels wherever the ball goes.

> ### ★ Rule 29: only what is written into the **individual** can persist
> What is written into the world (books, music) vanishes with the environment;
> only what is written into `trait_identity` / `flags` travels with the ball.
> **Product implication: giving it a book is worth less than letting it live through an event.**

## 5. ★ Goal promoted to the main carrier ★

```
                     routine ratio   goal ratio
doting ↔ hands-off        0.72          1.79   ← the old axis, never passing on routine
rich world ↔ barren world  1.51          1.30
```

**The feeding axis never reached 1 on routine (a ceiling of 0.80 before 017), and reaches 1.79 at the goal layer.**

And it can be stated in one sentence:

```
goal                    doting   hands-off     diff
make the home sturdier   39.5%     29.2%     -10.3%
store more food          12.3%     54.0%     +41.7%
see the world            48.2%     16.7%     -31.5%
```

> The pampered ball spends half its life running into the distance; the neglected one spends half its life hoarding food.

This is the first time since experiment 011 that **the user's influence both exceeds the baseline and can be stated as a sentence**.
`behavior.py` has moved the goal layer into the main-carrier position.

The reasoning (written into the script comments): stronger than routine · carries `created_from` for attribution ·
can be stated as a sentence · is the most natural interface once an LLM is wired in (`context_packet` is organised around it).

---

## ★ The rules from experiment 019

27. **The suppression of needs must act on intention formation, not intention execution.**
    Waiting until condition falls before suppressing the goal means the deficit is already done.

28. **Persistence is not "how much was retained" but "how much was created in the first place".**
    Retention rates distinguish nothing between factors (all 85–103%); the main metric must be the absolute post-transplant ratio.

29. **Only what is written into the individual can persist.**
    What is written into the world (books, music) vanishes with the environment; what is written into trait_identity / flags travels with the ball.

30. **A structure that is written and never read is an ornament.**
    `knowledge` has content, can be recited, and affects behaviour not at all — which is why books lose to weather.

---

## Still unsolved

- ⚠ **`knowledge` is not wired into `score()`.** This is the direct to-do of rule 30:
  semantic memory should affect behaviour (for instance "knowing there is food far away" → more inclined to explore in the lean season),
  or the "books" product line cannot stand at the behaviour layer.
- ⚠ **The barren world's 90-day mortality is 37.5%.** An extreme world, but it must be confirmed as the design intent.
- ⚠ **The five goal parameters** (BONUS / OFF_TASK / REFRACTORY / STALL_DAYS / slack)
  have still never been swept for robustness once.
- Not one single factor clears 1 after the transplant; **only the combination does** (rule 26 holds again).
- `paired.py` / `ablation.py` need re-running on the fixed v2 to obtain a baseline.

---

---

---

# Experiment 020 — state levelling + deletion test: where does the difference actually live

> Date: 2026-08-11
> Background: the external ablation (`persistence_ablation.py`) has already shown that persistence is **not hardcoded** —
> with all three floor mechanisms switched off, the transplant ratio is still 1.07 and mortality is only 4%.
> But the margin above 1.0 falls from 0.18 to 0.07, and visibly distinct falls from 74.8% to 60.4%.
> **What is reported externally is the 1.07 row, not 1.18. The floors are not the source but an amplifier of about sixty percent.**

## 1. ★ State levelling: that caution curve is real (`leveling.py`) ★

After the transplant into a neutral world, caution keeps widening. Two readings:

```
strong  differentiation is self-sustaining — internal structure keeps generating caution-raising experiences (path dependence)
weak    state confound — it simply has not recovered; its condition/food store are worse, so it keeps meeting bad things
```

**Method**: at the moment of transplant, force hunger / energy / condition / shelter / inventory
to be exactly equal, leaving only personality / memory / goals different.
(`hardship` is deliberately not cleared — it is experience, not state.)

**★ Methodological correction: settle the surviving set per point ★**
The first version computed every row on "those alive at day 120", a loss of 24.5%/38.0%.
But the survivors are precisely "the balls that did not run off", which is exactly what this curve is about —
**selecting the sample by the conclusion**. Changed to computing each checkpoint separately:

```
[not levelled]        caution  curiosity  industry  condition   valid pairs   loss
day 30 (transplant)     +19.3     -20.8     +10.7      +1.1         188      6.0%
day 60                  +26.3     -17.4      +9.2     +12.9         187      6.5%
day 90                  +30.2     -17.6      +9.7     +13.2         185      7.5%
day 120                 +32.6     -19.2      +9.7     +14.8         151     24.5% ⚠

[levelled]
day 30 (transplant)     +19.3     -20.8     +10.7      +1.1         188      6.0%
day 60                  +28.9     -17.6     +11.7     +18.9         188      6.0%
day 90                  +32.2     -17.9     +11.2     +23.9         180     10.0%
day 120                 +30.3     -17.9      +9.6     +21.4         124     38.0% ⚠
```

Using only the points with loss ≤15% (30/60/90):

```
caution growth after the transplant    not levelled +10.9    levelled +12.9   (118%)
```

> ### ★ The strong reading holds, and more strongly than expected ★
> **After levelling the state, the gap does not narrow; it widens faster.**

The core prediction of the weak reading is "the barren twin is in worse shape so it keeps meeting bad things". The measurement says the opposite:
**at day 90 in the levelled group the barren twin's condition is +23.9 and its food store +8.6 — it is living better,
and still becoming more cautious.** The recovery-curve explanation is falsified outright.

## 2. The deletion test: a four-step ladder (`deletion.py`)

Delete each layer in a ladder at the moment of transplant:

```
condition          caut at move  +30 caut  +60 caut  +30 ratio  +60 ratio  +60 visible  +60 loss
① full                 +19.3       +26.3     +30.2      1.17       1.23       70.6%       6.5%
② −episodic memory     +19.3       +26.3     +30.2      1.17       1.23       70.6%       6.5%
③ −episodic+semantic   +19.3       +26.3     +30.2      1.17       1.23       70.6%       6.5%
④ traits only          +19.3       +26.7     +31.3      1.14       1.32       71.8%       6.0%
```

### ⚠ ②③ match ① to the decimal point — that is not a conclusion, it is evidence of a bug

Checking the code: `self.memories` is read only in `recall()` and `landmarks`,
and `recall()` is called only by `context_packet()`; `context_packet()`
**has never been called by `score()` or `tick()`.** The same goes for `knowledge`.

> ### ★ Rule 31: the entire memory system is currently write-only ★
> Rule 30 of experiment 019 was about `knowledge`. It is now confirmed that **episodic memory is the same**.
> That whole layer of structure added in note ④: retrievable, recitable, and **with zero effect on behaviour**.
>
> So steps ②③ of the deletion test are **no-ops by construction**;
> they cannot measure "how important memory is", only "memory is not wired in".

Step ④ (deleting flags / hardship / goal as well) actually raises the ratio to 1.32.
So the difference is **entirely** settled in the personality vector (+ the floors), and nothing else is carrying it.

## 3. Three code corrections (`persistence.py`)

**(a) The mechanism check counted the wrong thing.** It computed `len(b) - len(a)`, which is "how many more B has than A",
not "how far the two differ". Two balls with 3 completely different knowledge entries each would score 0.
Only after switching to the **symmetric difference of the sets** (how many entries exist on only one side) does the mechanism table carry information:

```
factor        routine after move  goal after move  semantic memory  permanent identity  landmark
books                0.87              0.80             1.54              0.43            1.54
music                0.62              0.53             0.46              0.35            0.46
weather              0.88              0.94             0.97              0.72            0.97
material             0.57              0.53             0.09              0.03            0.09
food rate            0.58              0.57             0.20              0.05            0.20
combination (ref)    1.18              1.07             1.84              0.71            1.84
```

**Weather's permanent-identity difference of 0.72 is the highest of any single factor** (books 0.43).
And books' semantic-memory difference of 1.54 is the highest yet still loses to weather — **precisely because of rule 31: that column does not enter behaviour.**
Material at 0.03 and food at 0.05 write practically nothing persistent, and are indeed the weakest (0.57 / 0.58).

**(b) The restoration phase was run in three directions.** The `objects` of "baseline" are empty, so on the question of "are there books"
it equals the barren world: a rich twin moved there loses its books and the `learn` channel is cut — an asymmetric adaptation cost.

```
factor           →baseline   →rich world   →barren world
books               0.87         0.79           0.88
weather             0.88         0.97           0.88
combination (ref)   1.18         1.22           1.08
```

**The direction dependence is mild, and the combination is ≥1 in all three directions (1.08–1.22), so the conclusion is solid.**

**(c) `cohort()` gained a cache.** With six factors × four cohorts, the baseline world was being recomputed many times over.

---

## ★ The rules from experiment 020

31. **The entire memory system is write-only.** Neither episodic nor semantic memory enters `score()`.
    Retrievable, narratable, and with zero effect on behaviour — deleting it changes no number.

32. **Settle the surviving set per point.** Computing the whole table on "those alive at the end"
    means selecting the sample by the conclusion — especially when the survivors' defining feature is the very feature being measured.

33. **Report the most conservative variant externally.** All floors off gives 1.07 and the full architecture gives 1.18;
    1.07 is what should be reported. The floors are not the source of persistence, but they amplify it by about sixty percent.

---

## Still to do

- ⚠ **Wire memory into behaviour** (rules 30 + 31). This is the biggest structural gap right now:
  `knowledge` should enter `score()` or `propose_goals()`,
  or the "give it a book" product line cannot stand at the behaviour layer,
  and the middle two steps of the deletion test will never measure anything.
- **The novel-situation probe** (state levelling + cross-sample prediction) has not been done.
- **Long-horizon mortality**: the 120-day paired loss is 24.5% (38.0% in the levelled group),
  so the last point of the curve is unusable. Either fix it to <10%, or only ever report up to 90 days.
- The five goal parameters still have not been swept for robustness.

---

---

---

# Experiment 021 — a methodological audit: a precision check-up for writing the paper

> Date: 2026-08-13
> Trigger: preparing to write 018–020 up as a paper, first asking "are there enough runs".
> Conclusion: **the number of runs is not the problem; the upward bias caused by too few is.**
> Every ratio reported until now was optimistic.

## 1. ★ The ratio estimator is systematically biased upward ★

Bootstrapping the transplant ratio (cluster bootstrap, resampling by agent):

```
condition             N=150               N=600               N=1500
full architecture  1.181 [1.030,1.359]  1.150 [1.073,1.231]  1.132 [1.085,1.184] ✅
−all floors ①②     1.065 [0.912,1.244]  1.075 [0.993,1.160]  1.044 [0.996,1.094] ❌
```

The point estimate **falls monotonically** with N. The cause is that `ratio = a ratio of means`, the denominator (baseline TV) is noisy, and
`E[X/Y] > E[X]/E[Y]` (Jensen's inequality). The smaller the sample, the greater the inflation.

> ### ★ Rule 34: a ratio must be reported with its sample size, and the sample size must be maxed out ★
> 1500 seeds take only 44 seconds. Stopping at 150/250 previously was purely a failure to realise there was a bias.
> **Every ratio in the paper is re-run at N=1500.** The headline is corrected from 1.18 to **1.13**.

## 2. ★ Adjacent pairing made the baseline too small ★

The baseline at `transplant.py:106` is `(al[i], al[i+1])` with a step of 2 — each ball used once,
paired by "adjacent seeds". Switching to random pairing (with exactly the same sample size):

```
baseline pairing method      ratio      CI width
adjacent, once (current)    1.1499      0.1402
random pairing K=1          1.1321      0.1360     ← same sample size, merely shuffled
random pairing K=5          1.1248      0.1131     ← 19% narrower, +14 seconds
random pairing K=20         1.1251      0.1077     ← saturated, not worth it
```

Two findings:

1. **Balls generated from adjacent seeds are more alike than two random ones** → baseline too small → ratio inflated by 2.2%.
   This is an implementation problem, not a statistical one: it is worth checking how `scenarios.make` derives
   the child RNG from the seed, since adjacent integers may produce correlated initial personalities.
2. The baseline is a U-statistic, and K=5 already reaches the variance lower bound (the between-agent variance).

> ### ★ Rule 35: baseline pairing must be random and repeated K=5 times ★
> 19% more precision for free, plus removal of a 2.2% bias.

After all three corrections, the evolution of the headline number:
`1.18 (as logged) → 1.13 (N maxed out) → 1.125 (pairing fixed)`. **Always > 1, but shrinking all the way.**

## 3. ⚠ That 1.07 of rule 33 does not stand

`− all floors ①②` at N=1500 is **1.044, 95% CI [0.996, 1.094] — right on the line, containing 1.0**.
More N cannot rescue it, because the true value is around 1.04.

The reviewer's challenge anticipated at the head of `persistence_ablation.py`:

> "You did not discover irreversibility, you wrote irreversibility in."

**The current data cannot answer it.** Once the floors are off, the effect falls into the noise. Two routes:
- **Honest downgrade**: admit that `trait_identity` is a **necessary mechanism** of persistence, not an amplifier.
  The sentence in rule 33, "the floors are not the source but an amplifier of about sixty percent", must be withdrawn.
- **Fix the mechanism and measure again**: wire memory into `score()` (the to-do of rules 30/31),
  give persistence a second channel that does not rely on `max()`, and see whether the no-floor variant can stand.

(The `− all three off` row at 1.04 is even less usable: mortality 28%, survivor contamination.)

## 4. ★ The parameter-randomisation set (`param_sweep.py`) ★

Answering "is this just a hand-tuned parameter set". Not a grid scan: N parameter sets are drawn independently
from a prior (15 knobs randomised simultaneously), the transplant experiment is re-run for each, and **the distribution of the effect** is reported.

Along the way the hardcoded slack in `sim.py` was exposed as `GOAL_SLACK_FOOD` / `GOAL_SLACK_COND`
(defaults unchanged, behaviour bit-identical), so the mechanism of rule 27 can now be swept.

### ★ Official results (500 sets × 300 seeds, 30.7 minutes, 12 processes) ★

```
500 sets sampled → 374 valid → 324 after dropping wipeouts (mortality > 40%)   total attrition 35.2%

transplant ratio (routine)  median 1.058 [1.045, 1.079]   IQR [1.010, 1.128]
                            share > 1  80.2% [75.9%, 84.6%]
transplant ratio (goal)     median 1.061                  share > 1  72.2%
log ratio (routine)         median 0.048                  share > 0  78.4%
```

**Conclusion: the effect is not something a hand-tuned parameter set produced.** The CI of the median clearly excludes 1.0, and the lower quartile
is also above 1 (1.010). The paper can state directly:

> Across 500 randomly sampled parameter configurations (15 parameters jointly randomised, 324 sets after dropping wipeouts),
> the median post-transplant ratio is 1.058 (95% CI [1.045, 1.079]),
> and 80.2% ([75.9%, 84.6%]) of configurations have a ratio > 1.

**The hand-tuned default configuration (1.132) sits at the 75.6th percentile of this distribution** — favourable, but far from
extreme. That sentence should be written into the paper proactively, not left for a reviewer to ask about.
(Incidentally: the floor-ablation variant at 1.044 sits at the 44.1st percentile, exactly mid-range among random configurations.)

### Parameter sensitivity (Spearman ρ against the transplant ratio)

```
TRAIT_DRIFT          +0.432   ← the only one above 0.4
PERSONALITY_WEIGHT   +0.289
LANDMARK_BONUS       -0.153
LANDMARK_PERMANENT   +0.136
GOAL_SWITCH_MARGIN   +0.112
the other 10          |ρ| < 0.09
```

> ### ★ Rule 36: the effect increases monotonically with the positive-feedback gain, and the goal-layer parameters barely affect it ★
> `TRAIT_DRIFT` (ρ=+0.43) is the only major driver, with `PERSONALITY_WEIGHT` second
> (+0.29). All five goal parameters (BONUS / OFF_TASK / REFRACTORY / STALL_DAYS /
> SLACK) have **|ρ| < 0.09** — the "goal parameter robustness" to-do carried over two rounds since 019
> is closed here: the conclusion is entirely insensitive to them.
>
> ⚠ But `TRAIT_DRIFT` must be discussed proactively. **Note that it is evidence, not a threat**:
> if persistence really comes from that self-amplifying loop, then the effect **should** rise with the loop's gain.
> This is the same thing as §3 (switching the floors off drops the effect into the noise), seen from the other side.
> The paper should present it as mechanistic evidence, not hide it as a fragility.

⚠ **The 35.2% attrition is a selection effect and must be disclosed**: what was dropped are configurations where "the parameters
were drawn too harshly and the balls cannot survive", not a random subset. `dead_move` / `dead_stay` are all persisted in
`sweep_results.csv`; the paper must state clearly how many were dropped and under what rule.

⚠ The pilot (31 sets) reported 67.7% and ρ=0.588 at the time, both small-sample noise. **This is itself another instance of rule 34** —
the conclusion from 31 sets differs from the conclusion from 324 by 12 percentage points.

### ★ Holdout confirmation (seeds 10000–10299, never touched) ★

011→021 iterated 21 rounds on seeds 0–299, a textbook garden of forking paths.
Moving the same analysis unchanged onto untouched seeds and re-running 500 sets:

```
                 development (0–299)      holdout (10000–10299)      diff
routine median  1.058 [1.045, 1.079]    1.041 [1.031, 1.050]    +0.016 [+0.001, +0.042]
routine > 1          80.2%                    72.9%                  −7.3 pp
goal median     1.061 [1.050, 1.073]    1.031 [1.015, 1.039]    +0.031 [+0.015, +0.050]
goal > 1             72.2%                    62.2%                 −10.0 pp

TRAIT_DRIFT          ρ=+0.432                 ρ=+0.426
PERSONALITY_WEIGHT   ρ=+0.289                 ρ=+0.288
```

**Three conclusions:**

1. ✅ **The claim stands.** The holdout median is **1.041, 95% CI [1.031, 1.050], excluding 1.0**,
   with 72.9% of random configurations > 1. On a fresh batch of unseen seeds the conclusion is unchanged.
2. ⚠ **But the development set really was inflated.** The difference CIs of both carriers **exclude 0**
   (routine +0.016 [+0.001, +0.042]; goal +0.031 [+0.015, +0.050]).
   21 rounds of iteration really did leave a mark on the seeds — small in magnitude, but **measurable**.
3. ★ **The sensitivity structure reproduces almost perfectly** (0.432→0.426, 0.289→0.288).
   The magnitude was lifted slightly by forking paths, and **the mechanistic conclusion is entirely unaffected**.

> ### ★ Rule 37: the paper reports the holdout numbers, not the development ones ★
> Development gives 1.058 / 80.2% and holdout gives 1.041 / 72.9%. **Report the latter.**
> And put this comparison table itself into the Methods — proactively showing "we quantified our own
> forking paths and reported the more conservative version" is a plus, not an admission of weakness.

## 5. The statistical work still missing (required for the paper)

1. ✅ ~~**A holdout seed set**~~ **done** (see the end of §4): 500 sets on seeds 10000–10299,
   median 1.041 [1.031, 1.050] still excluding 1.0, but with a measurable inflation on the development set.
   → Rule 37: the paper reports the holdout numbers.
2. ✅ ~~**Change the estimator to obtain a p value**~~ **done** (`significance_main.py`).
   Push the statistic down to each seed: `δ_i = TV(same seed across worlds) − TV(same world across seeds)`;
   δ can be either sign → **sign permutation is legitimate**, sidestepping the "TV is always positive" blockage of notes line 804.

```
                      n     numerator TV  baseline TV  ratio   mean δ    dz    δ>0      p
── development set seeds 0+, N=1500 ──
full architecture   1429   0.3103  0.2742  1.132  +0.0362  0.20  40.7%  0.0001 ***
−all floors ①②      1411   0.2960  0.2869  1.032  +0.0092  0.05  35.6%  0.0778 n.s.
── holdout set seeds 10000+, N=1500 ──
full architecture   1411   0.3094  0.2746  1.127  +0.0348  0.20  41.0%  0.0001 ***
−all floors ①②      1399   0.2983  0.2885  1.034  +0.0098  0.05  36.4%  0.0638 n.s.
```

   **The full architecture gives p=0.0001 and the holdout reproduces it exactly** (1.132 vs 1.127).
   **The floor ablation gives p≈0.07, not significant** — consistent with the CI conclusion of 021 §3, with the two methods corroborating each other.

> ### ★ Rule 38: the effect lives in the right tail, it is not uniformly distributed ★
> **`δ>0` is only 41%.** In other words, **for the median seed the baseline actually exceeds the cross-world difference**;
> the mean is positive because a few highly differentiated twins pull it up. Cohen's dz is only **0.20** (a small effect).
>
> The paper must not write "the environment makes agents different" but
> **"the environment makes some agents very different"** — heavy-tailed differentiation.
> That is actually more interesting (a threshold effect / path dependence), but it must be reported faithfully,
> and someone should go and find out what kind of seeds that 40% are (a new experiment).
3. **Multiple-comparison correction.** 6 factors × 3 restoration directions × 2 carriers = 36 tests, not one of them corrected.
   At minimum apply Benjamini–Hochberg FDR, or the ranking "weather 0.88 vs books 0.87" means nothing.
4. **Test-retest reliability (ICC)** and a **generalization test** (the novel-situation probe) are both still at zero.

---

## ★ The rules from experiment 021

34. **A ratio must be reported with its sample size, and the sample size must be maxed out.** A ratio is a biased estimator,
    systematically inflated at small N. 1500 seeds take 44 seconds; there is no reason to stop at 150.

35. **Baseline pairing must be random and repeated K=5 times.** Adjacent pairing makes the baseline 2.2% too small,
    and random K=5 buys 19% more precision for free.

36. **The effect increases monotonically with the positive-feedback gain (`TRAIT_DRIFT`), and the five goal-layer parameters barely affect it.**
    Across 500 random parameter sets, 72.9% (holdout) of configurations have a ratio > 1 — the effect is not hand-tuned.

37. **The paper reports the holdout numbers.** 21 rounds of iteration left a measurable inflation on the development seeds
    (routine +0.016, goal +0.031, both CIs excluding 0), but the mechanistic conclusion reproduces exactly.

---

## Still to do (after 021)

- ✅ ~~run the 500-set parameter sweep formally~~ **done**: 80.2% [75.9%, 84.6%] of configurations > 1,
  median 1.058 [1.045, 1.079]. The goal-parameter robustness to-do is closed at the same time.
- ⚠ **The floor-ablation line either needs a mechanism fix or a change of argument** (§3); this is the paper's biggest risk.
  → A preregistration has been written: [[Experiment 022 preregistration — wiring memory into decisions]] (frozen 2026-08-13, code unchanged).
  ★ While writing the preregistration, checking the code revealed that **rule 31 was half wrong**: `flags` and `hardship`
  **have long been wired into `score()` and `propose_goals()`** (sim.py:682/683/685/527/529/534),
  and the only unwired ones are `knowledge` (semantic) and `memories` (episodic).
  That lowers the prior for 022 — flags is already a "discrete marker → score bonus" design,
  and with the floors off the ratio is still only 1.044. See §2 of the preregistration.
- ⚠ Check the seed derivation in `scenarios.make`: whether adjacent seeds produce correlated initial personalities.
- Not one of the four statistical items in §5 above has been done.
- Carried over from 019/020: wiring memory into `score()`, the 120-day mortality, the novel-situation probe.

---

---

---

---

# Experiment 022 — wiring semantic memory into decisions: P1 passes, P2 does not

> Date: 2026-08-13 / 14
> **Preregistration (frozen before any code change): [[Experiment 022 preregistration — wiring memory into decisions]]**
> Every result, verdict and mid-course implementation correction is recorded in that document; only conclusions and rules are recorded here.

## 1. What was done

`knowledge` had been write-only (rule 30). This time it is wired into `score()` and
`propose_goals()`, and given a **forgetting rate** (use it or lose it),
adding `KNOWLEDGE_WEIGHT / KNOWLEDGE_GOAL_WEIGHT / KNOWLEDGE_FORGET`.
Regression check: with the three parameters zeroed it **reproduces exactly** 021's 1.27/1.18/1.26/1.07.

★ A prior discovery: **rule 31 was half wrong**. `flags` and `hardship` have long been wired into
`score()` and `propose_goals()` (`sim.py:682/683/685/527/529/534`),
and the only unwired ones are `knowledge` and `memories`. This finding is written into §2 of the preregistration,
and **the expectation for this experiment was lowered in advance** on that basis.

## 2. Results

On the preregistration-reserved seeds 20000–21499, N=1500:

```
P1 (ratio > 1 with all floors off)        ✅ pass
  022 off  1.007 [0.969, 1.043]  p=0.824 n.s.   ← a complete zero on the reserved block
  022 on   1.058 [1.029, 1.102]  p=0.0001 ***

P2 (deleting knowledge at transplant should collapse it by ≥0.05)   ❌ fail
  ① delete nothing        1.058 [1.029, 1.102]
  ② delete knowledge only 1.047 [1.011, 1.083]   a drop of only 0.011, CIs overlapping
  ④ delete flags only     1.047 [1.001, 1.074]   ← drops by exactly the same amount
  ⑤ delete all three      1.040 [0.997, 1.068]  p=0.0707 n.s.
```

**By the preregistered decision rule: P1 hits and P2 does not → the knowledge channel is not claimed.**

## 3. ★ The rules from experiment 022 ★

39. **Wiring changes the speed of differentiation, not the retention mechanism.** Once semantic memory enters `score()`,
    the balls of the two worlds separate further **during development**; what remains after the transplant lives in the trait vector
    and is almost independent of whether knowledge is still there (deleting all of it costs only 0.011).
    **"Persistence" and "magnitude of differentiation" are two different things.**

40. **Deleting knowledge and deleting flags cost the same.** Semantic memory is not a special carrier,
    merely one more equivalent discrete marker — consistent with the prior expectation in §2 of the preregistration.

41. **Episodic memory is still a complete no-op.** The variant deleting only memories is **bit-identical** to deleting nothing.
    The episodic half of rule 31 still holds.

## 3b. The relaxation test — ⚠ **unanswered, destroyed by mortality** (`relaxation_test.py`)

The question P2 left open: is the 1.040 remaining after deleting everything persistence, or "30 days is not enough to drift back"?
Run to 120 days and measured in three independent 30-day windows (all floors off, 022 on):

```
                    n      loss    ratio   95% CI
① delete nothing
  days  30– 60    1388    7.5%   1.058  [1.030, 1.103]  ≠1
  days  60– 90    1163   22.5%   1.100  [1.056, 1.135]  ⚠
  days  90–120     832   44.5%   1.109  [1.067, 1.160]  ⚠
⑤ delete semantic+episodic+flags
  days  30– 60    1394    7.1%   1.040  [0.995, 1.069]  contains 1.0
  days  60– 90    1138   24.1%   1.100  [1.057, 1.145]  ⚠
  days  90–120     787   47.5%   1.150  [1.104, 1.218]  ⚠
```

**Neither hypothesis is confirmed: the ratio rises rather than falls. But that rise is almost certainly a survivor effect.**

- The loss goes 7.5% → 22.5% → **44.5%**. The last two windows are far past the 15% threshold and are **unusable**.
- The situation of rule 32 fits exactly: *the survivors are precisely "the balls that did not run off", which is the very property being measured*.
  Those that died are mostly the kind that run into the distance and do not hoard — which is exactly the direction of differentiation.
  **The larger between-group difference left after filtering them out was created by selection, not by time.**
- The only usable window is the first: ① = 1.058, significantly ≠1, and **⑤ = 1.040 with a CI containing 1.0**.
  That is, in the one clean window, deleting everything leaves it **unable to stand**.

> ### ★ Rule 42: running longer cannot answer the relaxation question; fix the mortality first ★
> All floors off in the baseline world gives a 120-day paired loss of 44.5% (020 recorded 24.5% for the full architecture).
> At that loss rate, any long-horizon conclusion is a function of selection effects.
> **To answer "does the difference drift back", the 120-day loss must first be pushed below 15%,
> not the window made longer.**

⚠ So the 1.040 left by P2 **is still hanging**: it has been shown neither to be a residual artefact
nor to be real persistence. The paper can only report the first window and note that the long horizon is unmeasurable.

## 3c. ★ Mortality diagnosis: two major findings ★ (`mortality_diagnose.py`)

400 seeds × 2 worlds × 120 days, transplanted to baseline:

```
condition                        mortality   pursuing at death
full architecture + 022 on           7.6%    recover 72% / stock_food 28%
all floors off + 022 on             22.1%    stock_food 79% / recover 21%
all floors off + 022 off            53.9%    stock_food 62% / recover 38%   ← the worst
full architecture + 022 off         13.0%    recover 53% / stock_food 47%
```

### Finding one: the cause of death is a **sleep death spiral**, not "raising the wrong ambition"

The death profile of all four variants is identical: **condition 0, hunger 74–87 and food store 0.5 at death**,
with **sleep accounting for 53–56%** of the last 10 days (survivors 41–49%),
and `gather_material` only 0.2–2.8% (survivors 9–18%).

**It is not that they were not thinking about food** (62–79% were pursuing `stock_food` when they died),
**it is that they had no waking time.** The mechanism is in `act()`:

```python
eff = 0.35 + 0.65 * self.condition / 100     # poor condition → no amount of sleep restores it
```

condition falls → sleep efficiency drops to 0.35 → it needs 3× as long asleep → the day disappears →
it gathers nothing → hungrier → worse condition. **A positive-feedback trap with no exit.**
The `sleep` score is `(100−energy)×0.9`, and at hunger 80 `gather_food` scores only about 38,
so **sleep always wins.** Deaths cluster on days 75–105: a chronic spiral, not an acute event.

> ### ~~★ Rule 43: at the limit of hunger, survival actions must outweigh sleep ★~~
> ### ❌ **Rule 43 withdrawn (2026-08-14) — see §3d, the causality was backwards**
> ~~The same class of problem as rule 27, in a different place.~~
> **Sleep is not the cause of death, it is a symptom.** All three fixes raised mortality when measured; see below.

### ⚠ Finding two: the floor ablation is **contaminated**, which directly undermines 021 §3

```
full architecture 13.0%  →  all floors off 53.9%     (022 off)
full architecture  7.6%  →  all floors off 22.1%     (022 on)
```

**Switching off `trait_identity` / `trait_floor` multiplies mortality by 2–4.**
The reason: the floors hold industry / caution high, and what they hold up is **the propensity to forage and build**.
Once the floors are off, the traits drift back to the middle → no longer industrious → straight into the spiral above.

> ### ★ Rule 44: the floor is not only a "persistence mechanism", it is simultaneously a **survival mechanism** ★
> When `persistence_ablation.py` switches the floors off it **switches off two things at once**,
> so the 1.007 / 1.044 measured there are mixed with **survivor bias from differential mortality** —
> they are not "pure persistence with the hardcoding removed".
>
> **021 §3 and the P1/P2 of 022 are all affected.**
> The direction of the conclusion probably does not change (the 60-day loss of those variants is only 4–8%),
> but the "all floors off" control **is itself unclean** and must be re-run once mortality is fixed.

### Incidentally: 022 cut mortality by more than half (53.9% → 22.1%)

Once semantic memory enters decisions, the ball takes better care of itself (it knows to hoard food and repair its house).
This is a positive result of 022 independent of P1/P2, **and it is a genuine improvement at the behaviour layer**,
not a metric game.

## 3d. ★ All three fixes failed and rule 43 is withdrawn ★ (`fix_compare.py`)

Three candidate fixes were built per rule 43 and parameterised into `sim.py` (all off by default):
A `SLEEP_SUPPRESS` suppresses the intent to sleep · B `HUNGER_URGENCY` raises foraging urgency ·
C `SLEEP_EFF_FLOOR` raises the floor on sleep efficiency.

```
fix                   dead% full   dead% no floor   ratio full           ratio no floor
status quo              18.7%          40.7%     1.086 [1.043,1.162]  1.097 [1.031,1.160]
A suppress sleep 0.5    19.7%          54.7%     1.084 [1.036,1.160]  1.108 [1.046,1.178]
A suppress sleep 1.0    21.7%          56.7%     1.086 [1.041,1.166]  1.110 [1.048,1.182]
B raise urgency 25      23.0%          62.3%     1.098 [1.036,1.153]  1.114 [1.057,1.199]
B raise urgency 50      26.0%          65.3%     1.090 [1.034,1.175]  1.123 [1.060,1.192]
C sleep floor 0.60      23.7%          76.7%     1.117 [1.054,1.184]  1.115 [1.053,1.193]
C sleep floor 0.80      31.0%          81.0%     1.133 [1.067,1.208]  1.126 [1.061,1.205]
A0.5+C0.6          27.0%      79.7%    1.099 [1.044,1.181]  1.122 [1.061,1.206]
```

**Not one of the eight variants lowers mortality; every one raises it. C is especially bad (40.7% → 81.0%).**

C is the decisive counter-evidence: raising sleep efficiency = sleep is worth more = less sleep needed = more daytime,
so by rule 43's logic mortality should **fall**, and measured it **doubles**.

> ### ★ Rule 45: what the dead did more of in a diagnostic table is not the cause of death, it may be a symptom ★
> `mortality_diagnose.py` showed the dead sleeping 53–56% against survivors' 41–49%, and I inferred rule 43 from that.
> **The inference was backwards**: falling condition causes both more sleep and death,
> a textbook common-cause confound. **Sleep is what keeps them alive, not what kills them** —
> suppress it, or make it "unnecessary", and the ball spends the time exploring and dies faster.
>
> The lesson: once a correlation is diagnosed, **it must be falsified by an intervention in the opposite direction** before it can be called causal.
> This time variant C is what saved us.

## 3e. The real cause: condition is a monotone funnel, and this world has no steady state

60 seeds run to 120 days (all floors off, 022 on), averaged by segment:

```
        world food   condition   energy   industry
alive  day  35   3.20    70.8      39.7      72.2
       day  60   3.63    53.0      38.7      78.1
       day  90   4.09    43.3      41.0      82.5
       day 115   2.91    34.9      40.8      85.4
dead   day  35   3.84    53.6      37.0      67.4
       day  60   3.77    31.3      30.4      71.0
       day  90   3.07    15.5      33.0      79.0
       day 115   0.64     2.8      53.0     100.0
```

Three things are obvious:

1. **World food is not exhausted** (it stays at 3–4). This is not a resource problem.
2. **Energy stays at 30–40 throughout.** Not an energy problem; the sleep mechanism has not failed.
3. **Condition falls monotonically for every ball — survivors included** (70.8 → 34.9, still falling).
   **Industry rises all the way instead** (the dead reach 100 at the end) — they try their utmost and still fall.

> ### ★ Rule 46: this world has no sustainable equilibrium; every ball is on a countdown to death ★
> Condition leaks one way only, and no behaviour can pull it back. Death is not "falling into a trap",
> it is **"whoever starts lowest hits zero first"**. Run to 200 days and the population would probably be wiped out.
>
> The 60-day experiments look fine (a loss of 4–8%) only because **the countdown has not finished**.
> **No long-horizon experiment is possible until the condition balance is fixed** — this is not a statistical problem,
> it is a model without a steady state.

## 3f. ★ The condition balance sheet: after the transplant the recovery channel is **completely shut** ★

Condition changes in **exactly one place** in the whole of `sim.py` (lines 906–910), each tick:

```python
if self.hunger > 70:    self.condition -= 0.40     # drain
elif self.hunger < 30:  self.condition += 0.16     # restore
# 30 ≤ hunger ≤ 70: nothing happens ← a dead zone 40 points wide
```

The drain is **2.5×** the restore, with a dead zone in between. Measured tick shares per phase (50 seeds,
barren world → transplanted to baseline on day 30, all floors off):

```
              hunger>70  hunger<30  dead zone  net condition/day
alive  days   0-29    6.0%    19.6%     74.4%      +0.18
       days  30-59    7.1%     2.1%     90.8%      −0.61
       days  60-89    1.7%     1.1%     97.2%      −0.12
       days  90-119   1.6%     0.0%     98.4%      −0.15
dead   days   0-29   13.6%    17.9%     68.5%      −0.62
       days  30-59    7.5%     0.0%     92.5%      −0.72
       days  60-89    6.2%     0.0%     93.8%      −0.59
       days  90-119  27.4%     0.0%     72.6%      −2.63
```

> ### ★ Rule 47: the system settles inside the dead zone, so the recovery channel might as well not exist ★
> **After the transplant, the share of time with "hunger<30" collapses to 0–2%** (it was 18–20% during development).
> That is, **the +0.16 recovery channel almost never fires**,
> and the system spends 90–98% of its time in a dead zone where nothing happens,
> being hollowed out little by little by the occasional −0.40.
>
> **No ball has a positive balance after day 30** — even the healthiest survivor is at −0.12/day.
> This is not "some balls are unlucky", it is **the structural absence of a steady state**.
> Mortality is therefore decided entirely by "starting condition + time" and is essentially independent of behavioural strategy —
> which also explains why all three behaviour-layer fixes (§3d) failed:
> **they move the numerator while the problem is in the denominator.**

### Quantitative target (fixed before any change)

Survivors spend 97% of ticks in the dead zone, 1.7% draining and 1.1% restoring. To reach a zero net balance,
about **0.005/tick** must be added inside the dead zone (or equivalently the recovery threshold raised from 30 to ~55,
turning part of the dead zone into a recovery zone).

Three candidate directions (**not yet implemented, awaiting a decision**):

- **① raise the recovery threshold** `hunger < 30` → `< 55`. The smallest change, cutting the dead zone in half directly.
- **② slow recovery inside the dead zone too** (say +0.05/tick), preserving the "eat well to recover fast" gradation.
- **③ recovery not driven by hunger alone**, letting shelter / sleep contribute to condition. The most intuitive, the largest change.

⚠ All three change **every historical number** (011–022). And by the lesson of rule 45,
**mortality and the ratio must be measured together**; any fix that keeps the balls alive while flattening the world difference is a failure.

## 3g. ★ Fix comparison: only "threshold 65" passes both criteria ★ (`cond_compare.py`)

```
fix                   dead% full   dead% no floor   ratio full           ratio no floor
status quo             18.7%⚠         40.7%⚠    1.086 [1.043,1.162]  1.097 [1.031,1.160]
① threshold 45         15.7%⚠         46.3%⚠    1.082 [1.042,1.169]  1.114 [1.057,1.195]
① threshold 55         13.7%          43.3%⚠    1.096 [1.044,1.177]  1.130 [1.063,1.206]
① threshold 65          5.0%           7.3%     1.142 [1.068,1.218]  1.150 [1.072,1.220]  ★
② dead zone +0.03      12.0%          40.3%⚠    1.087 [1.045,1.171]  1.112 [1.057,1.195]
② dead zone +0.06      10.0%          35.3%⚠    1.100 [1.052,1.192]  1.129 [1.060,1.206]
③ shelter +0.05         7.7%          34.3%⚠    1.099 [1.052,1.185]  1.112 [1.050,1.189]
③ shelter +0.10         6.7%          34.0%⚠    1.117 [1.078,1.187]  1.130 [1.053,1.188]
①55 + ③0.05        12.0%      45.7%⚠   1.119 [1.048,1.199]  1.139 [1.075,1.215]
```

**Only ①threshold 65 brings the "no floor" column down (40.7% → 7.3%).** The other eight
improve the full architecture and are **all ineffective** with no floors (34–46%) —
and the no-floor case is precisely the contamination source of rule 44; without curing it, 021 §3 and 022 cannot be re-run.

### ★ A surprise: the ratio did not collapse; it generally rose ★

The prior worry was "better condition → less pressure in the barren world → the world difference is flattened".
Measured, **all nine variants have a ratio ≥ the status quo**, with ①65 the highest (1.142 / 1.150).

> ### ★ Rule 48 (hypothesis): survival pressure compresses behavioural variance ★
> A ball about to starve has no choice but to forage; only a well-fed ball has the slack to express personality.
> As mortality falls, **the true magnitude of differentiation becomes visible instead**.
> This also implies the ratios in earlier 60-day windows were **suppressed by survivor filtering** —
> the opposite direction to the inflation in long-horizon windows; both biases exist.
> ⚠ For now this is only an explanation with no direct test.

### ⚠ There is a cliff between 55 and 65 that must be mapped first

No-floor mortality is **43.3%** at threshold 55 and **7.3%** at threshold 65.
There is no transition in between, which suggests **the equilibrium hunger level falls exactly between 55 and 65**,
and once the threshold crosses it, the vast majority of ticks flip from the dead zone into the recovery zone.

**This is a fragile point**: any parameter that changes the equilibrium hunger level (HUNGER_RATE, FOOD_NUTRITION,
world food regrowth) could make mortality explode again.
**Before adopting it, sweep 58/60/62/65/68/70 to measure the cliff's position and steepness**,
and confirm that the chosen value has enough margin from it.

> ⚠ **The diagnosis in the paragraph above is wrong; see §3h.** There is no cliff and no threshold sweep is needed.
> The explanation "the equilibrium hunger level is stuck between 55 and 65" was falsified outright by `cliff_probe.py`
> (the zero is at T≈38). The truth is that **the rich-world arm has a sloth valley** (rule 49).
> The original text is kept because it demonstrates a classic error: **explaining the difference between two curves as a threshold in one curve.**

## 3h. ★ The cliff is fake: the truth is a sloth valley + half a selection effect ★
(`cliff_probe.py` · `death_split.py` · `rule48_test.py`)

§3g left two to-dos: sweep the threshold to locate the cliff, and verify rule 48. Both were done,
**but the threshold sweep itself turned out to be unnecessary** — the cliff can be computed directly, and it does not exist.

### 1. No sweep needed: the net balance is a functional of the hunger distribution

Condition changes in exactly one place, `sim.py:924-930`, so

```
net condition/tick(T) = COND_RECOVER·P(hunger<T) − COND_DRAIN·P(hunger>70)
                      = 0.16·P(hunger<T) − 0.40·P(hunger>70)
```

One distribution measurement predicts the **whole** threshold curve. Measured (N=60, barren→baseline@30,
counting only post-transplant ticks) and extrapolated from the "status quo" distribution:

```
T =        30      40      45      50      55      60      65      70
net/tick  −0.009  +0.003  +0.021  +0.048  +0.082  +0.111  +0.133  +0.144
```

**The zero is at T≈38, not between 55 and 65.** The status quo (T=30) gives −0.009/tick = −0.22/day,
the same order as the −0.12 to −0.15/day measured in §3f ✓ — rule 46's "no steady state" now has a closed-form source.

By this curve, raising it to 45 should fix everything. But §3g measured 46.3% at the 45 variant. **Where is the contradiction?**

### 2. ★ Negative feedback: the hunger distribution shifts up by itself and eats 60% of the fix ★

Because the distribution is not exogenous. Measured per variant (full architecture):

```
              dead%   median hunger   P(hunger>70)   p5–p95 width   net balance at T using its **own** distribution
status quo    16.7%      53.8            2.8%           32.5         −0.009  ← negative, no steady state
① threshold 55  1.7%      56.2            9.0%           35.0         +0.030
① threshold 60  1.7%      58.8           11.6%           32.5         +0.043
① threshold 65  1.7%      58.8           14.2%           35.0         +0.056
③ shelter +0.10 5.0%      56.2            7.4%           32.5         (same convention as above)
```

As soon as condition improves, the `urgency = max((hunger−60)/40, (85−condition)/85, 0)` at `sim.py:733` slackens —
the ball forages less, **median hunger rises 5 points and P(hunger>70) quintuples**, eating about 60% of the gain from raising the threshold
(at T=65: extrapolated +0.133, only +0.056 left in reality).

> ### ★ Rule 49 (part one): a condition fix is partly cancelled by behavioural negative feedback ★
> `urgency` reads both condition and hunger, so "making the ball healthier" directly "makes the ball lazier".
> Any change at the condition layer must have its balance recomputed **on that variant's own hunger distribution**;
> extrapolating from the status quo distribution overestimates it by more than a factor of two.
>
> The good news: negative feedback = self-stabilisation. §3g's worry that "any change to HUNGER_RATE / FOOD_NUTRITION
> will make mortality explode" **does not hold** — the system has restoring force against perturbation.

Incidentally: the p5–p95 width stays at 30–35 points, the same order as `FOOD_NUTRITION = 20` —
hunger really is a narrow sawtooth, and both step thresholds (70 and T) sit inside it.
The structural fragility is real, but softened by the negative feedback.

### 3. ★ Rule 49 (part two): the sloth valley — the middle variants are deadlier, and only for the rich world ★

§3g's paired mortality smeared the two worlds into one number (`live` at `fix_compare.py:52`
requires both arms to survive). Split apart (`death_split.py`, N=300, 120 days):

```
                  ── full architecture ──      ── all floors off ──
                rich   barren  predicted pair  rich   barren  predicted pair  §3g measured
status quo      0.7%   18.7%      19.2%      24.3%   23.3%      42.0%       40.7%
① threshold 55  7.7%    6.3%      13.5%      36.3%   14.0%      45.2%       43.3%   ← rich ↑12pp
① threshold 60  3.7%    5.3%       8.8%      18.0%    8.0%      24.6%         —
① threshold 65  0.7%    4.3%       5.0%       2.0%    5.3%       7.2%        7.3%
③ shelter +0.10 0.0%    6.7%       6.7%      25.3%   16.0%      37.3%       34.0%
```

First the reconciliation: "predicted pair" = `1−(1−p_rich)(1−p_barren)`, differing from §3g's measurement by **≤3.3pp in every cell**.
The two arms are approximately independent, and this independent new pipeline reproduces cond_compare — cross-validation passes.

Now the truth. **The barren-world arm improves monotonically** (23.3 → 14.0 → 8.0 → 5.3).
What explodes is the **rich world**: `24.3% → 36.3% (T=55) → 18.0% (T=60) → 2.0% (T=65)`.

> ### ★ Rule 49: raising the recovery threshold has to **cross a valley**, and the valley exists only for well-fed balls ★
> The mechanism follows rule 49 (part one): raise the threshold → condition↑ → urgency slackens → sloth → hunger shifts up.
> **Balls raised in the barren world have a high industry floor (the hardship ratchet of rule 47) and can withstand sloth;
> rich-world balls have no such brake, and one slackening slides them into P(hunger>70).**
> At the middle variants (55/60) the recovery gain does not yet cover the sloth loss → a net worsening.
> Only at 65 is the valley crossed.
>
> So the "cliff between 55 and 65" seen in §3g is **the far slope of the sloth valley**, not a threshold in the equilibrium hunger level.
> **The difference between two curves (rich/barren) was misread as a step in one curve.**
>
> Corollary: **the margin direction of ①threshold 65 is the opposite of what §3g assumed** — the danger is lowering it (falling back into the valley),
> and raising it is safe. 65 is 10 points from the valley floor (55) and can be adopted.

### 4. The hardship ratchet was not cut off (the item the §3g criteria table cannot see)

Raising the recovery threshold = condition permanently high = `deficit=(100−condition)/100` at `sim.py:936` tends to zero
= `trait_floor ← hardship_norm × 22` at `sim.py:941` may stop working.
And at `sim.py:890`, hardship is **forgotten** once condition ≥99.5.
**That ratchet is exactly what 021 §3 and 022 are studying, and neither criterion can see it**
(the no-floor column already has the floors switched off). Measured (full architecture, survivors only):

```
              final cond  hardship  hnorm   floor−identity  fears_hunger trigger rate
status quo       34.9      48.5     0.997      78.18            100%
① threshold 55   55.1      32.9     0.931      77.15             93%
① threshold 60   64.1      27.5     0.866      76.40             88%
① threshold 65   68.6      23.5     0.827      75.68             86%
③ shelter +0.10  61.9      32.2     0.843      76.15             88%
```

**Essentially falsified, and ①65 can be adopted**: hnorm only falls from 1.00 to 0.83,
and the ratchet strength goes 21.9 → 18.2 points without being cut off. But two things worth recording turned up:

> ### ★ Rule 50: the hardship ratchet is a binary switch, not a graded signal ★
> `hardship_norm = 1 − exp(−hardship/1.5)`, and `HARDSHIP_SCALE = 1.5` means
> about 5 days of accumulated deficit pins it at 1.0 — while the measured hardship is **23–48**.
> **Every ball, in every variant, is saturated at the ceiling.**
>
> So the individual difference the floor carries **cannot** come from "how much suffering there was"; it can only come from
> `_hardship_anchor` (`sim.py:938`) — **the personality snapshot at the moment of first going hungry, frozen in place**.
> This is the mechanistic version of §4's sentence "persistence can only come from a ratchet acting on the trait variables themselves",
> and can go straight into the paper: **the floor is not a memory, it is one irreversible sample.**
>
> ⚠ The quantity to watch is therefore not the mean hnorm but the **fears_hunger trigger rate: 100% → 86%**.
> ①65 means 14% of balls **never enter the ratchet**, which changes the composition of the denominator in the 021 §3 ablation.

> **⚠ The sentence above about "14% never enter the ratchet" is wrong, and is corrected in 023 §7.**
> `fears_hunger` and `_hardship_anchor` are **two different events**:
> the anchor is written at `sim.py:965` the first time `condition < 100` (nearly everyone), while
> `fears_hunger` requires `hardship_norm ≥ 0.5` (`HARDSHIP_STORY_AT`) and is a **narrative landmark**.
> The measured anchor-presence rate is **bit-identical** in v2/v3 (96.5% / 98.2% / 97.5%) —
> only the landmark falls. **No fewer balls enter the ratchet itself; what changed is the moment of sampling.**

### 5. ★ Rule 48 downgraded: half of it is a selection effect ★ (`rule48_test.py`)

§3g computed each variant's ratio on **its own surviving subset**, so as mortality falls a different batch of balls enters the statistic —
and what rule 48 wants to say is precisely that "who gets filtered out changes the ratio"; the two are entangled. Three improvements:
① a common seed set (alive in all variants × both worlds); ② per-seed paired δ + sign permutation (§3g compared whether
N_BOOT=400 CIs overlapped, which could never decide significance); ③ every variant shares one set of opponent indices.

```
              ── full architecture (n common=741/800) ──   ── all floors off (n common=747/800) ──
            own-set ratio  common-set ratio  Δvs status  p      own-set ratio  common-set ratio  Δvs status  p
status quo      1.098          1.090          —       —            1.082          1.072          —       —
① threshold 55  1.109          1.092       +0.0027  0.196 n.s.      1.101          1.085       +0.0048  0.003 **
① threshold 60  1.110          1.100       +0.0053  0.027 *         1.114          1.091       +0.0068  0.001 ***
① threshold 65  1.134          1.109       +0.0086  0.002 **        1.114          1.090       +0.0068  0.002 **
③ shelter +0.10 1.117          1.108       +0.0055  0.000 ***       1.087          1.073       +0.0005  0.662 n.s.
```

> ### ★ Rule 48 (revised): the ratio really did rise, but half of it is a selection effect and the effect is very small ★
> The ①65 vs status quo difference: own set +0.036 → common set **+0.019**.
> **About 47% of §3g's "surprise" is a selection effect** (44% in the no-floor column, consistent).
> The other half is real: p=0.002, but **dz is only 0.11–0.14** — a tiny effect,
> detectable only thanks to N=741 pairs.
>
> The original hypothesis "survival pressure compresses behavioural variance" points the right way, **but does not support §3g's "the implication is considerable"**.
> Saying "the ratios in earlier 60-day windows were suppressed by survivor filtering" is right;
> saying "the true magnitude of differentiation became visible" overstates it by a factor of two.
>
> Circumstantial evidence (not tested by this script): rule 34 says the ratio estimator is inflated at small N,
> and the status quo has the smallest effective N yet the lowest ratio — **the direction of that bias cannot explain this**,
> so the remaining half is not Jensen bias in disguise.

**One incidental discriminating fact**: ③shelter is strongest under the full architecture (p=0.0001)
and **falls to exactly zero** with all floors off (p=0.66). So ③'s ratio gain **depends on the floor mechanism**,
while ①65 is significant on both sides with the same magnitude (+0.0086 / +0.0068) —
**①65's gain does not run through the floor channel.** For the purposes of re-running 021 §3,
①65 is the cleaner choice.

### 6. Conclusion: adopt ① threshold 65 and label it v3

All four criteria now pass, and each has a mechanistic explanation rather than being just a number:

| Criterion | Result |
|---|---|
| mortality (paired, full/no floor) | 5.0% / 7.2%, both columns <15% ✅ |
| the ratio does not collapse | on the common set it actually rises by +0.019, p=0.002 ✅ |
| parameter margin | the valley floor is at 55 and 65 is outside it; the dangerous direction is **downward**, not upward ✅ |
| the hardship ratchet survives | hnorm 1.00→0.83, trigger rate 100%→86% ⚠ must be reported alongside the re-run |

"Why 65" now has an answer: **it was not swept for; 55–60 fall inside the sloth valley and
65 is the first round ten past it.** A reviewer can accept that sentence.

⚠ **When re-running 021 §3 / 022, the fears_hunger trigger rate must be reported alongside** —
v2 gives 100% and v3 gives 86%, so the denominator of the ablation has changed.

## 4. Implications for the paper

The reviewer's line "you did not discover irreversibility, you wrote irreversibility in" **is still unanswered**.
The honest conclusion (pre-written as the third case of §4 of the preregistration):

> In this architecture, discrete structures wired into behaviour (flags, knowledge) are not sufficient to maintain
> individual differences after a transplant; persistence can only come from a ratchet acting on the trait variables themselves.

**The main line should become: characterising the minimal mechanism needed to produce persistent individual differences, and pointing out that discrete memory structures are not part of it.**

> ### ★ The preregistration really did its job this time ★
> Without P2's threshold fixed in advance, seeing P1's 1.058 / p=0.0001 would almost certainly have led to declaring success,
> followed by a reviewer sending it back using the very same deletion test. **This experience itself belongs in the paper's Methods.**

---

## How to reproduce

```powershell
cd C:\Users\yinan\Desktop\ai-sandbox
python scenarios.py            # population report
python environment.py          # environment experiment (the current difference)
python transplant.py           # transplant: is the difference a personality
python leveling.py             # ★state levelling: is the curve a discovery or an artefact★
python deletion.py             # ★the deletion ladder: which layer the difference lives in★
python persistence_ablation.py # ★is persistence hardcoded★
python persistence.py          # single-factor persistence + mechanism check + three-direction restoration
python behavior.py             # behaviour layer + goal layer as the main carrier
python paired.py               # the paired experiment: numeric layer
python ablation.py             # ablation: mechanism contributions + the null self-check
python diagnose.py             # landmark trigger rates
python significance.py         # permutation test (group comparison)
python param_sweep.py          # ★the parameter-randomisation set: is the effect hand-tuned★
python sweep_report.py         # read sweep_results.csv and produce the sentences the paper can quote
python significance_main.py    # ★the p value of the main result (per-seed δ + sign permutation)★
python test_022_regression.py  # 022 regression: zeroing KNOWLEDGE_* must reproduce 021
python p1_test.py              # 022 P1: can the no-floor variant still exceed 1 after wiring
python p2_test.py              # 022 P2: non-nested deletion; is knowledge what holds it up
python relaxation_test.py      # relaxation: is the remaining 1.04 persistence or unfinished drift
python mortality_diagnose.py   # cause-of-death diagnosis (⚠ its conclusion was overturned by rule 45; kept as a counterexample)
python fix_compare.py          # comparison of the three behaviour-layer fixes (⚠ all eight variants failed)
python cond_compare.py         # ★three condition-balance fixes × mortality + ratio★
python cliff_probe.py          # ★cliff probe: hunger distribution + net-balance prediction + the hardship ratchet★
python death_split.py          # ★split mortality back into single worlds → the sloth valley (rule 49)★
python rule48_test.py          # ★rule 48 discrimination: common seed set + per-seed pairing★
python v3_revalidate.py       # ★v3 mechanistic revalidation: 021§3 / 022 P1 / P2 same-seed against v2★
python anchor_probe.py --verify # ★A: anchor day checked seed by seed for v2/v3 (falsifying 023§7.5)★
python anchor_probe.py         # ★B: anchor content intervention + negative control (rule 54)★
python sweep.py                # ⚠ deprecated
python food_sweep.py           # ⚠ deprecated
```

---

# Experiment 023 — versioning the model: v2 frozen, v3 forked

> **A dividing line.** Today's step is not "another round of tuning" but the model moving from an
> **exploratory architecture** into a **paper-candidate architecture**.
> 011–022 were all completed under v2 and are kept as development history; v3 forks off from here.

> Experiments 011–022 were conducted under model v2 and are retained as
> development history rather than overwritten by subsequent model correction.

## 1. v2 frozen

`ai-sandbox/v2_frozen/` (2026-08-15): the **complete** source and raw results as they stood before the change
(30 files + `SHA256SUMS.txt` + `README.md`). Self-contained, so
`cd v2_frozen && python <script>.py` reproduces any historical number from 011–022 directly.

⚠ **Every old number before line 2306 is kept**, including those already overturned (rule 43 overturned by rule 45,
§3g's "cliff" overturned by §3h). Keeping the original text and noting when and by what evidence it was overturned —
that habit is exactly the same material as the "the preregistration did its job" paragraph in the paper's Methods.

## 2. The definition of v3: one number changed

```python
# sim.py
MODEL_VERSION = "v3"
COND_RECOVER_AT = 65.0   # v3: condition-stability correction (v2 = 30.0)
```

A bit-for-bit comparison confirms: the **only executable difference** between `v2_frozen/` and the main directory is this constant
(everything else is comments and the new `MODEL_VERSION`). So the "v2 arm" = setting it back to 30.0 in the v3 code,
which is equivalent to running `v2_frozen/` — and that is exactly what the revalidation script does.

### Why 65 (this sentence has to withstand a reviewer)

**It was not "a parameter sweep found 65 gives the lowest mortality"** but a complete closed-loop mechanistic account (§3h / rule 49):

```
raise the recovery threshold → condition improves → survival urgency weakens
             → well-fed agents forage less → hunger rises → mortality **goes up** = the sloth valley
             → by 65 the condition margin suffices to cross that negative-feedback stretch → mortality falls again

mortality
  ^
  |        _
  |      _/ \_          ← the sloth valley (36.3% in the rich world at T=55)
  |  ___/     \
  |            \______  ← T=65, 2.0%
  +---------------------> COND_RECOVER_AT
     30   55  60  65
```

**65 is the first round ten past the sloth valley.**
That also settles the margin direction: **the danger is lowering it (falling back into the valley); raising it is safe.**

> ### ★ Rule 51: in a closed loop, a "locally healthier rule" does not necessarily raise fitness monotonically ★
> The agent is a behaviour–physiology closed loop: `condition ↑ → urgency ↓ → foraging ↓ →
> hunger ↑ → death ↑`. Local intuition ("surely faster physical recovery is better") can flip sign inside a loop.
> **ABM / Artificial Life parameters cannot be tuned by local intuition**; they must be measured end to end.
> This is not a main conclusion of the paper, but it suits a supplementary figure or the model-audit section well.

## 3. The final wording of rule 50

§3h measured that `HARDSHIP_SCALE = 1.5` saturates `hardship_norm` rapidly
(measured hardship 23–48, pinned at 1.0 after about 5 days), so **every ball in every variant is at the ceiling**.
So the mechanism is not "hungrier → stronger hardship → more personality change" but:

```
the first condition < 100 (sim.py:965) — early, and for nearly everyone
        ↓ written once
_hardship_anchor = the trait snapshot at that moment        ← write-once, never rewritten afterwards
        ↓
trait_floor ← min(anchor[t] + w×22×hnorm, 90) (sim.py:970)
```

> ### ★ Rule 50 (final draft · revised per experiment 024) ★
> **Hardship consolidation is initiated by an early, near-universal,
> write-once capture of the agent's trait state. The v3 condition
> correction does not alter the timing of this capture; instead, it alters
> the subsequent accumulation and behavioral expression of hardship.**
>
> The hardship mechanism is started by a single **early, nearly universal write-once personality snapshot**.
> The v3 condition correction **did not change when the snapshot is written**; it changed the accumulation of hardship
> after the snapshot and its behavioural expression.
>
> Evidence: in part A of experiment 024, the first anchor-write day is **identical on 300/300 seeds** between v2/v3
> (median day 6 / days 12–14, depending on architecture). It must also be so mechanistically —
> before the anchor is written the two versions are bit-identical.

> ### ★ Rule 50b: `fears_hunger` is a narrative marker, not the moment of consolidation ★
> It is recorded only once `hardship_norm ≥ 0.5` (`HARDSHIP_STORY_AT`),
> 13–20 days after the anchor. At most it tells you
> **"when the agent accumulated enough hardship to be called 'afraid of hunger' at the narrative level"**,
> and **not** "when the personality was consolidated".
> ⚠ In future the date or trigger rate of `fears_hunger` **must not** be used to argue about consolidation —
> that is exactly how 023 §7.5 came off the rails.

**This has already begun to answer the paper's big question: "how exactly is history preserved?"**
The answer appears to be neither traditional episodic memory, nor semantic knowledge,
nor a continuously accumulating hardship scalar, but **event-triggered consolidation**.
— which connects neatly to the state transplant to come.

## 4. The nature of the revalidation (which must be stated clearly, or it will be taken as confirmatory)

We have already seen the data, changed the model, and 65 was itself picked by a diagnostic experiment.
So the correct name for this next step is:

> **v3 mechanistic revalidation / robustness reanalysis** ——
> not a new confirmatory experiment.

Re-running on **the original seeds** is an advantage, not a problem: the only variable is `COND_RECOVER_AT 30 → 65`,
and a same-seed comparison attributes "the conclusion changed" cleanly to that one number rather than to "a different batch of balls".
**But it cannot carry the final confirmation.** Final confirmation waits until the model is fully frozen and
uses a block of seeds **that has never been run**.

### 011–020 are not re-run

011–020 are the development history of building the model and finding problems; their job is done.
What needs revalidating is only the **causal claims that depended on the survival confound**:

| Item revalidated | Question |
|---|---|
| 021 §3 | floor ablation: does `−all floors ①②` still stand |
| 022 P1 | is the no-floor ratio > 1 after wiring |
| 022 P2 | does persistence disappear once knowledge is deleted |
| rule 50 diagnosis | fears_hunger trigger rate / first-trigger day / anchor presence rate |

The wording for Methods: *once a structural survival confound was found in the model it was corrected,
and every core conclusion that depended on that confound was then revalidated.*

### The whole route

```
v2 → find the mortality / survivor confound → mechanistic diagnosis → find the sloth valley
   → v3 (COND_RECOVER_AT 65) → mechanistic revalidation on the old seeds
   → freeze the whole model + predictions → final confirmation on brand-new seeds
```

**That is more credible than "everything was designed right the first time".**

## 5. Version marking of raw results (`resultmeta.py`)

v2 → v3 is completely invisible from the contents of a CSV. So the convention: for any raw result written to disk,
the first five columns are fixed as `model_version / experiment / condition / seed / cond_recover_at`
(the last is redundant but worth it — no digging through code when something goes wrong). `param_sweep.py` is already wired in.

⚠ The existing `sweep_results.csv` / `holdout.csv` are from v2 and their headers lack these columns.
To re-sweep under v3, use a different `--out` and **do not mix them into the same file**.

## 6. ⚠ How to handle the falling fears_hunger trigger rate

§3h measured a trigger rate of 100% (v2) → 86% (v3) under the full architecture. This must be handled carefully:

- **Main effects are always reported on all predefined seeds**; analysing only triggerers to make the effect look better is not allowed.
  "Whether fears_hunger fired" **is itself a result produced by the simulation**,
  and selecting triggerers afterwards re-creates the selection problem — the same class of error we just fixed.
- The correct wording: `86% triggered the hardship mechanism.`
  Then results within the triggerers are reported as a **secondary descriptive analysis**.
- When re-running 021§3, report alongside it:
  `floor ON` → trigger rate / first-trigger day / anchor presence rate / survival rate;
  `floor OFF` → survival rate.


## 7. ★ v3 mechanistic revalidation results ★ (`v3_revalidate.py`, N=1500, same seeds)

74 tasks / 10 processes / about 40 minutes. The only variable is `COND_RECOVER_AT: 30 → 65`.

**First, validating the pipeline**: the v2 arm produces 022 P1 = **1.058 [1.029, 1.102] p=0.0001**,
**bit-identical** to the number published in the body of 022 ✓. So the v2/v3 differences below are real differences, not implementation differences.

### 7.1 The correction really works (mortality)

```
                          v2 dead   v3 dead
022 P1 full architecture     8.1%     4.3%
022 P1 −all floors ①②        7.5%     4.1%
021§3 effective n (/1500)   1411      1430
```

Mortality **halves** in the 60-day window. (For the effect at 120 days see §3h: 40.7% → 7.2%.)

### 7.2 022 P1: passes, and more strongly

```
condition                       v2                            v3
022 off −all floors ①②  1.007 [0.969,1.043] n.s. ✗   1.013 [0.971,1.049] n.s. ✗
022 off full architecture 1.106 [1.068,1.135] ***  ✓   1.124 [1.090,1.166] ***  ✓
022 on  −all floors ①②  1.058 [1.029,1.102] ***  ✓   1.090 [1.047,1.128] ***  ✓  ← the P1 criterion
022 on  full architecture 1.066 [1.035,1.101] ***  ✓   1.124 [1.077,1.161] ***  ✓
```

**P1 still passes under v3, rising from 1.058 to 1.090.** Consistent in direction with rule 48 of §3h
(the effect grows **slightly** once the survival confound is fixed), and of a commensurate magnitude.

### 7.3 022 P2: still fails — the preregistered conclusion is unchanged

```
what is deleted at transplant   v2 ratio   drop      v3 ratio   drop
① delete nothing (=P1)           1.058      —         1.090      —
② delete semantic knowledge      1.047   −0.011       1.057    −0.033
③ delete episodic memories       1.058    0.000       1.090     0.000   ← still a bit-identical no-op
④ delete flags only              1.047   −0.011       1.038    −0.052
⑤ delete semantic+episodic+flags 1.040   −0.018       1.029    −0.061
```

**The P2 criterion (② at least 0.05 below ① with non-overlapping CIs): v2 ✗, v3 still ✗**
(a drop of 0.033 < 0.05, and [1.047,1.128] overlaps [1.015,1.095]).

> ### ★ The preregistered conclusion holds unchanged under v3 ★
> "Discrete structures wired into behaviour are not sufficient to maintain individual differences after a transplant" — this is **not**
> a product of the survival confound. With the confound fixed, P2 still fails.
> This is today's most valuable line: **it upgrades the main conclusion from "possibly an artefact" to "still holds after correction".**

But two existing rules must be amended:

> ### ★ Rule 40 (revised): under v3, flags cost more than knowledge ★
> In v2, deleting knowledge and deleting flags cost **the same** (−0.011 each),
> which was the basis for "semantic memory is not a special carrier, merely one more equivalent discrete marker".
> Under v3 they separate: **flags −0.052 > knowledge −0.033**.
> The "equivalent" half must be withdrawn; the "knowledge is not a special carrier" half still holds
> (it is in fact the weaker of the three).

> ### ★ Rule 41 strengthened: episodic memory is still a **bit-identical** no-op under v3 ★
> ③ and ① are exactly equal in both versions (1.058 / 1.090, not one digit off).
> Staying bit-identical across a model correction makes this one settled.

⚠ One quantity to watch: ⑤ (deleting all three) erases only **31%** of the excess above 1 in v2
(0.018/0.058) and **68%** in v3 (0.061/0.090).
So the share carried by discrete storage has **grown** under v3 — but ⑤'s CI still contains 1.0
(1.029 [0.983,1.062] p=0.217), so it cannot be turned round into "discrete structures are the carrier after all".
**This is a question left for the final confirmation.**

### 7.4 021 §3 floor ablation: the honest downgrade stands, but the two seed blocks disagree ⚠

```
                          v2                       v3
seeds 0+     full architecture  1.132 p=.0001 ***       1.172 p=.0001 ***
seeds 0+     −all floors        1.032 p=.078  n.s.      1.036 p=.057  n.s.
seeds 10000+ full architecture  1.127 p=.0001 ***       1.148 p=.0001 ***
seeds 10000+ −all floors        1.034 p=.064  n.s.      1.057 p=.0029 **   ← ⚠
```

**Main conclusion: the withdrawal of rule 33 remains correct.** With the floors off, the ratio falls to 1.03–1.06,
and **"mortality contamination" can no longer explain it this time** — the two routes at the end of 021 §3
(honest downgrade / fix the mechanism and re-measure) now have their answer: **the mechanism was fixed and the effect still did not come back.**

> ### ★ Rule 52 ⚠: the no-floor variant gives inconsistent significance across two seed blocks ★
> Under v3, seeds 0+ give 1.036 n.s. while seeds 10000+ give 1.057 p=.003.
> **The same model, the same N=1500, only a different seed block, and the conclusion flips.**
> That means the true value sits near the detection limit and the significance of any single seed block is **untrustworthy**.
> Reporting this variant in the paper requires **reporting both blocks**, not picking the significant one.
> This open case is left for the final confirmation (a brand-new seed block) to settle.

### 7.5 The rule 50 diagnosis ⚠ the interpretation in this section was overturned by experiment 024; the table itself is valid

```
version world   architecture   alive%   fears_hunger%  anchor%  median fears_hunger day
                                                       ↑ this column is not the anchor day
v2   rich    full architecture 100.0%     95.1%       98.5%        20
v3   rich    full architecture 100.0%     94.3%       98.5%        27
v2   barren  full architecture  91.9%     92.7%       98.2%        23
v3   barren  full architecture  95.7%     83.0%       98.2%        31
v2   barren  all floors off     92.5%     92.5%       97.5%        26
v3   barren  all floors off     95.9%     85.9%       97.5%        33
```

**★ Correcting §3h ★** I wrote in §3h that "①65 means 14% of balls never enter the ratchet", and **that is wrong**.
`_hardship_anchor` and `fears_hunger` are two different events:

- `_hardship_anchor` (`sim.py:965`): written the first time `condition < 100` → **nearly everyone**
- `fears_hunger` (`HARDSHIP_STORY_AT = 0.5`): needs about a day of full deficit accumulated → **a narrative landmark**

Measured, the **anchor presence rate is bit-identical in v2/v3** (96.5% / 97.5% / 98.5% / 98.2%),
and only the landmark falls (92.7% → 83.0%).

> ### ~~★ A corollary of rule 50: what v3 moves is the **moment** of consolidation ★~~ ⚠ withdrawn
> ~~The median first-trigger day goes 20–26 days → 27–33 days… sampled later → sampling a more mature personality.~~
>
> **⚠ This whole paragraph is withdrawn; see part A of experiment 024.** The `first-trigger day` column in the table above records
> **`fears_hunger`**, and `v3_revalidate.py` never recorded the first write day of `_hardship_anchor` at all —
> using the landmark's date to argue about the snapshot's date was a straight mix-up.
>
> And from the code the inference **could never have held**: the anchor is written on the tick of the first
> `condition < 100`; condition can only be
> pulled below 100 by `COND_DRAIN` (hunger>70), and while condition
> is still 100 the gain from raising `COND_RECOVER_AT` is entirely eaten by `clamp`. **Before the anchor is written, v2/v3 are bit-identical**,
> so the anchor day must be the same. Measured in experiment 024: **identical on 300/300 seeds**.

### 7.6 Status summary

| | v2 | v3 | Conclusion |
|---|---|---|---|
| 022 P1 | 1.058 ✓ | 1.090 ✓ | passes, more strongly |
| 022 P2 | ✗ | ✗ | **the preregistered conclusion is unchanged** |
| 021§3 no floors | 1.032/1.034 n.s. | 1.036 n.s. / 1.057 ** | the downgrade stands, ⚠ inconsistent across blocks |
| episodic memory | bit-identical no-op | bit-identical no-op | rule 41 strengthened |
| flags vs knowledge | equivalent | flags weigh more | rule 40 revised |
| 60-day mortality | 7.5–8.1% | 4.1–4.3% | the correction works |

**The main story is beginning to close**:

> Experience-dependent differentiation can be enhanced by semantic knowledge,
> but long-term persistence is primarily carried by a separate
> event-triggered consolidation mechanism.

## 8. Still to do (after 023)

1. **Freeze the whole model and write down the predictions**, then do the final confirmation on a **seed block that has never been run**.
   The open case of rule 52 (the no-floor variant) is settled by it.
2. **A causal test of the anchor moment**: pin `_hardship_anchor` artificially at day 10/20/30
   and see how the P1 ratio moves. A direct test of the corollary of rule 50.
3. **state transplant + novel-situation generalization** — these two decide whether this is
   "a decent ABM experiment" or really answers the question:
   **does an identical individual truly become a behaviourally different "individual" because it lived through a different past.**
4. ⑤ (deleting all three) erases 68% of the effect under v3 (only 31% under v2) and needs explaining.

---

# Experiment 024 — v3 frozen + the anchor-content causal probe

> **v3 is frozen**: `ai-sandbox/v3_frozen/` (32 files + full sha256 + README).
> From this moment the default mechanisms of `sim.py` are not changed again. Later experiments may only be
> **experiment-level interventions** (changing agent instance state or a temporary switch, restored afterwards).
> If an experiment exposes a structural problem forcing a model change → **fork v4 and repeat the freezing procedure**; do not edit v3 in place.

## 1. Part A: falsifying "v3 postponed consolidation" (`anchor_probe.py --verify`)

That inference in 023 §7.5 is wrong, and this section nails it down.

```
world     architecture      anchor day v2  anchor day v3   identical per seed   fears day v2  fears day v3
rich     full architecture       6.0            6.0           1500/1500             19.0          24.0
rich     all floors off         14.0           14.0           1500/1500             24.0          27.0
barren   full architecture       6.0            6.0           1500/1500             22.0          24.0
barren   all floors off         11.0           11.0           1500/1500             25.0          23.0
```

**The anchor write day is identical on 1500/1500 seeds between v2 and v3.**
It must be so mechanistically: the anchor is written on the tick of the first `condition < 100`,
and condition can only be pulled below 100 by `COND_DRAIN` (hunger>70); while condition is still 100,
the gain from `COND_RECOVER_AT` is entirely eaten by `clamp` —
**before the anchor is written the two versions are bit-identical**.

What moved later is `fears_hunger` (+2 to 5 days). Rules 50 / 50b have been rewritten accordingly (023 §3).

> ### ★ Rule 53: do not use one variable's timestamp to argue about another variable's timestamp ★
> 023 §7.5 used the date of `fears_hunger` to argue about the date of `_hardship_anchor`,
> while the script **never recorded the latter at all**. The two events are 13–20 days apart and the conclusion was entirely inverted.
> **Before reporting "when X happened", confirm that the script recorded that very quantity.**

## 2. Part B: the anchor-content causal probe — an anchor-content transplant

Not "only start writing the anchor on day N" (which would change both ① the snapshot content and ② when the floor takes effect).
Instead: run development normally (days 0–29, saving trait snapshots at days 5/10/20/29) →
on day 30 `deepcopy` an **exactly identical state (including RNG)** → **change only `_hardship_anchor`**
→ every branch enters the common garden from the same state. The only variable = the history slice stored in the anchor.

### ★ The negative control: passes perfectly ★

```
−all floors ①② · N=1500 · n=1448
branch          ratio      Δ vs natural      p
natural anchor  1.146        —              —
Day 5        1.146     +0.0000    1.0000 n.s.
Day 10       1.146     +0.0000    1.0000 n.s.
Day 20       1.146     +0.0000    1.0000 n.s.
Day 29       1.146     +0.0000    1.0000 n.s.
no anchor       1.146     +0.0000        1.0000 n.s.
```

**All six branches are bit-identical.** The only route by which `_hardship_anchor` acts really is
anchor → `trait_floor` (`sim.py:970`), and once the floor is frozen to `FrozenZero`,
what is in the anchor affects not a single tick. **No leak, no second pathway.**

### primary: passes, but the effect is tiny

```
full architecture · N=1500 · n=1446
branch          ratio     mean δ    Δ vs natural     dz       p
natural anchor  1.150    0.0457       —             —        —
Day 5        1.150    0.0458    +0.0001   0.02   0.4287 n.s.
Day 10       1.150    0.0457    +0.0000   0.00   0.9559 n.s.
Day 20       1.153    0.0467    +0.0010   0.06   0.0255 *
Day 29       1.156    0.0476    +0.0019   0.09   0.0004 ***
no anchor       1.155    0.0474    +0.0017        0.08   0.0029 **
```

**The primary prediction holds**: the anchor-content intervention really does produce a detectable difference (Day20/Day29/no anchor).
**But the magnitude is tiny**: the largest Δ = +0.0019, which against "the part above 1" (0.150) is only **1.3%**.

**secondary (not preregistered)**: Day 5 ≈ Day 10 ≈ natural — as expected,
since the natural anchor's median write day is day 6, so the Day5/Day10 snapshots are essentially the same one.
What really differs is from Day 20 onwards. The direction is **the later (or the absence of it) → the higher the ratio**,
i.e. **an early anchor slightly suppresses the between-world difference** (pinning the floor to a personality that has not yet differentiated).

> ### ★ Rule 54: what matters is that a floor existed, not which snapshot the floor is anchored to ★
> Placing the two experiments side by side:
> - 021§3 (floor ablation): full 1.150 → no floors 1.036, **switching the floors off collapses it by 76%**
> - 024 B (changing the anchor content): natural → no anchor moves it by only **1.3%**
>
> So persistence depends on **the floor ratchet channel itself having existed**,
> and is **insensitive to which history slice it is anchored to**.
> Rule 50's line "the write-once sample is the carrier of persistence" must be **downgraded**:
> the sample really is write-once and really is causal, but **the individual information it carries barely enters the result**.

⚠ **The scope limitation of this experiment (which must go into the paper)**: the intervention point is day 30,
and `trait_floor` accumulates with `max()` — the floor raised by the natural anchor during development
**is already burned in and this experiment did not dismantle it**. So what is measured here is
**"how much causal influence the anchor still has after the transplant"**, not "how important the anchor mechanism is overall".
The latter is answered by the floor ablation of 021§3 (a great deal). The two numbers do not contradict; they measure different things.

## 3. ⚠ Two errors in this experiment itself (recorded as counterexamples)

**(a) mp.Pool worker reuse caused version contamination.**
Part A's `task_verify` sets `sim.COND_RECOVER_AT = 30.0/65.0` inside the worker process,
and part B's `_prep()` did not set it back explicitly — **worker processes are reused**,
so whether B ran v2 or v3 depended on task scheduling order. The same command produced completely different numbers twice
(natural anchor 1.260 vs 1.119). The first version's result of "a perfect negative control + everything significant under the full architecture"
**was a product of contamination and is void**.

> ### ★ Rule 55: globals changed inside a subprocess must be set explicitly by every task and never inherited ★
> `mp.Pool` reuses workers. Any `setattr(sim, ...)` stays in the process and affects later tasks.
> **Every task function must write out every global it depends on at its start**,
> even those that look like defaults.
> The self-check: **run the same command a second time with a different `--workers`; the results must be bit-identical.**
> (After the fix, workers=12 and workers=5 were verified identical.)

**(b) The deepcopy trap of `FrozenZero`.**
`FrozenZero(dict)`'s `__setitem__` is a no-op, and `copy.deepcopy` rebuilds a dict subclass
**precisely by feeding data through `__setitem__`** → it produces an **empty dict** → reading `trait_floor['industry']`
raises `KeyError` outright. v3 is frozen, so `FrozenZero()` is rebuilt inside the experiment script to patch it
(it carries no state, reads are always 0 and writes always dropped, so rebuilding is equivalent).
**Every state-transplant experiment from now on will hit this**, so note it in advance.

## 4. Status

| Question | Answer |
|---|---|
| did v3 postpone consolidation? | ❌ no, the anchor day is identical on 1500/1500 seeds |
| does the anchor act only through trait_floor? | ✅ yes, the negative control's six branches are bit-identical |
| is the anchor content a causal carrier? | ✅ yes (p=0.0004), but it explains only 1.3% |
| does persistence rely on the anchor's content? | ❌ no, it relies on "a floor having existed" (rule 54) |

**Next: fix the FINAL PREREGISTRATION in writing, and only then open the brand-new seed block.**
See `ai-sandbox/FINAL_PREREGISTRATION.md`.

---

# Experiment 025 — FINAL CONFIRMATION (executing the preregistration)

> The full preregistration: `ai-sandbox/FINAL_PREREGISTRATION.md` (fixed 2026-08-15, unchanged before the run)
> The execution script: `ai-sandbox/final_confirm.py` (imports from `v3_frozen/` and verifies the sha256 at startup)

## 0. ⚠ The scope of this confirmation (written at the very top to prevent later misquotation)

**This is "the final confirmation of the current persistence architecture", not the final confirmation of the
core goal of the whole research programme.**

What it confirms: whether a different past leaves a persistent behavioural difference **within one common garden**,
and which mechanisms carry that difference.

What it **does not test**: whether those differences generalize into different decisions in a **situation
neither side has ever experienced**.

So even if every criterion passes beautifully, what may be written is
**"the foundation of persistent individuality / path dependence is now solid"**,
**not** "generalized individuality has been demonstrated".
The latter belongs to the next stage, **novel-situation generalization**. **The two must not be conflated in the paper.**

## 1. The state of convergence at the persistence layer (a stocktake before the final run)

| Proposition | Status | Basis |
|---|---|---|
| different experience → a persistent behavioural difference | ✓ | 018–022, and the 023 v3 revalidation at 1.124–1.172 |
| not a mortality artifact | ✓ | 023: with mortality halved the effect is **stronger**, not weaker |
| episodic memory is not the carrier | ✓ very strong | deleting memories is a **bit-identical** no-op in both v2/v3 (rule 41) |
| semantic knowledge is not the main carrier | ✓ increasingly strong | P2 fails in both v2/v3 (023 §7.3) |
| the floor architecture matters a great deal | ✓ | 021§3: 1.150 → 1.036, a 76% collapse |
| the anchor's specific snapshot barely matters after the transplant | ✓ new | 024: explains only 1.3% (rule 54) |
| is there still a faint residual with no floor | **?** | rule 52: the two seed blocks disagree → **R52 decides** |

**Only the last row is unknown.** The other five are **replications, not discoveries** in the final run —
the paper must say so and must not present a replication as a confirmation.

## 2. Three gates before execution (all passed)

1. **Frozen verification**: all 32 files of `v3_frozen/SHA256SUMS.txt` match ✓
   the model is confirmed to come from `v3_frozen`, with `MODEL_VERSION=v3` and `COND_RECOVER_AT=65.0` ✓
2. **The rule 55 self-check**: the output of `--workers 12` and `--workers 5` is **byte-identical** ✓
3. **The whole pipeline shaken down**: five conditions + four criteria + the negative control all run through on development seeds ✓
   (negative-control fingerprint: deleting memories and deleting nothing are **exactly identical**)

## 3. ⚠ Stopped before launch: the R52 criterion is undecidable (`r52_precision.py`)

The rehearsal (**development seeds** 0–1499, N=1500, not final):

```
condition                  n     dead rich  dead barren   ratio   95% CI
H1  full architecture     1447    0.0%       3.5%       1.153  [1.113, 1.196]  ✓
P1  −all floors ①②        1448    0.0%       3.5%       1.139  [1.098, 1.183]  ✓
P2② delete knowledge      1449    0.1%       3.3%       1.102  [1.062, 1.144]  ✗ (drop .037, CIs overlap)
NC③ delete memories       1448    0.0%       3.5%       1.139  [1.098, 1.183]  ✓ bit-identical to P1
R52 −floors · 022 off     1430    1.5%       3.2%       1.037  [1.000, 1.084]  ⚠
```

R52's printed CI lower bound is exactly **1.000**. The criterion is "lower bound > 1.00",
so "pass/fail" turns on the fourth decimal of a bootstrap quantile — and that digit carries Monte Carlo error.

**Changing only the analysis-layer random seed** (same data, same model, same estimator), run 8 times:

```
analysis seed  CI lower   verdict      analysis seed  CI lower   verdict
777           1.00054    ✓ pass       4777          1.00011    ✓ pass
1777          0.99875    ✗ fail       5777          0.99938    ✗ fail
2777          1.00118    ✓ pass       6777          1.00121    ✓ pass
3777          1.00145    ✓ pass       7777          0.99972    ✗ fail

lower-bound range [0.99875, 1.00145]   jitter 0.00271
|median lower bound − 1.00| = 0.00032   vs jitter 0.00271      → 5/8 judge "pass"
```

> ### ★ Rule 56: a bright-line criterion must first be shown to be decidable at the expected effect size ★
> "CI lower bound > 1.00" is clean to write, but when the true value sits right on 1.00
> it hands the scientific conclusion to the **analysis-layer random seed**. 5/8 vs 3/8 = a coin flip.
> **When a preregistration states a criterion, it must also preregister "whether this criterion is decidable at the expected effect size"** —
> or simply allow a third outcome, "on the detection boundary, the criterion cannot decide".
>
> This was caught **before the final block was burned**, thanks to a rehearsal using only already-burned seeds.
> **A one-shot resource must be rehearsed first.**

### ⚠ More bootstrap iterations cannot save it

Raising `N_BOOT` only compresses the Monte Carlo error; it does not change the **limiting value** of the bootstrap quantile.
As `N_BOOT → ∞` the lower bound converges to ≈ **1.0003** — the verdict would go from "randomly pass/fail"
to "stably pass, but winning by three parts in ten thousand".
**That turns random arbitrariness into deterministic arbitrariness; it does not turn it into meaning.**

The real problem is not precision but that **R52's true value sits on the detection limit**:
021 gives 1.036 n.s. on the development block and 1.057 ** on the holdout block, and now the development block at N=1500 has a lower bound ≈ 1.0003.
Rule 52's "the two seed blocks give opposite conclusions" is exactly this.

**The decision is handed back, and the final block is untouched.** 50000–51499 remains intact and unused.

## 4. ⚠ The first `--final` was an empty run — an incident record

The first execution of `--final` output `n = 0` for every condition. **That is not a result, it is a chunk-indexing bug.**

```python
jobs = [... (ci, w, s0, min(CHUNK, N - s0)) ...          # should be seed0 + N - s0
        for s0 in range(seed0, seed0 + N, CHUNK)]
```

At `seed0 = 0` the two happen to be equal; at `seed0 = 50000`, `N − s0 = 1500 − 50000` is **negative**
→ `range(s0, s0 + negative)` is empty → every task simulates 0 seeds.

**The key point: `scenarios.make` was never called once for 50000–51499; not a single tick was run and
no observation was produced.** So the final block **was not burned**, and re-running after the fix is not
adaptive analysis — we did not see one byte of data from that seed block.
The void file is kept as `final_confirm_result.VOID_bug.txt` (with the reason for voiding stated at the top).

> ### ★ Rule 57: a rehearsal must use parameters of **the same shape** as the official run ★
> The full-size rehearsal was done at `seed0 = 0`, which is precisely the one value at which this bug does not fire —
> so it skipped the entire code path the official run would take.
> **Do not rehearse with special cases like 0 / 1 / the empty set, which make boundary conditions disappear.**
> The re-check after the fix used `--seed0 20000` (the already-burned 022 block, consuming no new seeds),
> which takes exactly the same non-zero-offset path as the final run.

**One positive result**: §4 of the preregistration, "insufficient effective n is judged **invalid** rather than not significant",
displayed the failure as `⚠ invalid` instead of quietly outputting a number based on an empty sample.
Had it said "report not significant if n is too small", this empty run would have looked like a genuine negative conclusion.

Two hard stops added afterwards (both abort immediately and produce no output file):
① a coverage self-check: the planned number of simulations must equal `number of conditions × 2 × N` exactly;
② an `n = 0` interception, declaring that "n=0 is a failure, not a mortality rate".

## 5. ★ FINAL CONFIRMATION results ★ (seeds 50000–51499, run once)

```
condition                  n    dead rich  dead barren   ratio   95% CI            mean δ   dz      p
H1  full architecture     1441   0.0%       3.9%       1.142  [1.098, 1.183]  +0.0444  0.20  0.0001
P1  −all floors ①②        1449   0.0%       3.4%       1.134  [1.090, 1.175]  +0.0417  0.18  0.0001
P2② delete knowledge      1448   0.1%       3.3%       1.102  [1.056, 1.141]  +0.0309  0.14  0.0001
NC③ delete memories       1449   0.0%       3.4%       1.134  [1.090, 1.175]  +0.0417  0.18  0.0001
R52 −floors · 022 off     1429   1.7%       3.1%       1.046  [1.002, 1.086]  +0.0147  0.06  0.0154
```

### Criterion verdicts

| Criterion | Result | Value |
|---|---|---|
| **H1** main effect | **✓ pass** | 1.142 [1.09816, 1.18343] |
| **P1** still > 1 with all floors off | **✓ pass** | 1.134 [1.09043, 1.17507] |
| **P2** delete knowledge | **✗ fail** | drop +0.032 < 0.05, CIs overlap |
| **R52** | **◐ on the detection boundary; this criterion cannot decide** | 1.046 [1.00208, 1.08609] |
| negative control, episodic memory | **✓ bit-identical** | 0.344305459704 vs 0.344305459704 |

### Comparison with the prior predictions (preregistration §7, copied line by line)

```
        prediction            measured          match?
H1      pass, 1.12–1.16      pass, 1.142       ✓ exact match
P1      pass, 1.07–1.10      pass, 1.134       ⚠ direction right, point estimate **above the predicted interval**
P2      fail, drop≈0.03      fail, drop 0.032  ✓ precisely on target
R52     fail, 1.03–1.06      boundary, 1.046   the ratio falls inside the predicted interval; read as "cannot decide"
episodic memory  bit-identical   bit-identical   ✓
```

⚠ **P1's point estimate is above the prior predicted interval** (predicted 1.07–1.10, measured 1.134).
Recorded faithfully; **the predicted interval is not widened after the fact**. The likely cause is that the prediction copied the 023 v3 revalidation value
(1.090, seeds 20000+), while seed blocks fluctuate by ±0.04 anyway
(H1 gives 1.172 / 1.148 / 1.142 across the three blocks).

### R52: why 8/8 is still judged "cannot decide"

The boundary diagnostic: across 8 analysis seeds the lower bound ranges over `[1.00100, 1.00454]`, MC SD = 0.00103,
and **8/8 are > 1.00** — in the Monte Carlo sense it is stable.

But the threshold of preregistration amendment A is `|lo − 1.00| ≥ 0.01`, and the measured `lo − 1 = 0.00208`.
**Per the preregistration it is judged "◐ cannot decide".**

> ### ★ This is where the temptation must be resisted ★
> "8/8 passed, why does that not count as a pass?" — because the threshold was set **before the run**,
> and it was set not only for Monte Carlo noise but also because "winning by twenty parts in ten thousand on a CI lower bound
> is not enough to support a scientific claim".
> **Arguing about whether the threshold should have been 0.01 after seeing the result is adaptive analysis.**
> Amendment A was written without seeing the final data, so it is executed as written.

### The substance of R52 (descriptive, not a criterion)

The point estimates on three independent seed blocks agree closely and the direction has never changed:

```
021 development block   1.036   n.s.
021 holdout block       1.057   **
FINAL block             1.046   p=0.0154, dz=0.06
```

**A residual effect with a stable direction, a very small magnitude (≈+0.04), and always hugging the detection limit.**
The honest statement: *with all floors off there remains a small residual difference whose direction agrees across three independent seed blocks,
but whose magnitude is too small for our preregistered criterion to decide whether it exceeds 1.*
Rule 52's open case **stays open**; a one-shot resource is not spent forcing a verdict.

## 6. Closing out the persistence layer

| Proposition | Final status |
|---|---|
| different experience → a persistent behavioural difference | **✓ confirmed** (H1, brand-new seed block, 1.142) |
| not a mortality artifact | ✓ (v3 mortality 3–4%, the effect grew rather than shrank) |
| episodic memory is not the carrier | **✓ very strong** (a bit-identical no-op in all three independent runs) |
| semantic knowledge is not the main carrier | **✓** (P2 fails in all three: v2/v3/final) |
| the floor architecture matters a great deal | ✓ (1.142 → 1.046) |
| the anchor's specific snapshot barely matters | ✓ (024, explains only 1.3%) |
| a faint residual with no floor | **◐ undecided**, direction stable, magnitude ≈+0.04 |

**The main sentence that can go into the paper:**

> Experience-dependent differentiation can be enhanced by semantic knowledge,
> but long-term persistence is primarily carried by a separate
> event-triggered consolidation mechanism.

⚠ **Scope** (preregistration §0.5): what is confirmed above is the **persistence architecture**.
It does **not** demonstrate generalized individuality — whether those differences generalize into different decisions in a
**situation neither side has experienced**. That belongs to the next stage, novel-situation generalization.
**The two must not be conflated in the paper.**

## 7. Next

The persistence layer closes out here, and the current model will not be dissected further.
The next question is the one from the very beginning: **can what history left behind act on a future never seen before.**

---

# ★ The persistence stage is sealed ★ (2026-08-16)

Experiments 011–025 end here. Every execution has finished and no process is left running.

```
v2_frozen/   COND_RECOVER_AT = 30    the original model of experiments 011–022
v3_frozen/   COND_RECOVER_AT = 65    the paper-candidate architecture, MODEL_VERSION = "v3"
FINAL_PREREGISTRATION.md             fixed in writing and executed (including amendment A)
final_confirm_result.txt             seeds 50000–51499, run once
final_confirm_result.VOID_bug.txt    the void record of the first empty run (see 025 §4)
```

Seed blocks burned and no longer usable as a holdout:
`0–1499`, `10000–11499`, `20000–21499`, `50000–51499`.

**Everything after this belongs to a new stage; persistence will not be dissected again.**

---

# Experiment 026 — NOVEL-SITUATION (design v3 settled, not executed)

The full design: `ai-sandbox/NOVEL_SITUATION_DESIGN.md` (v3)
**The design has converged and will not be expanded further.** `60000–61499` untouched, `v3_frozen/` unmodified.
Next: write the mechanism layer and the group-blind calibration script, and fix `S` and `λ` on `20000+`.

## ★★ Rule 61: counterfactual sibling branches ★★

**This is the most important item in the whole design, far more so than whether the RF uses 8 layers or 12.**

**The wrong way** (v2's implicit assumption):

```
agent → run W days in the familiar world and measure B_familiar → then enter the frozen ground and measure B_novel
```

**Those W days of familiar measurement are themselves an extra stretch of experience** and keep changing
traits / goal / trait_floor / knowledge / hardship.
By the time it enters the frozen ground, what is predicted is **no longer "one historical state facing two futures"**.

**The necessary way**:

```
end of development → state levelling → a complete snapshot (including RNG)
                                   ↙            ↘
                              clone F          clone N
                              familiar world      novel world
                                 ↓                ↓
                             B_familiar        B_novel
```

At the **instant of forking** the two clones have identical complete executable state and **identical RNG state**,
**nothing that happens in either branch may feed back into the other**, and both run for **the same length W**.

⚠ `FrozenZero()` must be rebuilt after forking (the deepcopy trap hit in 024).

## Features / target / loss (settled)

- **`B_familiar` = 182 dimensions**: 168 (24 hours × 7 actions, normalised within each hour)
  + 7 (whole-window action shares) + 7 (second half − first half changes).
  The last 14 are deterministic summaries and **introduce no new information**; they merely make it easier for the RF to read "what it does at what hour"
  and "whether behaviour is still drifting in a familiar environment".
  **Not 7 dimensions** — otherwise one reviewer sentence, "history is only restoring the
  circadian/temporal information you compressed away yourself", would be unanswerable. 182 dimensions make G1 harder to pass, **but harder to dismiss once passed**.
- **`B_novel` = 7-dimensional action shares** (deliberately favouring M0: 182 dimensions → predicting 7)
- **loss = TV distance** (continuing the project's usual behavioural metric):
  `d_i = TV(actual, M0 prediction) − TV(actual, M1 prediction)`.
  In plain terms: **how much better we predict how this ball will allocate its behaviour in the new world
  once we know its past.** The twins of one seed are **averaged first**, then seed-level inference is done.
- ⚠ **After levelling, `entry_state` is a constant in the main analysis** (identical by construction),
  so `M0 = f(B_familiar)`; it is a real variable only in the unlevelled paired-matching secondary analysis.

## ★ Rule 56 strengthened: eliminate analysis randomness rather than merely measuring it ★

The lesson of R52 was "change the analysis seed and the conclusion flips". This time it is blocked at the source:

- **deterministic CV folds**: `fold = deterministic_hash(seed) % K`, with twins always in the same fold
- **the RF `random_state` fixed**, and `n_estimators = 1000` to suppress forest randomness
- **the bootstrap uses a fixed analysis seed, with replicates raised to 10,000**

**The formal analysis is essentially deterministic.** The 8-seed rehearsal is demoted to a stability diagnostic.

## Models and criteria

- **RF is primary**, with Ridge on a quadratic basis expansion for robustness, **and both are not required to be significant**; no k-NN.
- A group-blind small hyperparameter grid (`max_depth {8,12,None}` × `min_samples_leaf {5,10,20}`
  × `max_features {sqrt,0.5,1.0}`), **optimising M0 only** —
  the tuning script does not receive history, and is **still less** allowed to look at which model maximises M1−M0;
  **when performance is close, the more regularised option is specified in advance.**
- Inference: the seed-cluster bootstrap 95% CI lower bound of `ΔOOS` > 0. The permutation test is demoted to secondary.
- **Declaring "insufficient capacity" from a capacity control requires both conditions at once**: the control's own CI lower bound > 0,
  **and** its point estimate ≥ 50% of the true history's. (Looking at the point estimate alone would let one noisy C1
  that happens to reach 51% kill the experiment. 50% is a deliberate guardrail and is not pretended to be a theoretical constant.)

## Calibration (rule 58, group-blind)

Pooled pass conditions: each of the two strategies 20–80%; overall survival ≥80%; meeting the gate within 5 days ≤50%;
**the gate really does open** (20–80% meet it before the window ends);
**not a pseudo-fork** (each strategy's survival **≥80% individually and differing by ≤10pp**). Take the smallest `S`/`λ` satisfying the conditions.

> ### ★ What if no S / λ satisfies the conditions ★
> **Then the probe's design is not clean enough, and the standards must not be relaxed just to let it run.**
> 026 measures strategy transfer, **not a fresh study of survival selection**.

Probe B is compressed into a one-dimensional λ: `c_f = λ·k_food` (k=1) and `c_s = λ·k_shelter` (k=22) —
in a two-dimensional space "minimum coupling strength" has no unique meaning.

## Rule 60: affordance gating must be non-destructive

Probe A **must never** write `world.food = 0`. `take_food` deducts from the **stock**
(`sim.py:181-186`), so zeroing it burns the world's food store every tick — that is "destroying food",
not "being unable to reach food". Use a `GatedWorld` subclass instead: the stock regenerates as usual and only the access rule changes;
`shelter` is read at call time (no one-tick lag); and when the gate is shut, one rng draw is consumed under the same condition as v3,
**so the gate changes only affordance and does not perturb the random stream**.

> The general lesson: **when temporarily restricting a variable with stock semantics, do not rewrite the stock;
> change the access rule.**

## G3 is still a mechanism question, not a necessary condition

If persistence is carried by the floor in the first place,
`history → floor consolidation → novel context → new divergence`
**it can perfectly well be genuine generalization**. **The carrier may stay the same;
what is new is that it produces new functional consequences on an unseen problem.**
G1 disappearing with the floor off → *generalization depends on the same consolidation
architecture*, which is **not a failure**.

## The naming criterion

**Both structurally orthogonal probes passing G1 → only then may *generalized individuality* be used;
only one passing → only *novel-context transfer* may be written.** Adding probes afterwards is forbidden.

## ★★ Rule 62: the behaviour window and the consequence window must be separated ★★

Calibration allows nearly 20% of the novel probe to die, but G1 predicts a **7-dimensional action share**.
If one ball dies on day 8 and another survives the whole window:

- **dropping the dead** → creates **survivor selection** again
  — exactly what the persistence stage spent a great many experiments cleaning out (rule 44)
- **using the behaviour up to death directly** → **the observation windows have different lengths**, so the shares are not comparable;
  and death itself may be caused by the rich/poor history
  → G1 would mix **"who lives longer"** with **"how decisions are made"**

So it is split into two windows:

```
enter the novel world
      ↓
[decision window] W_dec days ——— B_novel → G1 (behaviour)  in-window survival must be ≥ 95%
      ↓
keep running
      ↓
[consequence window] run to the end ——— survival / food / shelter / condition → G2 (consequences)
```

> **G1 measures "how it chooses when facing an unfamiliar situation" and G2 measures "what consequences those choices later produce".
> These two must not be mixed. Defining G1 by "analysing survivors only" is forbidden.**

`B_familiar` likewise takes only the decision window (both branches equal in length, rule 61);
both branches then run on into the consequence window — the familiar branch's consequences are the yoked control baseline for G2.

`W_dec` gets the same treatment as `S`/`λ` and is **not chosen by intuition**: the candidate set `{5,7,10,14}` days is fixed in writing first,
then chosen group-blind on `20000+`. In two dimensions a unique solution is taken by **lexicographic order**
(shortest `W_dec` first, then smallest `S`/`λ`), avoiding a repeat of the `c_f/c_s` "minimum has no unique meaning" problem.

## Two implementation-layer reminders (already written into §9 of the design)

- **The median for C2 may only be computed on the training fold** and then applied to the held-out fold —
  using the whole-data median would cause test information leakage.
  (C1 = `explore × build` is a pure product and has no such problem.) The same goes for any standardisation/binning.
- **Sibling isolation must be proven actively**: after forking, do not merely check that no references are shared —
  also run a **mutation test**: change clone F's `inventory`/`traits`/`world.food` and
  **assert that clone N is bit-unchanged**, then do it in the reverse direction. Cheap, but it proves the branches really are isolated.
  **If it does not pass, do not proceed.**

## The checklist of alternative explanations closed off (the design stage ends here)

| Alternative explanation | How it is closed off |
|---|---|
| sequential-measurement contamination | **rule 61** counterfactual sibling branches |
| familiar behaviour over-compressed | a **182-dimensional** `B_familiar` |
| M0 deliberately weakened | the **capacity controls** C1 / C2 (a guardrail, not a proof) |
| picking parameters to produce the effect | **rule 58** group-blind calibration |
| analysis randomness | **rule 56 strengthened**: deterministic folds + a fixed random_state + a fixed bootstrap seed |
| frozen ground burning the stock by mistake | **rule 60** a non-destructive `GatedWorld` |
| selection bias from death | **rule 62** decision / consequence window separation |

**The design ends here and will not be expanded further.** Next: mechanism implementation →
group-blind calibration on `20000+` → `NOVEL_PREREGISTRATION.md` → and only then touch `60000–61499`.

## ★ Rule 63: "complete executable state" must be audited field by field, never listed from memory ★

The first version of the mechanism layer wrote the state hash as `"memories": len(ag.memories)` —
**"has 5 memories" ≠ "the 5 memories have the same content"**, and `memories` is read back by
`recall()` (`sim.py:517/554/563`). So two agents could share a hash while their memory contents differ →
**the full-levelling negative control would miss a hidden difference**, making that control fake.

The audit method: grep the read points of v3's Agent / World / Life **field by field** —
**read back → EXEC (enters the hash, and must be levelled along with everything else); write-only → LOG.**

```
Agent EXEC  traits / trait_floor / trait_identity / hunger / energy / shelter /
            condition / inventory / hardship / _hardship_anchor / flags /
            knowledge / knowledge_strength / alive / rng
            memories        ★ read back by recall() (517/554/563) ★ must be complete, not just its length
            goal_satiation  ★ read back at sim.py:694 — the goal refractory period ★
            action_log      ★ read back at sim.py:619/626 — goal progress ★
Agent LOG   action_by_hour / goal_by_day / goal_history      (never read back inside sim.py)
World EXEC  food / objects / p / weather / rng
            storm_damage    ★ a dynamic attribute, present only after a storm; read back at sim.py:942 ★
World LOG   events                                            (written only by influences)
Life  EXEC  inf_rng
```

⚠ The audit caught two more than expected: **`action_log`** (thought to be a pure log, in fact feeding goal progress)
and **`storm_damage`** (a **dynamic attribute**, existing in `__dict__` only after a storm,
and impossible to find by "listing the fields").

### How it is implemented: a structural assertion rather than a hand-written list

`audit_fields()` takes the set difference over `vars(agent/world/life)`,
**and any unclassified field makes it raise**.
What that guards against is not "v3 changing later" (v3 is frozen) but **"I overlooked a field"** —
which is exactly how the first version went wrong.

It is also split into two scopes:
- `exec_state()` = EXEC only → used by the **full-levelling negative control** (after levelling, LOG should differ anyway)
- `full_state()` = EXEC + LOG → used by **fork isolation / determinism tests** (stricter)

### Mechanism-layer self-checks (`novel_situation.py`, all passing)

```
✓ rule 60: a shut gate burns no stock, regen is normal, an open gate yields food
✓ rule 61: the sibling mutation test passes in both directions (including memories content / goal_satiation /
           action_log / world.p)
✓ negative control: identical complete state → bit-identical
✓ forking with all floors off does not hit the FrozenZero deepcopy trap
✓ rule 63: the field audit assertion works, and both memories content and goal_satiation enter the hash
✓ Probe B: λ=0 equals no coupling, λ>0 really changes the trajectory
```

> **⚠ One consequence for the full-levelling negative control**: since `action_log` / `memories` /
> `goal_satiation` are all EXEC, **full levelling must level them too**,
> or the statement "the two groups are indistinguishable on every dimension" does not hold. A control script cannot level
> only traits/floor/knowledge.


## ★ Group-blind calibration results: both probes fail ★ (`novel_calibrate.py`, N=300)

The negative control passes first: **with the rule off (S=0 / λ=0), survival in both the decision and consequence windows is 100.0%**,
and each strategy is at 100% too — the implementation is correct, so the failures below are genuine design problems.

### Probe A "frozen ground": all 24 cells fail

```
 W_dec   S    dec-win alive  con-win alive  builder  explorer  build alive  expl alive   gap
   5   0.00     100.0%        100.0%        24.2%     75.8%     100.0%      100.0%     0.0%   ←baseline
   5  55.00   100.0%    54.7%  17.4%  75.5%   98.1%   49.8%  48.3%
   5  80.00   100.0%    41.3%  17.3%  75.5%   85.3%   35.2%  50.1%
```

Failure counts: ③ consequence-window survival 24/24, ⑥ strategy survival 24/24, ① strategy shares 22/24.

> ### ⚠ My argument in the design was wrong, and is corrected here ⚠
> Design §2 said: "the yield of `explore` goes through `EXPLORE_FOOD_YIELD` and does not pass through `world.food`
> → both routes are survivable". **"Bypasses the gate" ≠ "can survive".** Computing the rates makes it clear:
>
> ```
> expected explore yield = 0.28 × 0.5      = 0.14 food/tick
> needed to hold hunger steady = 2.2 / 20  = 0.11 food/tick
> ```
>
> A margin of only 27%, while each explore costs 9 energy (the base cost is only 1.2), so the
> ball must spend a great many ticks asleep → **at the actual explore share the net balance is negative**.
> Measured explorer survival: 35–51%.
>
> **I read "possibility" off the code structure without verifying "magnitude"** —
> the same class of error as the "cliff" in §3g (before rule 49).

### Probe B "saline soil": all 28 cells fail

```
 W_dec    λ    con-win alive  builder  explorer  build alive  expl alive   gap    coupling change
   5   0.00     100.0%       24.2%     75.8%     100.0%      100.0%     0.0%      ←baseline
   5   0.10     96.4%   24.2%  75.8%   85.3%  100.0%  14.7%    0.059
   5   0.20     79.0%   24.2%  75.8%   13.3%  100.0%  86.7%    0.063
   5   0.30     75.6%   24.2%  75.5%    0.0%   99.8%  99.8%    0.068
```

At λ=0.1 seven conditions hold and only ⑥ fails. At N=60 the gap was 12.0pp; **at N=300 it is 14.7pp** —
raising the sample moves it **further** from passing, so it is not noise. λ≥0.2 is a cliff: builder survival goes 13% → 0%.

### ★ Rule 64: v3 has only one food economy, so any probe that touches it produces a survival split rather than a strategy split ★

The two probes fail in **exactly the same shape: one strategy always becomes lethal**.

- Probe A gates `world.food` → the **explorers** lose their food source → they die
- Probe B has material gathering destroy `world.food` → the **builders** hollow out their own food source → they die

The root cause is the same: **`world.food` is v3's only real food source**,
and the yield rate of `explore` is not enough to live on independently (see above). So **any structural manipulation
of food availability turns a "strategy difference" into a "survival difference"**.

There is one more thing I got wrong: **the strategy classification (b vs e) does not correspond to dependence on a food source**.
The balls classified as "explorers" **still gather**; they merely have a higher explore share.
So Probe A's premise "there are two independent food routes" **fails twice over**.

> **Conclusion: v3's action economy is too narrow to support probes of the type "produce a strategy fork on a new structure".**
> This is not badly tuned parameters; it is determined by the economic structure of the model.

### Why probe designs can be iterated safely now

**The calibration is group-blind** — the script structurally cannot obtain the developmental-world label,
and its output contains only pooled quantities. **So not one bit of information about the rich/poor difference has leaked.**
Redesigning the probe on the basis of the calibration results **does not harm the final standing of `60000–61499`.**

This is exactly the value of doing the group-blind calibration first: **it caught "this experiment simply cannot measure
what it wants to measure" before the final was burned.**

### Three routes (awaiting a decision; I will not choose on my own)

1. **Change track**: design a probe that does not touch the food economy (the material/shelter economy, the information economy
   `read`/`book`, temporal structure), preserving survival so that a genuine strategy choice can appear.
2. **Admit the scope**: v3's action economy is not sufficient to measure novel-situation generalization; write that
   into the paper honestly — which is itself an honest architectural conclusion.
3. ⚠ A grey area: the λ grid is `{0.1, 0.2, …}` with no 0.05. Adding smaller values after seeing 0.1 come close
   **is not relaxing the criteria, but it is expanding the search space after the fact** (grid fishing);
   and a smaller λ weakens ⑧ "the coupling bites", so it is not free. **Explicit authorisation is required.**


## ★ Rule 65: a novel probe must not touch food ★

> **A novel probe's main manipulation must not directly change hunger, condition or the long-term sustainable
> food supply; survival may serve only as a safety check and must not become the probe's strategic reward function.**

What is to be measured is "whether the past made two agents take different approaches to a new problem",
**not** "who is better at surviving an artificially manufactured famine mechanism".

So the target shape of a new probe is:

```
both routes can continue to live normally
        ↓
but obtain different **non-survival** consequences
```

**Probe A "frozen ground" and Probe B "saline soil" are formally retired** (the record is kept, see the previous section).

### Why the other two routes are not chosen

- **Not adding a foraging mechanism to v3** (raising `EXPLORE_FOOD_YIELD` or adding a food economy):
  that would already be a fork to **v4**, the 011–025 evidence about v3 persistence would no longer connect,
  and "does v4 still have the original persistence architecture" would have to be confirmed again,
  dragging the project back to the model-validation stage. Worse, it would create an entirely reasonable suspicion:
  **"did you change the agent specially so that generalized individuality would appear?"**
  Even done with complete honesty, there is no need to take on that explanatory burden.
- **Not rushing to declare "v3 cannot do it"**: all that has been shown is that **the food economy cannot be used for this class of probe**,
  not that v3 fails in every structurally novel situation.
  The correct conclusion is **"we picked the wrong battlefield"**, not "the architecture cannot do it".

## ★ Behavioural-economy audit (group-blind) ★ (`novel_econ_audit.py`, n=591)

Measure the rates before choosing a new track — precisely where Probe A came unstuck.
30 days of common garden, survival 100.0%:

```
action              mean share  between-indiv SD    CV      p90−p10   balls >0
eat                  0.108        0.0007          0.01      0.001    100.0%   ← metabolically rigid, almost no individual difference
sleep             0.315    0.0524    0.17     0.146   100.0%
gather_food       0.041    0.0412    1.02     0.113    78.7%
gather_material   0.120    0.1676    1.40     0.426    58.4%   ★
build             0.022    0.0295    1.34     0.054    58.2%
explore           0.395    0.2453    0.62     0.640    76.0%   ★
read                 0.000        0.0000            —       0.000      0.0%   ← the baseline world has no books
```

> ### ★ Rule 66: `explore ↔ gather_material` is the only strategy axis in v3 with enough individual variance ★
> The `p90−p10` of those two actions is **0.640 / 0.426**, far above every other action;
> while the between-individual SD of `eat` is only **0.0007** — **eating is metabolically rigid
> and carries almost no individual difference**. That explains rule 64 from another angle:
> **touching food = touching a dimension that had no individual difference in the first place, which can only squeeze out a survival difference.**
>
> A new probe should be built on the `explore ↔ gather_material` axis:
> the largest variance, both routes **legal in both developmental worlds** (only the `material_yield` rate differs, 2.0 vs 0.5),
> and it does not touch food supply.

### ⚠ The read / book track has a fatal asymmetry and should be abandoned

Measured, **`read` has a share of 0.0000 in the common garden and 0% of balls ever did it** —
because `ACTION_REQUIRES_OBJECT = {"read": "book"}` and the `baseline` world has no books.

And the two developmental worlds are: **the rich world with `objects = ("book","music")` and the barren world with `objects = ()`.**

So putting a book into the novel world means:

```
for a ball raised in the rich world = **old experience** (it read books during development and has knowledge)
for a ball raised in the barren world = **something entirely new** (it has never seen a book)
```

**That is not "novel to both"; it re-exposes a developmental difference.**

Worse: `read` is identically 0 in `B_familiar` (the common garden has no books),
So this "prior-experience advantage" **would never appear inside `B_familiar` at all** —
it would pour straight into `ΔOOS`, letting G1 pass for a **trivial reason**.
**That is exactly the kind of false positive G1 most needs to block.**

> ### ★ Rule 67: a novel situation must be **equally novel** to both groups ★
> If an affordance exists in one developmental world but not in the other,
> then introducing it in a novel situation = re-exposing the developmental difference;
> that is a variant of N0 (parameter extrapolation), **not structural novelty**.
> Before choosing a probe one must verify: **is this affordance equally accessible in both developmental worlds?**
> `material` exists on both sides (only a 2.0 vs 0.5 rate difference) → eligible;
> `book` / `music` exist only in the rich world → not eligible.

## ⚠ A scope limitation that has to be stated alongside this

v3 has **no online causal learning**, so an agent **cannot "discover" a new rule and pick a route from it**.
It can only react **passively** to the changed payoffs (via goal progress, inventory, state).

So the new probe's novel structure has to produce behavioural divergence **through the reactive pathway**
(`gather_material` payoff changes → `improve_home` goal progress changes → goal switching changes),
**it must not rely on "the agent realizes it should do X first in order to do Y"**.
The design text is not allowed to be written that way either (wording discipline, §0).

## Awaiting a decision on the next step

The new probe sits on the `explore ↔ gather_material` axis, does not touch food, and is equally novel to both groups.
The concrete mechanism is **undecided**; per instructions I do not settle it myself. Candidate directions (all satisfying rules 65/66/67):

1. **Material accessibility depends on exploration history**: `material_yield` depends on recent explore volume
   — a new relation (present in neither world), with both routes remaining perfectly viable
2. **Material depletion / fallow**: continuous gathering makes `material_yield` decay, forcing alternation
3. **A new shelter–material coupling**: the payoff of `build` depends on the "source diversity" of the material

All three touch only the material/shelter economy; `eat` and `world.food` are left strictly untouched.

## Probe A2 "pathfinding": failed the feasibility calibration (`novel_calibrate2.py`, N=300)

Mechanism (implemented to the precise definition): material can only be obtained by performing `gather_material`,
**and that gather’s yield depends on the fraction of explore within the last τ ticks** (bonus α).
Pure explore gets no material; pure gather gets it inefficiently; what pays off is the **temporal combination**.

```
   τ    α  surviv    hit  hitSD  yield    gain trajTV   material by explore tercile (low/mid/high)
   6  0.5  100.0%  13.4%  0.143  1.005   +0.5%  0.000   116.2   0.8   0.0
  24  4.0  100.0%  49.7%  0.441  1.091   +9.1%  0.010   116.4   1.0   0.0
  48  4.0  100.0%  52.1%  0.459  1.120  +12.0%  0.011   116.6   1.2   0.0
```

**Rule 65 is fully met**: 100% survival, cell-by-cell indistinguishable from the rule-off condition —
**the "do not touch food" principle really does remove the survival confound**, and that is this round’s solid gain.
The hit rate climbs with τ from 13% to 54%, cross-individual SD reaches 0.46 — the mechanism itself works.

**But ⑤ trajectory TV is only 0.000–0.011 (threshold 0.02); 16/16 cells fail.**
**There is a new rule in the code, but no new strategy landscape in the behaviour.**
⚠ This is precisely what the manipulation check added this round caught — without it,
this probe would have walked all the way to the final run under the illusion that "the mechanism works".

### ⚠ Correction: material is **not** in surplus, it is **bimodal**

I earlier judged from the three-tercile means (116 / 0.8 / 0.0) that "material is in severe surplus". **That was wrong.**
Measuring material stock directly after 30 days of common garden (n=237):

```
median 0.0    p10 0.0    p90 203.0
share with stock < 3 (the cost of one build): 76.8%
```

**The median is 0; 77% of the balls cannot afford even a single build.** The distribution is extremely bimodal:
a few gatherers hoard 100–200, while the vast majority sit **at 0 the whole time**.

> ### ★ Rule 68: a multiplicative bonus is identically zero for individuals who never perform the action ★
> A2 hands out a **multiplicative** bonus of the form `material_yield × (1 + α·f)`.
> - For the 77% of balls that never gather: **it multiplies zero** — no bonus, however large, has any effect
> - For the 23% who do gather: they already hoard 116, so the bonus lands **where it cannot be spent**
>
> **The bonus reaches no population that can both access it and use it.**
> When designing a probe one must first check: **what fraction of individuals actually performs the action the manipulation acts on?**
> The only non-food actions performed by nearly everyone are `sleep` (100%) and `explore` (76%).

### The pincer structure (three rounds of group-blind evidence)

```
resource      binding constraint?             individual variance?
food/hunger   yes (rule 64)                   no — eat cross-individual SD = 0.0007
material      yes for 77% (stock stuck at 0)  yes — p90−p10 = 0.426
              but that 77% never gathers → the manipulation cannot reach them
```

**Manipulating the binding constraint (food) can only squeeze out survival differences;
manipulating the one that has variance (material) cannot reach the people actually constrained by it.**

This is no longer a fourth case of "picking the wrong battlefield"; it is starting to become a **structural conclusion about v3’s action economy**:
there seems to be no dimension in v3 that **simultaneously** satisfies "nearly universal participation", "large individual differences" and "non-food".

### Evidential constraints on the next step (not decided unilaterally)

Per rule 68 the manipulation has to land on an action performed by **nearly everyone**. Excluding food, only these remain:

- `sleep` (100% performed, p90−p10 = 0.146) — but it is tied to condition through
  `SLEEP_EFF_FLOOR`, so **whether that violates rule 65 needs a decision**; I do not broaden the reading myself
- `explore` (76% performed, p90−p10 = 0.640, the largest variance) — its **non-food** outputs are
  landmark / flag / knowledge plus trait feedback (curiosity +0.20, caution −0.10).
  A new structure acting on explore's **informational output** may be the only direction not yet falsified


## ★ v3 novel-probe capacity audit (unified eligibility standard, group-blind) ★

After three consecutive probe failures, **no fourth one is sought by intuition**; instead every existing behavioural channel in v3 is swept
with **one and the same set of six eligibility criteria** (`novel_capacity_audit.py`, n=591, 100% survival):

```
  Q1 nearly universal         participation ≥ 70%         Q4 not life-or-death   (rule 65)
  Q2 enough variance          p90−p10 ≥ 0.10              Q5 readback path       into score()/goal
  Q3 genuinely binding        ≥20% of individuals bound   Q6 equally accessible  (rule 67)
```

```
channel                     Q1 part  Q2 var  Q3 bind  Q4 safe Q5 read Q6 equal  verdict
sleep / energy              100.0%✓  0.146✓   54.0%✓        ✗       ✓        ✓  not eligible
explore / non-food output    76.0%✓  0.640✓   23.0%✓        ✓       ✓        ✓  ★ eligible
material / build             58.4%✗  0.426✓   75.5%✓        ✓       ✓        ✓  not eligible
goal structure               99.3%✓  0.533✓   87.1%✓        ✓       ✓        ✓  ★ eligible
knowledge                    99.7%✓  0.500✓   87.8%✓        ✓       ✓        ✓  ★ eligible
shelter / storm             100.0%✓  0.976✓   51.6%✓        ✗       ✓        ✓  not eligible
objects / action legality     0.0%✗  0.000✗    0.0%✗        ✓       ✓        ✗  not eligible
```

### ★ Conclusion: 026 is not sealed — three channels are eligible ★

**The judgement that "three failures are enough to declare v3 incapable" was one step premature.**
What failed three times was in fact **the same class of channel** (the resource economy: food, material),
while v3 still has **non-resource** channels that have never been tested: `goal structure`, `knowledge`,
and the **informational output** of `explore`.

> ### ★ Rule 69: classify consecutive failures before deciding between "change battlefield" and "declare impossibility" ★
> Probes A / B / A2 were all built on the **resource economy** (food → food → material).
> Three failures prove only that **this one class — the resource economy — does not work**; they cannot be extrapolated to "v3’s action economy does not work".
> **Before declaring architectural impossibility, one must first run a unified-standard sweep covering every channel.**

### Additional warnings for the three eligible channels (to be plugged before the next round)

- **`goal structure` (the strongest)**: 99.3% of balls have adopted ≥2 goal types, dominant-goal share p90−p10 = 0.533,
  87.1% are not monopolised by a single goal. Goals feed straight into `score()`, and the two worlds share one and the same
  `GOAL_ACTIONS`. ⚠ Q4 means "does not directly decide life or death", not "cannot possibly affect survival" —
  the feasibility calibration must still verify survival ≈ 100% as usual.
- **`knowledge`**: ⚠ **a Q6 asymmetry at the key level** — the `books` knowledge entry
  can only be acquired through `read`, `read` requires books, and **books exist only in the rich world**.
  The channel as a whole is eligible (every other key is obtainable on both sides), but **no probe may touch
  book-sourced knowledge**, or it falls straight back into the rule-67 trap.
- **`explore` non-food output**: ⚠ **Q3 is only 23.0%, barely past the 20% line** —
  meaning **77% of the balls already hold `loves_exploring`**; the informational output is **close to saturation**.
  This is isomorphic to A2's failure mechanism (the bonus lands where it cannot be spent) — **the highest risk of the three**.

### If all three channels also fail in the next round

only then is 026 sealed under "v3 does not have an action economy in which generalization can be tested cleanly",
and v4 is forked. **v4's design goal would then be very clear — not to make the model more complex,
but to fill the gap the experiments exposed: at least one economy that is "not life-or-death", "open to nearly everyone",
"supports several effective strategies" and "lets agents adapt behaviourally to a new contingency".**

> ★ The key methodological distinction ★
> Upgrading to v4 is **not about "tuning until the paper's result shows up"**;
> it is because **group-blind feasibility testing has clearly demonstrated that
> frozen v3 lacks the degrees of freedom required to measure this question**. Those two motives are worlds apart.


## A small goal-pair audit: the precondition for clearing Probe C (`goal_pair_audit.py`, n=591)

The capacity audit's "99.3% used ≥2 goal types" does not automatically establish that
these **two specific goals**, `see_the_world` / `improve_home`, are common enough. Checked on their own:

```
goal                adopted    goal-days%  days/agent   share p90−p10
improve_home         95.9%        25.3%       7.6        0.433  ★
stock_food           94.2%        25.3%       7.6        0.567
see_the_world        96.1%        48.0%      14.4        0.533  ★
learn                 0.0%         0.0%       0.0        0.000
recover              16.6%         1.3%       0.4        0.067

agents that adopted both        : 92.7%      ← the conflict needs subjects
this pair's share of goal-days  : 73.3%
goal switches (30 days)         : median 10 (p10 2, p90 12)
```

**The clearance condition is met by a wide margin.** This pair is the **dominant goal pair** in the common garden,
not a fringe case, and 92.7% of the balls have adopted both — the conflict has plenty of subjects to act on.

⚠ Two things were confirmed along the way:
- **`learn` participation is 0.0%** — consistent with `read = 0` (the baseline world has no books).
  So among M0's goal features, `learn` and `recover` (16.6%) are near-dead dimensions;
  **do not pad the feature set with dead dimensions**.
- Goal switching runs at a median of 10 times per 30 days → **the goal-switch dynamics are lively in themselves**,
  and that is exactly what Probe C sets out to act on.

### Two structural points in shelter (checked against the code; they support the floor of 40)

```
sim.py:792   s += 10 if self.shelter > 30 else -5        ← the step in the sleep score
sim.py:662   if self.shelter < 75:  pri = (75-shelter)/75*0.8 + c   ← improve_home priority
sim.py:611   clamp(self.shelter / 80.0, 0, 1)            ← improve_home goal progress
```

**shelter = 30 really is a structural point** (the sleep score jumps from +10 to −5).
So taking **40** as the hard floor is well founded: it steers clear of the step at 30,
while still sitting inside the range (< 75) where the `improve_home` priority is **responsive** —
and the levelling point shelter = 50 already lies in that range, so `improve_home` is active on entry.


## Probe C "the home falls into disrepair": retired (`novel_calibrate3.py`, N=300)

Mechanism: each explore wears shelter down by κ (hard floor 40), while `build` repairs it under the original rule;
**the ON/OFF backgrounds are perfectly isomorphic** (both `storm_chance=0`), the only difference being κ;
after the fork only `agent.goal` is cleared, leaving traits/floors/knowledge/flags/goal_satiation untouched.

```
    κ    satur.   trunc.      failure mode         cells
 0.05     75.3%     0.0%      ② unsaturated <20%   20/20
 0.10     76.1%     0.1%      ④ action landscape   20/20
 0.20     77.6%     0.1%      ⑤ goal layer too     19/20
 0.40     80.4%     0.1%      ③ both goals active   5/20
 0.80     85.0%     0.3%
```

### ★ Rule 70: saturation must measure "can the intervention still be applied", not "is the variable pinned to its bound" ★

I first defined saturation as `P(shelter == 40)` (the fraction of time pinned to the bound). **That was wrong.**
Probe C's guard is `if shelter > 40`, and shelter carries a **natural decay of 0.35/tick**,
so it slides below 40 on its own; from then on, however much the agent explores, the effect **fails silently**,
yet shelter does not stop at 40, so the "pinned fraction" stays near 0 — **a severe underestimate of saturation**.

The correct definition: **the fraction of explores at which the wear can no longer be applied because `shelter ≤ 40`**.
Measured at **75–85%** (threshold 20%). The two conventions differ by two orders of magnitude and give opposite conclusions.
**The truncation rate is only 0.0–0.3%**, which is direct evidence that "the pinned-to-bound convention will show no saturation".

### ⚠ The real reason: shelter is **bimodal**, not "in a steady state at 32"

My earlier note saying "steady state ≈ 32" was inaccurate as well. Measuring the day-by-day trajectory directly under the OFF condition (n=237):

```
day after entry  median    p10    p90  share <40  share <30
day 0              41.6   41.6   99.7       0.0%       0.0%
day 1              33.2   33.2   99.0      63.6%       0.0%
day 2              24.8   24.8   97.9      61.9%      61.9%
day 5               0.0    0.0   99.3      51.7%      51.7%
day 29              0.0    0.0   97.6      54.4%      53.4%
```

**p10 = 0.0 while p90 = 97.6 — extremely bimodal.**
About 52% of the balls give up on shelter entirely and sit at 0 for good; the other ~48% hold it at ~98 throughout.
The "mean of 32–41" is purely an artefact of mixing the two modes.

For Probe C this means:

- **52% of the balls**: from day 2 onward shelter ≤ 40 → κ **never lands at all**
- **48% of the balls**: shelter ~98, and a single build adds +22 → even κ=0.8 is a mere **drizzle**

**No population at all falls in the range where κ could do anything.**

### ★ Rule 71: v3's resource states are bimodal across the board, leaving gradient-type interventions no middle ground to act on ★

Putting the four rounds side by side, the same shape keeps reappearing:

```
material   77% stuck at 0    23% hoard 100–200             (rule 68)
shelter    52% stuck at 0    48% hold at ~98               (this section)
food       binding for all   but eat cross-ind. SD=0.0007  (rules 64/66)
```

**v3's positive feedback (trait drift + goal persistence) pushes agents toward specialisation**,
so every resource axis collapses into two heaps: "all in" and "all out".

> **The irony: the very positive-feedback machinery that produces persistent individual differences
> is also what wipes out the middle ground on which a gradient-type novel contingency could act.**

This may well be the **common root cause** of all four failures — A / B / A2 / C —
rather than four independent design mistakes.

⚠ **But 026 is not declared over on this basis** — that is exactly the step taken too early last time (rule 69).
There is still one channel in the capacity audit that is **not bimodal**:

```
knowledge   99.7% have ≥1 entry    87.8% have fewer than 4    → the distribution is a **gradient**, not bimodal
```

`knowledge` is the only channel with **near-universal participation and a continuously distributed value**.
Whether the next round should go there awaits a decision.


## ★ Rule 72: the window convention of a manipulation check must match G1 ★

A genuine implementation bug was found in `novel_calibrate3.py` (**recorded here, not fixed quietly**):

```python
def act_share(r, w_dec):        # ← w_dec is passed in, but never used in the body
    acc = Counter()
    for h in r["per_hour"]:     # ← this aggregates the **entire consequence window**
        acc.update(h)
```

The goal side, meanwhile, uses `r["goals"][:w_dec]`. So:

```
goal manipulation check   = decision window   ✓
action manipulation check = entire consequence window   ✗
```

**This is not aligned with rule 62, "separate the decision and consequence windows".**

> ### Rule 72 ###
> **Every manipulation check must use the same window convention as G1.**
> When the two sides use different windows, a reading like "the goal changed but the action did not" is **meaningless** —
> you are comparing quantities on two different time scales.
> In implementation terms: action trajectories must be stored per day (or per decision window) separately,
> not kept only as a whole-window `per_hour` aggregate.

⚠ **This does not affect the conclusion that Probe C is retired** — the retirement rests on intervention saturation
(75–85%) and the bimodal shelter trajectory, both of which are independent evidence and both outside the window convention.
But if Probe D goes ahead, **this must be fixed first**.

## knowledge effective-support audit (group-blind, books excluded, n=591)

Following rule 70: do not ask "does the variable look continuous", ask **"can a fixed-size intervention still change the
argmax"**. The path by which knowledge enters a decision is
`score += KNOWLEDGE_WEIGHT(12.0) × know(key) × slack` (`sim.py:835`),
so the maximum available swing is 12.0, and whether behaviour changes depends on **the top1−top2 margin at decision time**.

```
[1] knowledge_strength (★ not the number of entries ★)
key               held mean str     p10     p50     p90
far_places      77.0%    0.746    0.000   0.979   0.980
shelter         46.4%    0.439    0.000   0.000   0.980
food            88.8%    0.646    0.000   0.680   0.979

[2] decision margin = top1 − top2   (n = 425,520 decision ticks)
    p10 0.59   p25 1.76   median 4.57   p75 9.22   p90 16.42

[3] effective support
   Δ     flippable decisions   responsive agents
  1.0        15.7%            67.9%
  3.0        37.4%           100.0%
  6.0        59.1%           100.0%
 12.0        83.8%           100.0%
```

### ⚠ I wrote the clearance criterion with the wrong convention (corrected, not retro-approved)

I had written the clearance condition as "share of responsive **agents** ∈ [20%, 80%]", which left only
Δ=1.0 "eligible". **But that upper bound is wrong**:

- The saturation rule 70 worries about is at the **low end** (the intervention can no longer change anything)
- The risk at the **high end** is "the intervention overwhelms everything", and that has to be measured by the **share of flippable decisions**,
  not by the share of agents. At Δ=3.0, 100% of agents are responsive,
  which only means "every ball still has room to move" — that is a **good** thing, not saturation.

### The correct reading: **Δ ∈ [1, 6] gives 16–59% of decisions flippable, with every ball retaining slack
— the first channel in four rounds that genuinely has dynamic range.**
Compare Probe C: at 75–85% of the intervention moments the wear **could not be applied at all**.

**How the criterion should be set is not something I change on my own** (that is exactly adaptive analysis) —
it needs a decision. My suggestion: the threshold should be set on the **share of flippable decisions ∈ [20%, 60%]** (corresponding to Δ≈2–6).

### ★ Rule 73: knowledge_strength itself is nearly binary; the gradient lives in the margin ★

Table [1] has to be read carefully: `far_places` has p10 = 0.000 and p50 = 0.979 —
because strength returns to a full 1.0 the moment it is learned, and then decays by only 0.02 per day.
**So "does the agent have this piece of knowledge" is essentially 0/1, not a gradient** — rule 71 holds here too.

What is genuinely graded is the **decision margin** (p10 0.59 → p90 16.42).

> So Probe D must **act on the margin structure**
> and **must not rely on "knowledge strength is continuous"** — it is not.
> This has to be written into Probe D's design constraints, or it will repeat A2's "multiplicative bonus multiplied by zero" mistake.


---

# ★ Experiment 026 sealed — novel-situation generalization cannot be tested cleanly in v3 ★

**No Probe D will be designed. 026 ends here.**

## Conclusion (the honest version, ready for the paper)

> Within the frozen v3 architecture we **found no action economy in which
> novel-situation generalization can be tested cleanly**. This is not "we failed to think of a good probe";
> it is a structural result from four rounds of **group-blind feasibility testing**.

Four probes, four kinds of failure, **every one of them stopped before any final block was burned**:

| Probe | Mechanism | Reason for failure | Rule |
|---|---|---|---|
| A permafrost | shelter gates world.food | survival split: explorers survive 35–51% | 64 |
| B saline flats | zero-sum coupling of gathering ↔ foraging | survival split (reversed): builders 13% → 0% | 64 |
| A2 pathfinding | explore raises gathering yield | **the multiplicative bonus misses**: 77% of balls never gather, so it multiplies zero | 68 |
| C disrepair | explore wears shelter down | **intervention saturation 75–85%**: shelter is bimodal, nobody sits in the active range | 70 / 71 |

## ★ The common root cause: rule 71 ★

```
material  77% stuck at 0 23% hoard 100–200
shelter   52% stuck at 0 48% hold at ~98
knowledge nearly 0/1 (refilled to 0.98 on learning, decays only 0.02/day)  ← rule 73
food      binding for allbut eat cross-individual SD = 0.0007
```

**v3's positive feedback (trait drift + goal persistence) pushes agents toward specialisation,
every resource axis collapses into "all in / all out", and gradient-type interventions have no middle ground.**

> **The same positive-feedback machinery that produces persistent individual differences
> also wipes out the middle ground on which a gradient-type novel contingency could act.**
>
> This explains why the project was **so successful in the persistence phase
> and so hard in the generalization phase — they are two sides of one mechanism.**

## The one thing that escaped: the decision margin

The `knowledge effective-support audit` found that internal states are highly polarised,
**but the final decision margin is not fully polarised** (margin p10 0.59 → p90 16.42).
A standardised perturbation of Δ=3.0 can flip **37.4%** of decisions, and every ball retains some slack.

In plain terms: **these little balls already have quite fixed "personalities", but on the decisions where they
still hesitate a little themselves, an entrance remains.** This is kept, but **it is no longer asked to carry the big
generalization conclusion** — it becomes a mechanistic probe in the neighbourhood of rule 71 (see below).

## Assets 026 leaves behind (not discarded)

The mechanism layer of `novel_situation.py` (GatedWorld / the three probes / levelling / the rule-61 fork /
full executable state serialisation), the four group-blind calibration scripts,
and rules **60–73**. All of this can be reused directly in a v4 phase.

---

# Three closing items (the remaining work for the paper)

1. **A causal ablation of rule 71** — establish whether that positive feedback really causes both
   specialization and the drop in plasticity. **More scientific than building v4**:
   v4 would change the model, whereas an ablation asks directly whether the mechanism inside v3 is the cause.
   With an accompanying mechanistic probe: **susceptibility under a standardised decision perturbation (Δ=3.0)**
   — ⚠ it serves only as a mechanistic assay and **carries no generalization conclusion**.
2. **v3 parameter robustness** — currently the clearest hard gap for submission.
   The existing `sweep_results.csv` / `holdout.csv` belong to **v2**;
   the paper's candidate architecture is frozen v3,
   and a reviewer will certainly ask "why was the robustness analysis run on the old model?".
   → `param_sweep.py --out sweep_results_v3.csv` has been launched (500 sets × 300 seeds,
   with a `resultmeta` version column).
3. **Reproducibility + ODD + repo cleanup** — prereg / seed ledger / frozen dirs /
   SHA256 are all in place, but the engineering entry point is not:
   `pytest -q --collect-only` raises a collection error because `v2_frozen/` and `v3_frozen/` hold
   **test modules with the same names** as the root directory.
   Goal: **one command after a fresh clone runs the core regression / self-check end to end.**


## ★ v3 parameter robustness (`sweep_results_v3.csv`, 500 sets × 300 seeds, 45.5 minutes) ★

Filling the hard submission gap: the paper's candidate architecture is frozen v3,
but the earlier robustness analysis was run on v2. Now v3 has one of its own.

```
                           v2 (372→324 sets)            v3 (372→337 sets)
ratio, routine ★headline★  1.058  IQR[1.010,1.128]      1.076  IQR[1.010,1.153]
                           share > 1: 80.2%             share > 1: 78.3%
ratio, goals               1.061  IQR[0.992,1.116]      0.998  IQR[0.941,1.052]
                           share > 1: 72.2%             share > 1: 48.7%   ← ⚠
log ratio, routine         0.048  share > 0: 78.4%      0.062  share > 0: 76.6%
```

### ★ The headline robustness survives under v3 ★

**The routine (action-distribution) axis**: median 1.058 → **1.076** (slightly stronger),
and **78.3%** of the parameter sets are still > 1 (v2 had 80.2%).
The log ratio holds up equally well (76.6% vs 78.4%).
**This is the paper's headline metric, and it still holds across 500 random parameter sets.**

Incidentally: the number of sets dropped for total wipe-out falls **50 → 35** (a direct effect of the v3 mortality fix).

### ⚠ But the goal axis collapses to chance level under v3

`72.2% → 48.7%`, median `1.061 → 0.998`. **Essentially a coin flip.**

Mechanistically this makes sense: v3's only change is `COND_RECOVER_AT 30→65`,
condition sits permanently high → the `recover` goal is rarely triggered (the goal-pair audit measured only 16.6%)
→ so the **goal profiles of the two worlds converge**.
In other words, **a substantial part of the "world difference at the goal layer" in v2 was a projection of the condition difference**,
and that condition difference is exactly what we fixed in v3 (rules 46/47/49).

> ### ★ Rule 74: v3 preserves robustness at the action layer only, not at the goal layer ★
> The paper must **report the two separately**:
> - **Action-distribution axis**: median 1.076, 78.3% of parameter sets > 1 — robust, usable as the headline
> - **Goal axis**: median 0.998, 48.7% > 1 — **not robust across the parameter set; must not be claimed**
>
> ⚠ This is not bad news; it is **the result one should expect after correcting a confound**:
> the goal-layer difference had been riding on the condition difference all along.
> **The price of fixing the mortality confound is losing a secondary metric that was never clean.**

### Parameter sensitivity: v2 and v3 agree closely

```
              v2       v3
TRAIT_DRIFT        +0.432   +0.442   ← first in both versions
PERSONALITY_WEIGHT +0.289   +0.357   ← second in both versions
GOAL_BONUS         −0.050   −0.214   ← rises to third in v3
LANDMARK_BONUS     −0.153   −0.028   ← drops out in v3
```

**`TRAIT_DRIFT` is the most sensitive parameter in both versions (ρ≈0.44)** —
which corroborates the independent finding of the rule-71 ablation: **positive-feedback gain is the main source of persistence.**
Two completely independent analyses (parameter randomisation vs targeted ablation) point at the same mechanism,
which makes for a strong sentence in the paper.


## ★ Rule 71 causal ablation results: the second half is withdrawn ★ (`rule71_ablation.py`, N=300)

```
TRAIT_DRIFT   n      ratio    shelt.pol     mat.split     flippable    margin   mat.mid
   0.00     289      1.021        31.1%         93.8%         41.1%      3.95      6.2%
   0.30     288      1.012        56.2%         93.8%         38.6%      4.29      6.3%
   0.60     290      1.058        60.9%         93.6%         37.6%      4.57      6.4%
   1.20     289      1.157        58.7%         94.6%         38.0%      4.67      5.4%   ← v3 default
   2.40     286      1.575        78.8%         89.7%         44.2%      3.81     10.3%
```

### ✓ First half: positive feedback **causally** produces persistence

The transplant ratio runs `1.021 → 1.575`, essentially monotonic and over a wide range.
**At drift = 0 the ratio is only 1.021 — almost no individual difference is left.**

This is **independently corroborated** by the v3 parameter sweep: `TRAIT_DRIFT` is the most sensitive
knob among the 500 random parameter sets (Spearman ρ = **+0.442**; on v2 it was +0.432).
**Two completely independent analyses (parameter randomisation vs targeted ablation) point at the same mechanism.**

### ✗ Second half: does not hold, **withdrawn**

> ### ~~Rule 71 (original): the same positive feedback both produces persistence and wipes out the middle
> ground on which a gradient intervention could act~~ ★ withdrawn ★

The a-priori prediction was "(c) the share of flippable decisions falls monotonically with drift". Measured:

```
41.1% → 38.6% → 37.6% → 38.0% → 44.2%
```

**From 0 to the default of 1.2 it drops by only 3.1pp, and at 2.4 it climbs back to 44.2%.
That is not "plasticity being wiped out"; that is barely moving at all.**

More importantly, **the degree of material polarisation is entirely independent of drift**:
`93.8% → 89.7%`, and **at drift = 0 (no trait positive feedback whatsoever) it is already 93.8%**,
with the middle layer never rising above 5–10%.

> ### ★ Rule 71 (revised) ★
> `TRAIT_DRIFT` positive feedback **causally** produces persistence (1.02 → 1.58),
> and **partly** causes the polarisation of shelter (31% → 79%).
> **But it neither causes the bimodality of material (already 93.8% at drift=0)
> nor appreciably reduces plasticity at the decision layer (flippable decisions at Δ=3 stay between 37–44%).**

### ⚠ A consequential correction: the "elegant irony" line in the 026 sealing note is wrong

When sealing 026 I wrote:

> ~~"The same positive-feedback machinery that produces persistent individual differences also wipes out
> the middle ground on which a gradient-type novel contingency could act… two sides of one mechanism."~~

**That sentence is falsified by this ablation and is withdrawn.** The correct statement is:

> **The resource bimodality that blocked all four 026 probes is mainly a property of v3's resource dynamics
> themselves (material is consumed only by `build` at 3 per use; shelter decays monotonically at 0.35/tick),
> and has essentially nothing to do with the trait positive feedback that produces persistence.**

So the 026 sealing conclusion has to be **downgraded to a more conservative and more accurate version**:

> **The v3 resource economy does not support gradient interventions** — not ~~"positive feedback wiped out plasticity"~~.

The data support the former; the latter is a prettier mechanistic story with **no evidence** behind it.

> ### ★ Rule 75: the prettier the mechanistic story, the more it needs a targeted ablation to falsify it ★
> "Two sides of one mechanism" reads exactly like a paper highlight,
> and it is compatible with every observation in 026 — but **compatibility is not causality**.
> A single five-level targeted ablation (about 20 minutes) overturned it.
> **Before writing a mechanistic explanation into a paper, ask whether that mechanism can simply be switched off and tested.**


---

# ★ Wrapping up the v3 persistence paper package ★

## 1. Repo repair + reproduction entry point

`pytest --collect-only` went from **10 collection errors / no tests collected**
to **8 tests collected normally, all green (0.6 s)**.

Root cause: the root directory, `v2_frozen/` and `v3_frozen/` each hold a set of identically named modules
(`p1_test.py` / `p2_test.py` / `relaxation_test.py` / `rule48_test.py` /
`test_022_regression.py`), and pytest derives module names from the basename → `import file mismatch`.
**It cannot be solved by editing the frozen directories** (they are SHA-checked), so a `pytest.ini` was added at the root
restricting `testpaths = tests` and excluding the two frozen directories.
That incidentally removed another hazard: the `*_test.py` files in the root are **experiment scripts, not pytest tests**,
and used to be swept up by the `*_test.py` pattern, launching simulations that ran for tens of minutes.

Added: `tests/test_selfcheck.py` (frozen integrity / frozen imports / AST comparison of the single v2–v3 difference /
6 mechanism-layer checks / the rule-72 regression / determinism), plus `pytest.ini`, `requirements.txt` and
`REPRODUCE.md` (three reproduction tiers + which model each artifact came from + the seed ledger).
Deprecated and retired scripts were given a header marker; **not one was deleted**.

> ### ★ Rule 76: run a mutation check after writing tests, or "all green" may be fake ★
> Eight tests finishing in 0.6 s looks like nothing actually ran. Deliberately corrupting one
> checksum in `v3_frozen/SHA256SUMS.txt` → the tests turn red at once; restoring it → all green again.
> **Green without a mutation check does not count.**
>
> Also: the first version of the "v2/v3 differ by one constant" test compared **line by line after stripping `#` comments**,
> so the explanatory paragraph in the v3 docstring counted as a code difference. Switching to an **AST comparison with docstrings stripped**
> is what actually measures the "executable difference".

## 2. The ODD model description (`ODD.md`) — treated as a final static audit

Written to the ODD standard, with every sentence checked back against the code. **The audit turned up seven implicit mechanisms of the "I knew it, so I never wrote it down" kind**:

```
take_food            assumed zeroing world.food would block it → it actually deducts from stock; zeroing = burning the larder
memories             assumed a pure log → read back by recall()
action_log           assumed a pure log → feeds goal progress
goal_satiation       missed entirely → read back (refractory period)
storm_damage         missed entirely → a dynamic attribute, existing only after a storm
explore food output  assumed enough to live on → 0.14/tick vs 0.11/tick needed; net of sleep it is negative
knowledge_strength   assumed a continuous channel → nearly binary (0 or 0.98)
```

### ★ Rule 77: a line-number reference must state which version's numbering it uses ★

`v2_frozen/sim.py` has 1013 lines, `v3_frozen/sim.py` has 1043,
and **the offset is not constant** (+27 from the header docstring, then a further +3 from `MODEL_VERSION` in the middle):

```
                        v2     v3   offset
def take_food           154    181   +27
KNOWLEDGE_WEIGHT×know   805    835   +30
hardship += deficit     936    966   +30
_hardship_anchor        938    968   +30
```

⚠ **The `sim.py:NNN` references in experiment 023 and earlier in this log use v2 numbering**;
in `v3_frozen/` add 27 or 30. The line numbers in `ODD.md` have been unified to v3_frozen numbering.

### A newly discovered hidden mechanism: tie-breaking

When scores are equal, `max((score, action))` breaks the tie by **alphabetical order of the action name** →
`sleep` always wins and `build` always loses. **Measured over 19,200 decision ticks, exact ties occurred 0 times**;
it exists but has never fired. Recorded anyway — if someone later changes the scoring so that ties become common,
behaviour will be systematically biased toward `sleep`, and that was not documented anywhere until now.

## 3. Paper-claim audit (`CLAIMS.md`)

Every claim lands in one of three classes: **A main results** (directly supported after the v3 freeze),
**B mechanism results** (supported by targeted ablation), **C limitations** (no evidence; explicitly not claimed).

```
A1 persistent behavioural difference    final H1 = 1.142 [1.098,1.183] + robustness 78.3%
A2 not a mortality artifact             mortality 8.1%→4.3%, yet the effect grew rather than shrank
A3 floor-independent pathway            final P1 = 1.134 [1.090,1.175]
A4 discrete memory not the carrier      final P2 does not pass (v2/v3/final agree three times)
A5 episodic memory a bitwise no-op      fingerprints identical across three runs

B1 TRAIT_DRIFT causally drives it       ablation 1.021→1.575 + sweep ρ=+0.442 (two independent methods)
B2 floors carry most of persistence     1.142 → 1.046
B3 what matters is that floors existed  anchor content explains only 1.3%; negative control bitwise identical
B4 threshold 65 clears the idle valley  rich world 24.3%→36.3%→2.0%

C1 no floor-free residual effect        ⛔ sits on the detection boundary, undecidable (claim neither presence nor absence)
C2 goal axis                            ⛔ no claim made (48.7% over the v3 parameter set)
C3 novel generalization                 ⛔ may not be written as "failure"; only as "the v3 architecture cannot provide
                                        a clean novel-contingency test interface"
C4 positive feedback cuts plasticity    ⛔ the whole line is deleted (falsified by ablation)
C5 intended purpose                     ⛔ may not claim to simulate real personality formation
C6 architectural scope                  ⛔ wording like "the agent learns / understands / realizes" is forbidden
```

Also attached: a **forbidden-wording quick reference** and a **number-provenance checklist**
(marking which numbers come from v2 and must not be used as v3 evidence).

---

## ★ Phase line: the v3 persistence paper package is complete ★

The experimental phase ends here. Deliverables:

```
v2_frozen/ v3_frozen/            both frozen versions + SHA256
FINAL_PREREGISTRATION.md         preregistration (including amendment A)
final_confirm_result.txt         preregistered final confirmation (seeds 50000–51499, run once)
sweep_results_v3.csv             v3 parameter robustness
NOVEL_SITUATION_DESIGN.md        026 design (sealed, negative result)
ODD.md                           model description / static audit
CLAIMS.md                        claim ↔ evidence mapping + forbidden wording
REPRODUCE.md  pytest.ini  tests/ reproduction entry point
docs/SIMULATION_LOG.md           the entire process (every overturned conclusion kept verbatim)
```

Rules accumulated: **1–77**, of which **43, 48, 50, part of 71, and rule 33** were
**withdrawn or revised** by later experiments — the originals are all kept, annotated with when and by what evidence they were overturned.

---

# ★★ The v3 line is locked ★★ (2026-08-17)

**No further digging into v3 persistence, and no 78th or 79th mechanism experiment.**

The only condition for reopening: **finding a real bug that would change an existing conclusion**.
("I thought of a new mechanistic explanation" and "I would like to test one more pretty hypothesis" do not count.)

## The division of labour is fixed

```
v3   answers: can the past be left behind at all?      — done, see classes A/B in CLAIMS.md
v4   answers: can what was left be used for the future? — experiment 027
```

## Experiment 027 — Novel-Task Transfer (next phase, not started)

**The single research question:**

> When two agents with identical starting points but different pasts, who have since developed persistent differences,
> face for the first time **a new problem neither of them has ever seen**,
> will their different pasts make them **learn differently, choose differently, or adapt along different paths**?

### ★ No more forcing this into v3 ★

026 has already supplied the evidence: **v3's food / material / shelter world is not a usable
generalization test bed**. All four probes were stopped by the mechanism audit **before any final seed was touched**
— they effectively **saved us from running one wrong "confirmatory experiment"**.

### Explicit design requirements for v4 (read backwards from 026's failures, not "make the model more complex")

What v3 lacks is a **native pathway**:

```
new external rule  →  native perception by the agent  →  its own evaluation  →  its own choice
```

v3 has only the reactive scoring layer of `score()`, with **no online causal learning**,
so any "new contract" can only be implemented by having the experiment layer quietly add points to `score()` —
**that writes the conclusion in rather than measuring it.**

The accompanying requirements (also taken from 026's measurements, not invented):

| Requirement | Source |
|---|---|
| At least one economy that is **not life-or-death** | Rule 65 (touching food only squeezes out survival differences) |
| **Near-universal participation** (≥70%) | Rule 68 (a multiplicative bonus is identically 0 for those who never perform the action) |
| **Not collapsed into bimodality by positive feedback**, with a continuous middle state | Rule 71 (revised) + rule 73 |
| Several effective strategies that **all survive** | Rule 64 (otherwise it is a survival split, not a strategy fork) |
| **Equally novel** to both developmental worlds | Rule 67 (the books-style asymmetry is not allowed) |

### Assets 027 can inherit directly

- The mechanism layer of `novel_situation.py`: the sibling fork (rule 61), full executable state
  serialisation with mutation testing (rule 63), state levelling, and the non-destructive gate (rule 60)
- **The discipline of group-blind feasibility calibration itself** — 026's largest output:
  **proving, before a final block is burned, that "this experiment cannot measure what it means to measure"**
- Rules 55–77 (determinism, decidability, window conventions, saturation measures, mutation checks, …)
- **The seed ledger: `60000–61499` was never used because 026 was sealed, and is still clean**

### ⚠ One thing to do first when 027 begins

Once v4 forks, **none of v3's conclusions carry over automatically**.
The first question to answer: **does v4 still have the original persistence architecture?**
(Following 023's approach: re-verify H1 / P1 / P2 / the episodic-memory no-op on the same seeds.)
**Hanging v3's conclusions on v4 without re-verification is a methodological error.**

---

## Where this line finally stands

> v3 demonstrated that **experience leaves persistent differences**.
>
> 027 asks the stronger question —
> **whether the past genuinely shapes how an artificial agent later faces an unknown world.**


---

# ★★ Experiment 027 — Novel-Task Transfer + Reversal · FINAL ★★

**seeds 60000–61499, run exactly once, already completed (2026-08-17).**
Model: **v4 = the `v3_frozen/` core (byte-for-byte unchanged) + `novel_task.py`**
Parameter fingerprint `26778f672e9e7009` (α=0.05 β=0.05 τ=0.20)
Records: `final_027_result.txt` + `final_027_console.txt` (both transcribed in full below)

## Results (copied item by item from the files, not from memory)

```
n = 1428 / 1500
attrition   rich = 0.0000   poor = 0.0480   keep = 0.9520   ✓ passes the 90% gate

arm         metric                       mean diff              95% CI        p
main        H2 restricted switch latency   -0.0798  [-0.1632, -0.0035]   0.0464  *
main        H1 trial 1–10 exploration      +0.0006  [-0.0002, +0.0015]   0.1375
hist_blind  both metrics                   +0.0000   bitwise zero
trait_level both metrics                   +0.0000   bitwise zero

decidability diagnostics (8 analysis seeds)
  H2  lower-bound range [-0.1632, -0.1611]  MC SD 0.0009  judged significant 8/8
  H1  lower-bound range [-0.0003, -0.0002]  MC SD 0.0000  judged significant 0/8
```

## ★ Reading (under the three-valued rule of amendment 01) ★

> ### PRIMARY H2 = ◐ a history effect exists statistically, but **functional significance is not established**
>
> `Δ = −0.0798 trial`, 95% CI `[−0.1632, −0.0035]` **excludes 0**,
> but **the whole interval lies inside the ±1 trial practical-equivalence region**.

- Direction: `d = L_rich − L_poor < 0` → **balls raised in the rich world switch slightly faster after the reversal**
- Magnitude: **0.08 trial** on a 0–36 range, about **0.22%**, about **0.01 SD**
- All 8 analysis seeds judge the CI to exclude 0 → **not Monte Carlo noise**; it really is detectable
- **But it is far too small to carry any functional meaning.**

**The secondary H1 is not supported** (the CI contains 0, p=0.1375).
⛔ Per the preregistration, H1 may not stand in for the primary.

**Both pathway-isolation controls are bitwise zero** — no leakage;
the history effect enters the task by design through `curiosity/caution → novelty_style → β_i`.

## ★ Rule 79: amendment 01 saved this run just in time ★

Without the SESOI this result would have been written up as:

> ~~"H2 is significant (p = 0.046); developmental history changed reversal adaptation."~~

Whereas the truth is: **at n=1428, a difference of 0.08 trial is already enough to be "significant".**
The range is 36 trials.

**The SESOI was added after the rehearsal and before the final run was seen, and it was derived from the pooled
latency scale (mean 18.04 / SD 8.15 / smallest natural unit 1 trial), not from the between-group contrast.**
It is the only thing that stopped a large sample from dressing a minuscule difference up as a discovery.

⚠ A weakness in one diagnostic output (recorded, not changed): the decidability diagnostic prints the **lower-bound** range,
whereas here what decides "does the CI exclude 0" is the **upper bound** (−0.0035, hugging 0).
`judged significant 8/8` covers the substance (all 8 seeds exclude 0), but the printed interval is not the end that matters.
Next time it should print **whichever end lies closest to 0**.

## What 027 may and may not claim

| | |
|---|---|
| ✅ May write | In a task neither group had ever seen, a difference in reversal adaptation attributable to developmental history was **detected** (rich slightly faster), but its **magnitude falls below the pre-specified functional-significance threshold**, so **no transfer effect of practical size is claimed** |
| ✅ May write | The effect enters the task by design through `curiosity/caution → novelty style`; both pathway-isolation controls are bitwise zero |
| ⛔ May not write | ~~developmental history transferred to learning and adaptation in a jointly novel task~~ — **the functional threshold was not passed, so this sentence cannot be written now** |
| ⛔ May not write | *generalized individuality* (which in any case had to wait for a second orthogonal task) |
| ⛔ May not write | Any claim about H1 (not supported) |
| ⛔ May not write | "all historical carriers were searched" — the task offers no input port for any other carrier |

## The most informative part of this experiment

**Not "is there an effect" but "how big is the effect".**

v3 had already shown that **the past can persist** (final H1 = 1.142, robustness 78.3%).
027 now shows that those persisting differences **can indeed be read by an entirely new task**
(all 8 analysis seeds judge them detectable),
**but once passed through the pre-specified general exploration interface, only 0.08 of a trial remains** —
functionally close to nothing.

> **What the past leaves behind is very real;
> the part of it that transfers through this particular interface into an unknown future is very faint.**

This is a **highly informative negative/boundary result**, not a failure:
it turns "can individual differences affect the future" from a vague grand question
into a concrete conclusion **with a magnitude, a threshold and an interface dependency**.

## After 027

Per the closure rule, **no key design element is changed once the results have been seen**. 027 ends here.
`60000–61499` is burned and may not be reused.


## ★ Final wording of the 027 conclusion (tightened) ★

> **Differences formed by the past can leave a statistically detectable trace in an entirely new task,
> but once carried through the single pre-specified interface `curiosity/caution → novelty style`,
> the effect is only about 0.08 trial, far below the pre-set 1-trial functional threshold —
> so persistence did not automatically convert into novel-task adaptation of any practical size.**

### ⚠ Correction: "8/8" must be described as analysis-level Monte Carlo stability

I earlier phrased `judged significant 8/8` as "detectable 8/8", which reads too easily as "replicated 8 times out of 8".
**Wrong.** Those 8 runs used **the same 1428 pairs of data** and varied only the **analysis-layer** random seed.

- ✅ What it does prove: `p = 0.0464` **is not an artefact of bootstrap / permutation Monte Carlo jitter**
- ⛔ What it **cannot** prove: that sampling replication is strong
- ⚠ And **the CI upper bound is only −0.0035** — the statistical evidence itself hugs the zero boundary

In the paper this may only be written as **analysis-level Monte Carlo stability**.

> ### ★ Rule 80: distinguish "analysis-layer stability" from "sampling-layer replicability" ★
> Re-running with a different analysis seed = ruling out MC noise, nothing more;
> re-running with different **data** = replication. The two must never share a word in a report.

## ★ The study now holds two facts of very different magnitude ★

```
past → persistent behavioural difference             large
    v3 final persistence ratio = 1.142; 78.3% of 500 parameter sets point the same way

persistent difference → functional transfer in a strange task    very weak
    027 reversal latency = −0.0798 trial; the whole CI lies inside the ±1 equivalence region
    initial learning (H1) has no evidence at all
```

> ### ★ The core proposition (this may be the contribution unique to this set of experiments) ★
> **Persistent individuality ≠ automatically functional generalization.**
>
> An AI really can be "raised into something different" by its past,
> **but that does not mean the difference will matter noticeably on the new problems it meets later.**

---

# Experiment 028 — Interface-Width Test of Historical Transfer (in design, not started)

**The name deliberately avoids "generalization".** 027 forced out a key conceptual distinction:

```
is the historical information there at all    ← v3 proved it is
can a new task access that information        ← 027 proved: through one narrow interface only a very faint functional effect is readable
```

**028 exists specifically to prise these two apart.**

## ★ Iron rule: a wider interface ≠ giving history a larger weight ★

⛔ It must **never** be built as `027: β=0.05 → 0.08 trial` / `028: β=0.5 → 2 trial`
and then written up as "look, a wide interface transfers". **That would just be us amplifying the historical signal three- or tenfold.**

✅ The correct approach: **hold the total history→task coupling strength fixed and vary only how many
mutually distinct historical dimensions the task can read.**

```
narrow interface   reads only curiosity / caution        (= 027)
wide interface     reads curiosity / caution / industry  ← but the total coupling budget equals the narrow one
```

Not "one pipe at 0.05 → three pipes at 0.05 each (three times the signal)",
but **the same budget K spread over more historical dimensions**.

## The primary question (not "is the wide interface significant")

> **With the total coupling strength held equal,
> does a broad-history interface produce a larger cross-history novel-task effect
> than a narrow one?**

All three outcomes are informative:

| Outcome | Meaning |
|---|---|
| The wide interface is clearly stronger | 027's 0.08 was mainly because **only a very narrow pipe had been opened for the past** |
| The wide interface is still near 0 | the agent does hold marked differences from its past internally, but those differences **broadly lack functional transferability** |
| Only one dimension works | **different components of persistence have different transferability** |

## ⚠ Two design questions that must be settled before work starts (raised by me, awaiting a decision)

### ① In what unit is "equal total coupling budget" defined

"Equal" has to be operational. The only self-consistent definition I can see is
**that the population standard deviation SD(beta_i) of the `beta_i` produced by the interface is the same** —
because **it is that dispersion which can create between-group differences**, not the number of dimensions nor the sum of the weights.

### ② Under an equal budget, adding a "history-irrelevant" dimension **necessarily dilutes**

If `industry` carries little historical information, giving it part of the budget trades signal for noise,
so **"wide ≤ narrow" may be preordained by construction**
rather than being evidence that "interface width does not matter".

**This is not a design flaw, but it has to be declared in advance**:
"the wide interface is weaker" is an **interpretable outcome (dilution)**,
and it corresponds exactly to the third row of the table above — **different historical components differ in transferability**.

### ③ So the proposal is that 028 have more than two arms and instead **decompose by dimension**

```
arm A   reads only curiosity−caution   (= the 027 interface)
arm B   reads only industry
arm C   all three combined, same total budget as A/B
```

**Every arm's SD(beta_i) is aligned to the same K.**
Only that answers "which historical component transfers" directly, rather than merely "is wide better than narrow" —
and it covers precisely the third outcome the user listed.


---

# ★★ Experiment 028 — Interface Breadth and Component Transfer · FINAL ★★

**seeds 70000–71499, run exactly once, already completed (2026-08-17).**
`interface_sha=f82497fb5b1ff535…`  `task_fp=26778f672e9e7009`
Records: `final_028_result.txt` + `final_028_console.txt` + `final_028_STARTED.lock`

## 1. Validity gates (read before the outcome) — all passed

```
contemporaneous A: μ=0.036750  SD=0.012280
arm      oob bnd.mass  |Δμ|/SD_A |ΔSD|/SD_A  support   budget
Bp     0.14%    0.14%       2.3%       0.4%        ✓        ✓
Bm     0.14%    0.14%       0.5%       0.2%        ✓        ✓
Cp     0.07%    0.14%       2.6%       1.0%        ✓        ✓
Cm     0.10%    0.10%       0.1%       0.9%        ✓        ✓

primary (C±) ✓ valid      secondary (B±) ✓ valid
```

Thresholds: support 2% / budget 10%; the worst measured values are 0.14% / 2.6% — **a margin of 4–14×**.
The frozen transform transports cleanly onto the confirmatory population.

pre-task attrition diagnostic (not a binding gate):
rich 0.00% · poor 4.60% · valid twins **1431/1500 = 95.40%**.

## 2. Results (copied item by item from the files)

```
arm      E (paired)   95% CI
A        -0.0391      [-0.0818, +0.0028]
Bp       -0.0252      [-0.0783, +0.0245]
Bm       +0.0433      [-0.0070, +0.1034]
Cp       -0.0741      [-0.1377, -0.0245]
Cm       -0.0370      [-0.0720, -0.0035]

★PRIMARY G = -0.0021 trial   95% CI [-0.0307, +0.0231]   SESOI = 1.0 trial
 secondary R_B = 0.0252      95% CI [+0.0007, +0.0650]
```

## 3. ★ PRIMARY reading: the CI contains 0 ★

> **There is no evidence that a broader historical readout is stronger than 027's narrow interface.**
> `G = −0.0021 trial`, 95% CI `[−0.0307, +0.0231]`.

This corresponds to the **second pattern** in §6 of the preregistration:

> **C ≈ A — a wider historical readout did not increase transfer; the extra dimension gave no net gain.**

⚠ This may **not** be shortened to "wide interfaces do not work". What was found is that, under an equal budget,
reading one extra historical component orthogonal to A **left the transfer magnitude unchanged** — that is this experiment's conclusion, not a general claim about "interface width".

### ★ The min(·) rule saved us from a wrong conclusion that would have stood ★

```
|E_Cp| = 0.0741      |E_Cm| = 0.0370      |E_A| = 0.0391
min(|E_Cp|, |E_Cm|) = 0.0370  ≈  |E_A| = 0.0391   →  G ≈ 0
```

**Looking only at C+ gives `0.0741 vs 0.0391`, nearly a factor of two,
and C+'s CI `[−0.1377, −0.0245]` excludes 0** —
enough to be written up as "a wider readout interface doubles the transfer magnitude".

**But C− is only 0.0370.** In other words, that "gain" **depends entirely on which sign the industry residual
is connected with** — and for that sign we have **no mechanistic reason whatsoever** to specify one in advance.

> ### ★ Rule 83: a component with no semantic direction must be judged by its worst sign ★
> The preregistration froze `G = min(|E_C+|, |E_C−|) − |E_A|` precisely for this moment.
> Had only one sign been run (even one picked at random beforehand), there would have been **a 50% chance of
> concluding that the "breadth gain is significant" — a conclusion entirely produced by sign arbitrariness**.

### The benefit of the joint bootstrap is directly visible too

The CI for `G` is **0.054** wide, while a single-arm CI is about **0.08** wide —
**the CI of the difference is narrower than either single arm**, exactly what happens when the same-seed correlation cancels replicate by replicate.
Subtracting endpoints instead would inflate the width spuriously (measured at 29.2× in the adversarial test).

## 4. ⚠ The secondary R_B's CI excluding 0 **is not evidence**

`R_B = min(|E_B+|, |E_B−|) = 0.0252`, CI `[+0.0007, +0.0650]`.

**Excluding 0 is almost automatic here** — `R_B` is the minimum of two absolute values,
**≥ 0 by construction**, so the bootstrap distribution lies entirely in `[0, ∞)`,
and the 2.5% quantile is bound to be > 0 unless exact zeros are drawn in bulk.

> ### ★ Rule 84: "the CI excludes 0" carries no information for a non-negative statistic ★
> The preregistration defined `R_B` but **wrote no reading rule for it** (unlike `G`, which has a SESOI).
> That is a gap in the preregistration. **R_B can now only be reported descriptively**,
> stating explicitly that "its CI excluding 0 is not evidence of component transfer",
> and a threshold **must not** be added after the fact to turn it into a positive result.
>
> Descriptive facts: `B+ = −0.0252`, `B− = +0.0433` — the two signs point in **opposite directions**,
> and both magnitudes are far below the 1-trial functional threshold.

## 5. ★ Arm A: 027's narrow-interface effect **failed to replicate** ★

```
028 arm A   E_A = -0.0391   95% CI [-0.0818, +0.0028]   ← CI contains 0
027 orig.   E   = -0.0798   95% CI [-0.1632, -0.0035]   ← CI excludes 0
```

**The point estimate is about half of 027's, and the CI now contains 0.**

> **027 narrow-interface effect did not replicate on the new sampling block.**

This is a **sampling-level replication** (an entirely new block of seeds),
**as distinct from** the analysis-level Monte Carlo stability inside 027 (rule 80) —
the latter only showed that `p=0.0464` was not bootstrap jitter.

⚠ Per §5 of the preregistration, **A's success or failure is judged separately from G**: A failing to replicate **does not invalidate G**,
and G is still read by its own CI + SESOI as "the CI contains 0".

## 6. What 028 may and may not claim

| | |
|---|---|
| ✅ | Under an equal total coupling budget, **reading an additional historical component orthogonal to the exploration axis did not increase** novel-task transfer magnitude (G = −0.002, CI [−0.031, +0.023]) |
| ✅ | The conclusion is **robust to the sign** with which the industry residual is connected (worst-sign criterion) |
| ✅ | **027's narrow-interface effect failed to replicate on an entirely new sampling block** (E_A's CI contains 0, the point estimate halved) |
| ⛔ | ~~wide interfaces do not work~~ — only "this one orthogonal component, under this equal-budget setting, gave no net gain" |
| ⛔ | Any component-transfer claim based on `R_B`'s CI excluding 0 |
| ⛔ | *generalized individuality* |

## 7. What 027 and 028 show together

```
v3     past → persistent behavioural difference               large (1.142; 78.3% of the parameter set agree)
027    persistent difference → function transfer in a strange taskvery weak (0.08 trial, below the functional threshold)
028    widening the historical readout (equal budget)         no improvement (G ≈ 0)
028-A  that already very weak 027 effect                      no longer measurable on a different block of seeds
```

> ### ★ The core proposition (stronger than after 027) ★
> **Persistent individuality ≠ automatically functional generalization.**
>
> After 027 one could still say "perhaps the interface was simply too narrow".
> **028 widened the readout interface at an equal coupling budget and gained nothing;
> and 027's already faint effect did not replicate on a new sampling block.**
>
> So the more accurate statement now is: **through the class of general exploration interfaces we are able
> to construct, these persistent differences carry almost no replicable functional transfer.**


---

# Experiment 029 — Memory Transfer (in design, not started)

**2026-08-18 · only one thing was done today: opening `MEMORY_TRANSFER_DESIGN.md`**

⚠ **That file is not a preregistration**; it is a design draft and may be revised freely today.
The preregistration (`NOVEL_TASK029_PREREGISTRATION.md`) will only be written once all five questions have been
settled and the group-blind calibration has passed.

## The 029 question (frozen)

> **Can structurally relevant past experience be retrieved and causally used
> to adapt to a surface-novel problem?**

## Division of labour with the earlier experiments

```
025 / v3   can the past persist at all?                              ✓ clearly
027        does the personality left behind transfer by itself?      very weakly (0.08 trial)
028        does reading more personality history rescue it?          no (G ≈ 0)
029        can past experience be genuinely retrieved and used by analogy?← the new question
```

## Why 029 cannot be a sequel to 028

028 has walked the "read more broadly" route to its end, and **arm A of 027 did not replicate on a new sampling block**.
So what 029 must change is the **type of pathway**, not its bandwidth:

```
027 / 028   history → one scalar we read out on its behalf → β → exploration bonus
029         history → addressable entries → the agent retrieves by similarity itself → decision
```

**If 029 ends up degenerating into "the experimenter picks a better readout", it is simply a third arm of 028
and should not be a project of its own.**

## Version 1 answers only five questions (②–⑤ are all drafts, awaiting a decision)

① What exactly 029 measures — **frozen**
② What object "memory" is in the model, and which action counts as "retrieval" — open
③ What "surface-novel, structurally related" means, and how to guarantee it is not self-deception — open
④ How "retrieved and causally used" is cast as the primary endpoint — open
⑤ What counts as failure, and how to know before the run that the design is clean — open

## Disciplines already pinned into the draft (carried over)

- **Iron rule (from 028)**: a stronger retrieval channel ≠ giving history a larger weight. 029 needs the same equal-budget control.
- **The biggest risk**: if the similarity function is hand-written by us and we already know which experience "ought" to be useful,
  then what is measured is **our similarity function**, not the agent's retrieval. → it must be designer-blind.
- **Must come in pairs**: besides the match arm there must be a **structure-mismatch arm** (equally surface-novel),
  or any gain could just be "agents that have a memory explore more".
- **Rule 84 booked in advance**: if the primary uses a non-negative statistic such as `min(|·|)`,
  a reading threshold must be written **at the same time**, or the finished run can only be reported descriptively.
- **From rule 67 / 026**: the two developmental worlds must be equally novel; structural relatedness cannot exist for the rich branch alone.

## ★ Frozen before the run: a negative 029 is informative too ★

The core proposition is now **Persistent individuality ≠ automatically functional generalization**.
If 029 also comes out ≈ 0 the proposition does not change; it only strengthens to "even given a **genuine episodic retrieval channel**,
persistent individual differences still carry almost no replicable functional transfer".

**This paragraph is frozen now precisely to stop the design being revised after the run in pursuit of a positive result.**

## Seeds

```
80000–81499     ★ reserved for 029 FINAL ★   verified: never used as a seed anywhere in the repository
```
Which block calibration / rehearsal will use is still open; the 80000 block **must not** be touched.

## How to reproduce (new)

- `AI SANDBOX/MEMORY_TRANSFER_DESIGN.md` — the 029 design draft (a living document with a version log)

---

## ★ The 029 identifiability probe — `memory_transfer_probe.py` (2026-08-18) ★

**The program is deliberately not called `experiment029.py`.** Today it asks one thing only:
**whether the memory → retrieval → evidence → choice pathway is even capable of affecting the outcome.**
(We have been burned too often: running a group comparison when the mechanism has no capability at all.)

The base = 027's task, **with not a single number changed** (80 trials, reversal at trial 41, same α/β/τ, fingerprint
`26778f672e9e7009`). Seeds = the development block `0–399`. **80000–81499 untouched.**

### Three things settled today

**① The development history does not use rich/poor**; it is replaced by a clean, small learning history:

```
Stable    the rules of problems 1/2/3 never reverse
Volatile  identical problem count, reward magnitude and trial count, but each has a change point
```

stable/volatile is **not a personality**; it only gives the agent a different **store of experience**;
all concrete symbols are counterbalanced, so what is learned has to be
**"a relation that worked in the past sometimes stops working"**, not "B always turns good later".

**② 029 defines its own Episode structure** (it does not reuse `{event, day, importance, text}` —
that suits autobiographical memory but is not enough for causal transfer):

```
Episode: context / previous_expectation / observation / prediction_error
         / action_relation / outcome
```

> ### ★ Rule 85: transferable memory stores relations, not identities ★
> `action_relation` may only be **stay / switch**, and **never A / B**.
> Storing option identity leaves nothing transferable once the task changes — a new task has no A and B at all.
> Implemented as a **hard constraint** (`Episode.__post_init__` + `_assert_relational_only()`);
> any option identity appearing in a field raises immediately.

**③ A minimal relational retrieval** (version 1 deliberately avoids "genuinely intelligent" retrieval):

```
current: the old strategy used to be good + recent consecutive prediction errors
  → retrieve "previously-good strategy + persistent surprise"
  → m = E[R|switch, similar past] − E[R|stay, similar past]
  → logit(switch) = base_learning + λ·m
```

The essential difference from 027: `027: trait→β` has us reading out a scalar on its behalf;
`029: current situation → retrieval → past outcomes → evidence → choice`.

### Engineering self-checks — all passed

```
relational constraint   Episode stores only stay/switch   m(S)=−0.667  m(V)=+0.667  m(empty)=0
determinism             same body+memory+seed → identical trial by trial
memory-blind            at λ=0 the two memory stores match trial by trial on 400/400 seeds
```

### ★ POSITIVE CONTROL: passed ★ (same body/Q/reward table/u, only the memory swapped)

```
λ       traj changed   Δlatency(V−S)    Δpost-reversal accuracy
0.00      0.0%           +0.000          +0.0000   ← memory-blind, must be 0
0.25      4.5%           −0.095          +0.0015
0.50      9.2%           −0.138          +0.0021
1.00     17.8%           −0.125          +0.0029
2.00     28.5%           −0.180          +0.0068
4.00     41.5%           −0.168          +0.0099
```

The direction is right: Memory V (where switching used to pay off) → faster switching + higher post-reversal accuracy.

### ★ SWAP TEST: failed (at every λ) ★

```
λ       |memory eff|    |body eff|     ratio
0.25        0.091          0.351      0.26×
0.50        0.140          0.370      0.38×
1.00        0.104          0.384      0.27×
2.00        0.134          0.399      0.34×
4.00        0.107          0.447      0.24×
```

The memory effect is **consistent in direction across both bodies**, but only 1/4–1/3 the magnitude of the body effect.
**Swap the memory and the outcome still mainly follows body/traits** — exactly the case the SWAP test exists to catch.

### ★ Diagnosis: λ is not the problem ★

```
retrieval fired  180/400 seeds fired at least once (45.0%); on average only 0.69 of 80 trials per seed
                 median first-firing trial 43 (reversal at 40); almost no firing before the reversal (0.04)
base p(switch) at firing   median 0.208   IQR [0.179,0.245]   ≥0.9 in 0.0%
```

> ### ★ Rule 86: passing the positive control ≠ the mechanism is eligible; exposure matters too ★
> At firing time base p(switch) is only 0.21 → **the decision is not saturated; memory has room to act**.
> But memory enters the decision on only **0.69 trials** on average, whereas the body's β enters on **all 80**
> trials — **an exposure asymmetry of roughly 116×**.
>
> So raising λ only changes **more trajectories** (4.5%→41.5%) without moving the **endpoint**
> (Δlatency stays around −0.1): a single-trial push only shifts "which trial the switch happens on",
> and is washed out afterwards.
>
> **What needs fixing is the exposure/persistence of retrieval, not the coupling strength.**
> And under 028's equal-budget iron rule, **this SWAP comparison is not itself an equal-exposure comparison**,
> with the asymmetry running against memory.

### Candidates for the next step (★ not chosen today, awaiting a decision ★)

```
(a) keep the evidence in the decision while the situation lasts, instead of clearing it after a single trigger
(b) relax SURPRISE_RUN_MIN so retrieval fires earlier and more often
(c) redefine the SWAP reading: is |memory|>|body| too strict? equal exposure is the correct convention
(d) replace the base with a multi-change-point task — a single reversal gives memory only one chance
```

⚠ (c) is a **reading convention**, whereas (a)(b)(d) are **design changes**.
**Settle (c) first**, or this turns into "change the design until the metric looks good".

### Deliberately not done today

```
⛔ formal Stable vs Volatile comparison   ⛔ 029 final seeds   ⛔ preregistration
⛔ SESOI                                  ⛔ final λ value     ⛔ adding memory into sim.py
⛔ LLM / embedding                        ⛔ running episodic+semantic+abstraction all at once
```

### How to reproduce (new)

- `memory_transfer_probe.py` — the 029 identifiability probe (positive control + SWAP + diagnostics)
  → `memory_transfer_probe_result.txt`, `memory_transfer_probe_console.txt`
- `AI SANDBOX/MEMORY_TRANSFER_DESIGN.md` v2 — the 029 design draft (a living document)

---

## ★ (c) criterion revision + probe v2: stateful retrieval (2026-08-18, later the same day) ★

### ⛔ The SWAP dominance criterion is formally withdrawn ⛔

> **The original text is kept, not deleted** (see the previous section):
> `|memory effect| > |body effect|`, which failed at all five λ values.

> Original SWAP dominance criterion failed at all tested λ, after which
> inspection showed that the criterion compared an event-triggered channel
> active on ~0.69/80 trials with an always-on trait channel. The dominance
> criterion was therefore **retired before any Stable/Volatile outcome was
> observed**.

**The reason for withdrawal is not "it failed" but that it measures something other than what we want to know.**
It answers "is memory's endpoint effect larger than the body's";
what SWAP should answer is "**with the body held completely fixed and only the memory swapped, does future behaviour
change in the predicted direction with the memory content**". Two entirely different estimands.

> ### ★ Rule 87: an event-triggered mechanism cannot be compared with an always-on one on endpoint effect ★
> **This corrects the direction of rule 86.** Rule 86 was right that "exposure is what needs fixing",
> but the "comparison requires equal exposure" it implied is **wrong**:
> memory and personality should never have the same exposure — personality is an ever-present prior,
> while memory should be **invoked only when a relevant situation arises**. Forcing memory online on 80/80 trials
> would destroy this design's most important theoretical feature: **context-dependent retrieval**.
>
> The right approach: report **exposure** and **per-opportunity influence** separately.
> ```
> A. Exposure   E_i = #{retrieval-eligible trials}
> B. Potency    Δp_t = p_switch(M_V) − p_switch(M_S), computed on exactly the same decision state
> ```
> Potency freezes the decision state on the **memory-blind (λ=0) trajectory** and then swaps the memory counterfactually.

> ### ★ Rule 88: potential and realized retrieval must be reported apart ★
> `fired` is itself shaped by the preceding choice sequence (a cautious body stays three times in a row more easily
> and so triggers retrieval more readily) — **the firing count is itself a product of the task dynamics**.
> ```
> potential retrieval opportunity   defined on the memory-blind (λ=0) trajectory → measures mechanism exposure
> realized retrieval                what actually happens on the memory-enabled trajectory → part of the outcome
> ```
> ⛔ It is **absolutely forbidden** to analyse only the agents that "successfully recalled" — that is survivor conditioning.
> Written as an assertion: every aggregate must use all 400 seeds.

### The new SWAP estimand

```
M_C = L(Body C, Mem V) − L(Body C, Mem S)
M_K = L(Body K, Mem V) − L(Body K, Mem S)
M   = (M_C + M_K)/2          the body effect serves only as a robustness diagnostic
```
Of interest: directional consistency / pooled M / Body×Memory interaction / (later) a SESOI.

### Mechanism change: (a) one-shot → stateful (**not** "hold for a fixed N trials")

A fixed N would add an arbitrary parameter. It became a state machine instead, with **both resolution conditions using only quantities that already exist**:

```
NORMAL →(persistent surprise ≥3 in a row and the strategy in hand used to be good)→ RETRIEVE
      record the suspect strategy → ACTIVE: m keeps entering the working decision state
ACTIVE →① Q[the other] > Q[suspect]     "ah, it really did change"    → RESOLVED
       →② 3 consecutive non-surprises on suspect  "that was just chance"  → RESOLVED
```

★ **During ACTIVE, m acts on the suspect, not on "the switch action"** ★
v1 added `+λm` to switch on every trial, so once it pushed one switch through, the next trial became "switch back again" —
semantically wrong and prone to oscillation. It is now `logit(switch) += λ·m·s`, with
`s=+1` if the switch **leaves** the suspect and `s=−1` if it **returns** to it.
That is what "I suspect the rule has changed" means, and the suspicion lasts until it is confirmed or dispelled.
(`suspect` is a working variable at decision time, **not** an Episode field — rule 85 is unchanged.)

**Everything else is untouched**: the three thresholds, the single reversal, seeds 0–399, and λ is swept but not chosen.
The v1 file is kept intact, with an assertion guaranteeing it still reproduces the original result bit for bit (λ=1: 71/400, −0.125).

### ① ② EXPOSURE

```
mechanism       eligible      potential     realized(λ=1)
v1 one-shot        45.0%           0.75              0.69
v2 stateful        45.0%           7.18              6.96
```
Exposure goes 0.75 → 7.18 (9.6×). **It is still event-triggered (7.2/80),
and it has not been — and should not be — stretched to the body's 80/80.**

### ③ POTENCY (counterfactual memory swap on the λ=0 frozen decision state)

```
mechanism      opps     base p(sw)             satur.      mean|Δp|
v1 one-shot     300          0.208               0.0%        0.2205
v2 stateful    2873          0.400               0.0%        0.2807
```

> **v1's per-opportunity potency was never low to begin with (0.22 at λ=1).
> What v1 lacked was exposure, not potency.** This directly confirms rule 86's diagnosis.

### ④ The new SWAP — directional check: **PASS**

```
mechanism   λ          M_C      M_K  pooled M     95% CI (descr.) same sign interact.
v1 one-shot 1.00    -0.125   -0.083    -0.104    [-0.410, +0.215]       yes    -0.042
v2 stateful 0.25    -0.875   -0.900    -0.887    [-1.343, -0.471]       yes    +0.025
v2 stateful 1.00    -4.058   -3.920    -3.989    [-4.785, -3.231]       yes    -0.138
v2 stateful 4.00    -9.607   -9.710    -9.659   [-10.815, -8.549]       yes    +0.103
```

- **M_C and M_K share a sign across both mechanisms and every λ** → directional SWAP check: **PASS**
- The Body×Memory interaction is tiny relative to M (−0.138 vs −3.99 at λ=1)
  → **memory does not depend on one particular body in order to work**
- The CIs are **descriptive** (seed-cluster bootstrap, n_boot=10000, analysis seed 8181).
  **No SESOI is set today, so no functional-significance reading is made.**

### ⑤ DOWNSTREAM (a consequence only, not a criterion)

```
mechanism   λ     traj chg    Δlat(V−S)   Δpost-rev acc
v1 one-shot 1.00     17.8%       -0.125         +0.0029
v2 stateful 0.25     30.8%       -0.875         +0.0115
v2 stateful 1.00     43.2%       -4.058         +0.0535
v2 stateful 4.00     45.0%       -9.607         +0.1688
```

⚑ At λ=4 the trajectory-change rate is **45.0%, exactly the eligible-seed share** —
the ceiling is eligibility, as constructed: seeds that never trigger retrieval are by definition entirely unaffected.

### ★ Conclusion of the probe phase ★

> **v1's problem really was that "the retrieved evidence never formed a persistent decision state",
> not that λ was too small.**
> With not one threshold, task or seed changed, making retrieval stateful on its own
> moved pooled M from −0.10 to **−3.99 trial** (λ=1, a factor of 38).

### ⚠ The direction of risk has flipped (left to calibration, not handled today)

```
the mechanism may now be TOO STRONG: −9.7 trial at λ=4, while the latency range is only 0–36.
the hand-built memories sit at the MAXIMUM POSSIBLE CONTRAST (m_S=−0.667, m_V=+0.667).
real Stable/Volatile histories will produce a much smaller |m|.
→ −4 trial is an UPPER BOUND under maximum memory contrast, not an expected effect size.
```

⚠ Another thing to watch: **the ACTIVE window and the latency endpoint overlap by construction**
(the suspicion is dispelled roughly when the switch succeeds). Before any strong conclusion we need
**an endpoint that is not defined by that same window**.

### Still not done today

```
⛔ (b) relaxing SURPRISE_RUN_MIN   ⛔ (d) a multi-change-point task
⛔ final λ value   ⛔ final seeds   ⛔ preregistration   ⛔ SESOI
⛔ Stable/Volatile outcome         ⛔ adding memory into sim.py
```

**This is still not a scientific success for 029**: the memories are hand-built, λ is not frozen,
and Stable/Volatile has not been run at all.

### How to reproduce (new)

- `memory_transfer_probe2.py` — v2 stateful retrieval + the exposure×potency decomposition
  → `memory_transfer_probe2_result.txt`, `memory_transfer_probe2_console.txt`
- v1 `memory_transfer_probe.py` is **left untouched**; v2 carries an assertion that it still reproduces bit for bit

---

## ★ probe v3: the resolution timing bug fixed + endpoints reorganised (2026-08-18) ★

### The bug that was fixed

v2's loop order was `choice → reward → PE → test RESOLVED (on the old Q) → update Q`.
So whenever this trial's new evidence was **exactly** what pushed the new strategy's Q past the suspect's, it had not yet been written into Q at test time.

> **resolution test was originally evaluated before incorporating the current
> outcome into Q, allowing retrieved evidence to persist for one extra decision
> after the resolution criterion had effectively been met.**

Corrected to `… → PE → **update Q** → test RESOLVED on the updated Q`.
The `calm_run` condition is unchanged (it should use the pre-update PE anyway —
a prediction error is by definition relative to the expectation held **at that moment**).

**The v1 and v2 files and results are kept intact and not overwritten**; v3 carries assertions guaranteeing they still reproduce bit for bit.

### Effect of the fix: the effect shrinks, the story does not change

```
λ      pooled M pre-fix   pooled M fixed      Δ     same sign
0.25       -0.887            -0.786       +0.101      yes
1.00       -3.989            -3.621       +0.368      yes
4.00       -9.659            -9.486       +0.173      yes
λ=1  potential exposure 7.18 → 6.77   realized 6.96 → 6.53
λ=1  Δpost-reversal accuracy +0.0535 → +0.0499
```

> ### ★ The direction of this bug **inflated** the effect ★
> After the fix the core mechanism is **still clearly present**, and M_C / M_K still share a sign at every λ.
> "A bug existed, its direction favoured us, and the conclusion survives the fix" —
> that is the best possible case, and it has to be **reported unprompted**, not only when someone asks.

### ★ Endpoint reorganisation: latency is demoted ★

> ### ★ Rule 89: the primary endpoint must not overlap by construction with the mechanism's own active window ★
> The exit condition of `ACTIVE` ≈ "Q proves the new strategy is better",
> and restricted switch latency ≈ "the new strategy starts to dominate stably" — **the two are inherently bound together**.
> Latency can still be reported (it describes "how much faster memory makes the switch happen" very well),
> but it **cannot** be 029's strongest scientific endpoint.

**The new primary candidate: post-change cumulative errors**

```
C_i = Σ_{t=40..79} 1(choice_t ≠ correct_option_t)      how many wrong choices after the rule change
ΔC  = C(V-memory) − C(S-memory)                        ΔC < 0 when V helps
```

It is identical to `post_correct` (`C = 40(1 − post_correct)`, written as an assertion) but its unit is directly trials.
Advantages: the window is fixed in advance by the task / it never reads ACTIVE or RESOLVED / no never-switch censoring /
every agent has one / a SESOI is easy to set / it measures the actual functional cost.

```
ΔC (primary cand.)      M_C      M_K   pooled     95% CI (descr.)   same sign
v3 fixed  λ=0.25     -0.415   -0.480   -0.448    [-0.616, -0.279]         yes
v3 fixed  λ=1.00     -1.995   -2.053   -2.024    [-2.394, -1.670]         yes
v3 fixed  λ=4.00     -6.340   -6.433   -6.386    [-7.176, -5.629]         yes
Δlatency (2nd) λ=1   -3.708   -3.535   -3.621                             yes
```

**The primary asks "how many fewer mistakes are actually made"; the secondaries (latency / exposure / potency /
ACTIVE segment length / realized retrieval) explain "why".**

⚠ The hand-built MEM_S/MEM_V = ±0.667 is the **maximum contrast** → everything above is an **upper bound**, not an expected effect size.

---

## ★ The hand-built memory probe phase ends → on to acquisition (`memory_acquisition_probe.py`) ★

**The next step is not calibrating λ.** Until we know whether real Stable/Volatile histories produce m = 0.03 or 0.30,
arguing about λ = .25 versus 1 has no scientific meaning. The official order:

```
fix the resolution bug → lock an independent endpoint → build real Stable/Volatile histories
→ let the histories generate Episodes themselves → observe the real memory-evidence distribution → only then calibrate λ
```

### ★ Key design: both sides experience surprise ★

❌ "Stable never has a surprise while Volatile has many" → the memory difference would degenerate into
"one has data and the other does not", which is far too easy.
✅ **The same surface phenomenon means different things.**

```
t <  20     original strategy p_high, the other p_low   ← identical in both conditions
t 20–27     ★both drop to p_low★                        ← bitwise identical in both conditions
t ≥  28     Stable: the original recovers / Volatile: the other becomes the good one
```

Reward sampling shares a single random stream → **the two conditions are bitwise identical for t<28** (verified on 100 seeds × 3 problems).
**The anomaly on its own does not reveal which world you are in**; the difference lies only in "what this anomaly means".

### matching diagnostics

```
① total trials             150.00 = 150.00   ✓
② total reward opps        105.60 = 105.60   ✓
④ first-good=index0      0.4783 = 0.4783   ✓
③ episode count             2.88 vs 3.67   ≠ (a behavioural product; reported)
  total reward obtained    82.99 vs 73.19  ≠ (see the caveat below)
```

### ★ The m grown from real experience — the direction is exactly right ★

```
             n(m defined)  mean m     SD      p10     median     p90    m>0
Stable            94      -0.3783  0.3410  -0.7500  -0.4000  0.0000    8.5%
Volatile          96      +0.5257  0.2240  +0.2647  +0.5000 +0.8333  100.0%
separation = +0.9040   hand-built = +1.3333   →  real experience reaches 67.8% of the hand-built version
```

**Stable is negative (staying pays) and Volatile positive (switching pays), consistent with the design.**
Real experience really can grow the kind of relational evidence our hand-built memories stood for.

### ⚠⚠ But it stalls on yield: only 24% of agents grow a definable m ⚠⚠

```
episode completeness (both stay and switch entries present)  Stable 23.5%  Volatile 24.0%
→ roughly 3/4 of agents finish development with NO usable memory at all
```

Yield diagnostics (per problem; entry requires both halves at once):

```
                Q≥.60         stay-run≥3           both   longest
Stable          57.8%              56.9%          17.2%      2.98
Volatile        57.8%              77.0%          17.2%      3.62
```

> ### ★ Rule 90: the two halves of an entry condition can undermine each other by construction ★
> Entering the situation window requires "the strategy is still trusted (Q ≥ .60)" **and** "three disappointments in a row" —
> but **every disappointment pushes Q down**. At α=.05, three zeros take Q from .76 down to .65,
> so agents whose Q never climbed high enough are filtered out by this very clause.
> **The bottleneck is the first half** (only 57.8% have Q≥.60 at the anomaly onset) → what should change is
> **the amount of experience before the anomaly**, not the surprise half.
>
> ⛔ It is never permitted to work around this by "analysing only the agents that grew a memory" (rule 88: survivor conditioning).

### Caveat: realized reward cannot be matched

Volatile agents collect less in total (73.19 vs 82.99) because they have to relearn after the change point.
**Opportunity is already matched bit for bit**; matching realized reward would amount to cancelling the manipulation itself.
**Recorded, not fixed.**

### Deliberately not computed at this stage

```
⛔ novel-task latency   ⛔ post-change errors   ⛔ Stable vs Volatile transfer effect
```
**These quantities are not even present in the code** — that is what keeps the freedom to tune the acquisition mechanism
without starting to tune the design around a final outcome.

### How to reproduce (new)

- `memory_transfer_probe3.py` → `memory_transfer_probe3_result.txt` / `_console.txt`
- `memory_acquisition_probe.py` → `memory_acquisition_probe_result.txt` / `_console.txt`
- v1 `memory_transfer_probe.py` and v2 `memory_transfer_probe2.py` are **left untouched**;
  v3 carries assertions guaranteeing that both still reproduce bit for bit

---

## ★ Acquisition parameters frozen + λ interface-capacity calibration (2026-08-18) ★

### Frozen: only the learning length before the anomaly is increased

Decision: **increase pre-anomaly experience only**, leaving GOOD_THRESH / PE_THRESH /
SURPRISE_RUN_MIN untouched and adding no further problems. A purely upstream sweep (0–399, not yet connected to the novel task):

```
pre-anomaly   Stable completeness   Volatile completeness   complete-only m separation
   20              23.5%                  24.0%                  +0.904
   28              49.2%                  52.0%                  +0.872
   34              61.0%                  69.3%                  +0.902
★  36 ★            65.8%                  73.3%                  +0.894
   40              69.5%                  76.8%                  +0.884
```

> ### ★ Increasing pre-anomaly experience mainly fixes yield and barely changes memory contrast ★
> This is a **clean engineering correction**: it recovers the agents the entry condition filtered out
> rather than tuning the Stable/Volatile contrast ever stronger (separation is much the same at 34/35/36/38).

**Frozen as the 029 acquisition candidate:**

```
ANOMALY_AT  = 36      (was 20)
ANOMALY_LEN =  8      (unchanged)
T_PROBLEM   = 66      keeps the post-anomaly stretch at 66−36−8 = 22 (as before)
```

The reason for picking 36 rather than 40 is the **elbow**, not maximal separation:
20→36 buys +42pp / +49pp, while 36→40 buys only another 3–4pp.
(`memory_acquisition_probe.py` carries an assertion that there must still be 22 trials after the anomaly.)

### ★ Rule 91: memory availability is itself a developmental outcome ★

> **Memory availability is itself a developmental outcome. Do not condition
> transfer or calibration on successful memory formation. Report the extensive
> margin (P[m usable]) and intensive margin (m | usable) separately, but all
> primary analyses use the full predefined population.**

Measured at ANOMALY_AT=36 (missing either the stay or the switch side → m=0, meaning "no usable evidence"):

```
              extensive P[m usable]   intensive mean(m|usable)   all mean m   all median
Stable              65.8%                  −0.4099             −0.2695        −0.2440
Volatile            73.2%                  +0.4842             +0.3546        +0.4099

population-level separation (all agents, incl. m=0) = +0.6241   ★ this is the true value ★
complete-only separation (only those that grew one)  = +0.8940   ⚠ inflated
hand-built = +1.3333 → the real population reaches 46.8%, complete-only would look like 67.1%
```

⛔ Filtering out the agents that "failed to form a usable memory" and then calibrating on the most informative remainder
**systematically inflates the true input strength of the memory channel** — structurally the same error as
survivor conditioning (rule 88).

### The Stable/Volatile yields are unequal (65.8% vs 73.2%) and are **not fixed**

Volatile naturally accumulates both stay and switch experience more easily, and that is part of
`history → memory availability → future behavior`.
**Forcing completeness into balance = editing a post-treatment mediator.**
In future the memory effect will be split into an extensive margin (whether a usable relational memory formed)
and an intensive margin (how strong the direction is if one did), with SWAP / DELETE / SHUFFLE testing causality.

### Realized reward is likewise **not fixed**

Stable 117.24 vs Volatile 103.42 (under the new parameters). Volatile is lower because it has to relearn after
the change point. **Equalising realized reward for the sake of matching ≈ compensating Volatile and
cancelling the cost of volatility itself.** What genuinely needs matching is trial opportunity,
the opportunity count of the reward schedule, first-good identity, pre-anomaly observations and
task-length structure — all of which are already bit-for-bit equal (198.00 / 144.00 / 0.4783).

---

## ★ λ interface-capacity calibration (`memory_lambda_calibration.py`) ★

The question asked: **once real memory input has passed through this interface, can a single decision produce an effect that is neither saturated
nor negligible?** ⛔ It is **not** "which λ makes 029 most likely to succeed".

### Group-blindness is structural here

```
pooled_empirical_m()  both conditions flow into one pool → ★including m=0★ → sorted
                      sorting destroys the m ↔ condition correspondence; this module CANNOT recover the grouping
```
Input: n=800, mean +0.0426, median |m| 0.3571, **m=0 for 31.2%**
(≈1/3 of agents have an inert interface at any λ — precisely rule 91's extensive margin).

The `Δp` convention = relative to a **no-memory** counterfactual, with decision states taken from the λ=0 memory-blind trajectory
(probe3's frozen-state pipeline, 2708 states, median base p 0.382, 0.0% saturated in themselves).

```
   λ    mean|Δp|  median|Δp|  p90|Δp|   post-sat   P(flip)
 0.25    0.0176     0.0182    0.0382      0.0%       3.2%
 0.50    0.0352     0.0363    0.0764      0.0%       6.6%
 1.00    0.0699     0.0717    0.1520      0.0%      13.4%
 2.00    0.1339     0.1354    0.2923      0.6%      24.8%
 4.00    0.2272     0.2250    0.5046     12.7%      33.5%
 8.00    0.3050     0.2952    0.6694     46.3%      35.5%

active-memory exposure holds at ~7/80 across the whole grid → memory is still event-triggered ✓
```

### Three criteria (the reading conventions are set by this file, **not preregistered values**)

```
① not saturated     share pushed into p≤0.05 or ≥0.95 ≤ 5%
② real but not too strong   median|Δp| ≥ 0.02 and P(pref. flip) ≤ 25%
③ event-triggered   active exposure ≤ 20/80

   λ      ①        ②                        ③
 0.25   pass    ✗ med 0.018 (negligible)     pass
 0.50   pass    pass med 0.036 flip 6.6%     pass
 1.00   pass    pass med 0.072 flip 13.4%    pass
 2.00   pass    pass med 0.135 flip 24.8%    pass (flip sits right on the 25% line)
 4.00   ✗ 12.7%  ✗                          pass
 8.00   ✗ 46.3%  ✗                          pass
```

**Admissible band = λ ∈ {0.50, 1.00, 2.00}**

### Recommendation (★ this file does not freeze anything on the user's behalf ★)

> **λ = 1.00** — the centre of the admissible band, close to neither edge.
> 0.25 falls below the "not negligible" line; 2.00 sits right on the 25% flip-rate edge and has begun to saturate
> (0.6%); from 4.00 upward it saturates hard. At λ=1: median|Δp| 0.072, flip 13.4%, saturation 0.0%,
> exposure 6.73/80.

⚠ The **numeric thresholds of the three criteria also need a decision** — they are this file's reading conventions, not preregistered values.

⛔ This file does not and cannot compute: Stable vs Volatile ΔC / latency /
which λ separates the two groups best. The condition label is discarded at the input.

### How to reproduce (new)

- `memory_lambda_calibration.py` → `memory_lambda_calibration_result.txt` / `_console.txt`
- `memory_acquisition_probe.py` has frozen ANOMALY_AT=36 / LEN=8 / T=66
  and added an extensive / intensive margin report (rule 91)

---

## ★★ λ formally frozen + the OWN/DELETE/SWAP/SHUFFLE rehearsal (2026-08-18) ★★

### Frozen (★ from this moment on, never changed for any Stable/Volatile outcome ★)

```
SATURATION_MAX       = 0.05    # p ≤ .05 or ≥ .95
MEDIAN_ABS_DP_MIN    = 0.02
PREF_FLIP_MAX        = 0.25
ACTIVE_EXPOSURE_MAX  = 20      # /80 trials
MEMORY_LAMBDA        = 1.00
```

Admissibility requires **all four** conditions at once, with the exposure one using **max rather than mean**:

```
max( E[m10], E[m50], E[m90] ) ≤ 20/80
```

> **Event-triggeredness must not allow "one memory sign is already nearly always on
> but gets averaged away by the other two".** The maximum exposure at λ=1 is only 6.95/80, so the verdict is unaffected
> (re-run and confirmed: the admissible band is still {0.5, 1.0, 2.0}).

These four numbers are **engineering admissibility gates, not scientific significance
thresholds**: 5% saturation = memory must not push more than 1 in 20 eligible decisions to near-certainty;
median|Δp| ≥ .02 = if it cannot move even 2 percentage points it never really enters the decision;
flip ≤ 25% = at most one reversal in four — influential, but memory does not have the last word;
exposure ≤ 20/80 = pinning event-triggeredness down to "taking part in at most a quarter of the task"
(measured at only ~7/80; this one mainly guards against future architectural drift).

### ★ Rule 92: a selection rule must freeze "how the choice was made" along with the choice ★

> **Lambda was calibrated without condition labels or downstream transfer
> outcomes. Values were required to satisfy prespecified interface-capacity
> constraints on saturation, median probability shift, preference reversal,
> and retrieval exposure. Among admissible values, the log-scale midpoint of
> the admissible range was selected.**
>
> The admissible band {0.5, 1.0, 2.0} lies on a doubling grid, and `1.0 = √(0.5×2)` is exactly its log-scale centre —
> **what is chosen is "the point furthest from both failure directions", not "the most potent one"**.
> An assertion in the code raises immediately if λ ever stops equalling the log centre of the admissible band.
>
> This way, even if 029 FINAL comes out negative, nobody can ask "would a different λ have turned it positive?" —
> the answer being: **we do not know, and changing it after the fact is not allowed**; λ was frozen by interface
> properties before any group transfer outcome was seen.

The actual interface behaviour at λ=1: when a memory really is recalled, it typically moves the choice probability by about
**7 percentage points** (median|Δp| 0.0717, p90 0.1520), about **13.4%** of eligible
decisions therefore cross the original preference boundary, it **never pushes a decision close to certainty** (saturation 0.0%),
and it is online for only about **8–9% of the task** (6.5–7.0 / 80).
— capable of influencing a decision, yet neither an ornament nor a bolt-on controller.

---

## ★ Rehearsal: naturally grown memory wired into the novel task for the first time (development seeds 0–399) ★

### ⚠⚠ To be clear up front: under this architecture DELETE and SWAP are **algebraic identities** ⚠⚠

The body is a constant (NeutralBody) and the developmental history carries **nothing but memory** into the task,
so for any given seed the two conditions **differ only in memory**:

```
DELETE   both stores empty → identical trial by trial → ΔC ≡ 0        (identity, assertion passes)
SWAP     memories exchanged → OWN with swapped labels → ΔC ≡ −ΔC(OWN)  (identity, assertion passes)
```

> ### ★ Rule 93: with only one pathway, DELETE / SWAP degenerate into assertions, not evidence ★
> When the developmental history enters the test through **a single pathway**, "delete it and the effect disappears" and
> "swap it and the result follows" hold **necessarily by construction** — what they prove is
> **"there is no second leakage pathway"**, not "memory is causally effective".
>
> **For SWAP to become a non-trivial test, the developmental history must carry something besides memory**
> (the trait pathway of 027/028, for instance), or the agent's entire identity is its memory.
> That is a design conclusion for the real 029.
>
> This file runs them as **assertions** (raising on mismatch) and **does not interpret them as results**.

### PRIMARY: ΔC = C(Volatile) − C(Stable), paired on the same seed, ★ whole population ★

```
arm         C Stable   C Volatile      ΔC        95% CI (descr.)   rel. to OWN
OWN          20.867      19.940      -0.927   [-1.202, -0.677]        1.00
DELETE       20.545      20.545      +0.000   [+0.000, +0.000]        0.00   ←identity
SWAP         19.940      20.867      +0.927   [+0.680, +1.202]       -1.00   ←identity
SHUFFLE      20.490      20.578      +0.087   [-0.068, +0.242]       -0.09   ★
SWAP-XS      20.812      19.922      -0.890   [-1.140, -0.660]        0.96   ★
```

### ★ The two genuinely informative controls ★

**SHUFFLE** (shuffling `action_relation` within the agent's own entries: episode count,
stay/switch counts and the marginal outcome distribution are **all preserved**; only the action↔outcome relation is destroyed):

> ΔC collapses from **−0.927 to +0.087** (−9.4% of OWN), with the CI spanning 0.
> **The effect comes from the relational structure, not from the marginal statistics of the memory store.**

**SWAP-XS** (seed s uses the opposite-side memory of seed s+200):

> ΔC = **−0.890**, retaining **96.0%** of OWN.
> **The effect is carried by the memory content, not by any coupling from development and test sharing a seed.**

### SECONDARY mechanistic

```
arm        Δlatency   exposure S   exposure V   ACTIVE length S/V
OWN         -1.962       6.92         6.65        6.81 / 6.56
SHUFFLE     +0.275       6.82         6.70        6.72 / 6.60
SWAP-XS     -1.810       6.82         6.55        6.71 / 6.45
```
Memory stays event-triggered throughout (~6.6–6.9 / 80).

### The two definitions of the extensive margin **must not be mixed**

```
usable (m ≠ 0)                    Stable 64.2%   Volatile 73.2%
complete (entries on both sides)  Stable 65.75%  Volatile 73.25%
```
The difference is **6 Stable agents (1.5%) that do have entries on both sides, but whose two means happen to be exactly equal → m = 0**.
**Whichever one is reported must then be reported throughout; mixing them is not allowed.**

### How to read this

Natural Stable/Volatile developmental histories, passed through the **frozen λ=1 interface**,
produce a downstream difference of roughly **one fewer post-change error**;
that difference **survives re-pairing across seeds** (96%),
but is **destroyed once the marginals are preserved and only the action–outcome relation is shuffled** (−9.4%).

⚠ Every CI here is **descriptive**; there is no SESOI → **no functional-significance reading is made**.
⚠ This is a **rehearsal on development seeds**, not a confirmatory 029 result.
⛔ Neither λ nor any acquisition parameter may be changed on the basis of it.

### What is still missing before the preregistration can be written

```
① decide whether the developmental history should also carry a trait pathway (else SWAP stays an identity) — rule 93
② the SESOI (ΔC is measured in trials; OWN is currently ≈ 0.93)
③ fresh final seeds (80000–81499 is still clean)
④ MEMORY_TRANSFER029_PREREGISTRATION.md
```

### How to reproduce (new)

- `memory_transfer_rehearsal.py` → `memory_transfer_rehearsal_result.txt` / `_console.txt`
- `memory_lambda_calibration.py` has frozen the four gates + λ=1.00, switched the exposure gate to max,
  and added the assertion that "λ must equal the log centre of the admissible band"

---

## ★★ The last round of decisions before preregistration (2026-08-18) ★★

### ① The 029 primary does **not** add a trait pathway — rule 93 revised

> ### ~~Rule 93 (original, kept): for SWAP to be a non-trivial test, the developmental history must carry something besides memory~~
> **⚠ Revised.** The original statement is mathematically correct, but its **experimental-design inference is not** —
> deliberately adding a trait channel just to make one control "non-trivial" would turn the clean
> `history → relational memory → novel adaptation`
> back into `history → memory + traits → novel adaptation`,
> after which memory/trait competition, interaction and budget would all have to be handled again,
> i.e. the entire 027/028 apparatus. **There is no need for it.**

> ### ★ Rule 93 (final version) ★
> **When memory is the sole developmental pathway into the test task, DELETE
> and within-seed SWAP are algebraic integrity checks rather than independent
> causal evidence. A second developmental pathway should not be introduced
> merely to make these controls non-trivial; causal support should instead come
> from interventions on memory structure such as relational shuffling and
> cross-seed donor tests.**
>
> In plain terms: when memory is the only pathway by which development enters the test task, DELETE and same-seed
> SWAP are **algebraic integrity checks**, not independent causal evidence. **A second developmental pathway must not**
> **be added artificially just to make these controls "non-trivial"**; genuine causal support has to come from
> interventions on **the memory structure itself**, such as relational SHUFFLE and cross-seed donor tests.

**The goal of 029 is not to prove that "memory matters more than personality"**, but to show that real experience can produce
relational memory, and that this relational structure is enough to produce functional transfer on a structurally similar new problem.
So `NeutralBody` stays as it is and the architecture remains memory-only.

The naming is frozen along with it: `SWAP-XS` is **formally renamed `XSEED-DONOR`** —
it does not ask the same question as SWAP (SWAP asks "does the result follow the identity of the memory", an identity under this architecture;
XSEED-DONOR asks "does the effect rely on development and test sharing a seed", which is non-trivial).

### ② The extensive margin is formally defined as **complete**

```
primary extensive margin = P(relational memory complete)
                           complete := at least 1 stay entry and at least 1 switch entry
Stable 65.75%   Volatile 73.25%

also reported (reportable, but must not be called extensive / availability):
non-zero evidence rate     Stable 64.25%   Volatile 73.25%
```

> ### ★ Rule 94: m = 0 does not mean "no memory" ★
> Those 6 Stable agents (1.5%) **do have entries on both sides**; it is only that
> `mean(switch reward) == mean(stay reward)` → m = 0.
> **They formed a complete relational memory**; that experience simply tells them
> "**switching and staying made no difference in the past**" — which is **meaningful null evidence**.
> Defining memory availability as `m ≠ 0` would misclassify "formed a neutral experience"
> as "has no memory".
>
> So: completeness and the non-zero evidence rate **are two different quantities;
> whichever is reported must be reported throughout, and they must never be mixed**.
> Rule 91 is unchanged: **every primary transfer analysis still uses the whole predefined set of agents,
> including incomplete ones and those with m = 0.**

### ③ SESOI = **1.0 post-change error**

```
ΔC = C_Volatile − C_Stable      negative = the Volatile memory is better
SESOI: |ΔC| = 1.0 error   ⇔  one fewer mistake in 40 post-change trials  ⇔  2.5% accuracy
```

Rationale: it matches the **1-trial functional unit** of 027/028, instead of inventing a 0.5 / 0.75 threshold
ad hoc from the rehearsal's −0.927. And **the development result of −0.927 falls just below the threshold**,
so the threshold **cannot** retroactively dress the already-seen development result up as a "functional success" —
under this reading the development result counts only as *detectable / directionally strong, functional significance not established*.
**That is a point in favour of the preregistration's credibility.**

A three-band reading (following the 027/028 logic):

```
CI contains 0            No evidence of memory-mediated transfer
CI < 0 but not past −1   Detectable, but functional significance not established
CI entirely < −1         Functionally meaningful memory-mediated transfer established
CI entirely > 0          Clearly the opposite direction / harmful transfer
```
(The development rehearsal `[−1.202, −0.677]` falls in the second band.)

### ④ The confirmatory criterion for SHUFFLE — ⚠ one point needs a decision first

Rather than merely writing "SHUFFLE should get smaller", the **retention ratio** is frozen:

```
R = |ΔC_SHUFFLE| / |ΔC_OWN|
joint same-seed bootstrap, ★abs and division applied per replicate★ (lesson from 028)
⚠ rule 84: R is always ≥ 0, so "the CI excludes 0" is uninformative → the criterion reads the UPPER bound only
```

**Measured in the development rehearsal (n=400):**

```
R point estimate = 0.094      95% CI [0.005, 0.261]
```

> ### ⚠⚠ The two formulations read differently ⚠⚠
> ```
> (A) point estimate < 0.25   → satisfied (0.094)    the original wording: "the absolute point estimate is at most 25% of OWN"
> (B) CI upper bound < 0.25   → not satisfied (0.261)  more conservative
> ```
> **(B) is recommended**: only (B) really answers "does **at least 75%** of the transfer disappear
> once the relation is destroyed". FINAL's N=1500 is 3.75× the rehearsal, so the CI width shrinks to about 1/1.94,
> and 0.261 would very likely drop below 0.25 — but **that is a power inference, not a guarantee**, and (B) carries a real risk of failing.
> Adopting (A) would make this control almost impossible to fail, which would strip it of its point as a control.
>
> ⚠ **This must be recorded honestly**: the choice was made **after seeing the rehearsal's 0.094 / 0.261**,
> but frozen **before any number from the FINAL block was seen**. The results must say so explicitly.

Layered consequences: if the primary CI contains 0 → **R is neither computed nor interpreted** (a ratio is meaningless when the denominator is unidentifiable);
if the primary is detectable but R is not satisfied → no claim that the relational structure carries it; only
"a contribution from marginal statistics cannot be excluded" may be written. **The primary's success or failure does not change because of R.**

### ⑤ FINAL block frozen: `80000–81499, N=1500`

Verified: throughout the repository and this log, `80000` appears only in notes of the "untouched / do not touch / reserved" kind,
**no simulation path has ever used this block**. The engineering protection from 028 carries over:
once `final_029_STARTED.lock` exists, **the block is permanently burned even if the run crashes**;
the seed guard accepts only `seed0=80000, N=1500`; fingerprint + constants + sha256 are all checked.

---

## ★ The preregistration is written: `MEMORY_TRANSFER029_PREREGISTRATION.md` ★

Freeze status at a glance:

```
architecture      memory-only / NeutralBody              FROZEN
acquisition       36 + 8 + 22                            FROZEN
retrieval         stateful + post-Q resolution           FROZEN
λ                 1.00                                   FROZEN
capacity gates    5% / .02 / 25% / 20-of-80 (max)        FROZEN
primary           ΔC post-change errors                  FROZEN
SESOI             1.0 error                              FROZEN
extensive margin  P(memory complete) 65.75% / 73.25%     FROZEN
scientific control SHUFFLE (criterion §6.3 awaiting A/B) PENDING
seed-coupling     XSEED-DONOR                            FROZEN
integrity         DELETE / within-seed SWAP (not a result) FROZEN
FINAL             80000–81499, N=1500                    FROZEN
```

A new validity gate, **G2 interface capacity transport**:
on the FINAL block the four capacity readings are recomputed from the **group-blind (pooled, including m=0, sorted)**
empirical m, **before any outcome is read**; the fixed failure wording:

> Interface capacity calibrated on the development block did not transport to
> the confirmatory population; the memory channel is not cleanly interpretable
> under the preregistered capacity constraints.

⛔ A gate failure **does not permit re-estimating λ**.

### How to reproduce (new)

- `AI SANDBOX/MEMORY_TRANSFER029_PREREGISTRATION.md` — the 029 preregistration (a write-once file)
- `memory_transfer_rehearsal.py` updated: `XSEED-DONOR` renamed,
  the extensive-margin convention switched to completeness, and a joint bootstrap for the retention ratio added

---

## ★★ §6.3 decided as B + a full-size rehearsal of `final_029.py` (2026-08-18) ★★

### ① The SHUFFLE criterion is **B**: `CI_97.5%(R) < 0.25`

Requiring only the point estimate would state "**at least 75% of the transfer is destroyed**" **more strongly than the evidence allows**.
If the claim is that "most of the transfer disappears once the relational structure is destroyed",
**the uncertainty itself must support that sentence too**.

The honest way to write the development rehearsal (n=400) `R = 0.094, CI [0.005, 0.261]` is:

> **point estimate strongly supports collapse, but the rehearsal sample is
> insufficient to establish ≥75% attenuation with 95% confidence.**

It is **not** "it only just missed, so switch to A".

The disclosure that must accompany the results (already written into §6.3.1 of the preregistration and into the runner output):

> The §6.3 CI-upper interpretation was finalized after observing the development
> rehearsal retention estimate R=0.094, 95%CI[0.005,0.261], **but before any
> observation from the confirmatory seed block.**

> ### ★ Rule 95: a ratio criterion must state what to do when the denominator is unidentifiable ★
> If `ΔC_OWN ≈ 0`, the denominator of `R` approaches 0 → the ratio becomes unstable or explodes.
> **One cannot then say "the SHUFFLE control failed"** — there is no transfer for anything to be "retained" from.
>
> **The SHUFFLE retention criterion is interpreted only if the OWN primary
> effect shows evidence of transfer (its 95% CI excludes 0 in the preregistered
> direction). If OWN does not establish transfer, the retention ratio is
> reported descriptively but no relational-mediation claim is evaluated.**

### ② G2 is kept, and its failure semantics are frozen

> G2 failure does **not** mean "no memory transfer". It means the confirmatory
> contrast is **not cleanly interpretable under the preregistered
> calibrated-interface regime.**

The justification for λ=1 comes from promises made on the development block (event-triggered, genuinely influential, unsaturated, not taking
over the policy). If the natural m distribution drifts on FINAL then, even with λ unchanged, **what is being measured is no longer the
interface property that was calibrated**. Same logic as 028's transport gate: **after a failure λ may not be re-estimated**.

### ③ Two implementation details are frozen in the preregistration

```
XSEED donor mapping   donor_index(i) = (i + N//2) % N
                      FINAL N=1500 → (i+750)%1500; rehearsal N=400 → (i+200)%400
                      no self-donor / one-to-one / both conditions share the same permutation /
                      ⛔ donors may not be chosen on the basis of any memory or outcome
SHUFFLE permutation   rng = Random(SHUFFLE_SALT ^ seed ^ (len(episodes)<<8))
                      SHUFFLE_SALT = 0x29C10; ⛔ no new scheme may be generated at run time
```

---

## ★ `final_029.py` — the full-size rehearsal passes completely (seeds 10000–11499, N=1500) ★

**Not one seed of 80000–81499 was touched and no FINAL lock was created** (verified: in the repository `80000` appears only in
"do not touch / reserved" notes and in the runner's `FINAL_SEED0` constant).

### Preflight (all passed)

Task fingerprint + the sha256 of five modules + 15 frozen constants + the donor mapping + the **preregistration sha256**
`29e45930a07f2649…`. Any mismatch raises `SystemExit` with the message "an AMENDMENT must be written and the constants
re-frozen first; you may not simply edit a constant and start the run".

### Self-checks (all passed)

```
lock helper        atomic exclusive O_CREAT|O_EXCL; a second creation is rejected
worker determinism acquisition and transfer reproduce trial by trial
XSEED mapping      no self-donor and one-to-one at both N=400 and N=1500
SHUFFLE            the permutation is fixed by (seed, n_episodes); stay/switch counts and outcome marginals unchanged
analysis ordering  1→2→3→4→5→6→7→8→9 verified by assertion
```

★ **The STARTED lock is created before the very first acquisition trajectory** — a 029 seed starts producing
information from the acquisition stage onwards, not only once the novel task begins. The lock is never deleted automatically.

### Rehearsal results (an already-burned block, N=1500)

```
completeness      Stable 70.07%   Volatile 76.40%
non-zero evidence Stable 67.93%   Volatile 75.87%

G2   saturation 0.0000 ✓   median|Δp| 0.0742 ✓   flip 0.1443 ✓   max expo 6.50/80 ✓
G1 ✓   G3 ✓   → validity fully passed

arm             ΔC          95% CI
OWN          -0.8187   [-0.9387, -0.6993]
DELETE       +0.0000   [+0.0000, +0.0000]     ← identity
SWAP         +0.8187   [+0.6993, +0.9393]     ← identity
SHUFFLE      +0.0200   [-0.0520, +0.0933]
XSEED-DONOR  -0.9180   [-1.0527, -0.7880]     retains 112.1% of OWN

SESOI reading  →  Detectable memory-mediated transfer, but functional
                  significance not established. (second band)

retention  R = 0.0244   95% CI [0.0016, 0.1132]   upper bound < 0.25  →  ★satisfied★
```

### ⚠ Three things to know before take-off

**(a) Criterion B really is satisfiable at N=1500.**
The power-scaling check predicted `[0.014, 0.182]`; the full-size rehearsal measured `[0.0016, 0.1132]`,
leaving the upper bound comfortably below 0.25. **B is not a gate doomed to fail.**

**(b) ★ ΔC lies below the SESOI on both independent blocks ★**

```
development block 0–399 (N=400)       ΔC = -0.927   CI [-1.202, -0.677]
rehearsal block 10000–11499 (N=1500)  ΔC = -0.819   CI [-0.939, -0.699]
SESOI = 1.0
```

> **Both blocks land between −0.8 and −0.9, and the N=1500 CI is already narrow.
> So the most likely FINAL outcome is the second band (detectable, functional significance not established).**
> This is **not** a reason to change anything — quite the opposite: it shows SESOI=1.0 was not set to fit a result.
> But it must be known before take-off: **the "functionally meaningful" band is unlikely to be reached.**

**(c) The extensive margin varies between blocks.** §14 of the preregistration predicted, from the development block,
"Stable ≈ 66% / Volatile ≈ 73%"; the rehearsal block measured 70.07% / 76.40% (about +4pp).
**The preregistration is not changed** (it is frozen), but the reading must allow for ±4pp of between-block variation in this quantity.
The XSEED retention share tells the same story: 96.0% on the development block, 112.1% on the rehearsal block, both consistent with "no seed coupling".

### How to reproduce (new)

- `final_029.py` (`--rehearse` / `--final`)
  → `final_029_rehearsal_result.txt`, `final_029_rehearsal_console.txt`
- preregistration sha256 `29e45930a07f2649c7958fdc0cd20a389005ca43e93287b9f69e2ccdcf867145`

---

## ★ Two final execution-integrity hardenings before take-off (2026-08-18) ★

**Not a scientific change**: no hypothesis / endpoint / SESOI / λ / seed / SHUFFLE criterion /
treatment was modified.

### ① The freeze list was missing a runtime dependency

`final_029.py` calls `REH.BODY` and `REH.shuffled()` directly,
but `memory_transfer_rehearsal.py` was **not in `FROZEN_MODULES`** —
so an accidental edit to it would still leave preflight all green. Now added:

```
"memory_transfer_rehearsal.py": "b29b2d417fdaed52"
```

**Does this need an amendment: no.** §12.5 of the preregistration says verbatim "the sha256 of each module"
and **does not enumerate a module count**, so adding the hash of an existing runtime dependency is not a deviation from it.
(Had the text frozen "five modules", an implementation amendment would have been required.)

> ### ★ Rule 96: a freeze list must cover **every runtime dependency**, not "the main ones" ★
> Missing one imported module leaves a back door in preflight:
> it comes back all green while the code actually running has already changed.
> The way to check is to read the runner's imports and attribute accesses, not to list files from memory.

### ② The G2 fail path let two contradictory sentences appear together

Before the change: a G2 failure correctly printed *calibrated-interface validity compromised*,
but then **still proceeded to the SESOI reading**, potentially also printing, in the same FINAL,
*Functionally meaningful memory-mediated transfer established.*

Now locked behind a single master switch:

```
primary_interpretable = g1_ok and g2_ok and g3_ok

not primary_interpretable →
    verdict = "DESCRIPTIVE ONLY — confirmatory interpretation disabled
               because a preregistered validity gate failed."
    own_transfer = False        → SHUFFLE therefore becomes descriptive only
```

**On a gate failure every raw outcome is still written to disk** — the FINAL block is already burned
and the data must be preserved transparently; but it is **not permitted** to produce any of primary success /
functional success / SHUFFLE mediation.

⚠ G1/G3 failures were also moved from `SystemExit` onto **the same path** (voided but still written to disk),
for the same reason: once a block is burned there should at least be a record. The meaning of "the whole batch is void" is unchanged —
void means **no confirmatory claim may be made**, not that the data is deleted.

> ### ★ Rule 97: a validity-gate failure must **disable the reading**, not merely **append a warning** ★
> Printing "validity compromised" while letting the three-band reading print as usual
> leaves two contradictory sentences in one set of results, which will certainly be quoted out of context later.
> The right approach is a master switch that makes a success reading **physically impossible to generate**.

### ★ The fail path was actually exercised, not merely read off the code ★

Setting `SATURATION_MAX` temporarily to an unsatisfiable value and running on already-burned seeds 0–59:

```
G2 judged as failed            ✓
confirmatory disabled          ✓
verdict = DESCRIPTIVE ONLY     ✓
SHUFFLE descriptive only       ✓
"Functionally meaningful" absent             ✓
"Detectable memory-mediated transfer" absent ✓
"≥75% attenuation established" absent        ✓
raw outcome still written      ✓
analysis order intact          ✓
```

### ★ Final rehearsal: all five requirements pass ★

`python final_029.py --rehearse` (10000–11499, N=1500)

```
① all preflight checks still ✓                ✓
② now reports ★6★ frozen modules              ✓
③ every number for 10000–11499 bitwise unchanged  ✓ (the diff adds only the
   "confirmatory interpretation: enabled" line and two assertion lines; no number differs)
④ analysis order unchanged
   1-acquisition→2-G2→3-validity→4-primary→5-sesoi→6-shuffle→7-xseed
   →8-integrity→9-secondary                   ✓
⑤ 80000–81499 still untouched                ✓
   final_029_STARTED.lock does not exist      ✓
```

**Status: cleared for take-off. On the word "go", run `python final_029.py --final`.**

⚠ Known, and not a reason to hold: ΔC = −0.927 on the development block and −0.819 on the rehearsal block,
**both below SESOI=1.0** → FINAL will most likely land in the second band.
**Precisely because this is known, SESOI / λ / acquisition / task must not be touched again.**
The most valuable result of 029 may well be exactly this:

> relational memory really can transfer to a surface-unfamiliar but structurally similar new problem and causally
> reduce errors; but **whether that benefit reaches the preregistered practical functional threshold**
> is adjudicated independently by a brand-new FINAL block.

---

# ★★★ Experiment 029 — Memory-Mediated Transfer · FINAL ★★★

**2026-08-18 · seeds `80000–81499` (N=1500) · this block is permanently burned**

Preregistration: `MEMORY_TRANSFER029_PREREGISTRATION.md`, sha256 `29e45930a07f2649…`
(verified by the runner). `final_029.py` sha prefix `fb6a0cb672e33101`,
all 6 frozen-module hashes pass, task fingerprint `26778f672e9e7009`.
`final_029_STARTED.lock` was created **before the first acquisition trajectory**. Runtime 16.8 s.

## Results (copied item by item from `final_029_result.txt`, not from memory)

### 1. Acquisition / completeness

```
memory completeness (primary extensive margin)   Stable 65.40%   Volatile 74.80%
non-zero evidence rate                          Stable 64.13%   Volatile 74.53%
★ every primary analysis uses all 1500 × 2 predefined agents, including incomplete ones and m=0 ★
```

### 2–3. Validity gates — ★ all passed; confirmatory interpretation enabled ★

```
G2  saturation 0.0000 ✓   median|Δp| 0.0737 ✓   flip 0.1476 ✓   max expo 6.36/80 ✓
    (pooled m: n=3000, m=0 for 30.7%; eligible states 9324; the label is discarded at the input)
G1  bitwise identical before the anomaly ✓, reward opportunity bitwise equal ✓
G3  integrity assertions ✓
```

### 4. ★ PRIMARY ★

```
arm             ΔC          95% CI
OWN          -0.8833   [-1.0160, -0.7533]
DELETE       +0.0000   [+0.0000, +0.0000]     ← identity
SWAP         +0.8833   [+0.7540, +1.0160]     ← identity
SHUFFLE      +0.0093   [-0.0733, +0.0913]
XSEED-DONOR  -0.9240   [-1.0533, -0.7960]     retains 104.6% of OWN
```

### 5. ★★ The three-band SESOI reading ★★

```
95% CI [-1.0160, -0.7533]        SESOI = 1.0 post-change error
```

> ### ★ Detectable memory-mediated transfer, but functional significance not established. ★

⚠ **The CI's lower bound −1.0160 does cross −1, but the upper bound −0.7533 does not** —
the preregistered third band requires the **entire CI below −1**, so this reads as the second band. It is **not permitted**
to call it "close to functionally significant" merely because the lower bound crossed.

### 6. ★ SHUFFLE conditional retention ratio ★

```
R = |ΔC_SHUFFLE| / |ΔC_OWN| = 0.0106      95% CI [0.0015, 0.1102]
criterion (§6.3 B): CI upper bound < 0.25   →   ★satisfied★
```

> **≥75% attenuation established: the transfer is carried by the relational structure.**

The precondition for the conditional reading is met (OWN's CI lies entirely < 0, §6.3.2).

The disclosure that must accompany the results:

> The CI-upper interpretation in §6.3 was finalized after observing the
> development rehearsal retention estimate R = 0.094, 95% CI [0.005, 0.261],
> **but before any observation from the confirmatory seed block.**

### 7–9

```
XSEED-DONOR   ΔC = -0.9240, retains 104.6% of OWN → the effect does not rely on a shared development/test seed
integrity     DELETE 1500/1500 ≡ 0 ✓    SWAP 1500/1500 ≡ −OWN ✓ (algebraic identities, not evidence)
secondary     Δlatency OWN -1.5733 / SHUFFLE +0.0527 / XSEED -1.8433
              exposure 6.2–6.3 / 80 throughout → memory stays event-triggered
```

## ★ A-priori predictions vs actuals (transcribed against §14 of the preregistration) ★

```
item                   predicted                     actual                 
ΔC direction           < 0 (directional prediction)  −0.8833                ✓
does ΔC cross the SESOIunknown (the only real unknown)no, second band        —
G1 / G3                must pass                     passed                 ✓
G2 capacity transport  expected to pass              passed w/ margin (4/4) ✓
SHUFFLE R point est.   ≈ 0.1                         0.0106                 ✓ (smaller)
SHUFFLE CI upper <0.25 not predicted                 0.1102, satisfied      —
XSEED-DONOR            retains ≥ 80%                 104.6%                 ✓
memory completeness    ≈ 66% / 73%                   65.40% / 74.80%        ✓
```

**The one genuinely unknown item lands in the second band — consistent with the trend across all three blocks.**

```
development block 0–399 (N=400)       ΔC = -0.927   CI [-1.202, -0.677]
rehearsal block 10000–11499 (N=1500)  ΔC = -0.819   CI [-0.939, -0.699]
★FINAL block 80000–81499 (N=1500)     ΔC = -0.883   CI [-1.016, -0.753]★
```

Three independent blocks give **−0.82 to −0.93**, in close agreement. **"Most likely the second band" was written
down publicly before take-off, and that is exactly what happened. This is not post-hoc rationalisation.**

## ⚠⚠ Protocol deviation: it must be recorded truthfully ⚠⚠

> ### ★ Rule 98: a check the preregistration assigns to a stage must be performed at that stage ★
> §10 of the preregistration requires re-running with 8 different analysis seeds **during the rehearsal stage**,
> and switching to a widened three-valued reading **before FINAL is run** if the reading turns out to depend on the analysis seed.
>
> **This step was not done at the rehearsal stage.** It was done retrospectively, after FINAL had already run.
> A retrospective check **must not** be presented as having gone to plan — it is recorded honestly as a **protocol deviation**.

The retrospective results (**descriptive**, changing no reading; the same analysis-level MC stability as in 027, rule 80):

```
    seed     CI_lo     CI_hi   reading                   R upper   <0.25
   8181★   -1.0160   -0.7533   band 2 detect./func n.e.   0.1102   ✓
       1   -1.0160   -0.7547   band 2                     0.1083   ✓
       2   -1.0167   -0.7573   band 2                     0.1115   ✓
       3   -1.0147   -0.7547   band 2                     0.1102   ✓
       4   -1.0160   -0.7560   band 2                     0.1086   ✓
       5   -1.0180   -0.7560   band 2                     0.1111   ✓
       6   -1.0147   -0.7560   band 2                     0.1107   ✓
       7   -1.0133   -0.7547   band 2                     0.1090   ✓

8/8 readings agree; 8/8 R criteria agree
MC SD of CI_hi = 0.00115
distance to the 0 boundary 0.7533 = 655 × MC SD; distance to the −1 boundary 0.2467 = 214 × MC SD
```

**The reading sits far from both bright lines (well beyond the 10 × MC SD the preregistration asks for),
so this deviation created no substantive risk — but the next experiment must follow the stages as written.**

## What 029 may and may not claim

| | |
|---|---|
| ✅ | **Relational memory** grown naturally out of real developmental experience, passing through an **independently calibrated (group-blind) interface**, **causally reduced errors** on a surface-unfamiliar but structurally similar new problem (ΔC = −0.88, CI [−1.02, −0.75]) |
| ✅ | The effect is **carried by the relational structure**: with episode counts, stay/switch counts and outcome marginals all preserved and only the action↔outcome relation shuffled, **≥75% of the transfer disappears** (R = 0.011, CI upper bound 0.110 < 0.25) |
| ✅ | The effect **does not rely on development and test sharing a seed** (XSEED-DONOR retains 104.6%) |
| ✅ | **Functional significance is not established** — the preregistered 1-error threshold was not reached |
| ⛔ | ~~functionally meaningful transfer~~ — the third band requires the whole CI < −1, which was not reached |
| ⛔ | ~~analogical reasoning~~ / the agent "understood the structure" or "understood the causality" |
| ⛔ | ~~generalized individuality~~ |
| ⛔ | Presenting DELETE / within-seed SWAP as causal evidence (rule 93: under a memory-only architecture they are algebraic identities) |
| ⛔ | Calling `m ≠ 0` memory availability (rule 94: completeness and the non-zero evidence rate are two different quantities) |
| ⛔ | Reporting only the complete-only separation (rule 91) |

## ★ What 025 + 027 + 028 + 029 show together ★

```
025/v3  can the past persist at all                            clearly
027     does the personality left behind transfer by itself    very weak (0.08 trial), did not replicate
028     widening the personality readout at equal budget       no gain (G ≈ 0)
★029★   can relational memory from real experience transfer    ★yes: −0.88 error, carried by structure★
                                                               but below the 1-error functional threshold
```

> ### ★ The core proposition (final form) ★
> **Persistent individuality ≠ automatically functional generalization — but
> relational memory is a different matter.**
>
> 027/028 showed: compressing a developmental history into a personality readout and feeding it into a new task
> carries almost no replicable functional transfer.
> **029 shows: when a developmental history is stored as relational experience and retrieved on meeting
> a structurally similar situation, it really can causally reduce errors on a new problem** —
> the effect is stable (−0.82 to −0.93 across three blocks), attributable to the relational structure (SHUFFLE destroys ≥75%),
> and independent of seed coupling (XSEED 104.6%).
>
> **But it did not cross the functional threshold we set in advance.**
> The transfer is **real, mechanistically clear, and smaller than a single post-change error**.

## How to reproduce (new)

- `final_029.py --final` → `final_029_result.txt`, `final_029_console.txt`,
  `final_029_STARTED.lock`
- Seed ledger update: `80000–81499` = **029 FINAL (burned)**
