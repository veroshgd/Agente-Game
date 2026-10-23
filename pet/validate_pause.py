"""Experiment 'pause' (2026-10-23): does stashing a leisure plan during an urgent repair, and
re-weighing it afterwards, keep interests going after the repair? Product experiment.

    python -m pet.validate_pause dev [out_dir]          # seeds 3001-3010 + 6001-6010 (development / review)
    python -m pet.validate_pause validation [out_dir]   # seeds 7001-7020, ONCE, after CRITERIA were fixed

Arms (one change at a time; every other parameter as in v5). The maintenance rule x the
neighbor rule; 'end_open_*' are diagnostic arms, never candidates:
                 cap2 (2 unprompted visits a day)   rest4 (she rests 4 h after playing)
    none         v5            (baseline)            v5_rest4     (only the social rule)
    end          end_cap2      (only the interrupt)  v6           (current candidate v6)
    pause        pause_cap2    (new maintenance)     pause_rest4  (new combined candidate)
    end_open     end_open_cap2                       end_open_rest4
'end' is the v6 interrupt as recorded: it also ends plans the core closes that very morning as
'done' or 'stalled', which skips the core's 'done' memory and 6-day satiation. 'pause' leaves
those to the core (a pause must not hide a finished or failed plan); 'end_open' ends only
the plans 'pause' would stash, so pause - end_open isolates stash-and-resume itself.

Design per arm and birth seed (same seeds, routes, objects, invitations and lengths for all):
  routes  v5 design: grow 20 days on control / reading / garden / social, then garden + book
          and one invitation for everyone, 60 common days.
  pair    grow 20 days on reading -> uniform -> A (nothing) / B (invitation every morning) for
          30 days -> 1 washout day -> 30 withdrawal days, 3 continuation replicates (rep 0 = the
          original stream, reps 1-2 re-seed the pet's generator at the withdrawal start, the
          same for A and B). Replicates are averaged within the seed; no branch is dropped
          for never having met the neighbor, and first meetings are reported.
  safe    the v4 safe-home lives (6 seeds x 2 settings, 60 days), the same for every arm.
Every life is recorded hour by hour from birth (pet.lifestats) and safety-checked whole.

Definitions, fixed before the dev run:
  interruption   a morning with the trigger of v6 (home < HOME_INTERRUPT_BELOW, a learn /
                 see_the_world plan, improve_home ahead by the core's switch margin) on a plan
                 the core would not close that morning. Under 'none' the trigger is logged
                 (diagnostics) and the plan goes on. A trigger inside a running episode is
                 part of it.
  repair end     the first lived hour at or after the trigger with the home >= PAUSE_RESUME_AT.
  observation    starts at the repair end. The related action is a core 'read' for a learn
                 plan, a core 'explore' (garden, visit, explore) for see_the_world. Wait =
                 hours from the repair end to the first related action after it. Episodes with
                 no repair end, or no related action before the life ends, are counted apart,
                 never as 0 h, and stay in every denominator. Related hours = related actions
                 in the OBS_HOURS after the repair end (censored if the life ends first).
                 Added after the dev run showed 'any related action within 72 h' at ~100% in
                 every arm (a ceiling), before any validation seed.
  returned       'pause': the same plan (plan_id) resumed. All arms: a plan of the same type
                 is the morning goal within 3 days after the repair end.
"""
import copy
import hashlib
import json
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from . import engine
from . import lifestats as L
from . import validate_v5 as v5
from . import validate_v5_social as vs

DEV_SEEDS = list(range(3001, 3011)) + list(range(6001, 6011))      # already viewed: development / review
VALIDATION_SEEDS = list(range(7001, 7021))                          # unused before 2026-10-23 (checked)
SAFE_SEEDS = (1, 42, 901, 7, 123, 2024)
SAFE_ITEMS = (('garden',), ('garden', 'book', 'music'))
GROW, COMMON, PHASE, WASHOUT, WITHDRAW, REPS, WINDOW = 20, 60, 30, 1, 30, 3, 10
RETURN_DAYS = 3
OBS_HOURS = 72                 # window after the repair end for 'related hours'
ARMS = {                       # id: (neighbor scheme, maintenance)
    'v5': ('cap2', 'none'), 'v5_rest4': ('rest4', 'none'),
    'end_cap2': ('cap2', 'end'), 'v6': ('rest4', 'end'),
    'pause_cap2': ('cap2', 'pause'), 'pause_rest4': ('rest4', 'pause'),
    'end_open_cap2': ('cap2', 'end_open'), 'end_open_rest4': ('rest4', 'end_open'),
}
SIX = ('v5', 'v5_rest4', 'end_cap2', 'v6', 'pause_cap2', 'pause_rest4')
CANDIDATE = 'pause_rest4'
PARAMS = {k: getattr(engine, k) for k in ('HOME_INTERRUPT_BELOW', 'PAUSE_RESUME_AT', 'PAUSE_MAX_DAYS',
                                          'PAUSE_MAX_RESUMES', 'V6_REST_HOURS', 'MILI_VISITS_PER_DAY',
                                          'PREF_RATE', 'PREF_WEIGHT', 'SOCIAL_RATE', 'PREF_GOAL',
                                          'TRAIT_HOME_PULL', 'VISIT_MEMORY')}
CONFIG_ID = hashlib.sha256(json.dumps({'arms': ARMS, 'params': PARAMS, 'design': [GROW, COMMON, PHASE, WASHOUT,
                                       WITHDRAW, REPS, WINDOW, RETURN_DAYS]}, sort_keys=True).encode()).hexdigest()[:12]
# ---- FIXED 2026-10-23 after the dev run (3001-3010 + 6001-6010) and BEFORE seeds 7001-7020.
# Dev result known when fixing: real interruptions of open plans are rare (~1 per seed in 4 x 80
# days); the reading gap of pause_rest4 was below v6 and v5; pause - end_open was +0.8 h.
# Parameters were not tuned on dev results (sensitivity in AI juego/diag_pause_sensitivity.py:
# PAUSE_RESUME_AT 20-45, PAUSE_MAX_DAYS 2-6, PAUSE_MAX_RESUMES 1-4 change almost nothing).
# Product reasons for the thresholds:
#  K1  +2 related hours in the 3 days after a repair (~40 min a day of the interrupted
#      activity), visible in the diary as "went back to it"; the reference is v6, the current
#      'end the plan' rule. Fewer than 8 seeds with episodes in both arms = evidence insufficient.
#  K2  1 pp of all hours ~ 1.7 more reading hours a week for the reading-grown pet; positive in
#      at least 12 of 20 seeds; at most 0.5 pp worse than v5 on the same seeds. "Everyone reads
#      more" (read_mean_all_routes) is reported separately and decides nothing.
#  S   1/7 = one more unprompted visit a week (the 2026-10-17 unit), on the pair design from
#      birth (replicate means) and on the social - garden routes.
#  H   the v4 safe-home standard on every unique whole life; phase share failures no more than v5's.
#  D/L entropy at most 0.1 bits below v5; no activity but sleep above 60%; visits <= 12%;
#      no resume -> re-pause within 2 days; improve_home goal-days at most 5 points above v5.
CRITERIA = {
    'reference': 'v6',
    'K1_min_gain_hours': 2.0, 'K1_min_seeds_with_episodes': 8,
    'K2_min_read_gap': 0.01, 'K2_min_positive_seeds': 12, 'K2_max_drop_vs_v5': 0.005,
    'S_min_gap': 1 / 7, 'S_min_positive_seeds': 14,
    'D_max_entropy_drop': 0.1, 'D_max_top_share': 0.6, 'D_max_visit_share': 0.12,
    'L_max_improve_home_days_over_v5': 0.05,
}


def configure(s, arm):
    scheme, maint = ARMS[arm]
    vs.set_scheme(s, scheme)
    a = s.agent
    a.home_interrupt = maint != 'none'
    a.goal_pause = maint == 'pause'
    a.interrupt_open_only = maint == 'end_open'
    a.diagnostics = True          # social_diag + would-be interrupts; no behavior change (tested)
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


def grow(seed, route, arm, before=None):
    spec = v5.ROUTES[route]
    s = new_pet(seed, arm)
    for obj in spec['objects']:
        s.apply({'kind': 'object', 'value': obj})
    run_hours(s, GROW * 24, invite_daily=spec['invite_daily'], before=before)
    v5.uniform(s)
    return s


# ---------------------------------------------------------------- plan continuity
RELATED = {'learn': 'read', 'see_the_world': 'explore'}


def episodes(s):
    """Interruption episodes of one life, with the definitions in the module docstring."""
    trace, log = s.trace, s.agent.plan_log
    trig = [e for e in log if (e['event'] == 'paused'
                               or (e['event'] in ('trigger_kept', 'ended') and e.get('core_closes') is None))]
    out, busy_until = [], -1
    for e in trig:
        if e['tick'] < busy_until:
            continue
        rows = [r for r in trace if r[0] >= e['tick']]
        rep = next((r[0] for r in rows if r[3] >= engine.PAUSE_RESUME_AT), None)
        ep = {'tick': e['tick'], 'day': e['day'], 'type': e['type'], 'event': e['event'], 'plan_id': e.get('plan_id'),
              'repair_end': rep, 'wait': None, 'status': 'not_repaired', 'returned_same_type': None,
              'related_hours': None}
        if rep is None:
            out.append(ep)
            busy_until = 10 ** 9
            continue
        busy_until = rep
        nxt = next((r[0] for r in trace if r[0] > rep and r[2] == RELATED[e['type']]), None)
        ep['status'] = 'related_action' if nxt is not None else 'no_related_action'
        if trace[-1][0] >= rep + OBS_HOURS:          # else the life ended first: censored (None)
            ep['related_hours'] = sum(1 for r in trace if rep < r[0] <= rep + OBS_HOURS and r[2] == RELATED[e['type']])
        ep['wait'] = None if nxt is None else nxt - rep
        d0 = rep // 24
        days = s.agent.goal_by_day[d0 + 1:d0 + 1 + RETURN_DAYS]
        ep['returned_same_type'] = (e['type'] in days) if len(days) == RETURN_DAYS else None   # None: life ended
        out.append(ep)
    return out


def plan_fates(s):
    """'pause' arms: what became of every stashed plan (by plan_id)."""
    log, hist = s.agent.plan_log, s.agent.goal_history
    plans = {}
    for e in log:
        if e['event'] in ('paused', 'resumed', 'dropped') or (e['event'] == 'ended' and e.get('reason') == 'resume_limit'):
            if e['plan_id'] is None:
                continue
            p = plans.setdefault(e['plan_id'], {'type': e['type'], 'pauses': 0, 'resumes': 0, 'events': []})
            p['events'].append((e['day'], e['event'], e.get('reason')))
            p['pauses'] += e['event'] == 'paused'
            p['resumes'] += e['event'] == 'resumed'
    open_id = s.agent.goal.get('plan_id') if s.agent.goal else None
    paused_id = s.agent.paused_goal['goal']['plan_id'] if s.agent.paused_goal else None
    for pid, p in plans.items():
        closed = [g for g in hist if g.get('plan_id') == pid]
        last = p['events'][-1]
        if last[1] == 'dropped':
            p['fate'] = 'dropped_' + last[2]
        elif last[1] == 'ended':
            p['fate'] = 'ended_resume_limit'
        elif pid == paused_id:
            p['fate'] = 'still_paused_at_end'
        elif closed:
            p['fate'] = 'resumed_then_' + closed[-1]['outcome']
        elif pid == open_id:
            p['fate'] = 'resumed_still_open_at_end'
        else:
            p['fate'] = 'unknown'
        days = [d for d, ev, _ in p['events']]
        p['repause_within_2d'] = sum(1 for (d1, e1, _), (d2, e2, _) in zip(p['events'], p['events'][1:])
                                     if e1 == 'resumed' and e2 == 'paused' and d2 - d1 <= 2)
        p['span_days'] = (closed[-1]['closed_day'] if closed else days[-1]) - int(pid.split('@')[1])
    return plans


def goal_outcomes(s):
    c = Counter()
    for g in s.agent.goal_history:
        if g['type'] in engine.LEISURE_GOALS:
            c[(g['type'], g['outcome'], bool(g.get('resumes')))] += 1
    return {f'{t}|{o}|{"resumed" if r else "plain"}': n for (t, o, r), n in c.items()}


def reading_days(s, start_index):
    """Common phase: share of days with any reading, and mean length of reading-day runs."""
    rows = s.trace[start_index:]
    days = {}
    for r in rows:
        days.setdefault(r[0] // 24, 0)
        days[r[0] // 24] += r[2] == 'read'
    seq = [days[d] > 0 for d in sorted(days)]
    runs, cur = [], 0
    for x in seq + [False]:
        if x:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    return {'share_days': sum(seq) / len(seq), 'mean_run': sum(runs) / len(runs) if runs else 0.0, 'runs': len(runs)}


def isolated_pause_vs_end(snaps, hours=96):
    """Diagnostic on isolated copies (never a lived event): from the same morning state in which
    the trigger is about to be checked, live `hours` with the plan stashed vs ended."""
    out = []
    for snap in snaps:
        res = {}
        for mode in ('pause', 'end_open'):
            c = copy.deepcopy(snap)
            c.agent.goal_pause, c.agent.interrupt_open_only = mode == 'pause', mode == 'end_open'
            c.agent.home_interrupt = True
            gtype = c.agent.goal['type']
            n0 = len(c.agent.plan_log)
            for _ in range(hours):
                c.step()
            fired = any(e['event'] in ('paused', 'ended') for e in c.agent.plan_log[n0:n0 + 3])
            rows = c.trace[-hours:]
            res[mode] = {'related_hours': sum(r[2] == RELATED[gtype] for r in rows), 'fired': fired}
        if res['pause']['fired']:
            out.append({'type': gtype, 'diff_related_hours': res['pause']['related_hours'] - res['end_open']['related_hours']})
    return out


def snapshot_hook(snaps):
    def before(x):
        a = x.agent
        if (x.tick % 24 == 0 and a.shelter < engine.HOME_INTERRUPT_BELOW and a.goal
                and a.goal['type'] in engine.LEISURE_GOALS and a.paused_goal is None):
            snaps.append(copy.deepcopy(x))
    return before


# ---------------------------------------------------------------- jobs
def route_life(seed, route, arm, diag=False):
    snaps = []
    s = grow(seed, route, arm)
    s.phase('common')
    start = len(s.trace)
    run_hours(s, COMMON * 24, before=snapshot_hook(snaps) if diag and ARMS[arm][1] == 'pause' else None)
    rec = L.life_record(s, life_id=f'{arm}|route|{seed}|{route}', arm=arm, design='route', seed=seed, setting=route)
    rows = s.trace[start:]
    windows = []
    for w in range(0, len(rows), WINDOW * 24):
        part = rows[w:w + WINDOW * 24]
        acts = Counter(r[1] for r in part)
        windows.append({k: acts[k] / len(part) for k in L.CATEGORIES})
    rec['windows'] = windows
    ev = [e for e in s.events if e['kind'] == 'action' and e['tick'] >= GROW * 24]
    rec['spont_per_day'] = sum(e['action'] == 'visit' and not e['invited'] for e in ev) / COMMON
    rec['episodes'] = episodes(s)
    rec['plan_fates'] = plan_fates(s)
    rec['goal_outcomes'] = goal_outcomes(s)
    rec['reading_days'] = reading_days(s, start)
    rec['isolated'] = isolated_pause_vs_end(snaps) if snaps else []
    rec['improve_home_days_common'] = sum(g == 'improve_home' for g in s.agent.goal_by_day[GROW:]) / COMMON
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
        assert s.tick >= s.agent.invitation_until, 'an invitation is still pending at withdrawal'
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


def seed_job(args):
    seed, arm, diag = args
    routes = {r: route_life(seed, r, arm, diag) for r in v5.ROUTES}
    return {'seed': seed, 'arm': arm, 'routes': routes, 'pair': pair_lives(seed, arm)}


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


# ---------------------------------------------------------------- per-seed outcomes and arms
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def tv(p, q):
    return 0.5 * sum(abs(p[k] - q[k]) for k in L.CATEGORIES)


def seed_outcomes(job):
    """One number per (arm, birth seed) for each outcome. Replicates are averaged first."""
    R, P = job['routes'], job['pair']
    common = {r: R[r]['phases']['common'] for r in R}
    share = lambda r: {k: common[r]['counts'].get(k, 0) / common[r]['hours'] for k in L.CATEGORIES}
    eps = [e for r in R.values() for e in r['episodes']]
    rel = [e for e in eps if e['status'] == 'related_action']
    fates = Counter(p['fate'] for r in R.values() for p in r['plan_fates'].values())
    pauses = [p['pauses'] for r in R.values() for p in r['plan_fates'].values()]
    gap_rep = [mean([m['withdrawal']['spont_per_day'] for m in P if m['rep'] == k and m['branch'] == 'B'])
               - mean([m['withdrawal']['spont_per_day'] for m in P if m['rep'] == k and m['branch'] == 'A']) for k in range(REPS)]
    iso = [x['diff_related_hours'] for r in R.values() for x in r['isolated']]
    return {
        'read_gap': common['reading']['read'] - common['control']['read'],
        'read_gap_windows': [a['read'] - b['read'] for a, b in zip(R['reading']['windows'], R['control']['windows'])],
        'read_mean_all_routes': mean([common[r]['read'] for r in R]),
        'read_share': {r: common[r]['read'] for r in R},
        'tv_reading_control': tv(share('reading'), share('control')),
        'tv_reading_control_windows': [tv(a, b) for a, b in zip(R['reading']['windows'], R['control']['windows'])],
        'tv_mean_pairs': mean([tv(share(a), share(b)) for i, a in enumerate(R) for b in list(R)[i + 1:]]),
        'social_minus_garden_spont': R['social']['spont_per_day'] - R['garden']['spont_per_day'],
        'pair_B_minus_A_spont': mean(gap_rep), 'pair_B_minus_A_rep0': gap_rep[0],
        'pair_first_meet': {b: P[[m['branch'] for m in P].index(b)]['first_meet_tick'] for b in 'AB'},
        'pair_met_at_withdrawal': {b: P[[m['branch'] for m in P].index(b)]['met_at_withdrawal'] for b in 'AB'},
        'entropy_common': mean([common[r]['entropy'] for r in R]),
        'visit_share_common': mean([share(r)['visit'] for r in R]),
        'top_non_sleep_common_max': max(max(v for k, v in share(r).items() if k != 'sleep') for r in R),
        'kinds_last_week_min': min(R[r]['whole']['kinds_last_week'] for r in R),
        'episodes': len(eps), 'episodes_related': len(rel),
        'episodes_not_repaired': sum(e['status'] == 'not_repaired' for e in eps),
        'episodes_no_related_action': sum(e['status'] == 'no_related_action' for e in eps),
        'related_within_24h': (sum(e['wait'] <= 24 for e in rel) / len(eps)) if eps else None,
        'related_within_72h': (sum(e['wait'] <= 72 for e in rel) / len(eps)) if eps else None,
        'related_hours_72h': mean([e['related_hours'] for e in eps if e['status'] != 'not_repaired']),
        'related_hours_72h_censored': sum(e['status'] != 'not_repaired' and e['related_hours'] is None for e in eps),
        'median_wait_observed': sorted(e['wait'] for e in rel)[len(rel) // 2] if rel else None,
        'returned_same_type_3d': (sum(bool(e['returned_same_type']) for e in eps if e['returned_same_type'] is not None)
                                  / max(1, sum(e['returned_same_type'] is not None for e in eps))) if eps else None,
        'plan_fates': dict(fates), 'max_pauses_per_plan': max(pauses, default=0),
        'repause_within_2d': sum(p['repause_within_2d'] for r in R.values() for p in r['plan_fates'].values()),
        'max_plan_span_days': max((p['span_days'] for r in R.values() for p in r['plan_fates'].values()), default=0),
        'goal_outcomes': sum((Counter(r['goal_outcomes']) for r in R.values()), Counter()),
        'reading_days_share_reading_route': R['reading']['reading_days']['share_days'],
        'reading_run_reading_route': R['reading']['reading_days']['mean_run'],
        'improve_home_goal_days_common': mean([r['improve_home_days_common'] for r in R.values()]),
        'v6_ended_finished_plans': sum(1 for r in R.values() for e in r['plan_log']
                                       if e['event'] == 'ended' and e.get('core_closes')),
        'isolated_pause_minus_end_related_h': mean(iso), 'isolated_n': len(iso),
    }


def contrast(out, a, b, key):
    """Paired by birth seed: arm a - arm b."""
    xs = [out[a]['per_seed'][sd][key] for sd in out[a]['seeds']]
    ys = [out[b]['per_seed'][sd][key] for sd in out[b]['seeds']]
    return L.describe([None if x is None or y is None else x - y for x, y in zip(xs, ys)])


def summarise(jobs, safe, seeds):
    out = {}
    for arm in ARMS:
        per = {j['seed']: seed_outcomes(j) for j in jobs if j['arm'] == arm}
        lives = ([m for j in jobs if j['arm'] == arm for m in list(j['routes'].values()) + j['pair']]
                 + [m for m in safe if m['arm'] == arm])
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        keys = [k for k in per[seeds[0]] if all(num(per[sd][k]) or per[sd][k] is None for sd in seeds)
                and any(num(per[sd][k]) for sd in seeds)]
        out[arm] = {'seeds': seeds, 'per_seed': per, 'safety': L.safety_summary(lives),
                    'describe': {k: L.describe([per[sd][k] for sd in seeds]) for k in keys},
                    'windows_read_gap': [mean([per[sd]['read_gap_windows'][w] for sd in seeds]) for w in range(COMMON // WINDOW)],
                    'windows_tv': [mean([per[sd]['tv_reading_control_windows'][w] for sd in seeds]) for w in range(COMMON // WINDOW)],
                    'plan_fates': sum((Counter(per[sd]['plan_fates']) for sd in seeds), Counter()),
                    'goal_outcomes': sum((Counter(per[sd]['goal_outcomes']) for sd in seeds), Counter()),
                    'never_met_at_withdrawal': {b: sum(not per[sd]['pair_met_at_withdrawal'][b] for sd in seeds) for b in 'AB'}}
    return out


CONTRASTS = [('pause_rest4', 'v6'), ('pause_cap2', 'end_cap2'), ('pause_rest4', 'v5'), ('v6', 'v5'),
             ('end_cap2', 'v5'), ('v5_rest4', 'v5'), ('pause_cap2', 'v5'), ('pause_rest4', 'v5_rest4'),
             ('pause_rest4', 'end_open_rest4'), ('pause_cap2', 'end_open_cap2'),
             ('end_open_rest4', 'v6'), ('end_open_cap2', 'end_cap2')]
CONTRAST_KEYS = ('related_hours_72h', 'read_gap', 'read_mean_all_routes', 'tv_reading_control', 'related_within_72h', 'related_within_24h',
                 'returned_same_type_3d', 'pair_B_minus_A_spont', 'social_minus_garden_spont', 'entropy_common')


def evaluate(out):
    """Fixed criteria -> one verdict block (unrounded values). 'insufficient' counts as not met."""
    C = CRITERIA
    cand, base = out[CANDIDATE], out['v5']
    d, b = cand['describe'], base['describe']
    k1 = contrast(out, CANDIDATE, C['reference'], 'related_hours_72h')
    k2 = contrast(out, CANDIDATE, 'v5', 'read_gap')
    n_seeds = len(cand['seeds'])
    v = {}
    if k1['n'] < C['K1_min_seeds_with_episodes']:
        v['K1_continuity'] = 'insufficient'
    else:
        v['K1_continuity'] = k1['mean'] >= C['K1_min_gain_hours'] and k1['ci95'][0] > 0
    v['K2_differentiation'] = (d['read_gap']['mean'] >= C['K2_min_read_gap']
                               and d['read_gap']['positive'] >= C['K2_min_positive_seeds']
                               and k2['mean'] >= -C['K2_max_drop_vs_v5'])
    v['H_safety'] = cand['safety']['pass'] == cand['safety']['unique_trajectories']
    v['H_phase_no_worse_than_v5'] = ((cand['safety']['unique_trajectories'] - cand['safety']['phase_pass'])
                                     <= (base['safety']['unique_trajectories'] - base['safety']['phase_pass']))
    pg, rg = d['pair_B_minus_A_spont'], d['social_minus_garden_spont']
    v['S_social'] = (pg['mean'] >= C['S_min_gap'] and pg['positive'] >= C['S_min_positive_seeds'] and pg['ci95'][0] > 0
                     and rg['mean'] >= C['S_min_gap'])
    v['D_diversity'] = (d['entropy_common']['mean'] >= b['entropy_common']['mean'] - C['D_max_entropy_drop']
                        and min(d['kinds_last_week_min']['per_seed']) >= L.H['min_kinds_last_week']
                        and max(d['top_non_sleep_common_max']['per_seed']) <= C['D_max_top_share']
                        and d['visit_share_common']['mean'] <= C['D_max_visit_share'])
    v['L_no_loops'] = (max(d['max_pauses_per_plan']['per_seed']) <= engine.PAUSE_MAX_RESUMES + 1
                       and sum(d['repause_within_2d']['per_seed']) == 0
                       and d['improve_home_goal_days_common']['mean']
                       <= b['improve_home_goal_days_common']['mean'] + C['L_max_improve_home_days_over_v5'])
    v['_values'] = {'K1': k1, 'K2_gap': d['read_gap'], 'K2_change_vs_v5': k2, 'n_seeds': n_seeds,
                    'R1_historical_ratio': (d['read_gap']['mean'] / b['read_gap']['mean']) if b['read_gap']['mean'] else None,
                    'R1_note': 'historical ratio to v5; unstable when the v5 gap is near 0; decides nothing here'}
    return v


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    with Pool(14) as pool:
        jobs = pool.map(seed_job, [(sd, arm, True) for arm in ARMS for sd in seeds])
        safe = pool.map(safe_job, [(sd, it, arm) for arm in ARMS for sd in SAFE_SEEDS for it in SAFE_ITEMS])
    out = summarise(jobs, safe, seeds)
    contrasts = {f'{a} - {b}': {k: contrast(out, a, b, k) for k in CONTRAST_KEYS} for a, b in CONTRASTS}
    verdict = evaluate(out)
    compat = L.compat_check()
    final = {**{k: x for k, x in verdict.items() if k != '_values'}, 'compat_v1_v6': compat['pass']}
    final['candidate_for_next_round'] = all(x is True for x in final.values())
    final['_values'] = verdict['_values']
    report = {'sample': which, 'seeds': seeds, 'config_id': CONFIG_ID, 'arms': ARMS, 'params': PARAMS,
              'candidate': CANDIDATE, 'criteria': CRITERIA, 'final': final, 'compat': compat,
              'arms_summary': {arm: {k: v for k, v in o.items() if k != 'per_seed'} for arm, o in out.items()},
              'per_seed': {arm: o['per_seed'] for arm, o in out.items()}, 'contrasts': contrasts}
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    dst.mkdir(parents=True, exist_ok=True)
    slim = lambda m: {k: v for k, v in m.items() if k not in ('goal_by_day', 'plan_log', 'goal_history')}
    lives = [slim(m) for j in jobs for m in list(j['routes'].values()) + j['pair']] + [slim(m) for m in safe]
    (dst / f'pause_{which}_raw.json').write_text(json.dumps({'lives': lives, 'plan_logs': {
        m['life_id']: m['plan_log'] for j in jobs for m in j['routes'].values()}}, ensure_ascii=False, default=str), encoding='utf-8')
    (dst / f'pause_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    show = {arm: {k: (o['describe'][k]['mean'] if o['describe'][k].get('n') else None) for k in CONTRAST_KEYS + (
        'episodes', 'v6_ended_finished_plans')} for arm, o in out.items()}
    print(json.dumps(L.rounded({'config_id': CONFIG_ID, 'arms': show,
                                'safety': {a: {k: v for k, v in o['safety'].items() if k != 'failing'} for a, o in out.items()},
                                'plan_fates': {a: o['plan_fates'] for a, o in out.items()},
                                'contrasts_read_gap': {c: {k: v for k, v in d['read_gap'].items() if k != 'per_seed'} for c, d in contrasts.items()},
                                'contrasts_cont72': {c: {k: v for k, v in d['related_within_72h'].items() if k != 'per_seed'} for c, d in contrasts.items()},
                                'final': final}), ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
