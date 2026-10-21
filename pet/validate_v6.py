"""Rules v6: v5 + home interrupt + rest4 neighbor rule (product experiment).

    python -m pet.validate_v6 dev [out_dir]          # seeds 3001-3010 + 1/42/901/7/123 (already reviewed)
    python -m pet.validate_v6 validation [out_dir]   # seeds 6001-6010, fresh, run once after CRITERIA were fixed

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

Three parts, on the sample's seeds:
  H  safe home: the v4 standard on every life (6 safe-home seeds x 2 settings; the social
     design's full lives; the v5 design's four growth routes + 60 common days), hour by hour.
  S  social: pet.validate_v5_social unchanged (design, CRITERIA, verdict); pets are v6, and
     'cap2' there means v6 with the old daily cap.
  R  reading and variety vs v5, paired on the same seeds (v5 design: grow 20 days on a route,
     then the same garden + book for everyone, 60 days).
"""
import json
import math
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from . import validate_v5 as v5
from . import validate_v5_social as vs
from .engine import Session

DEV_SEEDS = vs.DEV_SEEDS                                    # 3001-3010, already reviewed
R_DEV_EXTRA = [1, 42, 901, 7, 123]                          # v5 DEV_SEEDS, part R / H only
VALIDATION_SEEDS = [6001, 6002, 6003, 6004, 6005, 6006, 6007, 6008, 6009, 6010]
SPENT_SEEDS = [5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009, 5010]   # v6a, not adopted
SAFE_SEEDS = (1, 42, 901, 7, 123, 2024)                     # = tests/test_pet_v4.py HOME_SEEDS
SAFE_ITEMS = (('garden',), ('garden', 'book', 'music'))
H_SCHEMES = ('cap2', 'rest4')
LEISURE = ('garden', 'visit', 'explore', 'read')
COMMON_DAYS = 60

# ---- FIXED 2026-10-21 after the dev run of this version and BEFORE seeds 6001-6010 were run.
# H: the v4 safe-home standard, unchanged, on every life. S: the 2026-10-17 social criteria,
# unchanged. R (new, after v6a): v6 keeps at least 80% of v5's reading-route - control gap,
# loses at most 2 pp of reading on any route, and at most 0.1 bits of activity entropy.
# v6 is adopted only if H holds for rest4 on every life, S says 'adopt' for rest4, and R holds.
CRITERIA = {
    'H_min_home': 3.0, 'H_never_zero': True, 'H_max_below20_share': 0.08,
    'H_max_upkeep_share': 0.15, 'H_min_leisure_share': 0.30, 'H_min_condition': 99.0,
    'H_min_kinds_last_week': 3,
    'S': 'pet.validate_v5_social.CRITERIA, verdict for rest4',
    'R1_min_gap_ratio_vs_v5': 0.8, 'R2_max_read_drop_pp': 2.0, 'R3_max_entropy_drop_bits': 0.1,
}


def new_pet(seed, scheme='cap2', rules=6):
    s = Session(seed, rules)
    vs.set_scheme(s, scheme)
    s.agent.diagnostics = True
    return s


# validate_v5_social builds every pet through new_pet(); here they are v6 pets.
vs.new_pet = new_pet


def life_check(s, hours, invite_daily_until=0):
    homes, cond = [], 100.0
    start = len(s.events)
    for _ in range(hours):
        if s.tick < invite_daily_until and s.tick % 24 == 8 and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
        s.step()
        homes.append(s.agent.shelter)
        cond = min(cond, s.agent.condition)
    ev = [e for e in s.events[start:] if e['kind'] == 'action']
    acts = Counter(e['action'] for e in ev)
    n = len(ev)
    last_week = {e['action'] for e in ev if e['tick'] >= s.tick - 7 * 24}
    return {'min_home': round(min(homes), 2), 'zero_hours': sum(h <= 0 for h in homes),
            'below20': round(sum(h < 20 for h in homes) / len(homes), 4),
            'upkeep': round((acts['gather_material'] + acts['build']) / n, 4),
            'leisure': round(sum(acts[a] for a in LEISURE) / n, 4),
            'read': round(acts['read'] / n, 4),
            'entropy': round(-sum(c / n * math.log2(c / n) for c in acts.values() if c), 4),
            'min_condition': round(cond, 2), 'kinds_last_week': len(last_week),
            'fears_hunger': 'fears_hunger' in s.agent.flags}


def merge(grow_m, obs_m, grow_days, obs_days):
    """The safe-home standard holds over the whole life: growth and observation together."""
    m = dict(obs_m)
    m['min_home'] = min(grow_m['min_home'], obs_m['min_home'])
    m['zero_hours'] += grow_m['zero_hours']
    m['below20'] = round((grow_m['below20'] * grow_days + obs_m['below20'] * obs_days) / (grow_days + obs_days), 4)
    m['min_condition'] = min(grow_m['min_condition'], obs_m['min_condition'])
    return m


def passes(m):
    C = CRITERIA
    return (m['min_home'] >= C['H_min_home'] and m['zero_hours'] == 0 and m['below20'] <= C['H_max_below20_share']
            and m['upkeep'] <= C['H_max_upkeep_share'] and m['leisure'] >= C['H_min_leisure_share']
            and m['min_condition'] >= C['H_min_condition'] and not m['fears_hunger']
            and m['kinds_last_week'] >= C['H_min_kinds_last_week'])


def safe_job(args):
    seed, items, scheme = args
    s = new_pet(seed, scheme)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    s.apply({'kind': 'invite', 'value': None})
    return {'design': 'safe', 'seed': seed, 'setting': '+'.join(items), 'scheme': scheme, **life_check(s, 60 * 24)}


def social_route_job(args):
    """Whole life of the social design's full-life check: route growth, then the common setting."""
    seed, route, scheme = args
    s = new_pet(seed, scheme)
    for obj in vs.ROUTES[route]['objects']:
        s.apply({'kind': 'object', 'value': obj})
    g = life_check(s, vs.GROW * 24, invite_daily_until=vs.GROW * 24 if vs.ROUTES[route]['invite_daily'] else 0)
    for obj in vs.UNIFORM_OBJECTS:
        if obj not in s.world.objects:
            s.apply({'kind': 'object', 'value': obj})
    if s.tick >= s.agent.invitation_until:
        s.apply({'kind': 'invite', 'value': None})
    return {'design': 'social_route', 'seed': seed, 'setting': route, 'scheme': scheme,
            **merge(g, life_check(s, vs.FULL_OBS * 24), vs.GROW, vs.FULL_OBS)}


def v5_route_job(args):
    """The v5 differentiation design (growth route, then garden + book for all), v5 or v6 rules."""
    seed, route, rules = args
    spec = v5.ROUTES[route]
    s = Session(seed, rules)
    for obj in spec['objects']:
        s.apply({'kind': 'object', 'value': obj})
    g = life_check(s, v5.GROW * 24, invite_daily_until=v5.GROW * 24 if spec['invite_daily'] else 0)
    v5.uniform(s)
    obs = life_check(s, COMMON_DAYS * 24)
    return {'design': 'v5_route', 'seed': seed, 'setting': route, 'rules': rules,
            'scheme': 'rest4' if rules >= 6 else 'v5', 'common': obs, **merge(g, obs, v5.GROW, COMMON_DAYS)}


def mean(xs):
    return sum(xs) / len(xs)


def home_part(lives):
    summary = {}
    for sc in H_SCHEMES:
        sub = [m for m in lives if m['scheme'] == sc]
        summary[sc] = {'lives': len(sub), 'pass': sum(m['pass'] for m in sub),
                       'min_home': min(m['min_home'] for m in sub), 'zero_hours': sum(m['zero_hours'] for m in sub),
                       'max_below20': max(m['below20'] for m in sub),
                       'upkeep_range': [min(m['upkeep'] for m in sub), max(m['upkeep'] for m in sub)],
                       'min_leisure': min(m['leisure'] for m in sub),
                       'min_condition': min(m['min_condition'] for m in sub),
                       'failing': [f"{m['design']} {m['seed']} {m['setting']}" for m in sub if not m['pass']]}
    return summary


def reading_part(r_lives, seeds):
    C = CRITERIA
    out = {}
    for rules in (5, 6):
        sub = [m for m in r_lives if m['rules'] == rules]
        share = {r: mean([m['common']['read'] for m in sub if m['setting'] == r]) for r in v5.ROUTES}
        gaps = [next(m['common']['read'] for m in sub if m['seed'] == sd and m['setting'] == 'reading')
                - next(m['common']['read'] for m in sub if m['seed'] == sd and m['setting'] == 'control') for sd in seeds]
        out[f'v{rules}'] = {'read_share': {k: round(v, 4) for k, v in share.items()},
                            'reading_minus_control': vs.describe(gaps),
                            'entropy': round(mean([m['common']['entropy'] for m in sub]), 4),
                            'min_home': min(m['min_home'] for m in sub),
                            'lives_below_3': sum(m['min_home'] < 3 for m in sub), 'lives': len(sub)}
    a, b = out['v5'], out['v6']
    gap5, gap6 = a['reading_minus_control']['mean'], b['reading_minus_control']['mean']
    out['verdict'] = {
        'R1': gap6 > 0 and gap6 >= C['R1_min_gap_ratio_vs_v5'] * gap5,
        'R2': all(b['read_share'][r] >= a['read_share'][r] - C['R2_max_read_drop_pp'] / 100 for r in v5.ROUTES),
        'R3': b['entropy'] >= a['entropy'] - C['R3_max_entropy_drop_bits'],
    }
    out['verdict']['pass'] = all(out['verdict'].values())
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
        results = pool.map(vs.run_seed, seeds)
    for m in h_lives + r_lives:
        m['pass'] = passes(m)
    home = home_part(h_lives + [m for m in r_lives if m['rules'] == 6])
    reading = reading_part(r_lives, r_seeds)
    analysis = vs.analyse(results)
    verdicts = {s: vs.verdict(analysis, s) for s in vs.CANDIDATES}
    adopt = (home['rest4']['pass'] == home['rest4']['lives'] and verdicts['rest4']['adopt']
             and reading['verdict']['pass'])
    report = {'sample': which, 'seeds': seeds, 'reading_seeds': r_seeds, 'criteria': CRITERIA,
              'social_criteria': vs.CRITERIA, 'home': home, 'reading': reading,
              'social_verdicts': verdicts, 'adopt_v6': adopt, 'social_analysis': analysis}
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    out.mkdir(parents=True, exist_ok=True)
    (out / f'v6_{which}_raw.json').write_text(json.dumps({'home_lives': h_lives, 'reading_lives': r_lives, 'social': results},
                                                         ensure_ascii=False, default=str), encoding='utf-8')
    (out / f'v6_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps({'home': home, 'reading': reading, 'social_verdicts': verdicts, 'adopt_v6': adopt},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
