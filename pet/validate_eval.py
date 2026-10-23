"""Experiment 'evaluation' (2026-10-24): can a pet form activity evaluations from lived
experience that carry information beyond recent frequency, show in its own behavior, and
change with new experience? Product experiment, NOT a rule version (default stays v5).

    python -m pet.validate_eval dev [out_dir]          # development seeds (all already viewed)
    python -m pet.validate_eval validation [out_dir]   # fresh seeds, ONCE, after CRITERIA were fixed

Arms (engine flags; everything else as in v5):
  v5, v6           historical references (as recorded)
  base             phase A base: rest4 + v6 home trigger + goal endings in order
                   (PetAgent.ordered_goals: done -> stalled -> only an open plan 'switched',
                   candidates re-proposed after any ending) + one repair rule chosen on dev
                   (PetAgent.home_emergency_unmute: below HOME_INTERRUPT_BELOW the satiation of a
                   finished / 'stalled' repair does not mute improve_home). Main control.
  eval             base + activity evaluation (PetAgent.evaluation, EVAL_* in engine.py). Candidate.
  dev-only ablations / diagnostics:
  eval_nodecision  evaluation learns but never enters a choice (must equal base: sanity)
  eval_frozen      evaluation acts, learning frozen at the end of growth (day 20)
  eval_flat        same mean evaluation term for read and garden (score scale, no activity information)
  ordered_noint    the base without the home trigger (is the trigger still needed?)
  ordered_only     ordered endings + trigger, without the repair rule (phase A step 1)
What is kept, replaced, added (eval vs base): the v5 liking (prefs: an enjoyment-weighted share
of leisure time, i.e. frequency x experience) is KEPT unchanged in goals and scores, so the
two arms differ only by the evaluation term. 'Habit' (pure recent frequency, PREF_RATE per
leisure hour) is recorded for diagnosis only and never decides anything.

Designs per arm and birth seed (same seeds, routes, objects, invitations, lengths):
  routes   grow 20 days (control / reading / garden / social) -> garden + book + one invitation
           for everyone -> 60 common days. Daily snapshots of Q, n, E, baseline, habit, prefs.
  pair     reading growth -> A (nothing) / B (invitation every morning) 30 days -> washout 1 ->
           withdrawal 30 days x 3 continuation replicates (averaged within the seed).
  plastic  (real life) reading growth -> 20 common days -> 'stay': 70 more common days, or
           'away': 30 days with an invitation every morning (less reading), then 40 common days.
  safe     the v4 safe-home lives (6 seeds x 2 settings, 60 days).
Diagnostics on isolated copies (never lived, never growth evidence):
  swap     at real common-phase states: choice with the evaluation as is / off / read<->garden swapped.
  rule     same counts, different experience; same experience, different counts (synthetic
           experiences fed to a copy of a real state; standard probe states).
  worse    from a real reading-grown state: 30 days in which reading feels half as good (only the
           experience channel of the copy is changed), then 20 normal days.
"""
import copy
import hashlib
import json
import math
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from . import engine
from . import lifestats as L
from . import validate_v5 as v5
from . import validate_v5_social as vs
from .engine import core

DEV_SEEDS = list(range(3001, 3011)) + list(range(6001, 6011))      # already viewed: development
VALIDATION_SEEDS = list(range(7021, 7041))                          # checked unused before 2026-10-24
SAFE_SEEDS = (1, 42, 901, 7, 123, 2024)
SAFE_ITEMS = (('garden',), ('garden', 'book', 'music'))
GROW, COMMON, PHASE, WASHOUT, WITHDRAW, REPS, WINDOW = 20, 60, 30, 1, 30, 3, 10
PL_COMMON, PL_AWAY, PL_AFTER = 20, 30, 40
ARMS = {
    'v5': {'scheme': 'cap2'},
    'v6': {'scheme': 'rest4', 'interrupt': True},
    'base': {'scheme': 'rest4', 'interrupt': True, 'ordered': True, 'unmute': True},
    'eval': {'scheme': 'rest4', 'interrupt': True, 'ordered': True, 'unmute': True, 'evaluation': True},
    'eval_nodecision': {'scheme': 'rest4', 'interrupt': True, 'ordered': True, 'unmute': True, 'evaluation': True, 'in_decision': False},
    'eval_frozen': {'scheme': 'rest4', 'interrupt': True, 'ordered': True, 'unmute': True, 'evaluation': True, 'freeze_after_growth': True},
    'eval_flat': {'scheme': 'rest4', 'interrupt': True, 'ordered': True, 'unmute': True, 'evaluation': True, 'flat': True},
    'ordered_noint': {'scheme': 'rest4', 'ordered': True, 'unmute': True},
    'ordered_only': {'scheme': 'rest4', 'interrupt': True, 'ordered': True},
}
DEV_ONLY = ('eval_nodecision', 'eval_frozen', 'eval_flat', 'ordered_noint', 'ordered_only')
MAIN = ('v5', 'v6', 'base', 'eval')
CANDIDATE, CONTROL = 'eval', 'base'
PARAMS = {k: getattr(engine, k) for k in ('EVAL_WEIGHT', 'EVAL_ALPHA_MIN', 'EVAL_BASE_RATE', 'EVAL_N0', 'EVAL_KEEP',
                                          'HOME_INTERRUPT_BELOW', 'V6_REST_HOURS', 'PREF_RATE', 'PREF_WEIGHT')}
CONFIG_ID = hashlib.sha256(json.dumps({'arms': ARMS, 'params': PARAMS, 'design': [
    GROW, COMMON, PHASE, WASHOUT, WITHDRAW, REPS, WINDOW, PL_COMMON, PL_AWAY, PL_AFTER]}, sort_keys=True).encode()).hexdigest()[:12]
# ---- FIXED 2026-10-24 after the dev run (3001-3010 + 6001-6010), BEFORE seeds 7021-7040.
# Dev decision on the candidate 'eval' (not sent to validation, so no fresh seed is spent on it).
# It missed two requirements this round set before any run (task points 6 and 8):
#  * safety: 251/252 unique whole lives (eval|plastic|6006|stay, lowest home 2.2 < 3);
#  * activity-specific information: eval - base reading gap +1.25 pp [0.30, 2.14], but the score
#    scale control eval_flat - base gives +0.59 pp and eval - eval_flat is +0.66 pp [-0.42, 1.70];
#    at the end of the common phase E_read of the reading route equals the control route's
#    (+0.001 [-0.025, 0.026]): growth history is not what the evaluation carries.
DEV_DECISION = {'candidate': 'eval', 'sent_to_validation': False,
                'reasons': ['safety 251/252 on dev', 'eval - eval_flat reading gap CI crosses 0',
                            'E does not differ by growth route at the end of the common phase']}
# Validation = phase A only: is the frozen base safe on fresh births, and at what cost?
# A1 every unique whole life of 'base' meets the v4 safe-home standard (all designs, all replicates);
# A2 phase share failures (phases >= 10 days) of 'base' no more than v6's on the same seeds;
# A3 social kept: pair B - A >= 1/7 visits/day (one more a week) in >= 14/20 seeds, CI lower > 0;
# A4 activity entropy of the common phase at most 0.1 bits below v6;
# plus replay compatibility. The cost (reading / garden gap, route TV distance vs v6 and v5) is
# reported with paired intervals and decides nothing.
CRITERIA = {'stage': 'A_base', 'A1_all_unique_whole_lives': True, 'A2_phase_fails_vs': 'v6',
            'A3_min_gap': 1 / 7, 'A3_min_positive': 14, 'A4_max_entropy_drop_vs_v6': 0.1}
VALIDATION_ARMS = ('v5', 'v6', 'base')


def configure(s, arm):
    c = ARMS[arm]
    vs.set_scheme(s, c['scheme'])
    a = s.agent
    a.home_interrupt = c.get('interrupt', False)
    a.ordered_goals = c.get('ordered', False)
    a.home_emergency_unmute = c.get('unmute', False)
    a.evaluation = c.get('evaluation', False)
    a.eval_in_decision = c.get('in_decision', True)
    a.eval_flat = c.get('flat', False)
    a.diagnostics = True       # social_diag only; no behavior change (tested)
    return s


def new_pet(seed, arm):
    return configure(L.TracedSession(seed, 5), arm)


def run_hours(s, hours, invite_daily=False, before=None):
    for _ in range(hours):
        if invite_daily and s.tick % 24 == 8 and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
        if before:
            before(s)
        s.step()


def grow(seed, route, arm):
    spec = v5.ROUTES[route]
    s = new_pet(seed, arm)
    for obj in spec['objects']:
        s.apply({'kind': 'object', 'value': obj})
    run_hours(s, GROW * 24, invite_daily=spec['invite_daily'])
    if ARMS[arm].get('freeze_after_growth'):
        s.agent.eval_learning = False
    v5.uniform(s)
    return s


def snapshot(a, day):
    return {'day': day, 'Q': dict(a.Q), 'n': dict(a.eval_n), 'E': {k: a.eval_term(k) for k in engine.EVAL_KEYS},
            'base': a.eval_base, 'habit': dict(a.habit), 'Q_fresh': dict(a.Q_fresh),
            'pref': {k: a.prefs[k] for k in ('read', 'garden', 'social')},
            'count': {k: a.eval_evidence[k]['count'] for k in engine.EVAL_KEYS}}


def swap_diag(x):
    """Choice at a real state, on an isolated copy: as is / evaluation off / read<->garden swapped."""
    c = copy.deepcopy(x)
    a, day = c.agent, c.tick // 24
    a.now = c.tick
    normal = a.choose(day)
    off = a.choice_without_evaluation(day)
    for d in (a.Q, a.eval_n):
        d['read'], d['garden'] = d['garden'], d['read']
    swapped = a.choose(day)
    return {'normal': normal, 'off': off, 'swapped': swapped}


def windows_of(rows):
    out = []
    for w in range(0, len(rows), WINDOW * 24):
        part = rows[w:w + WINDOW * 24]
        acts = Counter(r[1] for r in part)
        out.append({k: acts[k] / len(part) for k in L.CATEGORIES})
    return out


def route_life(seed, route, arm):
    s = grow(seed, route, arm)
    s.phase('common')
    start = len(s.trace)
    snaps, swaps = [], []
    evaluating = ARMS[arm].get('evaluation')

    def before(x):
        if not evaluating:
            return
        if x.tick % 24 == 0:
            snaps.append(snapshot(x.agent, x.tick // 24))
        if arm == 'eval' and (x.tick // 24) % 5 == 0 and x.tick % 24 in (10, 15):
            swaps.append(swap_diag(x))
    if evaluating:
        snaps.append(snapshot(s.agent, s.tick // 24))
    run_hours(s, COMMON * 24, before=before)
    rec = L.life_record(s, life_id=f'{arm}|route|{seed}|{route}', arm=arm, design='route', seed=seed, setting=route)
    rows = s.trace[start:]
    rec['windows'] = windows_of(rows)
    rec['growth_counts'] = rec['phases']['growth']['counts']
    ev = [e for e in s.events if e['kind'] == 'action' and e['tick'] >= GROW * 24]
    rec['spont_per_day'] = sum(e['action'] == 'visit' and not e['invited'] for e in ev) / COMMON
    rec['snapshots'] = snaps
    daily_read = Counter(r[0] // 24 for r in rows if r[1] == 'read')
    rec['daily_read'] = {d: daily_read.get(d, 0) for d in range(GROW, GROW + COMMON)}
    rec['swaps'] = swaps
    rec['eval_decisive_share'] = (sum(bool(e['decision'].get('eval_decisive')) for e in ev) / len(ev)) if evaluating else None
    rec['goal_endings'] = Counter(f"{g['type']}|{g['outcome']}" for g in s.agent.goal_history)
    return rec


def pair_lives(seed, arm):
    base = grow(seed, 'reading', arm)
    lives, branches = [], {}
    for name, daily in (('A', False), ('B', True)):
        s = copy.deepcopy(base)
        s.phase('intervention')
        run_hours(s, PHASE * 24, invite_daily=daily)
        s.phase('washout')
        run_hours(s, WASHOUT * 24)
        assert s.tick >= s.agent.invitation_until
        branches[name] = s
    for rep in range(REPS):
        for name, s0 in branches.items():
            s = copy.deepcopy(s0)
            if rep:
                s.agent.rng.seed(seed * 1000 + rep)
            s.phase('withdrawal')
            n0 = len(s.events)
            run_hours(s, WITHDRAW * 24)
            ev = [e for e in s.events[n0:] if e['kind'] == 'action']
            rec = L.life_record(s, life_id=f'{arm}|pair|{seed}|rep{rep}|{name}', arm=arm, design='pair', seed=seed,
                                rep=rep, branch=name, met_at_withdrawal=bool(s0.agent.shared))
            rec['withdrawal'] = vs.metrics(ev, WITHDRAW)
            lives.append(rec)
    return lives


def read_share(rows):
    return sum(r[1] == 'read' for r in rows) / len(rows)


def plastic_lives(seed, arm):
    """Real life: less reading for a while (daily invitations), then the common setting again."""
    s = grow(seed, 'reading', arm)
    s.phase('common')
    run_hours(s, PL_COMMON * 24)
    out, lives = {}, []
    for branch in ('stay', 'away'):
        c = copy.deepcopy(s)
        c.phase('away' if branch == 'away' else 'common2')
        i0 = len(c.trace)
        run_hours(c, PL_AWAY * 24, invite_daily=branch == 'away')
        mid = (snapshot(c.agent, c.tick // 24) if c.agent.evaluation else None)
        if branch == 'away':
            c.phase('washout')
            run_hours(c, 24)
            c.phase('after')
        i1 = len(c.trace)
        run_hours(c, PL_AFTER * 24 - (24 if branch == 'away' else 0))
        out[branch] = {'read_during': read_share(c.trace[i0:i1]), 'read_after': read_share(c.trace[i1:]),
                       'read_after_windows': [w['read'] for w in windows_of(c.trace[i1:])],
                       'snap_mid': mid, 'snap_end': snapshot(c.agent, c.tick // 24) if c.agent.evaluation else None}
        lives.append(L.life_record(c, life_id=f'{arm}|plastic|{seed}|{branch}', arm=arm, design='plastic', seed=seed,
                                   branch=branch))
    return out, lives


def worse_diag(seed, arm):
    """Isolated copy of a real reading-grown pet: reading feels half as good for 30 days."""
    if not ARMS[arm].get('evaluation'):
        return None
    s = grow(seed, 'reading', arm)
    run_hours(s, PL_COMMON * 24)
    out = {}
    for branch in ('normal', 'worse'):
        c = copy.deepcopy(s)
        a = c.agent
        if branch == 'worse':
            real = a.evaluate_experience
            a.evaluate_experience = lambda o, i, cf, en, real=real: real(o, i, cf * (0.5 if o == 'read' else 1.0),
                                                                          en * (0.5 if o == 'read' else 1.0))
        i0 = len(c.trace)
        run_hours(c, PL_AWAY * 24)
        q_mid = dict(a.Q)
        if branch == 'worse':
            del a.evaluate_experience
        i1 = len(c.trace)
        run_hours(c, 20 * 24)
        out[branch] = {'read_during': read_share(c.trace[i0:i1]), 'read_after': read_share(c.trace[i1:]),
                       'Q_mid': q_mid, 'Q_end': dict(a.Q), 'E_end_read': a.eval_term('read')}
    return out


PROBE_STATES = [(30, 80), (45, 60), (20, 95)]


def probe_read(a, day):
    """Mean score margin of read over the best other action at standard probe states
    (diagnostic copies; > 0 means read would be chosen)."""
    hits = n = 0
    for hunger, energy in PROBE_STATES:
        for bored in (0, 8):
            for hour in (10, 15):
                c = copy.deepcopy(a)
                c.now = day * 24 + hour
                c.hunger, c.energy, c.condition, c.shelter = float(hunger), float(energy), 100.0, 60.0
                c.inventory['food'], c.inventory['material'] = 6.0, 0.0
                c.goal, c.recent, c.invitation_until = None, ['explore'] * bored, -1
                scores = {x: c.score(x, day) for x in core.ACTIONS}
                other = max(v for x, v in scores.items() if x != 'read' and v is not None)
                hits += scores['read'] - other
                n += 1
    return hits / n


def rule_diag(seed):
    """Same counts / different experience, and same experience / different counts, fed to
    copies of one real state (synthetic experiences: diagnostic only)."""
    s = grow(seed, 'garden', 'eval')
    run_hours(s, 10 * 24)
    day = s.tick // 24
    out = {}
    for name, k, r in (('few_good', 10, 0.95), ('few_poor', 10, 0.45), ('many_good', 40, 0.95), ('many_poor', 40, 0.45)):
        a = copy.deepcopy(s.agent)
        for _ in range(k):
            a.evaluate_experience('read', -1, r, r)
        out[name] = {'Q': a.Q['read'], 'n': a.eval_n['read'], 'E': a.eval_term('read'), 'probe_read': probe_read(a, day),
                     'habit': a.habit['read']}
    a = copy.deepcopy(s.agent)
    out['none'] = {'Q': a.Q['read'], 'n': a.eval_n['read'], 'E': a.eval_term('read'), 'probe_read': probe_read(a, day)}
    return out


def seed_job(args):
    seed, arm = args
    routes = {r: route_life(seed, r, arm) for r in v5.ROUTES}
    plastic, pl_lives = plastic_lives(seed, arm)
    return {'seed': seed, 'arm': arm, 'routes': routes, 'pair': pair_lives(seed, arm), 'plastic': plastic,
            'plastic_lives': pl_lives, 'worse': worse_diag(seed, arm)}


def safe_job(args):
    seed, items, arm = args
    s = new_pet(seed, arm)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    s.apply({'kind': 'invite', 'value': None})
    s.phases = [('safe', 0)]
    run_hours(s, 60 * 24)
    return L.life_record(s, life_id=f"{arm}|safe|{seed}|{'+'.join(items)}", arm=arm, design='safe', seed=seed,
                         setting='+'.join(items))


# ---------------------------------------------------------------- analysis (birth seed = unit)
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def tv(p, q):
    return 0.5 * sum(abs(p[k] - q[k]) for k in L.CATEGORIES)


def r2(y, xs):
    """R^2 of an ordinary least-squares fit y ~ 1 + xs (xs: list of predictor lists)."""
    n = len(y)
    if n < len(xs) + 3:
        return None
    X = [[1.0] + [x[i] for x in xs] for i in range(n)]
    k = len(X[0])
    A = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    b = [sum(X[r][i] * y[r] for r in range(n)) for i in range(k)]
    for i in range(k):                                   # Gauss-Jordan with a tiny ridge
        A[i][i] += 1e-9
    M = [row + [bb] for row, bb in zip(A, b)]
    for i in range(k):
        piv = max(range(i, k), key=lambda r: abs(M[r][i]))
        M[i], M[piv] = M[piv], M[i]
        if abs(M[i][i]) < 1e-12:
            return None
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]
                M[r] = [a - f * c for a, c in zip(M[r], M[i])]
    beta = [M[i][k] / M[i][i] for i in range(k)]
    fit = [sum(bb * xx for bb, xx in zip(beta, X[r])) for r in range(n)]
    my = sum(y) / n
    sst = sum((v - my) ** 2 for v in y)
    return None if sst < 1e-15 else 1 - sum((v - f) ** 2 for v, f in zip(y, fit)) / sst


def seed_outcomes(job):
    R, P, PL = job['routes'], job['pair'], job['plastic']
    common = {r: R[r]['phases']['common'] for r in R}
    share = lambda r, k: common[r]['counts'].get(k, 0) / common[r]['hours']
    full = lambda r: {k: share(r, k) for k in L.CATEGORIES}
    gap_rep = [mean([m['withdrawal']['spont_per_day'] for m in P if m['rep'] == k and m['branch'] == 'B'])
               - mean([m['withdrawal']['spont_per_day'] for m in P if m['rep'] == k and m['branch'] == 'A']) for k in range(REPS)]
    o = {
        'read_gap': share('reading', 'read') - share('control', 'read'),
        'garden_gap': share('garden', 'garden') - share('control', 'garden'),
        'read_gap_windows': [a['read'] - b['read'] for a, b in zip(R['reading']['windows'], R['control']['windows'])],
        'read_gap_late': mean([a['read'] - b['read'] for a, b in zip(R['reading']['windows'][3:], R['control']['windows'][3:])]),
        'read_mean_all_routes': mean([share(r, 'read') for r in R]),
        'tv_mean_routes': mean([tv(full(a), full(b)) for i, a in enumerate(R) for b in list(R)[i + 1:]]),
        'tv_late': mean([tv(R[a]['windows'][w], R[b]['windows'][w]) for i, a in enumerate(R) for b in list(R)[i + 1:]
                         for w in range(3, COMMON // WINDOW)]),
        'entropy_common': mean([common[r]['entropy'] for r in R]),
        'visit_share_common': mean([share(r, 'visit') for r in R]),
        'top_non_sleep_common_max': max(max(v for k, v in full(r).items() if k != 'sleep') for r in R),
        'kinds_last_week_min': min(R[r]['whole']['kinds_last_week'] for r in R),
        'social_minus_garden_spont': R['social']['spont_per_day'] - R['garden']['spont_per_day'],
        'pair_B_minus_A_spont': mean(gap_rep),
        'pair_first_meet': {b: P[[m['branch'] for m in P].index(b)]['first_meet_tick'] for b in 'AB'},
        'pair_met_at_withdrawal': {b: P[[m['branch'] for m in P].index(b)]['met_at_withdrawal'] for b in 'AB'},
        'plastic_read_after_away_minus_stay': PL['away']['read_after'] - PL['stay']['read_after'],
        'plastic_read_during_away_minus_stay': PL['away']['read_during'] - PL['stay']['read_during'],
        'plastic_recovery_ratio': (PL['away']['read_after'] / PL['stay']['read_after']) if PL['stay']['read_after'] else None,
        'eval_decisive_share': mean([R[r]['eval_decisive_share'] for r in R]),
    }
    sw = [x for r in R.values() for x in r['swaps']]
    if sw:
        o['swap_changed'] = sum(x['swapped'] != x['normal'] for x in sw) / len(sw)
        o['off_changed'] = sum(x['off'] != x['normal'] for x in sw) / len(sw)
    snaps = [sn for r in R.values() for sn in r['snapshots']]
    both = [sn for sn in snaps if sn['n']['read'] > 0 and sn['n']['garden'] > 0]
    if snaps:
        dE = [sn['E']['read'] - sn['E']['garden'] for sn in snaps]
        dh = [sn['habit']['read'] - sn['habit']['garden'] for sn in snaps]
        dn = [math.log1p(sn['n']['read']) - math.log1p(sn['n']['garden']) for sn in snaps]
        o['r2_E_by_habit'] = r2(dE, [dh])
        o['r2_E_by_habit_and_count'] = r2(dE, [dh, dn])
        if len(both) > 5:
            dq = [sn['Q']['read'] - sn['Q']['garden'] for sn in both]
            o['r2_Q_by_habit_and_count'] = r2(dq, [[sn['habit']['read'] - sn['habit']['garden'] for sn in both],
                                                   [math.log1p(sn['n']['read']) - math.log1p(sn['n']['garden']) for sn in both]])
            dqf = [sn['Q_fresh']['read'] - sn['Q_fresh']['garden'] for sn in both]
            o['r2_Qfresh_by_habit_and_count'] = r2(dqf, [[sn['habit']['read'] - sn['habit']['garden'] for sn in both],
                                                         [math.log1p(sn['n']['read']) - math.log1p(sn['n']['garden']) for sn in both]])
            o['sd_Q_diff'] = (sum((v - mean(dq)) ** 2 for v in dq) / len(dq)) ** 0.5
            o['mean_abs_Q_diff'] = mean([abs(v) for v in dq])
        o['mean_abs_E'] = mean([abs(sn['E'][k]) for sn in snaps for k in engine.EVAL_KEYS])
        o['eval_term_max_points'] = engine.EVAL_WEIGHT * max(abs(sn['E'][k]) for sn in snaps for k in engine.EVAL_KEYS)
        end = {r: R[r]['snapshots'][-1] for r in R}
        o['E_read_reading_minus_control_end'] = end['reading']['E']['read'] - end['control']['E']['read']
        o['E_garden_garden_minus_control_end'] = end['garden']['E']['garden'] - end['control']['E']['garden']
        o['Q_read_reading_minus_garden_route_end'] = end['reading']['Q']['read'] - end['garden']['Q']['read']
    # Does E predict the next 5 days of reading beyond habit and experience count? (snapshots every
    # 2nd day; overlapping windows, so a diagnostic, not a test.) In 'eval_nodecision' E never acts,
    # so a gain there would be information E carries; in 'eval' it can also be E's own effect.
    X = []
    for r in R.values():
        for sn in r['snapshots']:
            d = sn['day']
            if (d - GROW) % 2 == 0 and d + 5 <= GROW + COMMON:
                X.append((sum(r['daily_read'][x] for x in range(d, d + 5)) / 120, sn['habit']['read'],
                          math.log1p(sn['n']['read']), sn['E']['read'], sn['Q']['read'] - (sn['base'] or 0)))
    if len(X) > 10:
        y = [x[0] for x in X]
        r_h = r2(y, [[x[1] for x in X], [x[2] for x in X]])
        r_he = r2(y, [[x[1] for x in X], [x[2] for x in X], [x[3] for x in X]])
        o['r2_next_read_by_habit_count'] = r_h
        o['delta_r2_next_read_from_E'] = None if r_h is None or r_he is None else r_he - r_h
    W = job['worse']
    if W:
        o['worse_read_during_minus_normal'] = W['worse']['read_during'] - W['normal']['read_during']
        o['worse_read_after_minus_normal'] = W['worse']['read_after'] - W['normal']['read_after']
        o['worse_Q_mid_minus_normal'] = W['worse']['Q_mid']['read'] - W['normal']['Q_mid']['read']
    return o


def summarise(jobs, safe, seeds, arms):
    out = {}
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for arm in arms:
        per = {j['seed']: seed_outcomes(j) for j in jobs if j['arm'] == arm}
        lives = ([m for j in jobs if j['arm'] == arm for m in list(j['routes'].values()) + j['pair'] + j['plastic_lives']]
                 + [m for m in safe if m['arm'] == arm])
        keys = sorted({k for sd in seeds for k, v in per[sd].items() if num(v)})
        out[arm] = {'seeds': seeds, 'per_seed': per, 'safety': L.safety_summary(lives),
                    'describe': {k: L.describe([per[sd].get(k) for sd in seeds]) for k in keys},
                    'windows_read_gap': [mean([per[sd]['read_gap_windows'][w] for sd in seeds]) for w in range(COMMON // WINDOW)],
                    'never_met_at_withdrawal': {b: sum(not per[sd]['pair_met_at_withdrawal'][b] for sd in seeds) for b in 'AB'},
                    'goal_endings': sum((Counter(r['goal_endings']) for j in jobs if j['arm'] == arm for r in j['routes'].values()), Counter())}
    return out


def contrast(out, a, b, key):
    xs = [out[a]['per_seed'][sd].get(key) for sd in out[a]['seeds']]
    ys = [out[b]['per_seed'][sd].get(key) for sd in out[b]['seeds']]
    return L.describe([None if x is None or y is None else x - y for x, y in zip(xs, ys)])


CONTRAST_KEYS = ('read_gap', 'garden_gap', 'read_gap_late', 'tv_mean_routes', 'tv_late', 'read_mean_all_routes',
                 'plastic_read_after_away_minus_stay', 'pair_B_minus_A_spont', 'social_minus_garden_spont', 'entropy_common')
CONTRASTS = [('eval', 'base'), ('base', 'v6'), ('base', 'v5'), ('eval', 'v5'), ('eval', 'eval_flat'), ('eval', 'eval_frozen'),
             ('eval_nodecision', 'base'), ('eval_flat', 'base'), ('eval_frozen', 'base'), ('ordered_noint', 'base'), ('ordered_only', 'base'), ('ordered_only', 'v6')]


def evaluate(out):
    """Phase A verdict on the fixed CRITERIA (unrounded values)."""
    C, b, ref = CRITERIA, out['base'], out[CRITERIA['A2_phase_fails_vs']]
    fails = lambda o: o['safety']['unique_trajectories'] - o['safety']['phase_pass']
    pg = b['describe']['pair_B_minus_A_spont']
    v = {'A1_base_safe_every_unique_life': b['safety']['pass'] == b['safety']['unique_trajectories'],
         'A2_phase_fails_not_above_v6': fails(b) <= fails(ref),
         'A3_social_kept': pg['mean'] >= C['A3_min_gap'] and pg['positive'] >= C['A3_min_positive'] and pg['ci95'][0] > 0,
         'A4_diversity': b['describe']['entropy_common']['mean'] >= ref['describe']['entropy_common']['mean'] - C['A4_max_entropy_drop_vs_v6']}
    v['_values'] = {'phase_fails': {a: fails(o) for a, o in out.items()},
                    'cost_vs_v6': {k: contrast(out, 'base', 'v6', k) for k in ('read_gap', 'garden_gap', 'tv_mean_routes')},
                    'cost_vs_v5': {k: contrast(out, 'base', 'v5', k) for k in ('read_gap', 'garden_gap', 'tv_mean_routes')}}
    return v


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    arms = list(ARMS) if which == 'dev' else list(VALIDATION_ARMS)
    with Pool(14) as pool:
        jobs = pool.map(seed_job, [(sd, arm) for arm in arms for sd in seeds])
        safe = pool.map(safe_job, [(sd, it, arm) for arm in arms for sd in SAFE_SEEDS for it in SAFE_ITEMS])
        rules = pool.map(rule_diag, seeds[:6]) if which == 'dev' else []
    out = summarise(jobs, safe, seeds, arms)
    contrasts = {f'{a} - {b}': {k: contrast(out, a, b, k) for k in CONTRAST_KEYS}
                 for a, b in CONTRASTS if a in out and b in out}
    verdict = evaluate(out)
    compat = L.compat_check()
    final = None
    if verdict is not None:
        final = {**{k: v for k, v in verdict.items() if not k.startswith('_')}, 'compat_v1_v6': compat['pass']}
        final['phase_A_base_confirmed'] = all(v is True for v in final.values())
        final['candidate_eval'] = DEV_DECISION
        final['_values'] = verdict.get('_values')
    report = {'sample': which, 'seeds': seeds, 'config_id': CONFIG_ID, 'arms': ARMS, 'params': PARAMS, 'dev_decision': DEV_DECISION,
              'criteria': CRITERIA, 'final': final, 'compat': compat,
              'arms_summary': {a: {k: v for k, v in o.items() if k != 'per_seed'} for a, o in out.items()},
              'per_seed': {a: o['per_seed'] for a, o in out.items()}, 'contrasts': contrasts, 'rule_diag': rules,
              'worse_diag': {j['seed']: j['worse'] for j in jobs if j['arm'] == CANDIDATE}}
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    dst.mkdir(parents=True, exist_ok=True)
    slim = lambda m: {k: v for k, v in m.items() if k not in ('goal_by_day', 'plan_log', 'goal_history', 'swaps')}
    lives = [slim(m) for j in jobs for m in list(j['routes'].values()) + j['pair'] + j['plastic_lives']] + [slim(m) for m in safe]
    (dst / f'eval_{which}_raw.json').write_text(json.dumps({'lives': lives}, ensure_ascii=False, default=str), encoding='utf-8')
    (dst / f'eval_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    show = {a: {k: o['describe'][k].get('mean') for k in o['describe']} for a, o in out.items()}
    print(json.dumps(L.rounded({'config_id': CONFIG_ID, 'arms': show,
                                'safety': {a: {k: v for k, v in o['safety'].items() if k != 'failing'} for a, o in out.items()},
                                'contrasts': {c: {k: {x: d[k].get(x) for x in ('n', 'mean', 'ci95', 'positive', 'negative')}
                                                  for k in ('read_gap', 'garden_gap', 'tv_mean_routes', 'plastic_read_after_away_minus_stay')}
                                              for c, d in contrasts.items()},
                                'final': final}), ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
