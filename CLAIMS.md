# Paper-claim audit — evidence marked beside every core conclusion

Rule: **every claim must fall into one of three categories**, and anything that fits none of
them may not be written.

| Category | Bar |
|---|---|
| **A main result** | direct experimental support obtained **after** v3 was frozen (preregistered where possible) |
| **B mechanism result** | supported by a **targeted ablation / deletion** experiment |
| **C limitation / open question** | **no evidence at present**; explicitly **not claimed** |

---

## A · Main results

### A1 A different past → a persistent behavioural difference that survives transplant into an identical environment
- `final_confirm_result.txt` **H1 = 1.142 [1.098, 1.183]**,
  seeds 50000–51499, **preregistered, run once**, dz = 0.20, p = 0.0001
- v3 parameter robustness: **78.3% > 1** across 500 random parameter sets, median 1.076
- ✅ May be the headline. **The metric must be stated as "the TV ratio of the per-hour action distribution".**

### A2 The difference is not a mortality artifact
- After the v3 correction, 60-day mortality went 8.1% → **4.3%**, while the effect **grew rather than shrank**
  (P1 1.058 → 1.090, 023 §7)
- Single-world mortality in the final stage: 0.0% / 3.9%
- ✅ May be written. This is what the whole 023 revalidation was worth.

### A3 There is a persistence channel that does not depend on the trait-floor ratchet
- `final_confirm` **P1 = 1.134 [1.090, 1.175]** (all floors off, 022 on)
- ✅ May be written.

### A4 Discrete memory structures wired into behaviour are not the long-term carrier
- `final_confirm` **P2 fails**: 1.134 → 1.102, a drop of 0.032 < 0.05 with overlapping CIs
- **All three independent runs fail** (v2 / v3 / final)
- ✅ May be written, and it is a **preregistered** conclusion rather than a post-hoc explanation.

### A5 Deleting episodic memory (`memories`) at the transplant point is a **bit-identical** no-op
- Across the v2 / v3 / final runs, the fingerprints with and without deleting `memories` are **exactly equal**
- ✅ May be written, and the wording may be strong ("bit-identical").

---

## B · Mechanism results

### B1 The `TRAIT_DRIFT` positive feedback is the causal driver of persistence
- **Targeted ablation**: drift 0 → 2.4 takes the transplant ratio **1.021 → 1.575** (near-monotone)
- **Independent corroboration**: it is the most sensitive knob across 500 randomised parameter sets,
  Spearman **ρ = +0.442** (+0.432 on v2)
- ✅ May be written. **Two independent methods point at the same mechanism**, which makes the sentence solid.

### B2 The floor architecture carries most of the persistence
- Full 1.142 → all floors off 1.046 (final); 021§3 points the same way
- ✅ May be written.

### B3 What matters is "that a floor existed", not "which snapshot the floor is anchored to"
- Experiment 024 anchor-content transplant: changing the anchor content explains only **1.3%** of the effect
- **Negative control**: with all floors off, the six branches are **bit-identical** (confirming the anchor has one channel only)
- ✅ May be written. ⚠ The **scope limitation** must be written alongside: the intervention point is day 30,
  and the floor raised by the natural anchor during development is **not dismantled**.

### B4 The v3 condition correction has to cross a "sloth valley"
- `death_split`: the rich world goes 24.3% →(T=55) **36.3%** →(T=60) 18.0% →(T=65) 2.0%
- Mechanism: condition↑ → survival urgency↓ → well-fed agents forage less → hunger rises again
- ✅ May be written. It gives "why the threshold is 65" a mechanistic explanation rather than "it swept best".

---

## C · Limitations / open questions (**explicitly not claimed**)

### C1 Whether the residual effect with all floors off exceeds 1 — **undecidable**
- final R52: **1.046 [1.00208, 1.08609]**; the CI lower bound clears 1.00 by two parts in ten thousand
- Judged, under **preregistration amendment A** (fixed before the run), as "**on the detection boundary; this criterion cannot decide**"
- The point estimates agree across three seed blocks (1.036 / 1.057 / 1.046): the direction is stable but the magnitude is tiny
- ⛔ **Neither "a residual effect exists" nor "it does not exist" may be written.** Write "undecidable".
- ⛔ In particular it must not be re-judged because the boundary diagnostic gave 8/8 > 1 — the threshold was fixed **before the data were seen**.

### C2 The goal axis — **no claim made**
- Across the v3 parameter set: **48.7% > 1, median 0.998** (v2 gave 72.2% / 1.061)
- Mechanism: v3 keeps condition permanently high → the `recover` goal rarely fires →
  **a substantial part of the goal-layer difference in v2 was riding on the condition difference**
- ⛔ **Must not be a main claim.** If mentioned at all, only as a discussion of "the price of fixing a confound".

### C3 Novel-context generalization — **not demonstrated**
- ⛔ **Must not be written** as "generalization failed" / "v3 cannot generalize"
- ✅ **The only admissible wording**:
  > **The current v3 architecture cannot provide a clean native novel-contingency test interface.**
  > Four structurally different probes all failed at the group-blind feasibility calibration stage
  > (survival split ×2, the multiplicative bonus coming to nothing, intervention saturating at 75–85%),
  > **and every one of them was stopped before the final seed block was used.** `60000–61499` was never used.
- This is a limitation **at the level of experimental design**, not a negative conclusion about the agent's
  capability — **we never managed to ask the question at all.**

### C4 ~~Positive feedback simultaneously reduces plasticity~~ — **deleted**
- ⛔ **Deleted in full.** It was once written as "two sides of the same mechanism", which reads far too much like a highlight.
- **Falsified by targeted ablation**: as drift goes 0 → 2.4, decisions flippable at Δ=3 go **41.1% → 38.0% → 44.2%**
  (non-monotone, a range of ~3pp); the degree of polarisation in `material` is **independent of drift**
  (already 93.8% at drift=0).
- The correct statement (which may be written): **the resource bimodality encountered in 026 comes mainly from
  the v3 resource dynamics themselves** (material is consumed only by build, at 3 per use, and shelter decays
  monotonically at 0.35/tick), and is **essentially unrelated to the trait positive feedback that produces persistence**.

### C5 The model's intended purpose
- ⛔ No claim of simulating real personality formation
- ✅ Write: a minimal apparatus for testing "whether experience can produce a behavioural difference that survives transplant"

### C6 Architectural scope
- v3 has **no online causal learning** — the agent cannot discover a new contingency by trial and error
- Any wording of the form "the agent learned / understood / became aware of" is ⛔ **forbidden outright**
- ✅ Write: "enters a new dynamic carrying its existing policy"

---

## Forbidden wordings (quick reference)

| ⛔ Must not write | ✅ Write instead |
|---|---|
| positive feedback also destroyed plasticity | (deleted; the resource bimodality is unrelated to the positive feedback) |
| generalization failed / cannot generalize | the v3 architecture cannot provide a clean novel-contingency test interface |
| the goal layer also shows a persistent difference | (no claim made; 48.7% across the parameter set) |
| a residual effect remains with all floors off | on the detection boundary; the preregistered criterion cannot decide |
| the agent learned / understood / became aware | the agent enters a new dynamic carrying its existing policy |
| knowledge is a continuous channel | knowledge strength is nearly binary (0 or 0.98) |
| the model simulates personality formation | a minimal apparatus testing experience → post-transplant difference |

---

## Cross-check table for the numbers

| Number | Source file | Model |
|---|---|---|
| 1.142 / 1.134 / 1.102 / 1.046 | `final_confirm_result.txt` | v3_frozen |
| 78.3% / 1.076 / ρ=+0.442 | `sweep_results_v3.csv` | v3_frozen |
| 1.021 → 1.575 | output of `rule71_ablation` | v3_frozen |
| 24.3% → 36.3% → 2.0% | experiment 3h `death_split` | the basis for fixing v3 |
| 1.3% (anchor content) | experiment 024 `anchor_probe` | v3_frozen |
| 80.2% / 72.2% (v2 robustness) | `sweep_results.csv` | **v2 — must not be used as evidence about v3** |
