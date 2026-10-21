"""Social-expression diagnosis under v5, and neighbor-rule candidates (product experiments).

    python -m pet.validate_v5_social dev [out_dir]          # seeds 3001-3010 (already reviewed)
    python -m pet.validate_v5_social validation [out_dir]   # seeds 4001-4010, run after CRITERIA were fixed

Question: the neighbor's daily visit limit may squash a difference in liking for her company
that earlier life already created. Only the neighbor's visiting rule is varied; v5's
preference rates and weights, trait pull, memory decay, goals, the two-step choice, hunger
care and home upkeep are untouched.

Paired design per seed (the unit of analysis is the seed's A/B pair):
  grow 20 days on the reading route -> uniform environment (one shared invitation)
  -> copy: A keeps the uniform environment, B also gets an invitation every morning, 30 days,
     both under the v5 rule (2 unprompted visits a day)
  -> 1 washout day so no invitation is still pending
  -> 30 'withdrawal' days under each scheme, at three levels:
     A  probe: from real states, only the scheme changes; expected visits, nothing lived
     B  frozen liking: preferences keep acting but stop learning (body, goals, memories move)
     C  normal learning
     Levels B and C use 3 continuation replicates (rep 0 = the original random stream,
     reps 1-2 re-seed the pet's generator at the withdrawal start, the same for A and B).
     Replicates are averaged within a seed; they are not extra births.
Full-life check: each candidate scheme from birth, for the social/garden routes and the A/B pair.

Invitations skip both the daily cap and the rest interval in every scheme (unchanged
convention). Expected-value probes are labelled probes; they never enter a pet's life.
"""
import copy
import json
import math
import random
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from . import engine
from .engine import Session
from .validate_v5 import ROUTES, UNIFORM_OBJECTS, mili_away

DEV_SEEDS = [3001, 3002, 3003, 3004, 3005, 3006, 3007, 3008, 3009, 3010]
VALIDATION_SEEDS = [4001, 4002, 4003, 4004, 4005, 4006, 4007, 4008, 4009, 4010]
SCHEMES = {                      # (unprompted visits per day, rest hours after a shared activity)
    'cap2': (2, 0),              # v5 baseline
    'cap4': (4, 0),              # candidate 1
    'rest4': (None, 4),          # candidate 2: no daily count, 4 h rest after each shared activity
    'nocap': (1000, 0),          # diagnostic only, never a product candidate
}
CANDIDATES = ('cap4', 'rest4')
GROW, PHASE, WASHOUT, WITHDRAW, WINDOW, REPS, FULL_OBS = 20, 30, 1, 30, 10, 3, 60
LEISURE = ('read', 'garden', 'visit', 'explore')
CATEGORIES = ('eat', 'sleep', 'read', 'garden', 'visit', 'explore', 'gather_material', 'build', 'gather_food')

# ---- Tentative product criteria. FIXED 2026-10-17 after the dev run (seeds 3001-3010) and
# BEFORE the validation run (4001-4010). Primary candidate chosen on dev: 'rest4' (consistent
# direction, no back-to-back visits, a rule a player can understand: "Mili rests after
# playing"). 'cap4' is reported descriptively only: on dev about half of its visits came
# within 2 h of the previous one, which reads as mechanical repetition. Dev caveat known when
# fixing: one rest4 full-life run touched home 0 (seed 3002, social route); the home criterion
# was nevertheless kept strict. Unit: one extra visit a week = 1/7 a day (product guess).
PRIMARY = 'rest4'
CRITERIA = {
    'E1_withdrawal_learning_gap_per_day': 1 / 7,    # B-A spontaneous visits/day, withdrawal under the scheme, normal learning
    'E1_min_positive_seeds': 7, 'E1_ci_lower_above': 0.0,
    'E2_full_life_route_gap_per_day': 1 / 7,        # social-garden spontaneous visits/day, scheme from birth
    'E2_windows_positive': 4, 'E2_min_seeds': 7,
    'E3_full_life_pair_gap_per_day': 1 / 7,         # B-A after withdrawal, scheme from birth
    'E3_min_positive_seeds': 7,
    'B1_min_condition': 99, 'B1_home_never_zero': True, 'B1_max_non_sleep_share': 0.6,
    'B1_max_visit_share': 0.12, 'B1_min_eat_share': 0.09, 'B1_min_upkeep_share': 0.04,
    'B1_entropy_drop_vs_cap2_max': 0.1,
    'B2_max_rapid_repeat_share': 0.35,              # visits within 2 h of the previous one (cap2 dev: 0.275)
}


def verdict(analysis, scheme):
    C, W, F = CRITERIA, analysis['withdrawal'][scheme]['learning'], analysis['full_life'][scheme]
    e1 = W['B_minus_A_spont_per_day']
    e2_seeds = sum(g > 0 and w >= C['E2_windows_positive'] for g, w in zip(
        F['social_minus_garden_spont_per_day']['per_seed'], F['social_minus_garden_windows_positive']))
    e3 = F['pair_B_minus_A_withdrawal']
    base = analysis['full_life']['cap2']
    out = {
        'E1': e1['mean'] >= C['E1_withdrawal_learning_gap_per_day'] and e1['positive'] >= C['E1_min_positive_seeds']
              and e1['ci95'][0] > C['E1_ci_lower_above'],
        'E2': F['social_minus_garden_spont_per_day']['mean'] >= C['E2_full_life_route_gap_per_day'] and e2_seeds >= C['E2_min_seeds'],
        'E3': e3['mean'] >= C['E3_full_life_pair_gap_per_day'] and e3['positive'] >= C['E3_min_positive_seeds'],
        'B1': (F['min_condition'] >= C['B1_min_condition'] and F['min_home'] > 0
               and F['top_non_sleep_share_max'] <= C['B1_max_non_sleep_share'] and F['visit_share']['mean'] <= C['B1_max_visit_share']
               and F['eat_share_min'] >= C['B1_min_eat_share'] and F['upkeep_share_min'] >= C['B1_min_upkeep_share']
               and F['entropy_bits']['mean'] >= base['entropy_bits']['mean'] - C['B1_entropy_drop_vs_cap2_max']),
        'B2': (F['rapid_repeat_share']['mean'] or 0) <= C['B2_max_rapid_repeat_share'],
        'E2_seeds': e2_seeds,
    }
    out['adopt'] = all(out[k] for k in ('E1', 'E2', 'E3', 'B1', 'B2'))
    return out


def set_scheme(s, scheme):
    cap, rest = SCHEMES[scheme]
    s.agent.visit_cap, s.agent.visit_rest_hours = cap, rest


def new_pet(seed, scheme='cap2'):
    s = Session(seed, 5)   # v5 experiment: rules pinned explicitly (2026-10-21)
    set_scheme(s, scheme)
    s.agent.diagnostics = True
    return s


def grow(seed, route, scheme='cap2'):
    s = new_pet(seed, scheme)
    for obj in ROUTES[route]['objects']:
        s.apply({'kind': 'object', 'value': obj})
    for _ in range(GROW * 24):
        if ROUTES[route]['invite_daily'] and s.tick % 24 == 8 and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
        s.step()
    for obj in UNIFORM_OBJECTS:
        if obj not in s.world.objects:
            s.apply({'kind': 'object', 'value': obj})
    if s.tick >= s.agent.invitation_until:
        s.apply({'kind': 'invite', 'value': None})
    return s


def live(s, days, invite_daily=False, sample=None):
    """Run whole days; return the action events. `sample(s)` is called before each step."""
    start = len(s.events)
    for _ in range(days * 24):
        if invite_daily and s.tick % 24 == 8 and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
        if sample:
            sample(s)
        s.step()
    return [e for e in s.events[start:] if e['kind'] == 'action']


def metrics(events, days):
    """Lived behavior of one run. Hours are not treated as independent samples anywhere."""
    acts = Counter(e['action'] for e in events)
    n = len(events)
    visits = [e for e in events if e['action'] == 'visit']
    spont = [e for e in visits if not e['invited']]
    d = [e['social_diag'] for e in events]
    available = [i for i, x in enumerate(d) if x['available_uninvited'] and x['met']]
    first_spont = next((i for i, e in enumerate(events) if e['action'] == 'visit' and not e['invited']), None)
    wait = None
    if available:
        later = [i for i, e in enumerate(events) if i >= available[0] and e['action'] == 'visit' and not e['invited']]
        wait = later[0] - available[0] if later else None
    per_day = Counter(e['tick'] // 24 for e in visits)
    ticks = [e['tick'] for e in visits]
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    shares = {k: acts[k] / n for k in CATEGORIES}
    windows = []
    for w in range(0, n, WINDOW * 24):
        part = events[w:w + WINDOW * 24]
        windows.append(sum(e['action'] == 'visit' and not e['invited'] for e in part) / (len(part) / 24))
    return {
        'spont_per_day': len(spont) / days, 'invited_per_day': (len(visits) - len(spont)) / days,
        'spont_windows': windows,
        'available_hours_per_day': len(available) / days,
        'explore_hours_per_day': sum(x['chose_explore'] for x in d) / days,
        'wanted_but_blocked_per_day': sum(x['drew'] and x['wanted'] and x['blocked'] is not None for x in d) / days,
        'drawn_per_day': sum(x['drew'] for x in d) / days,
        'first_available_hour': available[0] if available else None,
        'wait_to_first_spont_hours': wait, 'no_spont_visit': first_spont is None,
        'max_visits_in_a_day': max(per_day.values(), default=0),
        'rapid_repeat_share': (sum(g <= 2 for g in gaps) / len(gaps)) if gaps else None,
        'shares': shares,
        'entropy_bits': -sum(v * math.log2(v) for v in shares.values() if v > 0),
        'top_non_sleep_share': max(v for k, v in shares.items() if k != 'sleep'),
    }


def body(s):
    return {'condition': s.agent.condition, 'home': s.agent.shelter}


def probe_points(s, days):
    """Real states along a run, every 2nd day, 08-19 h (copies; the run itself is not touched)."""
    points = []

    def sample(x):
        day, hour = divmod(x.tick, 24)
        if (day % 2 == 0) and 8 <= hour < 20:
            points.append(copy.deepcopy(x))
    live(s, days, sample=sample)
    return points


def probe(points):
    """Expected unprompted visits per probed hour under each scheme, from identical states:
    the choice is re-made on an isolated copy with only the scheme changed; the visit is the
    expected value (explore chosen x neighbor available x visit chance), never a lived event."""
    out = {}
    for scheme in SCHEMES:
        expl = avail = exp = 0.0
        for state in points:
            c = copy.deepcopy(state)
            set_scheme(c, scheme)
            a = c.agent
            seen = {}
            real_act = a.act

            def act(action, day, hour=0, a=a):
                invited = a.now < a.invitation_until
                status = a.neighbor_status(day, hour, invited)
                chance = a.visit_chance(a.influence()[0])[0]
                seen.update(action=action, free=status == engine.NEIGHBOR_FREE and bool(a.shared or invited),
                            chance=1.0 if invited else chance)
                return real_act(action, day, hour)
            a.act = act
            c.step()                                 # isolated copy, discarded
            expl += seen['action'] == 'explore'
            avail += seen['free']
            exp += (seen['action'] == 'explore') * seen['free'] * seen['chance']
        n = len(points)
        out[scheme] = {'explore': expl / n, 'available': avail / n, 'expected_visit': exp / n}
    return out


def run_seed(seed):
    out = {'seed': seed, 'withdrawal': {}, 'probe': {}, 'full_life': {}}
    base = grow(seed, 'reading')
    branches = {}
    for name, daily in (('A', False), ('B', True)):
        s = copy.deepcopy(base)
        ev = live(s, PHASE, invite_daily=daily)
        live(s, WASHOUT)
        assert s.tick >= s.agent.invitation_until, 'an invitation is still pending at withdrawal'
        branches[name] = s
        out.setdefault('phase', {})[name] = {'accepted_invitations': sum(e['invited'] for e in ev if e['action'] == 'visit'),
                                             'prefs_end': dict(s.agent.prefs)}
    # Level A: probes from the baseline (cap2, normal learning, rep 0) trajectory of each branch.
    for name, s in branches.items():
        out['probe'][name] = probe(probe_points(copy.deepcopy(s), WITHDRAW))
    # Levels B and C: lived withdrawal runs under each scheme.
    for scheme in SCHEMES:
        for level, frozen in (('frozen', True), ('learning', False)):
            for rep in range(REPS):
                for name, s0 in branches.items():
                    s = copy.deepcopy(s0)
                    set_scheme(s, scheme)
                    s.agent.freeze_prefs = frozen
                    if rep:
                        s.agent.rng.seed(seed * 1000 + rep)          # same continuation stream for A and B
                    ev = live(s, WITHDRAW)
                    m = metrics(ev, WITHDRAW)
                    m.update(prefs_end=dict(s.agent.prefs), body_end=body(s))
                    out['withdrawal'].setdefault(scheme, {}).setdefault(level, {}).setdefault(rep, {})[name] = m
    # Full life: the scheme from birth (product view), rep 0 only.
    for scheme in ('cap2',) + CANDIDATES:
        fl = {}
        for route in ('social', 'garden'):
            s = grow(seed, route, scheme)
            homes = []
            ev = live(s, FULL_OBS, sample=lambda x, h=homes: h.append((x.agent.shelter, x.agent.condition)))
            m = metrics(ev, FULL_OBS)
            m.update(min_home=min(h for h, _ in homes), min_condition=min(c for _, c in homes))
            fl[route] = m
        b = grow(seed, 'reading', scheme)
        pair = {}
        for name, daily in (('A', False), ('B', True)):
            s = copy.deepcopy(b)
            live(s, PHASE, invite_daily=daily)
            live(s, WASHOUT)
            pair[name] = metrics(live(s, WITHDRAW), WITHDRAW)
        fl['pair'] = pair
        out['full_life'][scheme] = fl
    return out


# ---------------------------------------------------------------- statistics (seed = unit)
def boot_ci(values, n=10000, seed=12345):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(n))
    return [round(means[int(0.025 * n)], 3), round(means[int(0.975 * n)], 3)]


def describe(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {'n': 0}
    srt = sorted(vals)
    mid = len(srt) // 2
    median = srt[mid] if len(srt) % 2 else (srt[mid - 1] + srt[mid]) / 2
    return {'n': len(vals), 'mean': round(sum(vals) / len(vals), 3), 'median': round(median, 3),
            'positive': sum(v > 0 for v in vals), 'ci95': boot_ci(vals), 'per_seed': [None if v is None else round(v, 3) for v in values]}


def rep_mean(per_rep, name, key):
    vals = [per_rep[r][name][key] for r in per_rep if per_rep[r][name][key] is not None]
    return sum(vals) / len(vals) if vals else None


def analyse(results):
    A = {}
    for scheme in SCHEMES:
        A[scheme] = {}
        for level in ('frozen', 'learning'):
            gap, blocked, wait_a, wait_b, none_a, none_b, ent, rapid, maxday, rep_sd = [], [], [], [], 0, 0, [], [], [], []
            for r in results:
                pr = r['withdrawal'][scheme][level]
                g = [pr[k]['B']['spont_per_day'] - pr[k]['A']['spont_per_day'] for k in pr]
                gap.append(sum(g) / len(g))
                rep_sd.append(max(g) - min(g))
                blocked.append(rep_mean(pr, 'B', 'wanted_but_blocked_per_day'))
                wait_a.append(pr[0]['A']['wait_to_first_spont_hours'])
                wait_b.append(pr[0]['B']['wait_to_first_spont_hours'])
                none_a += pr[0]['A']['wait_to_first_spont_hours'] is None
                none_b += pr[0]['B']['wait_to_first_spont_hours'] is None
                ent.append(rep_mean(pr, 'B', 'entropy_bits'))
                rapid.append(rep_mean(pr, 'B', 'rapid_repeat_share'))
                maxday.append(max(pr[k][n]['max_visits_in_a_day'] for k in pr for n in 'AB'))
            A[scheme][level] = {
                'B_minus_A_spont_per_day': describe(gap),
                'replicate_range_of_gap': describe(rep_sd),
                'B_wanted_but_blocked_per_day': describe(blocked),
                'wait_hours_rep0': {'A': describe(wait_a), 'B': describe(wait_b),
                                    'no_visit_A': none_a, 'no_visit_B': none_b},
                'B_entropy_bits': describe(ent), 'B_rapid_repeat_share': describe(rapid),
                'max_visits_in_a_day': max(maxday),
            }
        A[scheme]['probe_B_minus_A_expected'] = describe(
            [r['probe']['B'][scheme]['expected_visit'] - r['probe']['A'][scheme]['expected_visit'] for r in results])
        A[scheme]['probe_available'] = describe([r['probe']['B'][scheme]['available'] for r in results])
    full = {}
    for scheme in ('cap2',) + CANDIDATES:
        fl = [r['full_life'][scheme] for r in results]
        full[scheme] = {
            'social_minus_garden_spont_per_day': describe([f['social']['spont_per_day'] - f['garden']['spont_per_day'] for f in fl]),
            'social_minus_garden_windows_positive': [sum(a - b > 0 for a, b in zip(f['social']['spont_windows'], f['garden']['spont_windows'])) for f in fl],
            'pair_B_minus_A_withdrawal': describe([f['pair']['B']['spont_per_day'] - f['pair']['A']['spont_per_day'] for f in fl]),
            'visit_share': describe([f[k]['shares']['visit'] for f in fl for k in ('social', 'garden')]),
            'read_share': describe([f[k]['shares']['read'] for f in fl for k in ('social', 'garden')]),
            'entropy_bits': describe([f[k]['entropy_bits'] for f in fl for k in ('social', 'garden')]),
            'rapid_repeat_share': describe([f[k]['rapid_repeat_share'] for f in fl for k in ('social', 'garden')]),
            'top_non_sleep_share_max': round(max(f[k]['top_non_sleep_share'] for f in fl for k in ('social', 'garden')), 3),
            'max_visits_in_a_day': max(f[k]['max_visits_in_a_day'] for f in fl for k in ('social', 'garden')),
            'min_home': round(min(f[k]['min_home'] for f in fl for k in ('social', 'garden')), 1),
            'min_condition': round(min(f[k]['min_condition'] for f in fl for k in ('social', 'garden')), 1),
            'eat_share_min': round(min(f[k]['shares']['eat'] for f in fl for k in ('social', 'garden')), 3),
            'upkeep_share_min': round(min(f[k]['shares']['gather_material'] + f[k]['shares']['build'] for f in fl for k in ('social', 'garden')), 3),
        }
    return {'withdrawal': A, 'full_life': full,
            'conventions': {'invitations_skip': ['daily cap', 'rest interval', 'away day'],
                            'invitations_never_skip': ['08-20 visiting hours'], 'washout_days': WASHOUT,
                            'reps': REPS, 'unit': 'seed (A/B pair); replicates averaged within seed'}}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    if which != 'dev' and CRITERIA is None:
        sys.exit('Fix CRITERIA before running the validation seeds.')
    with Pool(min(len(seeds), 14)) as pool:
        results = pool.map(run_seed, seeds)
    report = {'sample': which, 'seeds': seeds, 'schemes': SCHEMES, 'analysis': analyse(results)}
    if CRITERIA is not None:
        report['criteria'] = CRITERIA
        report['primary'] = PRIMARY
        report['verdicts'] = {s: verdict(report['analysis'], s) for s in CANDIDATES}
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    out.mkdir(parents=True, exist_ok=True)
    (out / f'v5_social_{which}_raw.json').write_text(json.dumps(results, ensure_ascii=False, default=str), encoding='utf-8')
    (out / f'v5_social_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(report['analysis'], ensure_ascii=False, indent=1, default=str)[:20000])


if __name__ == '__main__':
    main()
