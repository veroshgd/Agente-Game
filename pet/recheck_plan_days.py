"""Correction record (round 7, 2026-10-25) for the day-level plan metrics of pet/diag_plan.py, and the
case study of its one new phase failure. pet/diag_plan.py (sha256 f4fe054f..., its rule fixed before its
run) and docs/pet_plan_components/diag_plan_result.json are NOT edited; this module re-runs the same lives.

    python -m pet.recheck_plan_days [out_dir]      # default docs/pet_plan_components/correction_days

Defect: diag_interest.live() records day_state() at the END of each day, and diag_plan read day d from
days[d]. So days[d] was the state BEFORE the morning goal update of day d: its goal was the one of day
d - 1, and its 'learn' satiation was evaluated for day d with the satiation record of before that
morning (a plan closed 'done' / 'stalled' that morning was missed). days[0] was the pre-common state.
Fix: record each day right after the hour-0 step, i.e. after the core's morning update_goal. The hour-0
action cannot change the goal or the satiation record (both change only in update_goal), so this is the
value the pet acted under all day; it is checked against goal_by_day and the hour-0 decision record.
Recording reads only: trace fingerprints and generator end states must be identical (checked per run).

Case 6006 / rep 2 / hard, current vs no_offtask: lockstep hour by hour from the same common day-0 state;
in both lives the choice is also re-made at every hour with the other rule for the off-task penalty
(pure), which separates the DIRECT effect of the switch (hours where it changes the choice in the same
state) from what follows from the lives having diverged.
"""
import copy
import hashlib
import json
import sys
from contextlib import contextmanager
from multiprocessing import Pool
from pathlib import Path

from . import diag_interest as DI
from . import diag_plan as DP
from . import engine
from . import lifestats as L
from . import validate_interest as VI
from . import validate_read as VR

DAY_KEYS = ('learn_days', 'sat_days', 'mean_learn_sat', 'read_on_sat_days_out_learn')
CASE = (6006, 2, 'hard')


def rng_digest(s):
    return hashlib.sha256(repr(s.agent.rng.getstate()).encode()).hexdigest()[:16]


def live_morning(s, n_days, rows, mornings):
    """Same hours as diag_interest.live (24 a day); the day record is taken after the hour-0 step."""
    for _ in range(n_days):
        n0 = len(s.events)
        a = s.agent
        day = s.tick // 24
        VR.run_hours(s, 1)
        g = a.goal['type'] if a.goal else None
        first = DI.hour_rows(s, n0)[0]
        assert g == a.goal_by_day[-1] == first['goal_type'], (day, g, a.goal_by_day[-1], first['goal_type'])
        mornings.append({'day': day, 'goal': g, 'learn_sat': a._satiation('learn', day)})
        VR.run_hours(s, 23)
        rows.extend(DI.hour_rows(s, n0))


def corrected_metrics(rows, mornings):
    sat = [m['learn_sat'] > 0 for m in mornings]
    d0 = mornings[0]['day']
    return {'learn_days': sum(m['goal'] == 'learn' for m in mornings), 'sat_days': sum(sat),
            'mean_learn_sat': sum(m['learn_sat'] for m in mornings) / len(mornings),
            'read_on_sat_days_out_learn': sum(1 for r in rows if r['chosen'] == 'read' and sat[r['tick'] // 24 - d0]
                                              and r['goal_type'] != 'learn')}


def run_fixed(pets0, seed, cond, rep):
    out = {}
    for n, p in pets0.items():
        c = copy.deepcopy(p)
        for k, v in DP.CONDITIONS[cond].items():
            setattr(c.agent, k, v)
        c.agent.read_audit = True
        if rep:
            c.agent.rng.seed(seed * 1000 + rep)
        rows, mornings = [], []
        live_morning(c, VI.COMMON, rows, mornings)
        out[n] = {'m': corrected_metrics(rows, mornings), 'fingerprint': L.fingerprint(c.trace), 'rng': rng_digest(c)}
    return out


def run_original(pets0, seed, cond, rep):
    """diag_plan.run, with the generator end state (diag_plan does not keep it)."""
    out = {}
    for n, p in pets0.items():
        c = copy.deepcopy(p)
        for k, v in DP.CONDITIONS[cond].items():
            setattr(c.agent, k, v)
        c.agent.read_audit = True
        if rep:
            c.agent.rng.seed(seed * 1000 + rep)
        rows, days = [], [DI.day_state(c.agent)]
        DI.live(c, VI.COMMON, rows, days)
        out[n] = {'m': DP.pet_metrics(c, rows, days), 'fingerprint': L.fingerprint(c.trace), 'rng': rng_digest(c)}
    return out


def pets_at_common(seed):
    pets0 = {n: VI.book_pet(seed, DP.ARM, cl) for n, cl in (('clear', VI.CLEAR), ('hard', VI.HARD))}
    for p in pets0.values():
        p.phase('common')
    return pets0


def seed_job(seed):
    pets0 = pets_at_common(seed)
    res = {'seed': seed, 'runs': {}}
    for cond in DP.CONDITIONS:
        res['runs'][cond] = []
        for rep in range(DP.REPS + 1):
            old, new = run_original(pets0, seed, cond, rep), run_fixed(pets0, seed, cond, rep)
            res['runs'][cond].append({n: {'old': {k: old[n]['m'][k] for k in DAY_KEYS}, 'new': new[n]['m'],
                                          'same_life': old[n]['fingerprint'] == new[n]['fingerprint'] and old[n]['rng'] == new[n]['rng'],
                                          'fingerprint': new[n]['fingerprint']} for n in pets0})
    return res


# ---------------------------------------------------------------- case 6006 / rep2 / hard
@contextmanager
def offtask_counterfactual():
    """Adds to every audit record the choice under the OTHER off-task rule (pure, restored after)."""
    orig = engine.PetAgent.read_audit_record

    def rec(self, action, day):
        r = orig(self, action, day)
        r['other_rule'] = self._choice_with(day, goal_read_offtask_off=not self.goal_read_offtask_off)
        return r
    engine.PetAgent.read_audit_record = rec
    try:
        yield
    finally:
        engine.PetAgent.read_audit_record = orig


def case_hours(seed, rep, pet):
    pets0 = pets_at_common(seed)
    lives = {}
    with offtask_counterfactual():
        for cond in ('current', 'no_offtask'):
            c = copy.deepcopy(pets0[pet])
            for k, v in DP.CONDITIONS[cond].items():
                setattr(c.agent, k, v)
            c.agent.read_audit = True
            if rep:
                c.agent.rng.seed(seed * 1000 + rep)
            hours = []
            for _ in range(VI.COMMON * 24):
                a = c.agent
                n0, food0, mat0 = len(c.events), a.inventory['food'], a.inventory['material']
                VR.run_hours(c, 1)
                e = c.events[n0:]
                act = next(x for x in e if x['kind'] == 'action')
                au = act['decision']['audit']
                hours.append({'tick': act['tick'], 'day': act['tick'] // 24 - VI.GROW, 'action': act['action'],
                              'core': act['core_action'], 'other_rule': au['other_rule'], 'goal': au['goal_type'],
                              'home': a.shelter, 'material': a.inventory['material'], 'food_before': food0,
                              'hunger': au['body'][0], 'energy': au['body'][1], 'home_before': au['body'][2],
                              'refill': any(x['kind'] == 'home' for x in e)})
            lives[cond] = {'hours': hours, 'goals': [{k: g.get(k) for k in ('type', 'created_day', 'closed_day', 'outcome')}
                                                     for g in c.agent.goal_history if g.get('closed_day', 0) >= VI.GROW]
                           + ([{'type': c.agent.goal['type'], 'created_day': c.agent.goal['created_day'], 'open': True}]
                              if c.agent.goal else []),
                           'plan_log': [x for x in c.agent.plan_log if x['day'] >= VI.GROW],
                           'fingerprint': L.fingerprint(c.trace), 'rng': rng_digest(c)}
    return lives


def episodes(hours, below=20):
    out, cur = [], None
    for h in hours:
        if h['home'] < below:
            cur = cur or {'start_day': h['day'], 'start_tick': h['tick'], 'hours': 0, 'min': h['home'], 'goals': {}, 'acts': {}}
            cur['hours'] += 1
            cur['min'] = min(cur['min'], h['home'])
            cur['goals'][str(h['goal'])] = cur['goals'].get(str(h['goal']), 0) + 1
            cur['acts'][h['core']] = cur['acts'].get(h['core'], 0) + 1
        elif cur:
            cur['end_day'] = h['day']
            out.append(cur)
            cur = None
    if cur:
        cur['end_day'] = hours[-1]['day']
        out.append(cur)
    return out


def windows(hours, w=10):
    out = []
    for d0 in range(0, VI.COMMON, w):
        H = [h for h in hours if d0 <= h['day'] < d0 + w]
        cnt = lambda a: sum(h['core'] == a for h in H)
        out.append({'days': f'{d0}-{d0 + w}', 'below20': sum(h['home'] < 20 for h in H), 'build': cnt('build'),
                    'gather_material': cnt('gather_material'), 'read': cnt('read'), 'explore': cnt('explore'),
                    'improve_home_hours': sum(h['goal'] == 'improve_home' for h in H), 'learn_hours': sum(h['goal'] == 'learn' for h in H),
                    'min_home': min(h['home'] for h in H)})
    return out


def case_study(seed=CASE[0], rep=CASE[1], pet=CASE[2]):
    L2 = case_hours(seed, rep, pet)
    cu, no = L2['current']['hours'], L2['no_offtask']['hours']
    first = next(i for i, (x, y) in enumerate(zip(cu, no)) if x['core'] != y['core'])
    direct = {c: [{k: h[k] for k in ('day', 'tick', 'core', 'other_rule', 'goal', 'home_before', 'hunger', 'energy')}
                  for h in L2[c]['hours'] if h['core'] != h['other_rule']] for c in L2}
    first_goal = next((d for d in range(VI.COMMON) if cu[d * 24]['goal'] != no[d * 24]['goal']), None)
    keep = ('day', 'tick', 'core', 'other_rule', 'goal', 'home_before', 'hunger', 'energy', 'material', 'food_before')
    return {'case': f'{seed}/rep{rep}/{pet}', 'same_start': cu[0]['tick'] == no[0]['tick'],
            'first_divergence': {'hour_index': first, 'current': {k: cu[first][k] for k in keep},
                                 'no_offtask': {k: no[first][k] for k in keep},
                                 'identical_before': all(x['core'] == y['core'] and x['home'] == y['home'] for x, y in zip(cu[:first], no[:first]))},
            'direct_changes': direct,
            'first_goal_divergence_day': first_goal,
            'goals': {c: L2[c]['goals'] for c in L2},
            'daily_goal': {c: [L2[c]['hours'][d * 24]['goal'] for d in range(VI.COMMON)] for c in L2},
            'below20_hours': {c: sum(h['home'] < 20 for h in L2[c]['hours']) for c in L2},
            'below20_share': {c: sum(h['home'] < 20 for h in L2[c]['hours']) / len(L2[c]['hours']) for c in L2},
            'episodes': {c: episodes(L2[c]['hours']) for c in L2}, 'windows': {c: windows(L2[c]['hours']) for c in L2},
            'counts': {c: {a: sum(h['core'] == a for h in L2[c]['hours']) for a in engine.core.ACTIONS} for c in L2},
            'refills': {c: sum(h['refill'] for h in L2[c]['hours']) for c in L2},
            'lives': {c: {'fingerprint': L2[c]['fingerprint'], 'rng': L2[c]['rng']} for c in L2}}


# ---------------------------------------------------------------- summary
def summarise(jobs, original):
    jobs = sorted(jobs, key=lambda j: j['seed'])
    mean = lambda xs: sum(xs) / len(xs)
    per = {when: {c: [{**{f'level_{k}': mean([(r['clear'][when][k] + r['hard'][when][k]) / 2 for r in j['runs'][c]]) for k in DAY_KEYS},
                       **{f'gap_{k}': mean([r['clear'][when][k] - r['hard'][when][k] for r in j['runs'][c]]) for k in DAY_KEYS}}
                      for j in jobs] for c in DP.CONDITIONS} for when in ('old', 'new')}
    keys = per['new']['current'][0].keys()
    out = {'same_lives_all': all(r[n]['same_life'] for j in jobs for c in j['runs'] for r in j['runs'][c] for n in r),
           'old_equals_saved': all(abs(per['old'][c][i][k] - original['summary']['by_condition'][c][k]['per_seed'][i]) < 1e-12
                                   for c in DP.CONDITIONS for i in range(len(jobs)) for k in keys),
           'by_condition': {when: {c: {k: L.describe([x[k] for x in per[when][c]]) for k in keys} for c in DP.CONDITIONS} for when in per},
           'paired_vs_current': {when: {c: {k: L.describe([x[k] - y[k] for x, y in zip(per[when][c], per[when]['current'])]) for k in keys}
                                        for c in DP.CONDITIONS if c != 'current'} for when in per}}
    return out


def lookup(jobs, seed, cond, rep, pet):
    j = next(x for x in jobs if x['seed'] == seed)
    r = j['runs'][cond][rep][pet]
    return {'old': r['old'], 'new': r['new'], 'same_life': r['same_life']}


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_plan_components' / 'correction_days'
    dst.mkdir(parents=True, exist_ok=True)
    original = json.loads((dst.parent / 'diag_plan_result.json').read_text(encoding='utf-8'))
    with Pool(14) as pool:
        jobs = pool.map(seed_job, DP.DEV_SEEDS)
        case = pool.apply(case_study)
    S = summarise(jobs, original)
    checks = {'6006/no_offtask/rep2/hard': lookup(jobs, 6006, 'no_offtask', 2, 'hard'),
              '6001/no_offtask/rep0/clear': lookup(jobs, 6001, 'no_offtask', 0, 'clear')}
    saved = {j['seed']: j for j in original['per_seed']}
    case['matches_diag_plan_lives'] = {c: case['lives'][c]['fingerprint'] == saved[CASE[0]]['runs'][c][CASE[1]][CASE[2]]['fingerprint']
                                       for c in ('current', 'no_offtask')}
    (dst / 'recheck_plan_days.json').write_text(json.dumps({'summary': S, 'checks': checks, 'case': case, 'per_seed': jobs},
                                                           ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'same_lives_all': S['same_lives_all'], 'old_equals_saved': S['old_equals_saved'], 'checks': checks,
                                'case_first': case['first_divergence'], 'case_below20': case['below20_hours'],
                                'case_matches': case['matches_diag_plan_lives']}), ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
