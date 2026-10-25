"""Round 6 of 2026-10-25: which part of the plan holds back the expression of reading interest?
Diagnostics only (NOT a rule version, no weight, target, satiation or priority changed; default stays
v5). Development seeds 3001-3010 + 6001-6010 (already looked at): nothing here is a validation.

    python -m pet.diag_plan [out_dir]            # default docs/pet_plan_components

The core plan bonus on 'read' (sim.Agent.goal_bonus) has two separate parts:
  learn bonus   while the plan is 'learn' (the only plan with a 'read' weight): + 1.4 * 32 * pri * damp
  off-task      while any other plan is open: - 14 * pri * damp ('read' is discretionary)
Four conditions, ONLY those parts on 'read' changed (every other action and rule as it is):
  current       the mechanism as it is
  no_offtask    PetAgent.goal_read_offtask_off      (other plans no longer damp reading)
  no_learn      PetAgent.goal_read_learn_bonus_off  (a 'learn' plan no longer boosts reading)
  both          both off; must reproduce round 5's goal_read_bonus_off exactly (checked per run)
Lives: the matched pairs of validate_interest (candidate 'interest', clear 0.9 / hard 0.3 growth, then
60 common days with the standard book, 'keep'), from the same common day-0 state in every condition.
Continuations: the actual one (rep 0, = the round-4 lives under 'current', checked) + REPS reseeded ones
(rng.seed(seed * 1000 + rep), the same for both pets and in all four conditions).

FIXED 2026-10-25 BEFORE ANY RUN OF THIS MODULE (sha256 in docs/pet_plan_components/).
Unit = birth seed. Per seed, every metric is first averaged over its 1 + REPS continuations (they are
not independent samples); contrasts are paired within seed; CI = bootstrap 95 % over the 20 seeds.
  Primary metric  M = state part of the clear - hard read gap over the 60 common days (the share each pet
                  would read at that hour with the reading term removed; round 5: the compensation).
  Contrasts       D_X = M(X) - M(current), X in {no_offtask, no_learn, both};
                  interaction = D_both - D_no_offtask - D_no_learn.
  R0 replicated   D_both > 0 with CI lower > 0 (round 5's removal of the compensation). Otherwise the
                  round reports 'not replicated' and draws no component conclusion.
  R1 explains     component X explains the compensation if D_X CI lower > 0 AND mean D_X >= 0.5 mean D_both.
  R2 joint only   neither component meets R1 while R0 holds.
  R3 both         both components meet R1 (shares D_X / D_both reported).
  R4 additivity   the interaction CI excluding 0 = non-additive (reported, no verdict on its own).
  Ambiguous       a component with mean D_X >= 0.5 mean D_both but CI lower <= 0, or with CI lower > 0 but
                  mean < 0.5 mean D_both, is 'partial / not conclusive' and is reported as such.
Secondary, descriptive (same pairing): read gap and level over 60 days and days 30-60; reading hours
inside / outside a 'learn' plan; 'learn' plans done; days in a 'learn' plan; days under 'learn' satiation
and reading hours on those days outside a 'learn' plan; the instant part of the gap; home safety (v4
standard on whole lives and on phases >= 10 days, unique trajectories, union over runs, minimum home).
No condition is adopted in this round, whatever its reading difference: a larger gap is not a reason.
"""
import copy
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

from . import diag_interest as DI
from . import lifestats as L
from . import recheck_read_phases as RP
from . import validate_interest as VI

DEV_SEEDS = VI.DEV_SEEDS
ARM = 'interest'
REPS = 5
CONDITIONS = {'current': {}, 'no_offtask': {'goal_read_offtask_off': True},
              'no_learn': {'goal_read_learn_bonus_off': True},
              'both': {'goal_read_offtask_off': True, 'goal_read_learn_bonus_off': True}}
RULE = {'R0': 'D_both > 0, CI lower > 0', 'R1': 'D_X CI lower > 0 and mean D_X >= 0.5 mean D_both',
        'R2': 'R0 and no component meets R1', 'R3': 'both components meet R1',
        'R4': 'interaction CI excludes 0 -> non-additive', 'metric': 'state part of clear-hard gap, 60 common days'}
LATE = (VI.COMMON - VI.SPLIT) * 24


def pet_metrics(c, rows, days):
    a = c.agent
    share = lambda rs: sum(r['chosen'] == 'read' for r in rs) / len(rs)
    day_of = lambda r: r['tick'] // 24 - VI.GROW
    in_learn = lambda r: r['goal_type'] == 'learn'
    sat_day = [days[d]['learn_sat'] > 0 for d in range(VI.COMMON)]
    reads = [r for r in rows if r['chosen'] == 'read']
    start = VI.GROW
    done = [g for g in a.goal_history if g['type'] == 'learn' and g.get('outcome') == 'done' and g['closed_day'] >= start]
    d_all, d_late = DI.decompose(rows), DI.decompose(rows[-LATE:])
    common = c.trace[-VI.COMMON * 24:]
    return {'read_all': d_all['real'], 'read_late': d_late['real'], 'state_all': d_all['state'], 'state_late': d_late['state'],
            'instant_all': d_all['instant'], 'instant_late': d_late['instant'],
            'read_in_learn': sum(in_learn(r) for r in reads), 'read_out_learn': sum(not in_learn(r) for r in reads),
            'read_in_learn_late': sum(1 for r in rows[-LATE:] if r['chosen'] == 'read' and in_learn(r)),
            'read_out_learn_late': sum(1 for r in rows[-LATE:] if r['chosen'] == 'read' and not in_learn(r)),
            'learn_done': len(done), 'learn_days': sum(d['goal'] == 'learn' for d in days[:VI.COMMON]),
            'sat_days': sum(sat_day), 'mean_learn_sat': sum(d['learn_sat'] for d in days[:VI.COMMON]) / VI.COMMON,
            'read_on_sat_days_out_learn': sum(1 for r in reads if sat_day[day_of(r)] and not in_learn(r)),
            'min_home_common': min(x[3] for x in common), 'below20_common': sum(x[3] < 20 for x in common) / len(common)}


def run(pets0, seed, cond, rep, flags=None):
    out = {}
    for n, p in pets0.items():
        c = copy.deepcopy(p)
        for k, v in (CONDITIONS[cond] if flags is None else flags).items():
            setattr(c.agent, k, v)
        c.agent.read_audit = True
        if rep:
            c.agent.rng.seed(seed * 1000 + rep)
        rows, days = [], [DI.day_state(c.agent)]
        DI.live(c, VI.COMMON, rows, days)
        rec = L.life_record(c, life_id=f'{ARM}|plan|{seed}|{cond}|rep{rep}|{n}', arm=cond, design='plan', seed=seed, rep=rep, book=n)
        out[n] = {'m': pet_metrics(c, rows, days), 'life': rec, 'fingerprint': rec['fingerprint']}
    return out


def seed_job(seed):
    pets0 = {n: VI.book_pet(seed, ARM, cl) for n, cl in (('clear', VI.CLEAR), ('hard', VI.HARD))}
    for p in pets0.values():
        p.phase('common')
    _, flives = VI.matched(seed, ARM)
    frozen = {m['book']: m['fingerprint'] for m in flives if m['branch'] == 'keep'}
    res = {'seed': seed, 'runs': {}, 'checks': {}}
    for cond in CONDITIONS:
        res['runs'][cond] = [run(pets0, seed, cond, rep) for rep in range(REPS + 1)]
    res['checks']['current_rep0_is_round4'] = all(res['runs']['current'][0][n]['fingerprint'] == frozen[n] for n in frozen)
    res['checks']['both_is_goal_read_bonus_off'] = all(
        run(pets0, seed, 'both', rep, {'goal_read_bonus_off': True})[n]['fingerprint'] == res['runs']['both'][rep][n]['fingerprint']
        for rep in (0, 1) for n in pets0)
    return res


def per_seed(job, cond):
    """Mean over continuations: clear - hard gaps and the two pets' mean levels."""
    R = job['runs'][cond]
    keys = R[0]['clear']['m'].keys()
    mean = lambda xs: sum(xs) / len(xs)
    return {**{f'gap_{k}': mean([r['clear']['m'][k] - r['hard']['m'][k] for r in R]) for k in keys},
            **{f'level_{k}': mean([(r['clear']['m'][k] + r['hard']['m'][k]) / 2 for r in R]) for k in keys}}


def summarise(jobs):
    jobs = sorted(jobs, key=lambda j: j['seed'])
    P = {c: [per_seed(j, c) for j in jobs] for c in CONDITIONS}
    keys = P['current'][0].keys()
    out = {'checks': {k: all(j['checks'][k] for j in jobs) for k in jobs[0]['checks']},
           'by_condition': {c: {k: L.describe([x[k] for x in P[c]]) for k in keys} for c in CONDITIONS},
           'paired_vs_current': {c: {k: L.describe([x[k] - y[k] for x, y in zip(P[c], P['current'])]) for k in keys}
                                 for c in CONDITIONS if c != 'current'},
           'interaction': {k: L.describe([b[k] - o[k] - l[k] + cu[k] for b, o, l, cu in
                                          zip(P['both'], P['no_offtask'], P['no_learn'], P['current'])]) for k in keys}}
    out['safety'] = {c: {k: v for k, v in RP.safety_union([r[n]['life'] for j in jobs for r in j['runs'][c] for n in ('clear', 'hard')]).items()
                         if k != 'checks_lost_by_first_run_dedupe'} for c in CONDITIONS}
    for c in CONDITIONS:
        out['safety'][c]['min_home_common_any'] = min(r[n]['m']['min_home_common'] for j in jobs for r in j['runs'][c] for n in ('clear', 'hard'))
    return out


def verdict(S):
    D = S['paired_vs_current']
    m = 'gap_state_all'
    lo = lambda d: d['ci95'][0]
    db = D['both'][m]
    v = {'R0_replicated': db['mean'] > 0 and lo(db) > 0}
    comp = {}
    for x in ('no_offtask', 'no_learn'):
        d = D[x][m]
        big, sure = d['mean'] >= 0.5 * db['mean'], lo(d) > 0
        comp[x] = ('not evaluated (R0 failed)' if not v['R0_replicated'] else
                   'explains' if big and sure else 'partial / not conclusive' if big or sure else 'no')
    v['components'] = comp
    if not v['R0_replicated']:
        v['conclusion'] = 'not replicated: no component conclusion'
    else:
        ex = [x for x, c in comp.items() if c == 'explains']
        v['conclusion'] = ('both components (R3)' if len(ex) == 2 else f'{ex[0]} (R1)' if ex else 'joint only (R2)')
    it = S['interaction'][m]
    v['R4_non_additive'] = it['ci95'][0] > 0 or it['ci95'][1] < 0
    v['shares_of_D_both'] = {x: D[x][m]['mean'] / db['mean'] if db['mean'] else None for x in ('no_offtask', 'no_learn')}
    return v


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_plan_components'
    dst.mkdir(parents=True, exist_ok=True)
    with Pool(14) as pool:
        jobs = pool.map(seed_job, DEV_SEEDS)
    S = summarise(jobs)
    v = verdict(S)
    for j in jobs:
        for c in j['runs']:
            for r in j['runs'][c]:
                for n in r:
                    r[n]['life'] = {k: r[n]['life'][k] for k in ('life_id', 'fingerprint', 'h_pass', 'fails', 'phase_fails')}
    (dst / 'diag_plan_result.json').write_text(json.dumps({'rule': RULE, 'verdict': v, 'summary': S, 'per_seed': jobs},
                                                          ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'verdict': v, 'checks': S['checks']}), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
