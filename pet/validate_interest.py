"""Round 4 of 2026-10-23: can different reading EXPERIENCES leave an interest that LASTS in a common
setting and still CHANGES under lasting contrary experience? Product experiment, NOT a rule version
(default stays v5; every flag is off by default).

    python -m pet.validate_interest dev [out_dir]          # development (seeds 3001-3010, 6001-6010)
    python -m pet.validate_interest validation [out_dir]   # fresh seeds 7041-7060, ONCE, only if dev passed

Arms (all on the frozen phase A base + the round-3 reading result world mechanism):
  read_nodecision      value learnt, never in a choice              (control: same world)
  read_value           the round-3 single evaluation S in the read score   (current mechanism)
  interest             S + long-term interest I, one term, same bound   (CANDIDATE, engine INTEREST_*)
  interest_nodecision  I learnt, the term stays S                  (long-term part off: must equal read_value)
  read_lowrate         single S, learning-rate floor 0.05 -> 0.01  (control: just a lower learning rate)
  interest_flat        the candidate term on read AND explore      (control: equal bonus, no activity info)
Every arm's term has the same bound: READ_VALUE_WEIGHT * [-0.5, 0.5] * gates.

Design per birth seed ('matched', as round 3): grow 20 days with only a book, CLEAR (0.9) or HARD
(0.3); the value never decides in growth, so both pets live the same hours (checked); only the results
differ. Then the common setting (garden + standard book 0.6 + one invitation), the arm's rule:
  keep  60 common days                  -> persistence (days 30-60)
  swap  from common day 30 the books swap for 30 days -> lasting contrary experience
State-matched probe: a copy of the CLEAR pet with fixed body, resources, no goal, no boredom, no
invitation; into a second copy only the READING MEMORY of the hard pet (read_V, read_n, read_I) is
transplanted. Everything else (traits, knowledge, flags, prefs, memories, current goal) is the same,
so margin(read) differences come from the reading memory alone (0 by construction without it).
Safety counting uses the corrected phase marks and the union over runs (pet/recheck_read_phases.py).
"""
import copy
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

from . import engine
from . import lifestats as L
from . import recheck_read_phases as RP
from . import validate_eval as VE
from . import validate_pause as VP
from . import validate_read as VR
from . import validate_v5 as v5
from . import validate_v5_social as vs
from . import validate_v6 as V6
from .engine import core

DEV_SEEDS = VR.DEV_SEEDS
VALIDATION_SEEDS = list(range(7041, 7061))      # unused before this round (checked in tests and at run time)
GROW, COMMON, SPLIT, WINDOW = VR.GROW, VR.COMMON, VR.SPLIT, VR.WINDOW
CLEAR, HARD, STANDARD = VR.CLEAR, VR.HARD, VR.STANDARD
BASE = dict(VR.BASE, reading=True)
ARMS = {
    'read_nodecision': dict(BASE, decide=False),
    'read_value': dict(BASE, decide=True),
    'interest': dict(BASE, decide=True, interest=True),
    'interest_nodecision': dict(BASE, decide=True, interest=True, interest_decide=False),
    'read_lowrate': dict(BASE, decide=True, alpha_min=engine.READ_LOWRATE_ALPHA_MIN),
    'interest_flat': dict(BASE, decide=True, interest=True, flat=True),
}
CANDIDATE, CONTROL, SINGLE, OFF, LOWRATE, FLAT = ('interest', 'read_nodecision', 'read_value', 'interest_nodecision',
                                                  'read_lowrate', 'interest_flat')
PARAMS = {k: getattr(engine, k) for k in ('READ_CLARITY_DEFAULT', 'READ_VALUE_REF', 'READ_VALUE_WEIGHT', 'EVAL_ALPHA_MIN',
                                          'EVAL_N0', 'EVAL_KEEP', 'INTEREST_RATE', 'READ_LOWRATE_ALPHA_MIN',
                                          'HOME_INTERRUPT_BELOW', 'PREF_RATE')}
CONFIG_ID = hashlib.sha256(json.dumps({'arms': ARMS, 'params': PARAMS, 'books': [CLEAR, HARD, STANDARD],
                                       'design': [GROW, COMMON, SPLIT]}, sort_keys=True).encode()).hexdigest()[:12]
MEMORY_KEYS = ('read_V', 'read_n', 'read_I')

# ---- FIXED 2026-10-23 BEFORE any run of this module (development included). Unit = birth seed;
# effects are candidate pets 'clear' minus 'hard' unless said otherwise; CI = bootstrap 95 %.
#  P1 persistence, behaviour: read share over common days 30-60 ('keep') >= 0.5 pp, CI lower > 0.
#  P2 persistence, decision: state-matched probe at common day 60 ('keep') > 0, CI lower > 0.
#  P3 better than the current single evaluation: P2 probe interest - read_value > 0, CI lower > 0.
#  C1 change, behaviour: over days 30-60, gap(keep) - gap(swap) >= 1 pp, CI lower > 0.
#  C2 change, decision: probe at the end of 'swap' (day 60) < 0, CI upper < 0 (the preference reversed).
#  C3 not just a lower learning rate: C2 probe interest - read_lowrate < 0, CI upper < 0.
#  K1 whole common period: gap over 60 days ('keep') >= 1 pp, CI lower > 0, positive in >= 14/20.
#  K3 not just a bonus: K1 gap interest - interest_flat >= 0.5 pp, CI lower > 0; read_nodecision
#     gap exactly 0 in every seed; interest_nodecision lives identical to read_value in every seed.
#  K5 state-matched probe at common day 0 > 0, CI lower > 0.
#  H  every unique whole life of the candidate meets the v4 safe-home standard; its phase-share
#     failures (corrected counting) are no more than the control's.
#  S  social: seeds with pair B - A >= 1/7 at most 2 fewer than the control, mean B - A at least
#     control - 1/7 (the absolute count is reported).
#  D  common-phase entropy at most 0.1 bits below the control.
#  compat  all v1-v6 replays identical.
# Score bound: every arm's term is READ_VALUE_WEIGHT * [-0.5, 0.5] * gates (tests); mean |term| of
# each arm over the common days is reported so a bigger bonus is not read as a better memory.
# Dev must pass ALL of them; otherwise the round stops and no fresh seed is used.
CRITERIA = {'P1_min_late_gap': 0.005, 'C1_min_keep_minus_swap': 0.01, 'K1_min_gap': 0.01, 'K1_min_positive': 14,
            'K3_min_vs_flat': 0.005, 'S_max_fewer_seeds': 2, 'S_max_mean_drop': 1 / 7, 'D_max_entropy_drop': 0.1}


def configure(s, arm):
    c = ARMS[arm]
    vs.set_scheme(s, c['scheme'])
    a = s.agent
    a.home_interrupt = c.get('interrupt', False)
    a.ordered_goals = c.get('ordered', False)
    a.home_emergency_unmute = c.get('unmute', False)
    a.reading_outcome = c.get('reading', False)
    a.read_value_in_decision = c.get('decide', False)
    a.read_value_flat = c.get('flat', False)
    a.read_interest = c.get('interest', False)
    a.read_interest_in_decision = c.get('interest_decide', True)
    a.read_alpha_min = c.get('alpha_min', engine.EVAL_ALPHA_MIN)
    a.diagnostics = True
    return s


def new_pet(seed, arm):
    return configure(L.TracedSession(seed, 5), arm)


run_hours, read_share, windows = VR.run_hours, VR.read_share, VR.windows


def memory_state(a):
    return {'V': a.read_V, 'n': a.read_n, 'I': a.read_I, 'term': a.read_value_term(), 'pref_read': a.prefs['read'],
            'habit': a.read_habit, 'reads': a.read_evidence['count']}


# ---------------------------------------------------------------- state-matched probe
def probe_margin(x, day):
    ms = []
    for hunger, energy in ((30, 80), (45, 60), (20, 95)):
        for hour in (10, 15):
            c = copy.deepcopy(x)
            c.now = day * 24 + hour
            c.hunger, c.energy, c.condition, c.shelter = float(hunger), float(energy), 100.0, 60.0
            c.inventory['food'], c.inventory['material'] = 6.0, 0.0
            c.goal, c.recent, c.invitation_until = None, [], -1
            sc = {k: c.score(k, day) for k in core.ACTIONS}
            ms.append(sc['read'] - max(v for k, v in sc.items() if k != 'read' and v is not None))
    return sum(ms) / len(ms)


def probe(a, b, day):
    """Read margin of the clear pet minus the same pet carrying the hard pet's reading memory."""
    out = {}
    for label, on in (('with_memory', True), ('memory_off', False)):
        x = copy.deepcopy(a)
        y = copy.deepcopy(a)
        for k in MEMORY_KEYS:
            setattr(y, k, copy.deepcopy(getattr(b, k)))
        for c in (x, y):
            c.read_value_in_decision = on and c.read_value_in_decision
        out[label] = probe_margin(x, day) - probe_margin(y, day)
    return out


def mean_abs_term(s, i0):
    ds = [e['decision'] for e in s.events if e['kind'] == 'action' and e['tick'] >= i0 and e.get('decision')]
    vals = [abs(d.get('read_value', 0.0)) for d in ds if 'read_value' in d]
    return sum(vals) / len(vals) / engine.READ_VALUE_WEIGHT if vals else 0.0


# ---------------------------------------------------------------- designs
def book_pet(seed, arm, clarity):
    s = new_pet(seed, arm)
    s.apply({'kind': 'object', 'value': 'book'})
    s.world.p['book_clarity'] = clarity
    decide = s.agent.read_value_in_decision
    s.agent.read_value_in_decision = False                 # growth: never decides -> same lives
    run_hours(s, GROW * 24)
    s.agent.read_value_in_decision = decide
    v5.uniform(s)
    s.world.p['book_clarity'] = STANDARD
    return s


def matched(seed, arm):
    lives, res = [], {}
    pets = {name: book_pet(seed, arm, cl) for name, cl in (('clear', CLEAR), ('hard', HARD))}
    a, b = pets['clear'], pets['hard']
    res['growth_identical'] = [r[1] for r in a.trace] == [r[1] for r in b.trace]
    res['growth_reads'] = {n: p.agent.read_evidence['count'] for n, p in pets.items()}
    res['memory_start'] = {n: memory_state(p.agent) for n, p in pets.items()}
    res['probe_day0'] = probe(a.agent, b.agent, a.tick // 24)
    for p in pets.values():
        p.phase('common')
    i0, t0 = len(a.trace), a.tick
    for p in pets.values():
        run_hours(p, SPLIT * 24)
    res['probe_day30'] = probe(a.agent, b.agent, a.tick // 24)
    res['memory_split'] = {n: memory_state(p.agent) for n, p in pets.items()}
    res['early'] = {n: read_share(p.trace[i0:]) for n, p in pets.items()}
    for branch in ('keep', 'swap'):
        out = {}
        cs = {}
        for n, p in pets.items():
            c = copy.deepcopy(p)
            if branch == 'swap':
                c.world.p['book_clarity'] = HARD if n == 'clear' else CLEAR
                c.phase('swap')
            j0 = len(c.trace)
            run_hours(c, (COMMON - SPLIT) * 24)
            cs[n] = c
            out[n] = {'late': read_share(c.trace[j0:]), 'all': read_share(c.trace[i0:]), 'windows': windows(c.trace[i0:]),
                      'memory_end': memory_state(c.agent), 'mean_abs_term': mean_abs_term(c, t0)}
            lives.append(L.life_record(c, life_id=f'{arm}|matched|{seed}|{n}|{branch}', arm=arm, design='matched',
                                       seed=seed, book=n, branch=branch))
        out['probe_end'] = probe(cs['clear'].agent, cs['hard'].agent, cs['clear'].tick // 24)
        res[branch] = out
    return res, lives


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
        run_hours(c, VR.PHASE * 24, invite_daily=daily)
        c.phase('washout')
        run_hours(c, VR.WASHOUT * 24)
        branches[name] = c
    for rep in range(VR.REPS):
        for name, s0 in branches.items():
            c = copy.deepcopy(s0)
            if rep:
                c.agent.rng.seed(seed * 1000 + rep)
            c.phase('withdrawal')
            n0 = len(c.events)
            run_hours(c, VR.WITHDRAW * 24)
            ev = [e for e in c.events[n0:] if e['kind'] == 'action']
            rec = L.life_record(c, life_id=f'{arm}|pair|{seed}|rep{rep}|{name}', arm=arm, design='pair', seed=seed,
                                rep=rep, branch=name, met_at_withdrawal=bool(s0.agent.shared))
            rec['spont'] = vs.metrics(ev, VR.WITHDRAW)['spont_per_day']
            lives.append(rec)
    return lives


def plastic_lives(seed, arm):
    """The 110-day plastic life with phase marks (the corrected form of validate_read.plastic_life)."""
    s = new_pet(seed, arm)
    s.apply({'kind': 'object', 'value': 'book'})
    run_hours(s, GROW * 24)
    v5.uniform(s)
    out = []
    s.phase('common')
    run_hours(s, VR.PL_COMMON * 24)
    for branch in ('stay', 'away'):
        c = copy.deepcopy(s)
        c.phase('intervention')
        run_hours(c, VR.PL_AWAY * 24, invite_daily=branch == 'away')
        c.phase('recovery')
        run_hours(c, VR.PL_AFTER * 24)
        out.append(L.life_record(c, life_id=f'{arm}|plastic|{seed}|{branch}', arm=arm, design='plastic', seed=seed,
                                 branch=branch))
    return out


def seed_job(args):
    seed, arm = args
    out = {'seed': seed, 'arm': arm, 'routes': [route_life(seed, r, arm) for r in v5.ROUTES],
           'pair': pair_lives(seed, arm), 'plastic': plastic_lives(seed, arm)}
    out['matched'], out['matched_lives'] = matched(seed, arm)
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
mean = VR.mean


def all_lives(job):
    return job['routes'] + job['pair'] + job['plastic'] + job['matched_lives']


def seed_outcomes(job):
    P = job['pair']
    gap = [mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'B'])
           - mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'A']) for k in range(VR.REPS)]
    common = [m['phases']['common'] for m in job['routes']]
    M = job['matched']
    k, w = M['keep'], M['swap']
    return {'pair_B_minus_A_spont': mean(gap), 'entropy_common': mean([c['entropy'] for c in common]),
            'pair_met_A': P[0]['met_at_withdrawal'],
            'gap_all': k['clear']['all'] - k['hard']['all'], 'gap_late': k['clear']['late'] - k['hard']['late'],
            'gap_early': M['early']['clear'] - M['early']['hard'],
            'gap_late_swap': w['clear']['late'] - w['hard']['late'],
            'keep_minus_swap': (k['clear']['late'] - k['hard']['late']) - (w['clear']['late'] - w['hard']['late']),
            'gap_windows': [x - y for x, y in zip(k['clear']['windows'], k['hard']['windows'])],
            'swap_gap_windows': [x - y for x, y in zip(w['clear']['windows'], w['hard']['windows'])],
            'probe0': M['probe_day0']['with_memory'], 'probe0_off': M['probe_day0']['memory_off'],
            'probe30': M['probe_day30']['with_memory'],
            'probe_keep60': k['probe_end']['with_memory'], 'probe_keep60_off': k['probe_end']['memory_off'],
            'probe_swap60': w['probe_end']['with_memory'], 'probe_swap60_off': w['probe_end']['memory_off'],
            'growth_identical': M['growth_identical'], 'growth_reads': M['growth_reads']['clear'],
            'V_gap_start': M['memory_start']['clear']['V'] - M['memory_start']['hard']['V'],
            'I_gap_start': M['memory_start']['clear']['I'] - M['memory_start']['hard']['I'],
            'V_gap_keep60': k['clear']['memory_end']['V'] - k['hard']['memory_end']['V'],
            'I_gap_keep60': k['clear']['memory_end']['I'] - k['hard']['memory_end']['I'],
            'I_gap_swap60': w['clear']['memory_end']['I'] - w['hard']['memory_end']['I'],
            'term_gap_keep60': k['clear']['memory_end']['term'] - k['hard']['memory_end']['term'],
            'pref_read_gap_keep60': k['clear']['memory_end']['pref_read'] - k['hard']['memory_end']['pref_read'],
            'mean_abs_term': mean([k['clear']['mean_abs_term'], k['hard']['mean_abs_term']]),
            'read_mean_matched': mean([k['clear']['all'], k['hard']['all']]),
            'fingerprints': sorted(m['fingerprint'] for m in all_lives(job))}


def summarise(jobs, safe, seeds):
    out = {}
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for arm in ARMS:
        J = [j for j in jobs if j['arm'] == arm]
        if not J:
            continue
        per = {j['seed']: seed_outcomes(j) for j in J}
        lives = [m for j in J for m in all_lives(j)] + [m for m in safe if m['arm'] == arm]
        keys = sorted({k for sd in per for k, v in per[sd].items() if num(v)})
        gaps = [per[sd]['pair_B_minus_A_spont'] for sd in seeds]
        out[arm] = {'seeds': seeds, 'per_seed': per, 'safety': RP.safety_union(lives),
                    'describe': {k: L.describe([per[sd].get(k) for sd in seeds]) for k in keys},
                    'social_seeds_at_1_7': sum(g >= 1 / 7 for g in gaps),
                    'never_met_A': sum(not per[sd]['pair_met_A'] for sd in seeds),
                    'gap_windows': [mean([per[sd]['gap_windows'][i] for sd in seeds]) for i in range(COMMON // WINDOW)],
                    'swap_gap_windows': [mean([per[sd]['swap_gap_windows'][i] for sd in seeds]) for i in range(COMMON // WINDOW)],
                    'growth_identical_all': all(per[sd]['growth_identical'] for sd in seeds)}
    return out


def contrast(out, a, b, key):
    xs = [out[a]['per_seed'][sd].get(key) for sd in out[a]['seeds']]
    ys = [out[b]['per_seed'][sd].get(key) for sd in out[b]['seeds']]
    return L.describe([None if x is None or y is None else x - y for x, y in zip(xs, ys)])


def evaluate(out):
    C, cand, ctrl = CRITERIA, out[CANDIDATE], out[CONTROL]
    d = cand['describe']
    lo = lambda x: x['ci95'][0]
    hi = lambda x: x['ci95'][1]
    p3 = contrast(out, CANDIDATE, SINGLE, 'probe_keep60')
    c3 = contrast(out, CANDIDATE, LOWRATE, 'probe_swap60')
    k3 = contrast(out, CANDIDATE, FLAT, 'gap_all')
    same_off = all(out[OFF]['per_seed'][sd]['fingerprints'] == out[SINGLE]['per_seed'][sd]['fingerprints']
                   for sd in cand['seeds'])
    v = {'P1_persistence_behaviour': d['gap_late']['mean'] >= C['P1_min_late_gap'] and lo(d['gap_late']) > 0,
         'P2_persistence_probe': d['probe_keep60']['mean'] > 0 and lo(d['probe_keep60']) > 0,
         'P3_better_than_single': p3['mean'] > 0 and lo(p3) > 0,
         'C1_change_behaviour': d['keep_minus_swap']['mean'] >= C['C1_min_keep_minus_swap'] and lo(d['keep_minus_swap']) > 0,
         'C2_change_probe_reversed': d['probe_swap60']['mean'] < 0 and hi(d['probe_swap60']) < 0,
         'C3_not_just_lower_rate': c3['mean'] < 0 and hi(c3) < 0,
         'K1_whole_common': d['gap_all']['mean'] >= C['K1_min_gap'] and lo(d['gap_all']) > 0
                            and d['gap_all']['positive'] >= C['K1_min_positive'],
         'K3_not_just_bonus': (k3['mean'] >= C['K3_min_vs_flat'] and lo(k3) > 0
                               and all(x == 0 for x in ctrl['describe']['gap_all']['per_seed']) and same_off),
         'K5_probe_day0': d['probe0']['mean'] > 0 and lo(d['probe0']) > 0,
         'H_whole_life': cand['safety']['pass'] == cand['safety']['unique_trajectories'],
         'H_phase_not_above_control': cand['safety']['phase_fails'] <= ctrl['safety']['phase_fails'],
         'S_social_kept': (cand['social_seeds_at_1_7'] >= ctrl['social_seeds_at_1_7'] - C['S_max_fewer_seeds']
                           and d['pair_B_minus_A_spont']['mean'] >= ctrl['describe']['pair_B_minus_A_spont']['mean'] - C['S_max_mean_drop']),
         'D_diversity': d['entropy_common']['mean'] >= ctrl['describe']['entropy_common']['mean'] - C['D_max_entropy_drop'],
         'growth_counts_matched': cand['growth_identical_all']}
    v['_values'] = {'P3_vs_single': p3, 'C3_vs_lowrate': c3, 'K3_vs_flat': k3, 'interest_off_equals_single': same_off,
                    'phase_fails': {a: o['safety']['phase_fails'] for a, o in out.items()},
                    'whole_pass': {a: [o['safety']['pass'], o['safety']['unique_trajectories']] for a, o in out.items()},
                    'social_seeds_at_1_7': {a: o['social_seeds_at_1_7'] for a, o in out.items()}}
    return v


def seeds_unused():
    used = (set(VE.DEV_SEEDS) | set(VE.VALIDATION_SEEDS) | set(VP.VALIDATION_SEEDS) | set(V6.VALIDATION_SEEDS)
            | set(V6.SPENT_SEEDS) | set(DEV_SEEDS))
    return not set(VALIDATION_SEEDS) & used


SHOW = ('gap_all', 'gap_early', 'gap_late', 'gap_late_swap', 'keep_minus_swap', 'probe0', 'probe30', 'probe_keep60',
        'probe_swap60', 'probe_keep60_off', 'V_gap_start', 'I_gap_start', 'V_gap_keep60', 'I_gap_keep60', 'I_gap_swap60',
        'term_gap_keep60', 'pref_read_gap_keep60', 'mean_abs_term', 'read_mean_matched', 'pair_B_minus_A_spont',
        'entropy_common', 'growth_reads')


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    dst.mkdir(parents=True, exist_ok=True)
    if which == 'validation':
        dev = json.loads((dst / 'interest_dev_result.json').read_text(encoding='utf-8'))
        if not dev['final']['pass'] or not seeds_unused():
            raise SystemExit('development did not pass (or seeds already used): no validation run')
    seeds = DEV_SEEDS if which == 'dev' else VALIDATION_SEEDS
    with Pool(14) as pool:
        jobs = pool.map(seed_job, [(sd, arm) for arm in ARMS for sd in seeds])
        safe = pool.map(safe_job, [(sd, it, arm) for arm in ARMS for sd in VR.SAFE_SEEDS for it in VR.SAFE_ITEMS])
    out = summarise(jobs, safe, seeds)
    verdict = evaluate(out)
    compat = L.compat_check()
    final = {**{k: v for k, v in verdict.items() if not k.startswith('_')}, 'compat_v1_v6': compat['pass']}
    final['pass'] = all(v is True for v in final.values())
    report = {'sample': which, 'seeds': seeds, 'config_id': CONFIG_ID, 'arms': ARMS, 'params': PARAMS, 'criteria': CRITERIA,
              'final': final, 'values': verdict['_values'], 'compat': compat,
              'arms_summary': {a: {k: v for k, v in o.items() if k != 'per_seed'} for a, o in out.items()},
              'per_seed': {a: {sd: {k: v for k, v in r.items() if k != 'fingerprints'} for sd, r in o['per_seed'].items()}
                           for a, o in out.items()},
              'contrasts': {f'{a} - {b}': {k: contrast(out, a, b, k) for k in SHOW if k != 'growth_reads'}
                            for a, b in ((CANDIDATE, SINGLE), (CANDIDATE, LOWRATE), (CANDIDATE, FLAT), (CANDIDATE, CONTROL),
                                         (LOWRATE, SINGLE), (SINGLE, CONTROL))}}
    (dst / f'interest_{which}_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'final': final, 'values': {k: v for k, v in verdict['_values'].items()
                                                           if not isinstance(v, dict) or 'mean' not in v}
                                | {k: {x: v.get(x) for x in ('mean', 'ci95')} for k, v in verdict['_values'].items()
                                   if isinstance(v, dict) and 'mean' in v},
                                'describe': {a: {k: {x: o['describe'][k].get(x) for x in ('mean', 'ci95', 'positive', 'negative')}
                                                 for k in SHOW} for a, o in out.items()},
                                'gap_windows': {a: o['gap_windows'] for a, o in out.items()},
                                'swap_gap_windows': {a: o['swap_gap_windows'] for a, o in out.items()},
                                'failing': {a: o['safety']['failing'] for a, o in out.items()}}),
                     ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
