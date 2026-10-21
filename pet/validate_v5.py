"""v5 personality-differentiation validation (product experiments, not research).

    python -m pet.validate_v5 dev          # development seeds: look, debug, tune
    python -m pet.validate_v5 validation   # independent seeds: run once, criteria frozen below

Every pet is born identical per seed (same seed = same birth). Growth routes differ only in
the environment and opportunities the player offers (objects, invitations); preferences are
never written, actions never scripted and no experience is injected. What the pet actually
did is measured from its own event log.

A  same birth, different growth (days 0-20)         D  ablation: preference term on/off
B  uniform environment afterwards (days 20-50)       E  plasticity and health
C  probes: same instant state, history kept
"""
import copy
import json
import random
import sys
from collections import Counter
from pathlib import Path

from . import engine
from .engine import Session, core

DEV_SEEDS = [1, 42, 901, 7, 123]
VALIDATION_SEEDS = [2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010]
GROW, OBSERVE, WINDOW = 20, 60, 10           # days of growth, days of uniform observation, window
ROUTES = {
    'control': {'objects': [], 'invite_daily': False},
    'reading': {'objects': ['book'], 'invite_daily': False},
    'garden':  {'objects': ['garden'], 'invite_daily': False},
    'social':  {'objects': ['garden'], 'invite_daily': True},
}
UNIFORM_OBJECTS = ['garden', 'book']          # every route gets the same objects after growth
LEISURE = ('read', 'garden', 'visit', 'explore')

# ---- Tentative acceptance criteria, fixed BEFORE the validation seeds were run (2026-10-17).
# Product reasons: 3 percentage points of all hours is ~0.7 h a day, i.e. about five more
# reading entries a week in the diary; 0.08 more visits per hour the neighbor is free is
# about one more visit a day. "Persistent" = the sign holds in at least 4 of 6 ten-day
# windows (40 of 60 days) after the environment became the same for everyone.
# Dev-phase change, made before any validation run: windows went from 5 to 10 days (and
# observation from 30 to 60 days) because the core's goals run in ~8-10 day cycles, so a
# 5-day window often held no reading streak for either route. Thresholds were not changed.
# FROZEN 2026-10-17 before the single validation run: engine parameters and these criteria
# were not edited afterwards (SHA-256 of pet/engine.py and this file in PET_VALIDATION.md).
CRITERIA = {
    'read_gap_pp': 3.0,          # reading route - garden route, read share of all hours
    'social_gap': 0.08,          # social route - garden route, visits per neighbor-free hour
    'windows_same_sign': 4,      # of 6 windows
    'seed_share': 0.7,           # share of seeds that must show each effect
    'ablation_shrink': 0.5,      # probe gap must shrink by at least half without the term
    'plastic_share': 0.7,        # share of seeds whose reading-grown pet turns social when offered
    'max_activity_share': 0.7,   # no non-sleep activity above this share of a window
}


def mili_away(seed, day):
    return random.Random(seed * 100003 + day).random() < engine.MILI_AWAY_CHANCE


def grow(seed, route, pref_off=False):
    """Days 0-GROW under one route. Opportunities only: objects and invitation cards."""
    spec = ROUTES[route]
    s = Session(seed, 5)   # v5 experiment: rules pinned explicitly (2026-10-21)
    s.agent.pref_off = pref_off
    for obj in spec['objects']:
        s.apply({'kind': 'object', 'value': obj})
    for _ in range(GROW * 24):
        if spec['invite_daily'] and s.tick % 24 == 8 and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
        s.step()
    return s


def uniform(s):
    """Same objects for everyone, and one invitation so every pet has met the neighbor:
    from here on all routes get identical external opportunities."""
    for obj in UNIFORM_OBJECTS:
        if obj not in s.world.objects:
            s.apply({'kind': 'object', 'value': obj})
    if s.tick >= s.agent.invitation_until:
        s.apply({'kind': 'invite', 'value': None})


def observe(s, days, seed, invite_daily=False, sample=None):
    """Run `days` more days hour by hour; per window: activity shares, visits per hour the
    neighbor could meet, and the state the choices were made in (to check confounds)."""
    windows, start = [], s.tick
    rows = []
    for _ in range(days * 24):
        a = s.agent
        day, hour = divmod(s.tick, 24)
        if invite_daily and hour == 8 and s.tick >= a.invitation_until and s.world.has('garden'):
            s.apply({'kind': 'invite', 'value': None})
        met_before = bool(a.shared)
        visits_today = sum(1 for m in a.shared if m['tick'] // 24 == day)
        free = (8 <= hour < 20 and met_before and not mili_away(seed, day)
                and visits_today < engine.MILI_VISITS_PER_DAY)
        state = (a.hunger, a.energy, a.shelter, s.tick < a.invitation_until)
        s.step()
        e = s.events[-1]
        rows.append({'action': e['action'], 'free': free, 'hunger': state[0], 'energy': state[1],
                     'home': state[2], 'invited': state[3], 'condition': s.agent.condition})
        if sample is not None and (s.tick - start) % 24 == 0:
            sample.append({'day': s.tick // 24, **{k: round(v, 3) for k, v in s.agent.prefs.items()},
                           **{k: round(v, 1) for k, v in s.agent.traits.items()}})
    for w in range(0, len(rows), WINDOW * 24):
        part = rows[w:w + WINDOW * 24]
        acts = Counter(r['action'] for r in part)
        n = len(part)
        free_hours = sum(r['free'] for r in part)
        windows.append({
            'share': {k: acts[k] / n for k in ('read', 'garden', 'visit', 'sleep', 'eat', 'gather_material', 'build', 'explore')},
            'visit_per_free_hour': sum(r['free'] and r['action'] == 'visit' for r in part) / free_hours if free_hours else None,
            'free_hours': free_hours,
            'mean_hunger': sum(r['hunger'] for r in part) / n, 'mean_energy': sum(r['energy'] for r in part) / n,
            'mean_home': sum(r['home'] for r in part) / n, 'invited_hours': sum(r['invited'] for r in part),
            'min_home': min(r['home'] for r in part), 'min_condition': min(r['condition'] for r in part),
            'top_non_sleep': max((c / n for k, c in acts.items() if k != 'sleep'), default=0),
        })
    return windows


def lived(s, since=0):
    acts = Counter(e['action'] for e in s.events if e['kind'] == 'action' and e['tick'] >= since)
    return {k: acts[k] for k in ('read', 'garden', 'visit', 'explore', 'sleep', 'eat', 'gather_material', 'build')}


# ---------------------------------------------------------------- C/D. probes
PROBE_STATES = [(30, 80), (45, 60), (20, 95)]    # (hunger, energy) shared by every pet
PROBE_BOREDOM = [0, 8, 14]                         # hours of exploring in the last 24, same for every pet
PROBE_HOURS = [10, 15]


def probe(s, variant='full'):
    """Same instant state for every pet; history kept. Returns read-choice rate, explore rate
    and expected visits (explore rate x chance to seek the neighbor out).

    Unified: hunger, energy, condition 100, home 60, food 6, material 0, no goal, the same
    recent-boredom pattern, no invitation, neighbor free, same hour.
    Kept: traits, long-term preferences, shared memories (their recency), core knowledge.
    Variants remove one kept factor at a time: 'no_pref', 'no_memory', 'birth_traits',
    'no_knowledge' (the core's semantic memory, e.g. 'books'). 'no_pref' is the only one the
    acceptance criteria use; the others explain where a difference is carried."""
    out = {'read': 0, 'explore': 0, 'visit': 0.0, 'n': 0}
    for hunger, energy in PROBE_STATES:
      for bored in PROBE_BOREDOM:
        for hour in PROBE_HOURS:
            c = copy.deepcopy(s)
            a = c.agent
            day = c.tick // 24
            a.now = day * 24 + hour
            a.hunger, a.energy, a.condition, a.shelter = float(hunger), float(energy), 100.0, 60.0
            a.inventory['food'], a.inventory['material'] = 6.0, 0.0
            a.goal, a.recent, a.invitation_until = None, ['explore'] * bored, -1
            a.neighbor_status = lambda d, h, invited=False: engine.NEIGHBOR_FREE
            if variant == 'no_pref':
                a.pref_off = True
            elif variant == 'no_memory':
                a.influence = lambda: (0.0, [])
            elif variant == 'birth_traits':
                a.traits = dict(a.birth)
            elif variant == 'no_knowledge':
                a.knowledge_strength = {}
            scored = [(a.score(x, day), x) for x in core.ACTIONS]
            choice = max((v, x) for v, x in scored if v is not None)[1]
            out['n'] += 1
            if choice == 'read':
                out['read'] += 1
            if choice == 'explore':
                out['explore'] += 1
                bonus, _ = a.influence()
                chance = a.visit_chance(bonus)[0] if a.shared else 0.0
                out['visit'] += chance
    return {'read': out['read'] / out['n'], 'explore': out['explore'] / out['n'], 'visit': out['visit'] / out['n']}


# ---------------------------------------------------------------- run everything for a seed set
def run(seeds):
    report = {'seeds': seeds, 'criteria': CRITERIA, 'params': {k: getattr(engine, k) for k in (
        'PREF_RATE', 'PREF_DULL', 'PREF_WEIGHT', 'VISIT_BASE', 'VISIT_PREF')}, 'per_seed': {}}
    for seed in seeds:
        r = report['per_seed'][seed] = {'routes': {}, 'ablation_runs': {}, 'plasticity': {}}
        for route in ROUTES:
            s = grow(seed, route)
            grown = {'lived': lived(s), 'prefs': dict(s.agent.prefs), 'traits': dict(s.agent.traits)}
            uniform(s)
            probes = {}
            traj = []
            windows = []
            for k in range(OBSERVE // 10):           # probes every 10 days from day 20 (+ end)
                probes[s.tick // 24] = {v: probe(s, v) for v in ('full', 'no_pref', 'no_memory', 'birth_traits', 'no_knowledge')}
                windows += observe(s, 10, seed, sample=traj)
            probes[s.tick // 24] = {v: probe(s, v) for v in ('full', 'no_pref', 'no_memory', 'birth_traits', 'no_knowledge')}
            r['routes'][route] = {'grown': grown, 'windows': windows, 'probes': probes, 'trajectory': traj,
                                  'final_prefs': dict(s.agent.prefs), 'final_traits': dict(s.agent.traits),
                                  'alive': s.agent.alive}
            # D (run level): the same route lived with the preference term off from birth.
            t = grow(seed, route, pref_off=True)
            uniform(t)
            r['ablation_runs'][route] = observe(t, OBSERVE, seed)
        # E. plasticity: the reading-grown pet is now offered the neighbor every day.
        s = grow(seed, 'reading')
        uniform(s)
        start_prefs = dict(s.agent.prefs)
        traj = []
        windows = observe(s, OBSERVE, seed, invite_daily=True, sample=traj)
        r['plasticity'] = {'windows': windows, 'trajectory': traj, 'start_prefs': start_prefs,
                           'final_prefs': dict(s.agent.prefs)}
    return report


# ---------------------------------------------------------------- evaluation
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def evaluate(report):
    C = report['criteria']
    res = {'seeds': {}, 'summary': {}}
    for seed, r in report['per_seed'].items():
        R = r['routes']
        read_gaps = [(a['share']['read'] - b['share']['read']) * 100 for a, b in zip(R['reading']['windows'], R['garden']['windows'])]
        soc_gaps = [(a['visit_per_free_hour'] or 0) - (b['visit_per_free_hour'] or 0) for a, b in zip(R['social']['windows'], R['garden']['windows'])]
        abl = r['ablation_runs']
        abl_read = [(a['share']['read'] - b['share']['read']) * 100 for a, b in zip(abl['reading'], abl['garden'])]
        abl_soc = [(a['visit_per_free_hour'] or 0) - (b['visit_per_free_hour'] or 0) for a, b in zip(abl['social'], abl['garden'])]
        pr = lambda route, v, key: mean([p[v][key] for p in R[route]['probes'].values()])
        probe_read = {v: pr('reading', v, 'read') - pr('garden', v, 'read') for v in ('full', 'no_pref', 'no_memory', 'birth_traits', 'no_knowledge')}
        probe_soc = {v: pr('social', v, 'visit') - pr('garden', v, 'visit') for v in ('full', 'no_pref', 'no_memory', 'birth_traits', 'no_knowledge')}
        P = r['plasticity']
        health_fail = [(route, i, round(w['min_condition']), round(w['min_home'], 1), round(w['top_non_sleep'], 2))
                       for route, R_ in R.items() for i, w in enumerate(R_['windows'])
                       if w['min_condition'] < 99 or w['min_home'] <= 0 or w['top_non_sleep'] > C['max_activity_share']]
        health = all(w['min_condition'] >= 99 and w['min_home'] > 0 and w['top_non_sleep'] <= C['max_activity_share']
                     for route in R.values() for w in route['windows']) and all(route['alive'] for route in R.values()) \
            and all(5 <= v <= 95 for route in R.values() for v in route['final_traits'].values())
        res['seeds'][seed] = {
            'lived_growth': {k: R[k]['grown']['lived'] for k in R},
            'prefs_after_growth': {k: {p: round(v, 3) for p, v in R[k]['grown']['prefs'].items()} for k in R},
            'read_gap_pp': [round(x, 1) for x in read_gaps], 'read_gap_mean': round(mean(read_gaps), 2),
            'read_effect': mean(read_gaps) >= C['read_gap_pp'] and sum(x > 0 for x in read_gaps) >= C['windows_same_sign'],
            'social_gap': [round(x, 3) for x in soc_gaps], 'social_gap_mean': round(mean(soc_gaps), 3),
            'social_effect': mean(soc_gaps) >= C['social_gap'] and sum(x > 0 for x in soc_gaps) >= C['windows_same_sign'],
            'ablation_run_read_gap_mean': round(mean(abl_read), 2), 'ablation_run_social_gap_mean': round(mean(abl_soc), 3),
            'probe_read_gap': {k: round(v, 3) for k, v in probe_read.items()},
            'probe_social_gap': {k: round(v, 3) for k, v in probe_soc.items()},
            # The new environment's activities overtake reading, reading's liking falls from
            # where growth left it, and the pet reads less late than early (2-window means).
            'plastic': (max(P['final_prefs']['garden'], P['final_prefs']['social']) > P['final_prefs']['read']
                        and P['final_prefs']['read'] < P['start_prefs']['read']
                        and mean([w['share']['read'] for w in P['windows'][-2:]]) < mean([w['share']['read'] for w in P['windows'][:2]])),
            'plastic_detail': {'prefs_start': {k: round(v, 3) for k, v in P['start_prefs'].items()},
                               'prefs_end': {k: round(v, 3) for k, v in P['final_prefs'].items()},
                               'read_first': round(P['windows'][0]['share']['read'], 3), 'read_last': round(P['windows'][-1]['share']['read'], 3),
                               'visit_first': round(P['windows'][0]['share']['visit'], 3), 'visit_last': round(P['windows'][-1]['share']['visit'], 3)},
            'health': health, 'health_fail': health_fail,
            'confounds': {k: {m: round(mean([w[m] for w in R[k]['windows']]), 1) for m in ('mean_hunger', 'mean_energy', 'mean_home', 'invited_hours', 'free_hours')} for k in R},
        }
    S = res['seeds'].values()
    n = len(res['seeds'])
    full_r = mean([abs(s['probe_read_gap']['full']) for s in S]); off_r = mean([abs(s['probe_read_gap']['no_pref']) for s in S])
    full_s = mean([abs(s['probe_social_gap']['full']) for s in S]); off_s = mean([abs(s['probe_social_gap']['no_pref']) for s in S])
    res['summary'] = {
        'n_seeds': n,
        'read_effect_seeds': sum(s['read_effect'] for s in S), 'social_effect_seeds': sum(s['social_effect'] for s in S),
        'read_gap_mean_pp': round(mean([s['read_gap_mean'] for s in S]), 2),
        'read_gap_mean_pp_without_pref': round(mean([s['ablation_run_read_gap_mean'] for s in S]), 2),
        'social_gap_mean': round(mean([s['social_gap_mean'] for s in S]), 3),
        'social_gap_mean_without_pref': round(mean([s['ablation_run_social_gap_mean'] for s in S]), 3),
        'probe_read_gap': {v: round(mean([s['probe_read_gap'][v] for s in S]), 3) for v in ('full', 'no_pref', 'no_memory', 'birth_traits', 'no_knowledge')},
        'probe_social_gap': {v: round(mean([s['probe_social_gap'][v] for s in S]), 3) for v in ('full', 'no_pref', 'no_memory', 'birth_traits', 'no_knowledge')},
        'probe_shrink_read': None if not full_r else round(1 - off_r / full_r, 2),
        'probe_shrink_social': None if not full_s else round(1 - off_s / full_s, 2),
        'plastic_seeds': sum(s['plastic'] for s in S), 'healthy_seeds': sum(s['health'] for s in S),
    }
    sm = res['summary']
    res['verdict'] = {
        'read_persistent': sm['read_effect_seeds'] >= C['seed_share'] * n,
        'social_persistent': sm['social_effect_seeds'] >= C['seed_share'] * n,
        'ablation_read': sm['probe_shrink_read'] is not None and sm['probe_shrink_read'] >= C['ablation_shrink'],
        'ablation_social': sm['probe_shrink_social'] is not None and sm['probe_shrink_social'] >= C['ablation_shrink'],
        'plastic': sm['plastic_seeds'] >= C['plastic_share'] * n,
        'healthy': sm['healthy_seeds'] == n,
    }
    return res


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    report = run(seeds)
    result = evaluate(report)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    out.mkdir(parents=True, exist_ok=True)
    (out / f'v5_{which}_raw.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    (out / f'v5_{which}_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'summary': result['summary'], 'verdict': result['verdict']}, ensure_ascii=False, indent=1))
    for seed, s in result['seeds'].items():
        print(seed, 'read', s['read_gap_pp'], s['read_effect'], '| social', s['social_gap'], s['social_effect'],
              '| plastic', s['plastic'], '| health', s['health'])


if __name__ == '__main__':
    main()
