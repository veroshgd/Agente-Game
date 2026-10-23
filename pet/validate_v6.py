"""Rules v6: v5 + home interrupt + rest4 neighbor rule (product experiment).

    python -m pet.validate_v6 dev [out_dir]          # seeds 3001-3010 + 1/42/901/7/123 (development)
    python -m pet.validate_v6 validation [out_dir]   # seeds 6001-6010 (run once on 2026-10-21; since then REVIEW)

Why: rest4 passed its own social criteria on 4001-4010 but was not adopted because the home
margin under v5 was too thin (seed 42, garden: lowest home 2.9 < 3; one dev life reached 0).
Diagnosis (2026-10-21, AI juego/diag_home_margin.py): every low point was a goal lock in the
core, not a weak need. A leisure plan (see_the_world / learn) is kept for GOAL_MIN_DAYS, a
finished one can be re-picked the same morning, and improve_home 'stalls' under decay and is
muted for 6 days, while the home loses ~8.4 points a day with 3 materials already in hand.
Fix (PetAgent.home_interrupt): each morning, with the home below HOME_INTERRUPT_BELOW, if
improve_home outranks the current leisure plan by the core's own switch margin, that plan ends.

History, kept as it happened:
  v6a  interrupt at any home need. Passed H and S on fresh seeds 5001-5010
       (docs/pet_v6_validation/v6a_*), but afterwards reading was seen to have nearly vanished
       (full lives: 1.6-2.9% of hours under v5 -> 0.1%; reading route - control on dev seeds
       2.9 -> 0.9 pp). No criterion looked at reading, and S's entropy check compared with
       cap2 + interrupt, which had the same loss. NOT adopted; 5001-5010 are spent.
  v6   interrupt only below 15, chosen on dev seeds (10 let homes fall under 3; 20 cost more
       reading). Part R added so reading is compared with v5 on the same seeds.
  2026-10-23 statistics fix (this version of the script; criteria unchanged):
       * every life has an id and a trajectory fingerprint; the old '82 lives' held 30
         social-design lives identical to v5-design lives (same seed, route, rules, objects,
         invitations). Unique trajectories are counted apart from runs.
       * whole-life metrics from raw counts and hours (merge() kept the observation phase's
         upkeep / leisure / read / entropy / last week); per-phase results as well.
       * the social design's own lives (growth, invitations, washout, withdrawal, every
         replicate, the probe path) are now in the safety record.
       * verdicts on unrounded values; one 'final' block decides, docs quote it.
       Results of the 2026-10-21 runs stay in docs/pet_v6_validation/ as recorded.

Three parts, on the sample's seeds:
  H  safe home: the v4 standard on every unique whole life of the rest4 group (pet.lifestats);
     the share criteria on every phase of at least 10 days are reported as a warning only.
  S  social: pet.validate_v5_social design and CRITERIA unchanged, verdict recomputed from
     unrounded per-seed values; pets are v6, and 'cap2' there means v6 with the old daily cap.
  R  reading and variety vs v5, paired on the same seeds (v5 design: grow 20 days on a route,
     then the same garden + book for everyone, 60 days).
"""
import copy
import json
import sys
from multiprocessing import Pool
from pathlib import Path

from . import lifestats as L
from . import validate_v5 as v5
from . import validate_v5_social as vs

DEV_SEEDS = vs.DEV_SEEDS                                    # 3001-3010, already reviewed
R_DEV_EXTRA = [1, 42, 901, 7, 123]                          # v5 DEV_SEEDS, part R / H only
VALIDATION_SEEDS = [6001, 6002, 6003, 6004, 6005, 6006, 6007, 6008, 6009, 6010]   # REVIEW since 2026-10-21
SPENT_SEEDS = [5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009, 5010]   # v6a, not adopted
SAFE_SEEDS = (1, 42, 901, 7, 123, 2024)                     # = tests/test_pet_v4.py HOME_SEEDS
SAFE_ITEMS = (('garden',), ('garden', 'book', 'music'))
H_SCHEMES = ('cap2', 'rest4')
COMMON_DAYS = 60

# ---- FIXED 2026-10-21 after the dev run of this version and BEFORE seeds 6001-6010 were run.
# H: the v4 safe-home standard, unchanged, on every life. S: the 2026-10-17 social criteria,
# unchanged. R (new, after v6a): v6 keeps at least 80% of v5's reading-route - control gap,
# loses at most 2 pp of reading on any route, and at most 0.1 bits of activity entropy.
# v6 is adopted only if H holds for rest4 on every life, S says 'adopt' for rest4, and R holds.
# 2026-10-23: thresholds untouched; H now covers every unique whole life and phase (see above),
# and compatibility of v1-v6 replays is part of the final decision.
CRITERIA = {
    'H_min_home': 3.0, 'H_never_zero': True, 'H_max_below20_share': 0.08,
    'H_max_upkeep_share': 0.15, 'H_min_leisure_share': 0.30, 'H_min_condition': 99.0,
    'H_min_kinds_last_week': 3, 'H_phase_min_days': L.PHASE_MIN_DAYS,
    'S': 'pet.validate_v5_social.CRITERIA, verdict for rest4 (unrounded)',
    'R1_min_gap_ratio_vs_v5': 0.8, 'R2_max_read_drop_pp': 2.0, 'R3_max_entropy_drop_bits': 0.1,
}
assert (CRITERIA['H_min_home'], CRITERIA['H_max_below20_share'], CRITERIA['H_max_upkeep_share'],
        CRITERIA['H_min_leisure_share'], CRITERIA['H_min_condition'], CRITERIA['H_min_kinds_last_week']) == (
    L.H['min_home'], L.H['max_below20_share'], L.H['max_upkeep_share'], L.H['min_leisure_share'],
    L.H['min_condition'], L.H['min_kinds_last_week'])


def new_pet(seed, scheme='cap2', rules=6):
    s = L.TracedSession(seed, rules)
    vs.set_scheme(s, scheme)
    s.agent.diagnostics = True
    return s


# validate_v5_social builds every pet through new_pet(); here they are traced v6 pets.
vs.new_pet = new_pet


def run_hours(s, hours, invite_daily_until=0):
    for _ in range(hours):
        if s.tick < invite_daily_until and s.tick % 24 == 8 and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
        s.step()


def safe_job(args):
    seed, items, scheme = args
    s = new_pet(seed, scheme)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    s.apply({'kind': 'invite', 'value': None})
    s.phases = [('safe', 0)]
    run_hours(s, 60 * 24)
    return L.life_record(s, life_id=f"v6|safe|{seed}|{'+'.join(items)}|{scheme}", design='safe', seed=seed,
                         setting='+'.join(items), scheme=scheme, group=scheme)


def social_route_job(args):
    """Whole life of the social design's full-life check: route growth, then the common setting."""
    seed, route, scheme = args
    s = new_pet(seed, scheme)
    for obj in vs.ROUTES[route]['objects']:
        s.apply({'kind': 'object', 'value': obj})
    run_hours(s, vs.GROW * 24, invite_daily_until=vs.GROW * 24 if vs.ROUTES[route]['invite_daily'] else 0)
    for obj in vs.UNIFORM_OBJECTS:
        if obj not in s.world.objects:
            s.apply({'kind': 'object', 'value': obj})
    if s.tick >= s.agent.invitation_until:
        s.apply({'kind': 'invite', 'value': None})
    s.phase('common')
    run_hours(s, vs.FULL_OBS * 24)
    return L.life_record(s, life_id=f'v6|social_route|{seed}|{route}|{scheme}', design='social_route', seed=seed,
                         setting=route, scheme=scheme, group=scheme)


def v5_route_job(args):
    """The v5 differentiation design (growth route, then garden + book for all), v5 or v6 rules."""
    seed, route, rules = args
    spec = v5.ROUTES[route]
    s = L.TracedSession(seed, rules)
    s.agent.diagnostics = True                   # logs would-be interrupts only; behavior unchanged
    for obj in spec['objects']:
        s.apply({'kind': 'object', 'value': obj})
    run_hours(s, v5.GROW * 24, invite_daily_until=v5.GROW * 24 if spec['invite_daily'] else 0)
    v5.uniform(s)
    s.phase('common')
    run_hours(s, COMMON_DAYS * 24)
    return L.life_record(s, life_id=f'v{rules}|v5_route|{seed}|{route}', design='v5_route', seed=seed,
                         setting=route, rules=rules, group='rest4' if rules >= 6 else 'v5')


def run_seed_traced(seed):
    """validate_v5_social.run_seed, step for step (same copies, same streams, same results),
    plus a whole-life record of every branch it lives. tests/test_pet_pause.py checks equality."""
    out = {'seed': seed, 'withdrawal': {}, 'probe': {}, 'full_life': {}}
    lives = []
    tag = lambda s, **k: lives.append(L.life_record(s, seed=seed, **k))
    base = vs.grow(seed, 'reading')
    branches = {}
    for name, daily in (('A', False), ('B', True)):
        s = copy.deepcopy(base)
        s.phase('intervention')
        ev = vs.live(s, vs.PHASE, invite_daily=daily)
        s.phase('washout')
        vs.live(s, vs.WASHOUT)
        assert s.tick >= s.agent.invitation_until, 'an invitation is still pending at withdrawal'
        branches[name] = s
        out.setdefault('phase', {})[name] = {'accepted_invitations': sum(e['invited'] for e in ev if e['action'] == 'visit'),
                                             'prefs_end': dict(s.agent.prefs)}
    for name, s in branches.items():
        path = copy.deepcopy(s)
        path.phase('withdrawal')
        out['probe'][name] = vs.probe(vs.probe_points(path, vs.WITHDRAW))
        tag(path, life_id=f'v6|S|{seed}|probe_path|{name}', design='S_probe_path', scheme='cap2', branch=name,
            group='cap2')
    for scheme in vs.SCHEMES:
        for level, frozen in (('frozen', True), ('learning', False)):
            for rep in range(vs.REPS):
                for name, s0 in branches.items():
                    s = copy.deepcopy(s0)
                    vs.set_scheme(s, scheme)
                    s.agent.freeze_prefs = frozen
                    if rep:
                        s.agent.rng.seed(seed * 1000 + rep)
                    s.phase('withdrawal')
                    ev = vs.live(s, vs.WITHDRAW)
                    m = vs.metrics(ev, vs.WITHDRAW)
                    m.update(prefs_end=dict(s.agent.prefs), body_end=vs.body(s))
                    out['withdrawal'].setdefault(scheme, {}).setdefault(level, {}).setdefault(rep, {})[name] = m
                    tag(s, life_id=f'v6|S|{seed}|grow=cap2|withdraw={scheme}|{level}|rep{rep}|{name}',
                        design='S_withdrawal', scheme=scheme, level=level, rep=rep, branch=name,
                        group=scheme if scheme in H_SCHEMES else 'other')
    for scheme in ('cap2',) + vs.CANDIDATES:
        fl = {}
        for route in ('social', 'garden'):
            s = vs.grow(seed, route, scheme)
            s.phase('common')
            homes = []
            ev = vs.live(s, vs.FULL_OBS, sample=lambda x, h=homes: h.append((x.agent.shelter, x.agent.condition)))
            m = vs.metrics(ev, vs.FULL_OBS)
            m.update(min_home=min(h for h, _ in homes), min_condition=min(c for _, c in homes))
            fl[route] = m
            tag(s, life_id=f'v6|S|{seed}|full|{route}|{scheme}', design='S_full_route', scheme=scheme, setting=route,
                group=scheme if scheme in H_SCHEMES else 'other')
        b = vs.grow(seed, 'reading', scheme)
        pair = {}
        for name, daily in (('A', False), ('B', True)):
            s = copy.deepcopy(b)
            s.phase('intervention')
            vs.live(s, vs.PHASE, invite_daily=daily)
            s.phase('washout')
            vs.live(s, vs.WASHOUT)
            s.phase('withdrawal')
            pair[name] = vs.metrics(vs.live(s, vs.WITHDRAW), vs.WITHDRAW)
            tag(s, life_id=f'v6|S|{seed}|full|pair|{scheme}|{name}', design='S_full_pair', scheme=scheme, branch=name,
                group=scheme if scheme in H_SCHEMES else 'other')
        fl['pair'] = pair
        out['full_life'][scheme] = fl
    return out, lives


def mean(xs):
    return sum(xs) / len(xs)


def social_verdict_raw(results, scheme):
    """validate_v5_social.verdict on unrounded per-seed values (same criteria and logic)."""
    C = vs.CRITERIA
    e1 = L.describe([mean([r['withdrawal'][scheme]['learning'][k]['B']['spont_per_day']
                           - r['withdrawal'][scheme]['learning'][k]['A']['spont_per_day']
                           for k in r['withdrawal'][scheme]['learning']]) for r in results])
    fl = [r['full_life'][scheme] for r in results]
    base = [r['full_life']['cap2'] for r in results]
    e2 = L.describe([f['social']['spont_per_day'] - f['garden']['spont_per_day'] for f in fl])
    e2_windows = [sum(a - b > 0 for a, b in zip(f['social']['spont_windows'], f['garden']['spont_windows'])) for f in fl]
    e2_seeds = sum(g > 0 and w >= C['E2_windows_positive'] for g, w in zip(e2['per_seed'], e2_windows))
    e3 = L.describe([f['pair']['B']['spont_per_day'] - f['pair']['A']['spont_per_day'] for f in fl])
    routes = [f[k] for f in fl for k in ('social', 'garden')]
    ent = mean([m['entropy_bits'] for m in routes])
    ent_base = mean([f[k]['entropy_bits'] for f in base for k in ('social', 'garden')])
    rapid = [m['rapid_repeat_share'] for m in routes if m['rapid_repeat_share'] is not None]
    b1 = {'min_condition': min(m['min_condition'] for m in routes), 'min_home': min(m['min_home'] for m in routes),
          'top_non_sleep_max': max(m['top_non_sleep_share'] for m in routes),
          'visit_share_mean': mean([m['shares']['visit'] for m in routes]),
          'eat_share_min': min(m['shares']['eat'] for m in routes),
          'upkeep_share_min': min(m['shares']['gather_material'] + m['shares']['build'] for m in routes),
          'entropy_mean': ent, 'entropy_cap2_mean': ent_base}
    out = {'E1': e1['mean'] >= C['E1_withdrawal_learning_gap_per_day'] and e1['positive'] >= C['E1_min_positive_seeds']
                 and e1['ci95'][0] > C['E1_ci_lower_above'],
           'E2': e2['mean'] >= C['E2_full_life_route_gap_per_day'] and e2_seeds >= C['E2_min_seeds'],
           'E3': e3['mean'] >= C['E3_full_life_pair_gap_per_day'] and e3['positive'] >= C['E3_min_positive_seeds'],
           'B1': (b1['min_condition'] >= C['B1_min_condition'] and b1['min_home'] > 0
                  and b1['top_non_sleep_max'] <= C['B1_max_non_sleep_share'] and b1['visit_share_mean'] <= C['B1_max_visit_share']
                  and b1['eat_share_min'] >= C['B1_min_eat_share'] and b1['upkeep_share_min'] >= C['B1_min_upkeep_share']
                  and ent >= ent_base - C['B1_entropy_drop_vs_cap2_max']),
           'B2': (mean(rapid) if rapid else 0) <= C['B2_max_rapid_repeat_share']}
    out['adopt'] = all(out.values())
    out['values'] = {'E1': e1, 'E2': e2, 'E2_seeds': e2_seeds, 'E3': e3, 'B1': b1,
                     'B2_rapid_mean': mean(rapid) if rapid else None}
    return out


def first_meetings(lives):
    """When each withdrawal branch (rep 0, normal learning) first really met the neighbor."""
    out = {}
    for m in lives:
        if m['design'] == 'S_withdrawal' and m['level'] == 'learning' and m['rep'] == 0:
            out.setdefault(m['scheme'], {}).setdefault(m['branch'], []).append(m['first_meet_tick'])
    return {sc: {b: {'per_seed': v, 'never_met': sum(x is None for x in v)} for b, v in d.items()} for sc, d in out.items()}


def reading_part(r_lives, seeds):
    C = CRITERIA
    get = lambda rules, sd, r: next(m for m in r_lives if m['rules'] == rules and m['seed'] == sd and m['setting'] == r)
    out = {}
    for rules in (5, 6):
        common = {(sd, r): get(rules, sd, r)['phases']['common'] for sd in seeds for r in v5.ROUTES}
        out[f'v{rules}'] = {
            'read_share': {r: mean([common[sd, r]['read'] for sd in seeds]) for r in v5.ROUTES},
            'reading_minus_control': L.describe([common[sd, 'reading']['read'] - common[sd, 'control']['read'] for sd in seeds]),
            'entropy': mean([common[k]['entropy'] for k in common]),
            'entropy_whole_life': mean([get(rules, sd, r)['whole']['entropy'] for sd in seeds for r in v5.ROUTES])}
    a, b = out['v5'], out['v6']
    gap5, gap6 = a['reading_minus_control']['mean'], b['reading_minus_control']['mean']
    out['gap_change_v6_minus_v5'] = L.describe([y - x for x, y in zip(a['reading_minus_control']['per_seed'],
                                                                       b['reading_minus_control']['per_seed'])])
    out['verdict'] = {
        'R1': gap6 > 0 and gap6 >= C['R1_min_gap_ratio_vs_v5'] * gap5,
        'R2': all(b['read_share'][r] >= a['read_share'][r] - C['R2_max_read_drop_pp'] / 100 for r in v5.ROUTES),
        'R3': b['entropy'] >= a['entropy'] - C['R3_max_entropy_drop_bits'],
    }
    out['verdict']['pass'] = all(out['verdict'].values())
    out['R1_note'] = ('R1 is a ratio to the v5 gap; with the v5 gap near 0 it is unstable '
                      '(any small v6 gap passes or fails by noise). Kept as fixed on 2026-10-21.')
    return out


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    r_seeds = seeds + (R_DEV_EXTRA if which == 'dev' else [])
    with Pool(14) as pool:
        h_lives = (pool.map(safe_job, [(sd, it, sc) for sc in H_SCHEMES for sd in SAFE_SEEDS for it in SAFE_ITEMS])
                   + pool.map(social_route_job, [(sd, r, sc) for sc in H_SCHEMES for sd in seeds
                                                 for r in ('social', 'garden', 'reading')]))
        r_lives = pool.map(v5_route_job, [(sd, r, rules) for rules in (5, 6) for sd in r_seeds for r in v5.ROUTES])
        traced = pool.map(run_seed_traced, seeds)
    results = [r for r, _ in traced]
    s_lives = [m for _, lv in traced for m in lv]
    all_lives = h_lives + r_lives + s_lives
    home = {g: L.safety_summary([m for m in all_lives if m['group'] == g]) for g in ('v5', 'cap2', 'rest4', 'other')}
    reading = reading_part(r_lives, r_seeds)
    verdicts_rounded = {s: vs.verdict(vs.analyse(results), s) for s in vs.CANDIDATES}   # legacy, display only
    social = {s: social_verdict_raw(results, s) for s in vs.CANDIDATES}
    compat = L.compat_check()
    # H as fixed on 2026-10-21: the standard on every (now complete, unique) whole life. The
    # per-phase share check did not exist then, so it is reported as a warning, not applied.
    final = {'H_rest4_every_unique_whole_life': home['rest4']['pass'] == home['rest4']['unique_trajectories'],
             'S_rest4': social['rest4']['adopt'], 'R': reading['verdict']['pass'], 'compat_v1_v6': compat['pass']}
    final['adopt_v6'] = all(final.values())
    final['warning_phase_share_fails'] = {g: home[g]['unique_trajectories'] - home[g]['phase_pass'] for g in home}
    report = {'sample': which, 'seeds': seeds, 'reading_seeds': r_seeds, 'criteria': CRITERIA,
              'social_criteria': vs.CRITERIA, 'final': final, 'home': home, 'reading': reading,
              'social': social, 'social_verdicts_rounded_legacy': verdicts_rounded,
              'first_meetings': first_meetings(s_lives), 'compat': compat,
              'life_counts': {'runs': len(all_lives), 'unique_trajectories': len(L.dedupe(all_lives))}}
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    out.mkdir(parents=True, exist_ok=True)
    slim = lambda m: {k: v for k, v in m.items() if k not in ('goal_by_day',)}
    (out / f'v6_{which}_raw.json').write_text(json.dumps({'lives': [slim(m) for m in all_lives], 'social': results},
                                                         ensure_ascii=False, default=str), encoding='utf-8')
    (out / f'v6_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'final': final, 'home': {g: {k: v for k, v in h.items() if k != 'failing'} for g, h in home.items()},
                                'reading': {k: reading[k] for k in ('v5', 'v6', 'gap_change_v6_minus_v5', 'verdict')},
                                'social': {s: {k: v for k, v in d.items() if k != 'values'} for s, d in social.items()},
                                'life_counts': report['life_counts']}), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
