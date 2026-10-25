"""Round 8 of 2026-10-25: does checking the home's future before STARTING a leisure plan let the reading
interest show (off-task penalty on reading removed) without making the home less safe?
Product experiment, NOT a rule version (default stays v5; every flag off by default).

    python -m pet.validate_foresight dev [out_dir]          # development (3001-3010, 6001-6010)
    python -m pet.validate_foresight validation [out_dir]   # fresh seeds 7041-7060, ONCE, only if dev passed
                                                            #   (NOT run in round 8)

Base: the round-4/6 candidate arm 'interest' of pet/validate_interest.py (phase A base + reading result
+ long-term interest). Four conditions, only these switches:
  current       as it is
  no_offtask    PetAgent.goal_read_offtask_off (other plans no longer damp reading; round 6)
  foresight     PetAgent.home_foresight (engine SHELTER_AGEING / HOME_FORESIGHT_FLOOR: a NEW leisure plan
                is left out when shelter - 0.35 * 24 * GOAL_MIN_DAYS < 20 at the morning update; the rest
                is chosen by the existing rules, same sort and tie order; none left = no new plan)
  both          no_offtask + foresight                              (CANDIDATE)
The 'learn' bonus, the 12-read target, satiation, weights and the interrupt rules are unchanged.

Designs per birth seed (unit of analysis):
  reading   round 6's design: the matched clear / hard pets at common day 0 (grown under 'current'),
            switches set from common day 0, 60 days 'keep'; the actual continuation + REPS reseeded ones
            (seed * 1000 + rep, the same for both pets and all conditions). Metrics are averaged over the
            continuations within a seed first; never treated as independent samples.
  safety / social / diversity: the catalogue of validate_interest with the switches on FROM BIRTH:
            4 growth routes + 60 common days, the A/B pair with 3 withdrawal replicates, the 110-day
            plastic life with phase marks, the matched keep / swap lives, the v4 safe-home lives; plus the
            reading continuations above. Phase counting: union over runs (recheck_read_phases.safety_union).

CRITERIA, FIXED 2026-10-25 BEFORE ANY RUN OF THIS MODULE (sha256 in docs/pet_foresight/). Candidate 'both';
contrasts paired with 'current' within seed; CI = bootstrap 95 % over the 20 birth seeds.
  E1 60-day read gap clear - hard >= 1 pp, CI lower > 0, positive in >= 14/20 seeds   (round-3/4 K1 levels)
  E2 days 30-60 read gap >= 0.5 pp, CI lower > 0                                    (round-4 P1 levels)
  E3 more than now: 60-day gap - current's, CI lower > 0
  H1 every unique whole life of the candidate meets the v4 safe-home standard
  H2 its phase-share failures are no more than current's (same designs, union counting)
  L1 leisure not traded for the home: route common-phase leisure share - current's, mean >= -1 pp and CI lower > -2 pp
  R1 total reading not lower: mean read share of the two pets over 60 days - current's, mean >= -0.5 pp
  S  social: seeds with pair B - A >= 1/7 at most 2 fewer than current, mean B - A at least current - 1/7
  D  route common-phase entropy at most 0.1 bits below current
  compat  all v1-v6 replays identical
Upkeep share, the foresight-only and no_offtask-only conditions, and the number of plans the check left
out are reported, with no verdict. A better home bought with less leisure does not pass (L1). Dev must
pass ALL; otherwise the round stops, nothing is retuned and no fresh seed is used. If it passes, the
candidate is frozen for an independent run on 7041-7060 (not in this round) and not adopted.
"""
import copy
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

from . import diag_interest as DI
from . import engine
from . import lifestats as L
from . import recheck_read_phases as RP
from . import validate_interest as VI
from . import validate_read as VR
from . import validate_v5 as v5
from . import validate_v5_social as vs
from .engine import core

DEV_SEEDS = VI.DEV_SEEDS
VALIDATION_SEEDS = VI.VALIDATION_SEEDS
ARM = 'interest'
REPS = 5
CONDITIONS = {'current': {}, 'no_offtask': {'goal_read_offtask_off': True}, 'foresight': {'home_foresight': True},
              'both': {'goal_read_offtask_off': True, 'home_foresight': True}}
CANDIDATE, CONTROL = 'both', 'current'
PARAMS = {'SHELTER_AGEING': engine.SHELTER_AGEING, 'HOME_FORESIGHT_FLOOR': engine.HOME_FORESIGHT_FLOOR,
          'GOAL_MIN_DAYS': core.GOAL_MIN_DAYS, 'REPS': REPS}
CRITERIA = {'E1_min_gap': 0.01, 'E1_min_positive': 14, 'E2_min_late_gap': 0.005, 'L1_min_mean': -0.01, 'L1_min_ci_lower': -0.02,
            'R1_min_mean': -0.005, 'S_max_fewer_seeds': 2, 'S_max_mean_drop': 1 / 7, 'D_max_entropy_drop': 0.1}
CONFIG_ID = hashlib.sha256(json.dumps({'conditions': CONDITIONS, 'params': PARAMS, 'criteria': CRITERIA,
                                       'arm': VI.ARMS[ARM]}, sort_keys=True).encode()).hexdigest()[:12]
LATE = (VI.COMMON - VI.SPLIT) * 24


def configure(s, cond):
    VI.configure(s, ARM)
    for k, v in CONDITIONS[cond].items():
        setattr(s.agent, k, v)
    assert not s.agent.home_foresight or s.agent.ordered_goals
    return s


def new_pet(seed, cond):
    return configure(L.TracedSession(seed, 5), cond)


# ---------------------------------------------------------------- catalogue (validate_interest's, switches from birth)
def route_life(seed, route, cond):
    spec = v5.ROUTES[route]
    s = new_pet(seed, cond)
    for obj in spec['objects']:
        s.apply({'kind': 'object', 'value': obj})
    VR.run_hours(s, VI.GROW * 24, invite_daily=spec['invite_daily'])
    v5.uniform(s)
    s.phase('common')
    VR.run_hours(s, VI.COMMON * 24)
    return L.life_record(s, life_id=f'{cond}|route|{seed}|{route}', arm=cond, design='route', seed=seed, setting=route)


def pair_lives(seed, cond):
    s = new_pet(seed, cond)
    s.apply({'kind': 'object', 'value': 'book'})
    VR.run_hours(s, VI.GROW * 24)
    v5.uniform(s)
    branches, lives = {}, []
    for name, daily in (('A', False), ('B', True)):
        c = copy.deepcopy(s)
        c.phase('intervention')
        VR.run_hours(c, VR.PHASE * 24, invite_daily=daily)
        c.phase('washout')
        VR.run_hours(c, VR.WASHOUT * 24)
        branches[name] = c
    for rep in range(VR.REPS):
        for name, s0 in branches.items():
            c = copy.deepcopy(s0)
            if rep:
                c.agent.rng.seed(seed * 1000 + rep)
            c.phase('withdrawal')
            n0 = len(c.events)
            VR.run_hours(c, VR.WITHDRAW * 24)
            ev = [e for e in c.events[n0:] if e['kind'] == 'action']
            rec = L.life_record(c, life_id=f'{cond}|pair|{seed}|rep{rep}|{name}', arm=cond, design='pair', seed=seed,
                                rep=rep, branch=name, met_at_withdrawal=bool(s0.agent.shared))
            rec['spont'] = vs.metrics(ev, VR.WITHDRAW)['spont_per_day']
            lives.append(rec)
    return lives


def plastic_lives(seed, cond):
    s = new_pet(seed, cond)
    s.apply({'kind': 'object', 'value': 'book'})
    VR.run_hours(s, VI.GROW * 24)
    v5.uniform(s)
    out = []
    s.phase('common')
    VR.run_hours(s, VR.PL_COMMON * 24)
    for branch in ('stay', 'away'):
        c = copy.deepcopy(s)
        c.phase('intervention')
        VR.run_hours(c, VR.PL_AWAY * 24, invite_daily=branch == 'away')
        c.phase('recovery')
        VR.run_hours(c, VR.PL_AFTER * 24)
        out.append(L.life_record(c, life_id=f'{cond}|plastic|{seed}|{branch}', arm=cond, design='plastic', seed=seed, branch=branch))
    return out


def book_pet(seed, cond, clarity):
    s = new_pet(seed, cond)
    s.apply({'kind': 'object', 'value': 'book'})
    s.world.p['book_clarity'] = clarity
    decide = s.agent.read_value_in_decision
    s.agent.read_value_in_decision = False
    VR.run_hours(s, VI.GROW * 24)
    s.agent.read_value_in_decision = decide
    v5.uniform(s)
    s.world.p['book_clarity'] = VI.STANDARD
    return s


def matched_lives(seed, cond):
    pets = {n: book_pet(seed, cond, cl) for n, cl in (('clear', VI.CLEAR), ('hard', VI.HARD))}
    for p in pets.values():
        p.phase('common')
        VR.run_hours(p, VI.SPLIT * 24)
    lives = []
    for branch in ('keep', 'swap'):
        for n, p in pets.items():
            c = copy.deepcopy(p)
            if branch == 'swap':
                c.world.p['book_clarity'] = VI.HARD if n == 'clear' else VI.CLEAR
                c.phase('swap')
            VR.run_hours(c, (VI.COMMON - VI.SPLIT) * 24)
            lives.append(L.life_record(c, life_id=f'{cond}|matched|{seed}|{n}|{branch}', arm=cond, design='matched',
                                       seed=seed, book=n, branch=branch))
    return lives


def safe_job(args):
    seed, items, cond = args
    s = new_pet(seed, cond)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    s.apply({'kind': 'invite', 'value': None})
    s.phases = [('safe', 0)]
    VR.run_hours(s, 60 * 24)
    return L.life_record(s, life_id=f"{cond}|safe|{seed}|{'+'.join(items)}", arm=cond, design='safe', seed=seed)


# ---------------------------------------------------------------- reading design (round 6's)
def reading_runs(seed, cond):
    pets0 = {n: VI.book_pet(seed, ARM, cl) for n, cl in (('clear', VI.CLEAR), ('hard', VI.HARD))}
    for p in pets0.values():
        p.phase('common')
    runs = []
    for rep in range(REPS + 1):
        out = {}
        for n, p in pets0.items():
            c = copy.deepcopy(p)
            for k, v in CONDITIONS[cond].items():
                setattr(c.agent, k, v)
            c.agent.read_audit = True
            if rep:
                c.agent.rng.seed(seed * 1000 + rep)
            rows = []
            DI.live(c, VI.COMMON, rows, [])
            rec = L.life_record(c, life_id=f'{cond}|reading|{seed}|rep{rep}|{n}', arm=cond, design='reading', seed=seed, rep=rep, book=n)
            share = lambda rs: sum(r['chosen'] == 'read' for r in rs) / len(rs)
            out[n] = {'all': share(rows), 'late': share(rows[-LATE:]), 'life': rec,
                      'excluded': sum(1 for x in c.agent.plan_log if x['event'] == 'foresight_excluded' and x['day'] >= VI.GROW)}
        runs.append(out)
    return runs


def seed_job(args):
    seed, cond = args
    return {'seed': seed, 'cond': cond, 'routes': [route_life(seed, r, cond) for r in v5.ROUTES], 'pair': pair_lives(seed, cond),
            'plastic': plastic_lives(seed, cond), 'matched': matched_lives(seed, cond), 'reading': reading_runs(seed, cond)}


def check_job(seed):
    """'current' must be validate_interest's 'interest' (catalogue) exactly."""
    j = VI.seed_job((seed, ARM))
    return {'seed': seed, 'fps': sorted(m['fingerprint'] for m in VI.all_lives(j))}


# ---------------------------------------------------------------- per seed
mean = VR.mean


def catalogue_lives(job):
    return job['routes'] + job['pair'] + job['plastic'] + job['matched']


def seed_outcomes(job):
    P = job['pair']
    gap = [mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'B'])
           - mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'A']) for k in range(VR.REPS)]
    common = [m['phases']['common'] for m in job['routes']]
    R = job['reading']
    excl = [x['excluded'] for r in R for x in r.values()]
    return {'pair_B_minus_A_spont': mean(gap), 'entropy_common': mean([c['entropy'] for c in common]),
            'leisure_common': mean([c['leisure'] for c in common]), 'upkeep_common': mean([c['upkeep'] for c in common]),
            'read_routes_common': mean([c['read'] for c in common]),
            'gap_all': mean([r['clear']['all'] - r['hard']['all'] for r in R]),
            'gap_late': mean([r['clear']['late'] - r['hard']['late'] for r in R]),
            'read_all': mean([(r['clear']['all'] + r['hard']['all']) / 2 for r in R]),
            'read_late': mean([(r['clear']['late'] + r['hard']['late']) / 2 for r in R]),
            'leisure_reading': mean([(r[n]['life']['phases']['common']['leisure']) for r in R for n in r]),
            'upkeep_reading': mean([(r[n]['life']['phases']['common']['upkeep']) for r in R for n in r]),
            'excluded_reading_per_life': mean(excl),
            'excluded_routes_per_life': mean([sum(1 for x in m['plan_log'] if x['event'] == 'foresight_excluded') for m in job['routes']])}


def summarise(jobs, safe, seeds):
    out = {}
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for cond in CONDITIONS:
        J = sorted((j for j in jobs if j['cond'] == cond), key=lambda j: j['seed'])
        per = {j['seed']: seed_outcomes(j) for j in J}
        lives = [m for j in J for m in catalogue_lives(j)] + [m for m in safe if m['arm'] == cond] \
            + [r[n]['life'] for j in J for r in j['reading'] for n in r]
        keys = sorted({k for sd in per for k, v in per[sd].items() if num(v)})
        gaps = [per[sd]['pair_B_minus_A_spont'] for sd in seeds]
        out[cond] = {'per_seed': per, 'safety': RP.safety_union(lives),
                     'min_home_any': min(m['whole']['min_home'] for m in lives),
                     'max_below20_any_phase': max(p['below20'] for m in lives for p in m['phases'].values()
                                                  if p['hours'] >= L.PHASE_MIN_DAYS * 24),
                     'describe': {k: L.describe([per[sd].get(k) for sd in seeds]) for k in keys},
                     'social_seeds_at_1_7': sum(g >= 1 / 7 for g in gaps),
                     'catalogue_fingerprints': {j['seed']: sorted(m['fingerprint'] for m in catalogue_lives(j)) for j in J},
                     'reading_fingerprints': {j['seed']: [[r[n]['life']['fingerprint'] for n in ('clear', 'hard')] for r in j['reading']] for j in J}}
    return out


def contrast(out, a, b, key, seeds):
    return L.describe([out[a]['per_seed'][sd][key] - out[b]['per_seed'][sd][key] for sd in seeds])


def evaluate(out, seeds):
    C, cand, ctrl = CRITERIA, out[CANDIDATE], out[CONTROL]
    d = cand['describe']
    lo = lambda x: x['ci95'][0]
    e3 = contrast(out, CANDIDATE, CONTROL, 'gap_all', seeds)
    l1 = contrast(out, CANDIDATE, CONTROL, 'leisure_common', seeds)
    r1 = contrast(out, CANDIDATE, CONTROL, 'read_all', seeds)
    v = {'E1_gap_60d': d['gap_all']['mean'] >= C['E1_min_gap'] and lo(d['gap_all']) > 0 and d['gap_all']['positive'] >= C['E1_min_positive'],
         'E2_gap_days_30_60': d['gap_late']['mean'] >= C['E2_min_late_gap'] and lo(d['gap_late']) > 0,
         'E3_more_than_current': lo(e3) > 0,
         'H1_whole_life': cand['safety']['pass'] == cand['safety']['unique_trajectories'],
         'H2_phase_not_above_current': cand['safety']['phase_fails'] <= ctrl['safety']['phase_fails'],
         'L1_leisure_kept': l1['mean'] >= C['L1_min_mean'] and lo(l1) > C['L1_min_ci_lower'],
         'R1_reading_not_lower': r1['mean'] >= C['R1_min_mean'],
         'S_social_kept': (cand['social_seeds_at_1_7'] >= ctrl['social_seeds_at_1_7'] - C['S_max_fewer_seeds']
                           and d['pair_B_minus_A_spont']['mean'] >= ctrl['describe']['pair_B_minus_A_spont']['mean'] - C['S_max_mean_drop']),
         'D_diversity': d['entropy_common']['mean'] >= ctrl['describe']['entropy_common']['mean'] - C['D_max_entropy_drop']}
    v['_values'] = {'E3': e3, 'L1': l1, 'R1': r1}
    return v


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_foresight'
    dst.mkdir(parents=True, exist_ok=True)
    if which == 'validation':
        dev = json.loads((dst / 'foresight_dev_result.json').read_text(encoding='utf-8'))
        if not dev['final']['pass'] or not VI.seeds_unused():
            raise SystemExit('development did not pass (or seeds already used): no validation run')
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    with Pool(14) as pool:
        jobs = pool.map(seed_job, [(sd, c) for c in CONDITIONS for sd in seeds])
        safe = pool.map(safe_job, [(sd, it, c) for c in CONDITIONS for sd in VR.SAFE_SEEDS for it in VR.SAFE_ITEMS])
        checks = pool.map(check_job, seeds) if which == 'dev' else []
    out = summarise(jobs, safe, seeds)
    verdict = evaluate(out, seeds)
    compat = L.compat_check()
    final = {**{k: x for k, x in verdict.items() if not k.startswith('_')}, 'compat_v1_v6': compat['pass']}
    final['pass'] = all(x is True for x in final.values())
    checks_out = {}
    if which == 'dev':
        checks_out['current_catalogue_is_validate_interest'] = all(out['current']['catalogue_fingerprints'][c['seed']] == c['fps']
                                                                    for c in checks)
        r6 = json.loads((Path(__file__).resolve().parents[1] / 'docs' / 'pet_plan_components' / 'diag_plan_result.json').read_text(encoding='utf-8'))
        r6s = {j['seed']: j for j in r6['per_seed']}
        checks_out['reading_runs_are_round6'] = all(
            out[c]['reading_fingerprints'][sd][rep] == [r6s[sd]['runs'][c][rep][n]['fingerprint'] for n in ('clear', 'hard')]
            for c in ('current', 'no_offtask') for sd in seeds for rep in range(REPS + 1))
    contrasts = {f'{a} - current': {k: contrast(out, a, 'current', k, seeds) for k in out['current']['describe']}
                 for a in CONDITIONS if a != 'current'}
    report = {'sample': which, 'seeds': seeds, 'config_id': CONFIG_ID, 'conditions': CONDITIONS, 'params': PARAMS, 'criteria': CRITERIA,
              'final': final, 'values': verdict['_values'], 'checks': checks_out, 'compat': compat, 'contrasts': contrasts,
              'summary': {c: {k: v for k, v in o.items() if k not in ('per_seed', 'catalogue_fingerprints', 'reading_fingerprints')}
                          for c, o in out.items()},
              'per_seed': {c: o['per_seed'] for c, o in out.items()}}
    (dst / f'foresight_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'final': final, 'checks': checks_out,
                                'safety': {c: {k: o['safety'][k] for k in ('unique_trajectories', 'pass', 'phase_fails')}
                                           | {'min_home': o['min_home_any'], 'failing': [f['life'] for f in o['safety']['failing']]}
                                           for c, o in out.items()}}), ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
