"""Round 11 of 2026-10-25: reading + social interest. Can different reading AND social experiences leave
interests that persist in a common setting, adapt to new experiences, and compete for the pet's time,
without making the home less safe? Product experiment, NOT a rule version (default stays v5).

    python -m pet.validate_social dev [out_dir]      # development (3001-3010, 6001-6010); default docs/pet_social

No validation mode in this round: if development passes, the candidate is only made ready to freeze.

Reference: the frozen, independently validated round-8 candidate (validate_foresight 'both': interest arm +
goal_read_offtask_off + home_foresight), unchanged. Extension: pet/social_interest.py (social memory with
the reading memory's rule; social result = neighbor warmth x focus). Arms (all on the reference):
  ref        social memory learnt, never decides                      (= the validated candidate exactly)
  B          social term in the 'explore' score when she can meet     (CANDIDATE: interest moves the pet out)
  A          social term in the visit chance after going out          (mechanism control)
  B_frozen   B with the two experimental memories frozen at common day 0 (confidence included)
  none       neither experimental term decides (reading term off too)  (the four cells must live identically)
  B_sym      B + explore_offtask_off (plan damping lifted for explore too; secondary, no verdict)
Plan penalties: FIXED BEFORE ANY RUN. The candidate keeps the reference's plan rules as validated (reading
exempt from the off-task damping, explore not). B_sym measures what that asymmetry costs or gives; it is
reported only and cannot become the candidate in this round.

Design per birth seed (unit of analysis), 2 x 2 within the seed:
  growth 20 days, book + garden, an invitation every day: book clear 0.9 / hard 0.3 x neighbor warm 0.9 /
  cold 0.3. No experimental term decides in growth, so the four histories must be identical (actions,
  body, resources, plans, knowledge, traits, likings, generator state; checked); only the reading and
  social memories (and the recorded results) may differ.
  then the common setting (v5.uniform: one invitation; book 0.6, neighbor 0.6) for 30 days, and from common
  day 30 three branches of 30 days:
    keep           book 0.6, neighbor 0.6 for everyone
    read_change    grown with the clear book -> 0.3, with the hard book -> 0.9; neighbor 0.6
    social_change  grown with a warm neighbor -> 0.3, with a cold one -> 0.9; book 0.6
  continuations: the actual one + REPS reseeded from common day 0 (seed * 1000 + rep; the same for the four
  cells, every arm and every branch). Metrics are averaged over continuations within a seed first.
Exposure is recorded per pet and window (reading hours and results; hours she could meet unprompted;
spontaneous and invited visits; social results) and nothing is dropped for low exposure.
Effects (per seed): book effect on m = mean over neighbor of m(clear) - m(hard); neighbor effect = mean over
book of m(warm) - m(cold); interaction = [m(clear,warm) - m(hard,warm)] - [m(clear,cold) - m(hard,cold)].
Windows: C1 = common days 0-30 (before the branches), C2 = common days 30-60 (per branch).
Visits: 'spontaneous' = visit hours without a pending invitation; invited visits are counted apart.

CRITERIA, FIXED 2026-10-25 BEFORE ANY RUN OF THIS MODULE (sha256 in docs/pet_social/). Candidate B; CI =
bootstrap 95 % over the 20 birth seeds; contrasts with ref / B_frozen paired within seed.
  P1 reading persists: book effect on read share, C1 >= 1 pp, CI lower > 0, positive in >= 14/20
  P2 reading persists late: book effect on read share, C2 keep >= 0.5 pp, CI lower > 0
  P3 social persists: neighbor effect on spontaneous visits / day, C1 >= 1/7, CI lower > 0, >= 14/20
  P4 social persists late: same, C2 keep >= 1/14, CI lower > 0
  G  interest moves the pet out: neighbor effect on the share of explore among the hours she could meet
     unprompted, C1 > 0, CI lower > 0
  R1 reading adapts: book effect on read share C2, read_change - keep <= -1 pp, CI upper < 0
  R2 social adapts: neighbor effect on spontaneous visits / day C2, social_change - keep <= -1/7, CI upper < 0
  L1 learning adds reading adaptation: R1 contrast of B minus that of B_frozen < 0, CI upper < 0
  L2 learning adds social adaptation: R2 contrast of B minus that of B_frozen < 0, CI upper < 0
  N0 'none': the four cells live identically in every seed, continuation and branch
  N1 growth: the four histories identical in every seed and arm
  H1 every unique whole life of B (catalogue + design) meets the v4 safe-home standard
  H2 B's phase-share failures are no more than ref's (same designs, union counting)
  M  maintenance: route common-phase upkeep share B - ref, mean >= -0.5 pp and CI lower > -1 pp
  S  pair design social (as round 8): seeds with B - A >= 1/7 at most 2 fewer than ref, mean at least ref - 1/7
  D  route common-phase entropy at most 0.1 bits below ref
  compat  all v1-v6 replays identical
Reported with no verdict: cross effects (neighbor effect on reading, book effect on visits), interactions,
the full time budget per cell and window, total leisure (an observation, not a constraint), exposure,
invited visits, arm A's and B_sym's effects. Dev must pass ALL; otherwise the round stops, nothing is
retuned, and the failure is diagnosed with these criteria unchanged.
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
from . import recheck_read_phases as RP
from . import validate_foresight as VF
from . import validate_read as VR
from . import validate_v5 as v5
from . import validate_v5_social as vs
from .social_interest import SocialSession

DEV_SEEDS = VF.DEV_SEEDS
REPS = 5
GROW, COMMON1, COMMON2 = 20, 30, 30
CLEAR, HARD, WARM, COLD, STANDARD = 0.9, 0.3, 0.9, 0.3, 0.6
CELLS = [(b, n) for b in ('clear', 'hard') for n in ('warm', 'cold')]
BRANCHES = ('keep', 'read_change', 'social_change')
ARMS = {'ref': {}, 'B': {'entry': 'B'}, 'A': {'entry': 'A'}, 'B_frozen': {'entry': 'B', 'freeze': True},
        'none': {'no_read_term': True}, 'B_sym': {'entry': 'B', 'explore_offtask_off': True}}
CANDIDATE, REF, FROZEN, NONE = 'B', 'ref', 'B_frozen', 'none'
CATALOGUE_ARMS = ('ref', 'B', 'A', 'B_sym')
PARAMS = {'books': [CLEAR, HARD, STANDARD], 'warmth': [WARM, COLD, STANDARD], 'design': [GROW, COMMON1, COMMON2, REPS],
          'READ_VALUE_WEIGHT': engine.READ_VALUE_WEIGHT, 'VISIT_PREF': engine.VISIT_PREF}
CRITERIA = {'P1_min': 0.01, 'P1_pos': 14, 'P2_min': 0.005, 'P3_min': 1 / 7, 'P3_pos': 14, 'P4_min': 1 / 14,
            'R1_max': -0.01, 'R2_max': -1 / 7, 'M_mean': -0.005, 'M_ci_lower': -0.01,
            'S_max_fewer_seeds': 2, 'S_max_mean_drop': 1 / 7, 'D_max_entropy_drop': 0.1}
CONFIG_ID = hashlib.sha256(json.dumps({'arms': ARMS, 'params': PARAMS, 'criteria': CRITERIA, 'ref': VF.CONDITIONS['both']},
                                      sort_keys=True).encode()).hexdigest()[:12]
MEM_KEYS = {'read_V', 'read_n', 'read_I', 'read_today', 'book_progress', 's_V', 's_n', 's_I', 's_today', 'social_log',
            'last', 'read_evidence', '_focus', 'frozen'}


def configure(s, arm):
    VF.configure(s, 'both')                  # the validated candidate's switches, unchanged
    a, c = s.agent, ARMS[arm]
    a.social_memory = True
    a.social_entry = c.get('entry')
    a.explore_offtask_off = c.get('explore_offtask_off', False)
    if c.get('no_read_term'):
        a.read_value_in_decision = False
    return s


def new_pet(seed, arm):
    return configure(SocialSession(seed, 5), arm)


# ---------------------------------------------------------------- growth check
def state_digest(s):
    a = s.agent
    keep = {k: v for k, v in vars(a).items() if k not in MEM_KEYS and k not in ('world', 'rng')}
    ev = [{k: v for k, v in e.items() if k not in ('decision', 'read_outcome', 'text')} for e in s.events]
    h = hashlib.sha256(repr(sorted((k, repr(v)) for k, v in keep.items())).encode())
    w = {k: (v.getstate() if k == 'rng' else v) for k, v in vars(s.world).items() if k != 'p'}
    wp = {k: v for k, v in s.world.p.items() if k not in ('book_clarity', 'neighbor_warmth')}
    h.update(repr(sorted((k, repr(v)) for k, v in w.items())).encode() + repr(sorted(wp.items())).encode())
    h.update(repr(a.rng.getstate()).encode())
    h.update(repr(ev).encode())
    h.update(repr(s.trace).encode())
    return h.hexdigest()


def grow(seed, arm):
    pets = {}
    for b, n in CELLS:
        s = new_pet(seed, arm)
        s.apply({'kind': 'object', 'value': 'book'})
        s.apply({'kind': 'object', 'value': 'garden'})
        s.world.p['book_clarity'] = CLEAR if b == 'clear' else HARD
        s.world.p['neighbor_warmth'] = WARM if n == 'warm' else COLD
        s.agent.exp_decide = False
        VR.run_hours(s, GROW * 24, invite_daily=True)
        pets[(b, n)] = s
    digests = {c: state_digest(p) for c, p in pets.items()}
    for s in pets.values():
        s.agent.exp_decide = True
        v5.uniform(s)
        s.world.p['book_clarity'], s.world.p['neighbor_warmth'] = STANDARD, STANDARD
        if ARMS[arm].get('freeze'):
            s.agent.freeze()
        s.phase('common')
    mem = {f'{b}|{n}': {'read_V': p.agent.read_V, 'read_I': p.agent.read_I, 's_V': p.agent.s_V, 's_I': p.agent.s_I,
                        'reads': p.agent.read_evidence['count'], 'visits': len(p.agent.social_log)} for (b, n), p in pets.items()}
    return pets, len(set(digests.values())) == 1, mem


# ---------------------------------------------------------------- per window
def window(s, n0, t0):
    ev = [e for e in s.events[n0:] if e['kind'] == 'action']
    n = len(ev)
    acts = Counter(e['action'] for e in ev)
    avail = [e for e in ev if e['social_diag']['available_uninvited'] and e['social_diag']['met'] and not e['social_diag']['invited']]
    days = n / 24
    soc = [x for x in s.agent.social_log if x[0] >= t0]
    reads = [e for e in ev if e['core_action'] == 'read']
    return {'hours': n, **{f'share_{k}': acts[k] / n for k in L.CATEGORIES},
            'read': acts['read'] / n, 'leisure': sum(acts[k] for k in L.LEISURE) / n, 'upkeep': sum(acts[k] for k in L.UPKEEP) / n,
            'spont_per_day': sum(1 for e in ev if e['action'] == 'visit' and not e['invited']) / days,
            'invited_per_day': sum(1 for e in ev if e['action'] == 'visit' and e['invited']) / days,
            'avail_hours_per_day': len(avail) / days,
            'explore_in_avail': (sum(e['core_action'] == 'explore' for e in avail) / len(avail)) if avail else None,
            'read_hours': len(reads), 'read_gain_mean': (sum(e['read_outcome']['gain'] for e in reads) / len(reads)) if reads else None,
            'social_results': len(soc), 'social_gain_mean': (sum(x[1] for x in soc) / len(soc)) if soc else None}


def slim(rec):
    return {'life_id': rec['life_id'], 'fingerprint': rec['fingerprint'], 'fails': rec['fails'], 'h_pass': rec['h_pass'],
            'phase_fails': rec['phase_fails'], 'min_home': rec['whole']['min_home'],
            'phases': {k: {'fails': p['fails'], 'below20': p['below20'], 'hours': p['hours']} for k, p in rec['phases'].items()}}


def design_job(args):
    seed, arm = args
    pets, same_growth, mem = grow(seed, arm)
    reps, lives, none_identical = [], [], True
    for rep in range(REPS + 1):
        cur = {}
        for c, p in pets.items():
            x = copy.deepcopy(p)
            if rep:
                x.agent.rng.seed(seed * 1000 + rep)
            cur[c] = x
        out = {'C1': {}, 'C2': {b: {} for b in BRANCHES}}
        for c, x in cur.items():
            n0, t0 = len(x.events), x.tick
            VR.run_hours(x, COMMON1 * 24)
            out['C1'][f'{c[0]}|{c[1]}'] = window(x, n0, t0)
        for br in BRANCHES:
            fps = set()
            for (b, n), x in cur.items():
                y = copy.deepcopy(x)
                if br == 'read_change':
                    y.world.p['book_clarity'] = HARD if b == 'clear' else CLEAR
                elif br == 'social_change':
                    y.world.p['neighbor_warmth'] = COLD if n == 'warm' else WARM
                y.phase(br)
                n0, t0 = len(y.events), y.tick
                VR.run_hours(y, COMMON2 * 24)
                out['C2'][br][f'{b}|{n}'] = window(y, n0, t0)
                rec = L.life_record(y, life_id=f'{arm}|design|{seed}|rep{rep}|{b}|{n}|{br}', arm=arm, design='social', seed=seed)
                fps.add(rec['fingerprint'])
                if arm in CATALOGUE_ARMS:
                    lives.append(slim(rec))
            if arm == NONE and len(fps) != 1:
                none_identical = False
        reps.append(out)
    return {'seed': seed, 'arm': arm, 'same_growth': same_growth, 'growth_memory': mem, 'reps': reps,
            'none_identical': none_identical if arm == NONE else None, 'lives': lives}


# ---------------------------------------------------------------- catalogue (validate_foresight's, on this agent)
def catalogue_job(args):
    seed, arm = args
    saved = VF.new_pet
    VF.new_pet = new_pet                      # the catalogue functions build their pets through VF.new_pet
    try:
        routes = [VF.route_life(seed, r, arm) for r in v5.ROUTES]
        pair = VF.pair_lives(seed, arm)
        plastic = VF.plastic_lives(seed, arm)
        matched = VF.matched_lives(seed, arm)
    finally:
        VF.new_pet = saved
    P = pair
    gap = [VR.mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'B'])
           - VR.mean([m['spont'] for m in P if m['rep'] == k and m['branch'] == 'A']) for k in range(VR.REPS)]
    common = [m['phases']['common'] for m in routes]
    return {'seed': seed, 'arm': arm, 'lives': [slim(m) for m in routes + pair + plastic + matched],
            'pair_B_minus_A_spont': VR.mean(gap), 'entropy_common': VR.mean([c['entropy'] for c in common]),
            'upkeep_common': VR.mean([c['upkeep'] for c in common]), 'leisure_common': VR.mean([c['leisure'] for c in common]),
            'read_common': VR.mean([c['read'] for c in common])}


def safe_job(args):
    seed, items, arm = args
    s = new_pet(seed, arm)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    s.apply({'kind': 'invite', 'value': None})
    s.phases = [('safe', 0)]
    VR.run_hours(s, 60 * 24)
    return slim(L.life_record(s, life_id=f"{arm}|safe|{seed}|{'+'.join(items)}", arm=arm, design='safe', seed=seed))


def check_job(seed):
    """ref's catalogue must be validate_foresight 'both' exactly (fingerprints)."""
    lives = [VF.route_life(seed, r, 'both') for r in v5.ROUTES] + VF.pair_lives(seed, 'both') + VF.plastic_lives(seed, 'both') \
        + VF.matched_lives(seed, 'both')
    return {'seed': seed, 'fps': sorted(m['fingerprint'] for m in lives)}


# ---------------------------------------------------------------- effects
def cell_mean(job, win, branch, key):
    """Per cell, mean over continuations (None values skipped, counted)."""
    out = {}
    for c in (f'{b}|{n}' for b, n in CELLS):
        xs = [(r[win][c] if win == 'C1' else r[win][branch][c])[key] for r in job['reps']]
        out[c] = VR.mean(xs)
    return out


def effects(m):
    sub = lambda a, b: None if a is None or b is None else a - b
    avg = lambda a, b: None if a is None or b is None else (a + b) / 2
    book = avg(sub(m['clear|warm'], m['hard|warm']), sub(m['clear|cold'], m['hard|cold']))
    nb = avg(sub(m['clear|warm'], m['clear|cold']), sub(m['hard|warm'], m['hard|cold']))
    inter = sub(sub(m['clear|warm'], m['hard|warm']), sub(m['clear|cold'], m['hard|cold']))
    return {'book': book, 'neighbor': nb, 'interaction': inter, 'level': VR.mean(list(m.values()))}


KEYS = ('read', 'spont_per_day', 'invited_per_day', 'explore_in_avail', 'leisure', 'upkeep', 'avail_hours_per_day', 'read_hours',
        'social_results', 'read_gain_mean', 'social_gain_mean') + tuple(f'share_{k}' for k in L.CATEGORIES)


def seed_effects(job):
    out = {}
    for key in KEYS:
        out[f'C1|{key}'] = effects(cell_mean(job, 'C1', None, key))
        for br in BRANCHES:
            out[f'C2|{br}|{key}'] = effects(cell_mean(job, 'C2', br, key))
    out['R1'] = out['C2|read_change|read']['book'] - out['C2|keep|read']['book']
    out['R2'] = out['C2|social_change|spont_per_day']['neighbor'] - out['C2|keep|spont_per_day']['neighbor']
    return out


def summarise(designs, catalogues, safe, seeds):
    S = {}
    for arm in ARMS:
        J = sorted((j for j in designs if j['arm'] == arm), key=lambda j: j['seed'])
        E = {j['seed']: seed_effects(j) for j in J}
        d = {}
        for k in E[seeds[0]]:
            if isinstance(E[seeds[0]][k], dict):
                d[k] = {f: L.describe([E[sd][k][f] for sd in seeds]) for f in ('book', 'neighbor', 'interaction', 'level')}
            else:
                d[k] = L.describe([E[sd][k] for sd in seeds])
        S[arm] = {'effects': d, 'per_seed': E, 'same_growth_all': all(j['same_growth'] for j in J),
                  'none_identical_all': all(j['none_identical'] for j in J) if arm == NONE else None,
                  'growth_memory': {j['seed']: j['growth_memory'] for j in J}}
        if arm in CATALOGUE_ARMS:
            C = sorted((c for c in catalogues if c['arm'] == arm), key=lambda c: c['seed'])
            lives = [m for c in C for m in c['lives']] + [m for m in safe if m['life_id'].startswith(arm + '|')] \
                + [m for j in J for m in j['lives']]
            gaps = [c['pair_B_minus_A_spont'] for c in C]
            S[arm]['catalogue'] = {k: L.describe([c[k] for c in C]) for k in
                                   ('pair_B_minus_A_spont', 'entropy_common', 'upkeep_common', 'leisure_common', 'read_common')}
            S[arm]['catalogue_per_seed'] = {c['seed']: {k: c[k] for k in ('pair_B_minus_A_spont', 'entropy_common', 'upkeep_common',
                                                                         'leisure_common', 'read_common')} for c in C}
            S[arm]['social_seeds_at_1_7'] = sum(g >= 1 / 7 for g in gaps)
            S[arm]['safety'] = {k: v for k, v in RP.safety_union(lives).items() if k != 'checks_lost_by_first_run_dedupe'}
            S[arm]['min_home_any'] = min(m['min_home'] for m in lives)
            S[arm]['catalogue_fps'] = {c['seed']: sorted(m['fingerprint'] for m in c['lives']) for c in C}
    return S


def paired(S, a, b, key, field=None, seeds=DEV_SEEDS):
    g = lambda arm, sd: S[arm]['per_seed'][sd][key] if field is None else S[arm]['per_seed'][sd][key][field]
    return L.describe([g(a, sd) - g(b, sd) for sd in seeds])


def cat_paired(S, a, b, key, seeds=DEV_SEEDS):
    return L.describe([S[a]['catalogue_per_seed'][sd][key] - S[b]['catalogue_per_seed'][sd][key] for sd in seeds])


def evaluate(S, seeds=DEV_SEEDS):
    C, E, R = CRITERIA, S[CANDIDATE]['effects'], S[REF]
    lo, hi = (lambda x: x['ci95'][0]), (lambda x: x['ci95'][1])
    p1, p2 = E['C1|read']['book'], E['C2|keep|read']['book']
    p3, p4 = E['C1|spont_per_day']['neighbor'], E['C2|keep|spont_per_day']['neighbor']
    g, r1, r2 = E['C1|explore_in_avail']['neighbor'], E['R1'], E['R2']
    l1, l2 = paired(S, CANDIDATE, FROZEN, 'R1', seeds=seeds), paired(S, CANDIDATE, FROZEN, 'R2', seeds=seeds)
    m = cat_paired(S, CANDIDATE, REF, 'upkeep_common', seeds)
    cand = S[CANDIDATE]
    v = {'P1_read_persists': p1['mean'] >= C['P1_min'] and lo(p1) > 0 and p1['positive'] >= C['P1_pos'],
         'P2_read_persists_late': p2['mean'] >= C['P2_min'] and lo(p2) > 0,
         'P3_social_persists': p3['mean'] >= C['P3_min'] and lo(p3) > 0 and p3['positive'] >= C['P3_pos'],
         'P4_social_persists_late': p4['mean'] >= C['P4_min'] and lo(p4) > 0,
         'G_interest_moves_out': g['mean'] > 0 and lo(g) > 0,
         'R1_reading_adapts': r1['mean'] <= C['R1_max'] and hi(r1) < 0,
         'R2_social_adapts': r2['mean'] <= C['R2_max'] and hi(r2) < 0,
         'L1_learning_adds_read': l1['mean'] < 0 and hi(l1) < 0,
         'L2_learning_adds_social': l2['mean'] < 0 and hi(l2) < 0,
         'N0_none_identical': S[NONE]['none_identical_all'] is True,
         'N1_growth_identical': all(S[a]['same_growth_all'] for a in ARMS),
         'H1_whole_life': cand['safety']['pass'] == cand['safety']['unique_trajectories'],
         'H2_phase_not_above_ref': cand['safety']['phase_fails'] <= R['safety']['phase_fails'],
         'M_maintenance': m['mean'] >= C['M_mean'] and lo(m) > C['M_ci_lower'],
         'S_social_pair': (cand['social_seeds_at_1_7'] >= R['social_seeds_at_1_7'] - C['S_max_fewer_seeds']
                           and cand['catalogue']['pair_B_minus_A_spont']['mean'] >= R['catalogue']['pair_B_minus_A_spont']['mean'] - C['S_max_mean_drop']),
         'D_diversity': cand['catalogue']['entropy_common']['mean'] >= R['catalogue']['entropy_common']['mean'] - C['D_max_entropy_drop']}
    v['_values'] = {'P1': p1, 'P2': p2, 'P3': p3, 'P4': p4, 'G': g, 'R1': r1, 'R2': r2, 'L1': l1, 'L2': l2, 'M': m}
    return v


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    if which != 'dev':
        raise SystemExit('round 11 has a development mode only')
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_social'
    dst.mkdir(parents=True, exist_ok=True)
    out_file = dst / 'social_dev_result.json'
    if out_file.exists():
        raise SystemExit(f'{out_file} exists: development results are never overwritten')
    seeds = DEV_SEEDS
    with Pool(14) as pool:
        designs = pool.map(design_job, [(sd, a) for a in ARMS for sd in seeds])
        catalogues = pool.map(catalogue_job, [(sd, a) for a in CATALOGUE_ARMS for sd in seeds])
        safe = pool.map(safe_job, [(sd, it, a) for a in CATALOGUE_ARMS for sd in VR.SAFE_SEEDS for it in VR.SAFE_ITEMS])
        checks = pool.map(check_job, seeds)
    S = summarise(designs, catalogues, safe, seeds)
    v = evaluate(S, seeds)
    compat = L.compat_check()
    final = {**{k: x for k, x in v.items() if not k.startswith('_')}, 'compat_v1_v6': compat['pass']}
    final['pass'] = all(x is True for x in final.values())
    chk = {'ref_catalogue_is_validated_candidate': all(S[REF]['catalogue_fps'][c['seed']] == c['fps'] for c in checks)}
    report = {'sample': which, 'seeds': seeds, 'config_id': CONFIG_ID, 'arms': ARMS, 'params': PARAMS, 'criteria': CRITERIA,
              'final': final, 'values': v['_values'], 'checks': chk, 'compat': compat,
              'summary': {a: {k: x for k, x in o.items() if k not in ('per_seed', 'catalogue_fps')} for a, o in S.items()},
              'per_seed': {a: o['per_seed'] for a, o in S.items()},
              'contrasts': {f'{a} - ref': {k: {f: paired(S, a, REF, k, f) for f in ('book', 'neighbor', 'interaction', 'level')}
                                           for k in ('C1|read', 'C1|spont_per_day', 'C1|explore_in_avail', 'C1|leisure',
                                                     'C2|keep|read', 'C2|keep|spont_per_day')}
                            for a in ARMS if a != REF}}
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'final': final, 'checks': chk,
                                'safety': {a: {k: S[a]['safety'][k] for k in ('unique_trajectories', 'pass', 'phase_fails')}
                                           | {'min_home': S[a]['min_home_any']} for a in CATALOGUE_ARMS},
                                'values': {k: {x: y.get(x) for x in ('mean', 'ci95', 'positive', 'negative')}
                                           for k, y in v['_values'].items()}}), ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
