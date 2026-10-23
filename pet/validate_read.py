"""Round 3 of 2026-10-23: one real reading result (comprehension) and a reading value learnt from
it. Can different reading EXPERIENCES (not counts) form a lasting, changeable preference?
Product experiment, NOT a rule version (default stays v5; every flag is off by default).

    python -m pet.validate_read base2 [out_dir]      # verify the repair candidate base2 (dev + review seeds)
    python -m pet.validate_read dev [out_dir]        # development of the reading candidate
    python -m pet.validate_read validation [out_dir] # fresh seeds, ONCE, only if dev passed

Arms (on the frozen phase A base: rest4 + v6 trigger + ordered endings + emergency unmute):
  base             the frozen round-2 base (pet/validate_eval.py 'base')
  base2            base + no switch margin in the home emergency (PetAgent.emergency_no_margin)
  read_nodecision  base + the reading result world mechanism, value learnt, NEVER in a choice (control:
                   same world, must behave exactly as base)
  read_value       base + reading result + value in the read score (candidate)
  read_flat        base + reading result + the same term on read AND explore (equal bonus, no
                   activity information; control)
Concepts: actual result = comprehension gain of a reading hour (book clarity x focus) and the book
progress it builds; value = read_V (what results reading has given, with confidence n); habit =
read_habit (recent reading frequency, diagnostic only); current plan = the core goal (unchanged).

Designs per birth seed:
  matched  grow 20 days with only a book: a CLEAR book (clarity 0.9) vs a HARD book (0.3). During
           growth the value never decides, so both pets live the same hours and read the same number
           of times (checked: identical action sequences); only the results differ. Then the common
           setting (garden + the standard book 0.6 + one invitation) with the arm's decision rule:
           60 days ('keep'), or from common day 30 the books swap for 30 days ('swap': the clear-book
           pet now reads the hard book and vice versa).
  natural  the same two books with the arm's rule from birth (counts may differ; reported).
  catalogue (safety, social, diversity): 4 growth routes with the standard book + 60 common days;
           A/B pair with 3 withdrawal replicates; the 110-day 'plastic' life; the v4 safe-home lives.
State-matched probe (isolated copies, never lived): both pets of a pair at the same tick, with the
same body, resources, no goal, no recent boredom, no invitation, and the SAME core knowledge (the
clear-book pet's copied into the hard-book pet's copy). Read margin = score(read) - best other.
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
from .engine import core

DEV_SEEDS = list(range(3001, 3011)) + list(range(6001, 6011))
REVIEW_SEEDS = list(range(7021, 7041))          # used on 2026-10-23 (phase A): review only
VALIDATION_SEEDS = list(range(7041, 7061))      # checked unused before this round
SAFE_SEEDS = (1, 42, 901, 7, 123, 2024)
SAFE_ITEMS = (('garden',), ('garden', 'book', 'music'))
GROW, COMMON, SPLIT, PHASE, WASHOUT, WITHDRAW, REPS, WINDOW = 20, 60, 30, 30, 1, 30, 3, 10
PL_COMMON, PL_AWAY, PL_AFTER = 20, 30, 40
CLEAR, HARD, STANDARD = 0.9, 0.3, engine.READ_CLARITY_DEFAULT
BASE = {'scheme': 'rest4', 'interrupt': True, 'ordered': True, 'unmute': True}
ARMS = {
    'base': dict(BASE),
    'base2': dict(BASE, no_margin=True),
    'read_nodecision': dict(BASE, reading=True, decide=False),
    'read_value': dict(BASE, reading=True, decide=True),
    'read_flat': dict(BASE, reading=True, decide=True, flat=True),
}
# CHANGE LOG (before any reading run): the read_* arms were first written on base2. base2 then missed
# its own pre-set verification (dev phase-share failures 10 > base 9: pair|6005|rep1|B withdrawal
# below20), so it is not adopted and the reading arms use the frozen base. Criteria unchanged.
CANDIDATE, CONTROL, FLAT = 'read_value', 'read_nodecision', 'read_flat'
PARAMS = {k: getattr(engine, k) for k in ('READ_CLARITY_DEFAULT', 'READ_VALUE_REF', 'READ_VALUE_WEIGHT', 'EVAL_ALPHA_MIN',
                                          'EVAL_N0', 'EVAL_KEEP', 'HOME_INTERRUPT_BELOW', 'PREF_RATE')}
CONFIG_ID = hashlib.sha256(json.dumps({'arms': ARMS, 'params': PARAMS, 'books': [CLEAR, HARD, STANDARD],
                                       'design': [GROW, COMMON, SPLIT, PHASE, WASHOUT, WITHDRAW, REPS]},
                                      sort_keys=True).encode()).hexdigest()[:12]

# ---- FIXED 2026-10-23 BEFORE any run of this module (development included). Seed = unit.
# Product reason for the sizes: 1 pp of all hours ~ 1.7 reading hours a week, visible in the diary.
#  K1 lasting difference: clear - hard read share over the 60 common days ('keep') >= 1 pp,
#     CI lower > 0, positive in >= 14/20 seeds.
#  K2 persistence: the same over common days 30-60 >= 0.5 pp, CI lower > 0.
#  K3 not just a bonus: K1 gap of read_value minus that of read_flat >= 0.5 pp, CI lower > 0;
#     read_nodecision must show exactly 0 gap in every seed (same world, no decision).
#  K4 changeable: over days 30-60, gap('keep') - gap('swap') >= 1 pp, CI lower > 0.
#  K5 state-matched probe at common day 0: read margin clear - hard > 0, CI lower > 0.
#  H  every unique whole life of the candidate meets the v4 safe-home standard; its phase-share
#     failures are no more than the control's (both reported separately).
#  S  social not meaningfully lost vs the control: seeds with pair B - A >= 1/7 at most 2 fewer,
#     mean B - A at least control - 1/7 (the absolute 'B - A >= 1/7 in >= 14/20' is reported).
#  D  common-phase entropy at most 0.1 bits below the control.
# Dev must pass all of them; otherwise the round stops and no fresh seed is used.
CRITERIA = {'K1_min_gap': 0.01, 'K1_min_positive': 14, 'K2_min_late_gap': 0.005, 'K3_min_vs_flat': 0.005,
            'K4_min_keep_minus_swap': 0.01, 'S_max_fewer_seeds': 2, 'S_max_mean_drop': 1 / 7,
            'D_max_entropy_drop': 0.1}
# base2 (repair candidate) verification, fixed before its run: every unique whole life passes on the
# dev and the review seeds, phase-share failures no more than base, the two regression mornings fire.
BASE2_CRITERIA = {'all_unique_whole_lives': True, 'phase_fails_not_above': 'base'}


def configure(s, arm):
    c = ARMS[arm]
    vs.set_scheme(s, c['scheme'])
    a = s.agent
    a.home_interrupt = c.get('interrupt', False)
    a.ordered_goals = c.get('ordered', False)
    a.home_emergency_unmute = c.get('unmute', False)
    a.emergency_no_margin = c.get('no_margin', False)
    a.reading_outcome = c.get('reading', False)
    a.read_value_in_decision = c.get('decide', False)
    a.read_value_flat = c.get('flat', False)
    a.diagnostics = True
    return s


def new_pet(seed, arm):
    return configure(L.TracedSession(seed, 5), arm)


def run_hours(s, hours, invite_daily=False):
    for _ in range(hours):
        if invite_daily and s.tick % 24 == 8 and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
        s.step()


def read_share(rows):
    return sum(r[1] == 'read' for r in rows) / len(rows) if rows else None


def windows(rows):
    return [read_share(rows[w:w + WINDOW * 24]) for w in range(0, len(rows), WINDOW * 24)]


def value_state(a):
    return {'V': a.read_V, 'n': a.read_n, 'term': a.read_value_term(), 'habit': a.read_habit,
            'progress': a.book_progress, 'reads': a.read_evidence['count']}


# ---------------------------------------------------------------- matched / natural designs
def book_pet(seed, arm, clarity, decide_in_growth):
    s = new_pet(seed, arm)
    s.apply({'kind': 'object', 'value': 'book'})
    s.world.p['book_clarity'] = clarity
    decide = s.agent.read_value_in_decision
    s.agent.read_value_in_decision = decide and decide_in_growth
    run_hours(s, GROW * 24)
    s.agent.read_value_in_decision = decide
    v5.uniform(s)
    s.world.p['book_clarity'] = STANDARD
    return s


def probe(a, b, day):
    """State-matched read margins of two pets (isolated copies)."""
    out = {}
    for label, on in (('with_value', True), ('value_off', False)):
        margins = {}
        for name, x in (('clear', a), ('hard', b)):
            ms = []
            for hunger, energy in ((30, 80), (45, 60), (20, 95)):
                for hour in (10, 15):
                    c = copy.deepcopy(x)
                    c.now = day * 24 + hour
                    c.hunger, c.energy, c.condition, c.shelter = float(hunger), float(energy), 100.0, 60.0
                    c.inventory['food'], c.inventory['material'] = 6.0, 0.0
                    c.goal, c.recent, c.invitation_until = None, [], -1
                    c.knowledge_strength = dict(a.knowledge_strength)
                    c.knowledge = dict(a.knowledge)
                    c.read_value_in_decision = on and c.read_value_in_decision
                    sc = {k: c.score(k, day) for k in core.ACTIONS}
                    ms.append(sc['read'] - max(v for k, v in sc.items() if k != 'read' and v is not None))
            margins[name] = sum(ms) / len(ms)
        out[label] = margins['clear'] - margins['hard']
    return out


def matched(seed, arm):
    lives, res = [], {}
    pets = {name: book_pet(seed, arm, cl, decide_in_growth=False) for name, cl in (('clear', CLEAR), ('hard', HARD))}
    a, b = pets['clear'], pets['hard']
    res['growth_identical'] = [r[1] for r in a.trace] == [r[1] for r in b.trace]
    res['growth_reads'] = {n: p.agent.read_evidence['count'] for n, p in pets.items()}
    res['value_start'] = {n: value_state(p.agent) for n, p in pets.items()}
    res['probe_day0'] = probe(a.agent, b.agent, a.tick // 24)
    for p in pets.values():
        p.phase('common')
    i0 = len(a.trace)
    for p in pets.values():
        run_hours(p, SPLIT * 24)
    res['probe_day30'] = probe(a.agent, b.agent, a.tick // 24)
    res['value_split'] = {n: value_state(p.agent) for n, p in pets.items()}
    early = {n: read_share(p.trace[i0:]) for n, p in pets.items()}
    for branch in ('keep', 'swap'):
        out = {}
        for n, p in pets.items():
            c = copy.deepcopy(p)
            if branch == 'swap':
                c.world.p['book_clarity'] = HARD if n == 'clear' else CLEAR
                c.phase('swap')
            j0 = len(c.trace)
            run_hours(c, (COMMON - SPLIT) * 24)
            out[n] = {'late': read_share(c.trace[j0:]), 'all': read_share(c.trace[i0:]), 'windows': windows(c.trace[i0:]),
                      'value_end': value_state(c.agent)}
            lives.append(L.life_record(c, life_id=f'{arm}|matched|{seed}|{n}|{branch}', arm=arm, design='matched',
                                       seed=seed, book=n, branch=branch))
        res[branch] = out
    res['early'] = early
    return res, lives


def natural(seed, arm):
    pets = {name: book_pet(seed, arm, cl, decide_in_growth=True) for name, cl in (('clear', CLEAR), ('hard', HARD))}
    res = {'growth_reads': {n: p.agent.read_evidence['count'] for n, p in pets.items()}}
    lives = []
    for n, p in pets.items():
        p.phase('common')
        i0 = len(p.trace)
        run_hours(p, COMMON * 24)
        res[n] = read_share(p.trace[i0:])
        lives.append(L.life_record(p, life_id=f'{arm}|natural|{seed}|{n}', arm=arm, design='natural', seed=seed, book=n))
    return res, lives


# ---------------------------------------------------------------- catalogue (safety, social, diversity)
def route_life(seed, route, arm):
    spec = v5.ROUTES[route]
    s = new_pet(seed, arm)
    for obj in spec['objects']:
        s.apply({'kind': 'object', 'value': obj})
    run_hours(s, GROW * 24, invite_daily=spec['invite_daily'])
    v5.uniform(s)
    s.phase('common')
    run_hours(s, COMMON * 24)
    return L.life_record(s, life_id=f'{arm}|route|{seed}|{route}', arm=arm, design='route', seed=seed, setting=route)


def pair_lives(seed, arm):
    s = new_pet(seed, arm)
    s.apply({'kind': 'object', 'value': 'book'})
    run_hours(s, GROW * 24)
    v5.uniform(s)
    branches, lives = {}, []
    for name, daily in (('A', False), ('B', True)):
        c = copy.deepcopy(s)
        c.phase('intervention')
        run_hours(c, PHASE * 24, invite_daily=daily)
        c.phase('washout')
        run_hours(c, WASHOUT * 24)
        branches[name] = c
    for rep in range(REPS):
        for name, s0 in branches.items():
            c = copy.deepcopy(s0)
            if rep:
                c.agent.rng.seed(seed * 1000 + rep)
            c.phase('withdrawal')
            n0 = len(c.events)
            run_hours(c, WITHDRAW * 24)
            ev = [e for e in c.events[n0:] if e['kind'] == 'action']
            rec = L.life_record(c, life_id=f'{arm}|pair|{seed}|rep{rep}|{name}', arm=arm, design='pair', seed=seed,
                                rep=rep, branch=name, met_at_withdrawal=bool(s0.agent.shared))
            rec['spont'] = vs.metrics(ev, WITHDRAW)['spont_per_day']
            lives.append(rec)
    return lives


def plastic_life(seed, arm):
    s = new_pet(seed, arm)
    s.apply({'kind': 'object', 'value': 'book'})
    run_hours(s, GROW * 24)
    v5.uniform(s)
    out = []
    run_hours(s, PL_COMMON * 24)
    for branch in ('stay', 'away'):
        c = copy.deepcopy(s)
        run_hours(c, PL_AWAY * 24, invite_daily=branch == 'away')
        run_hours(c, PL_AFTER * 24)
        out.append(L.life_record(c, life_id=f'{arm}|plastic|{seed}|{branch}', arm=arm, design='plastic', seed=seed))
    return out


def seed_job(args):
    seed, arm, with_read = args
    routes = [route_life(seed, r, arm) for r in v5.ROUTES]
    out = {'seed': seed, 'arm': arm, 'routes': routes, 'pair': pair_lives(seed, arm), 'plastic': plastic_life(seed, arm)}
    if with_read and ARMS[arm].get('reading'):
        out['matched'], out['matched_lives'] = matched(seed, arm)
        out['natural'], out['natural_lives'] = natural(seed, arm)
    return out


def safe_job(args):
    seed, items, arm = args
    s = new_pet(seed, arm)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    s.apply({'kind': 'invite', 'value': None})
    s.phases = [('safe', 0)]
    run_hours(s, 60 * 24)
    return L.life_record(s, life_id=f"{arm}|safe|{seed}|{'+'.join(items)}", arm=arm, design='safe', seed=seed)


# ---------------------------------------------------------------- per seed, per arm
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def all_lives(job):
    return job['routes'] + job['pair'] + job['plastic'] + job.get('matched_lives', []) + job.get('natural_lives', [])


def seed_outcomes(job):
    P = job['pair']
    gap = [mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'B'])
           - mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'A']) for k in range(REPS)]
    common = [m['phases']['common'] for m in job['routes']]
    o = {'pair_B_minus_A_spont': mean(gap), 'entropy_common': mean([c['entropy'] for c in common]),
         'pair_first_meet_A': P[0]['first_meet_tick'], 'pair_met_A': P[0]['met_at_withdrawal']}
    M = job.get('matched')
    if M:
        k, s_ = M['keep'], M['swap']
        o.update(gap_all=k['clear']['all'] - k['hard']['all'], gap_late=k['clear']['late'] - k['hard']['late'],
                 gap_early=M['early']['clear'] - M['early']['hard'],
                 gap_late_swap=s_['clear']['late'] - s_['hard']['late'],
                 keep_minus_swap=(k['clear']['late'] - k['hard']['late']) - (s_['clear']['late'] - s_['hard']['late']),
                 gap_windows=[x - y for x, y in zip(k['clear']['windows'], k['hard']['windows'])],
                 probe0=M['probe_day0']['with_value'], probe0_off=M['probe_day0']['value_off'],
                 probe30=M['probe_day30']['with_value'], probe30_off=M['probe_day30']['value_off'],
                 growth_identical=M['growth_identical'], growth_reads=M['growth_reads']['clear'],
                 V_start_clear=M['value_start']['clear']['V'], V_start_hard=M['value_start']['hard']['V'],
                 term_start_gap=M['value_start']['clear']['term'] - M['value_start']['hard']['term'],
                 term_end_gap=k['clear']['value_end']['term'] - k['hard']['value_end']['term'],
                 habit_end_gap=k['clear']['value_end']['habit'] - k['hard']['value_end']['habit'],
                 swap_term_end_gap=s_['clear']['value_end']['term'] - s_['hard']['value_end']['term'],
                 read_mean_matched=mean([k['clear']['all'], k['hard']['all']]))
        N = job['natural']
        o.update(natural_gap=N['clear'] - N['hard'], natural_growth_reads_gap=N['growth_reads']['clear'] - N['growth_reads']['hard'])
    return o


def summarise(jobs, safe, seeds):
    out = {}
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for arm in sorted({j['arm'] for j in jobs}):
        J = [j for j in jobs if j['arm'] == arm]
        per = {j['seed']: seed_outcomes(j) for j in J}
        lives = [m for j in J for m in all_lives(j)] + [m for m in safe if m['arm'] == arm]
        keys = sorted({k for sd in per for k, v in per[sd].items() if num(v)})
        d = {k: L.describe([per[sd].get(k) for sd in seeds]) for k in keys}
        gaps = [per[sd]['pair_B_minus_A_spont'] for sd in seeds]
        out[arm] = {'seeds': seeds, 'per_seed': per, 'safety': L.safety_summary(lives), 'describe': d,
                    'social_seeds_at_1_7': sum(g >= 1 / 7 for g in gaps),
                    'never_met_A': sum(not per[sd]['pair_met_A'] for sd in seeds),
                    'gap_windows': ([mean([per[sd]['gap_windows'][w] for sd in seeds]) for w in range(COMMON // WINDOW)]
                                    if 'gap_windows' in per[seeds[0]] else None),
                    'growth_identical_all': (all(per[sd]['growth_identical'] for sd in seeds) if 'growth_identical' in per[seeds[0]] else None)}
    return out


def contrast(out, a, b, key):
    xs = [out[a]['per_seed'][sd].get(key) for sd in out[a]['seeds']]
    ys = [out[b]['per_seed'][sd].get(key) for sd in out[b]['seeds']]
    return L.describe([None if x is None or y is None else x - y for x, y in zip(xs, ys)])


def phase_fails(o):
    return o['safety']['unique_trajectories'] - o['safety']['phase_pass']


def evaluate(out):
    C, cand, ctrl = CRITERIA, out[CANDIDATE], out[CONTROL]
    d = cand['describe']
    k3 = contrast(out, CANDIDATE, FLAT, 'gap_all')
    v = {'K1_lasting_difference': d['gap_all']['mean'] >= C['K1_min_gap'] and d['gap_all']['ci95'][0] > 0
                                  and d['gap_all']['positive'] >= C['K1_min_positive'],
         'K2_persistence': d['gap_late']['mean'] >= C['K2_min_late_gap'] and d['gap_late']['ci95'][0] > 0,
         'K3_not_just_bonus': (k3['mean'] >= C['K3_min_vs_flat'] and k3['ci95'][0] > 0
                               and all(x == 0 for x in ctrl['describe']['gap_all']['per_seed'])),
         'K4_changeable': d['keep_minus_swap']['mean'] >= C['K4_min_keep_minus_swap'] and d['keep_minus_swap']['ci95'][0] > 0,
         'K5_state_matched_probe': d['probe0']['mean'] > 0 and d['probe0']['ci95'][0] > 0,
         'H_whole_life': cand['safety']['pass'] == cand['safety']['unique_trajectories'],
         'H_phase_not_above_control': phase_fails(cand) <= phase_fails(ctrl),
         'S_social_kept': (cand['social_seeds_at_1_7'] >= ctrl['social_seeds_at_1_7'] - C['S_max_fewer_seeds']
                           and d['pair_B_minus_A_spont']['mean'] >= ctrl['describe']['pair_B_minus_A_spont']['mean'] - C['S_max_mean_drop']),
         'D_diversity': d['entropy_common']['mean'] >= ctrl['describe']['entropy_common']['mean'] - C['D_max_entropy_drop'],
         'growth_counts_matched': cand['growth_identical_all']}
    v['_values'] = {'K3_vs_flat': k3, 'phase_fails': {a: phase_fails(o) for a, o in out.items()},
                    'social_seeds_at_1_7': {a: o['social_seeds_at_1_7'] for a, o in out.items()}}
    return v


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    dst.mkdir(parents=True, exist_ok=True)
    if which == 'base2':
        report = {}
        for name, seeds in (('dev', DEV_SEEDS), ('review_7021_7040', REVIEW_SEEDS)):
            with Pool(14) as pool:
                jobs = pool.map(seed_job, [(sd, arm, False) for arm in ('base', 'base2') for sd in seeds])
                safe = pool.map(safe_job, [(sd, it, arm) for arm in ('base', 'base2') for sd in SAFE_SEEDS for it in SAFE_ITEMS])
            out = summarise(jobs, safe, seeds)
            report[name] = {a: {'safety': o['safety'], 'phase_fails': phase_fails(o), 'social_seeds_at_1_7': o['social_seeds_at_1_7'],
                                'pair_B_minus_A': o['describe']['pair_B_minus_A_spont'], 'entropy': o['describe']['entropy_common']['mean']}
                            for a, o in out.items()}
            report[name]['verdict'] = {'all_unique_whole_lives': out['base2']['safety']['pass'] == out['base2']['safety']['unique_trajectories'],
                                       'phase_fails_not_above_base': phase_fails(out['base2']) <= phase_fails(out['base'])}
        report['config_id'], report['criteria'] = CONFIG_ID, BASE2_CRITERIA
        report['compat'] = L.compat_check()
        (dst / 'base2_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
        print(json.dumps(L.rounded({k: ({a: {x: y for x, y in v.items() if x not in ('safety', 'pair_B_minus_A')} | {
            'pass': v['safety']['pass'], 'uniq': v['safety']['unique_trajectories'], 'min_home': v['safety']['min_home'],
            'failing': [f['life'] for f in v['safety']['failing'] if f['fails']]} if isinstance(v, dict) and 'safety' in v else v
            for a, v in r.items()} if isinstance(r, dict) and 'verdict' in r else None) for k, r in report.items()}), indent=1, default=str))
        return
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    arms = ['read_nodecision', 'read_value', 'read_flat']
    with Pool(14) as pool:
        jobs = pool.map(seed_job, [(sd, arm, True) for arm in arms for sd in seeds])
        safe = pool.map(safe_job, [(sd, it, arm) for arm in arms for sd in SAFE_SEEDS for it in SAFE_ITEMS])
    out = summarise(jobs, safe, seeds)
    verdict = evaluate(out)
    compat = L.compat_check()
    final = {**{k: v for k, v in verdict.items() if not k.startswith('_')}, 'compat_v1_v6': compat['pass']}
    final['pass'] = all(v is True for v in final.values())
    report = {'sample': which, 'seeds': seeds, 'config_id': CONFIG_ID, 'arms': ARMS, 'params': PARAMS, 'criteria': CRITERIA,
              'final': final, 'values': verdict['_values'], 'compat': compat,
              'arms_summary': {a: {k: v for k, v in o.items() if k != 'per_seed'} for a, o in out.items()},
              'per_seed': {a: o['per_seed'] for a, o in out.items()},
              'contrasts': {f'{a} - {b}': {k: contrast(out, a, b, k) for k in ('gap_all', 'gap_late', 'keep_minus_swap', 'probe0',
                                                                                'pair_B_minus_A_spont', 'entropy_common', 'read_mean_matched')}
                            for a, b in ((CANDIDATE, FLAT), (CANDIDATE, CONTROL), (FLAT, CONTROL))}}
    (dst / f'read_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'final': final, 'phase_fails': verdict['_values']['phase_fails'],
                                'describe': {a: {k: {x: o['describe'][k].get(x) for x in ('mean', 'ci95', 'positive', 'negative')}
                                                 for k in ('gap_all', 'gap_late', 'gap_early', 'keep_minus_swap', 'probe0', 'probe0_off',
                                                           'probe30', 'term_start_gap', 'term_end_gap', 'natural_gap', 'pair_B_minus_A_spont',
                                                           'entropy_common', 'read_mean_matched', 'growth_reads')}
                                             for a, o in out.items()},
                                'gap_windows': {a: o['gap_windows'] for a, o in out.items()},
                                'safety': {a: {k: v for k, v in o['safety'].items() if k != 'failing'} | {
                                    'failing': [f['life'] for f in o['safety']['failing'] if f['fails']]} for a, o in out.items()},
                                'social_seeds_at_1_7': verdict['_values']['social_seeds_at_1_7'],
                                'K3_vs_flat': {x: verdict['_values']['K3_vs_flat'].get(x) for x in ('mean', 'ci95')}}),
                     ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
