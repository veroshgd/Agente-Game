"""Round 12 of 2026-10-25: the scope-corrected social entry 'B2' against round 11's 'B' and the reference,
plus a diagnosis of reading adaptation. Development seeds only; no validation mode.

    python -m pet.validate_social_b2 [out_dir]      # default docs/pet_social_b2

Round 11's protocol (pet/validate_social.py, sha256 24e168c0...) is REUSED, not edited: this module only
swaps in, at run time and in every worker, its pet factory (pet/social_interest_b2.SocialSessionB2, a subclass
of round 11's agent that also knows 'B2'), its arm table and the candidate's name. Design, windows, metrics
and CRITERIA are round 11's objects themselves (validate_social.CRITERIA, unchanged, R1 included).
Arms: ref, none, B (round 11's, re-run: must reproduce round 11's saved effects exactly), B2 (CANDIDATE),
B2_frozen (B2 with both experimental memories frozen at common day 0). Catalogue (safety): ref, B, B2.

FIXED 2026-10-25 BEFORE ANY RUN OF THIS MODULE (sha256 in docs/pet_social_b2/):
  formula   explore score += max(g, s + t) - max(g, s) when she can meet now (social_interest_b2 docstring)
  verdict   B2 must pass every criterion of validate_social.CRITERIA, evaluated exactly as round 11
            (validate_social.evaluate with B2 / B2_frozen in place of B / B_frozen) + compat
  checks    ref, none and B per-seed effects identical to round 11's saved result; growth identical
Reading-adaptation diagnosis (descriptive, no verdict; arms B and B2; branches keep and read_change; every
continuation, cell and day 30-60): reading hours and days, results, S, I, n, confidence, the term, the daily
I change (consolidation vs fading), and per hour the memory (S + I) and plan contributions to the read score,
the v5 liking part, read's gap to the chosen action, and the hours the term decides (promote / suppress).
Instrumented lives must equal uninstrumented ones (fingerprint and generator state; checked per life).
"""
import copy
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

from . import engine
from . import lifestats as L
from . import validate_read as VR
from . import validate_social as VS
from .social_interest_b2 import SocialSessionB2

ROUND11 = Path(__file__).resolve().parents[1] / 'docs' / 'pet_social' / 'social_dev_result.json'
ARMS = {'ref': {}, 'none': {'no_read_term': True}, 'B': {'entry': 'B'}, 'B2': {'entry': 'B2'},
        'B2_frozen': {'entry': 'B2', 'freeze': True}}
CATALOGUE_ARMS = ('ref', 'B', 'B2')
CANDIDATE, FROZEN = 'B2', 'B2_frozen'
DIAG_ARMS = ('B', 'B2')
CONFIG_ID = hashlib.sha256(json.dumps({'arms': ARMS, 'criteria': VS.CRITERIA, 'round11': VS.CONFIG_ID,
                                       'formula': 'max(g, s + t) - max(g, s)'}, sort_keys=True).encode()).hexdigest()[:12]


def new_pet(seed, arm):
    return VS.configure(SocialSessionB2(seed, 5), arm)


def patch():
    """Point round 11's protocol at this round's pets and arms (module globals only; no file edited)."""
    VS.new_pet, VS.ARMS, VS.CATALOGUE_ARMS = new_pet, ARMS, CATALOGUE_ARMS
    VS.CANDIDATE, VS.FROZEN = CANDIDATE, FROZEN


# ---------------------------------------------------------------- reading-adaptation diagnosis
def day_rows(s, d0_events):
    rows = [e for e in s.events[d0_events:] if e['kind'] == 'action']
    out = {'reads': 0, 'gain_sum': 0.0, 'mem': [], 'plan': [], 'pref': [], 'gap': [], 'promote': 0, 'suppress': 0,
           'learn_hours': 0}
    for e in rows:
        a = e['decision'].get('audit', {})
        if e['core_action'] == 'read':
            out['reads'] += 1
            out['gain_sum'] += e['read_outcome']['gain']
        if 'S' in a:
            out['mem'].append(a['S'] + a['I'])
            out['plan'].append(a['goal'])
            out['pref'].append(a['pref'])
            out['gap'].append(a['read_gap'])
            out['learn_hours'] += a['goal_type'] == 'learn'
            eff = a['effect'].get('term')
            out['promote'] += eff == 'promote'
            out['suppress'] += eff == 'suppress'
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return {'reads': out['reads'], 'gain_mean': out['gain_sum'] / out['reads'] if out['reads'] else None,
            'mem': mean(out['mem']), 'plan': mean(out['plan']), 'pref': mean(out['pref']), 'gap': mean(out['gap']),
            'promote': out['promote'], 'suppress': out['suppress'], 'learn_hours': out['learn_hours']}


def instrumented_branch(x, days):
    a = x.agent
    a.read_audit = True
    out = []
    for _ in range(days):
        I0, n0 = a.read_I, len(x.events)
        VR.run_hours(x, 24)
        r = day_rows(x, n0)
        r.update(S=a.read_V, I=a.read_I, n=a.read_n, conf=a.read_n / (a.read_n + engine.EVAL_N0) if a.read_n > 0 else 0.0,
                 term=a.read_value_term(), dI=a.read_I - I0, dI_kind='consolidation' if r['reads'] else 'fading')
        out.append(r)
    return out


def diag_job(args):
    seed, arm = args
    pets, same, _ = VS.grow(seed, arm)
    res = {'seed': seed, 'arm': arm, 'same_growth': same, 'reps': [], 'instrument_changes_nothing': True}
    for rep in range(VS.REPS + 1):
        cur = {}
        for c, p in pets.items():
            x = copy.deepcopy(p)
            if rep:
                x.agent.rng.seed(seed * 1000 + rep)
            VR.run_hours(x, VS.COMMON1 * 24)
            cur[c] = x
        rr = {}
        for br in ('keep', 'read_change'):
            rr[br] = {}
            for (b, n), x in cur.items():
                ys = []
                for instr in (True, False):
                    y = copy.deepcopy(x)
                    if br == 'read_change':
                        y.world.p['book_clarity'] = VS.HARD if b == 'clear' else VS.CLEAR
                    y.phase(br)
                    if instr:
                        days = instrumented_branch(y, VS.COMMON2)
                    else:
                        VR.run_hours(y, VS.COMMON2 * 24)
                    ys.append(y)
                same_life = (L.fingerprint(ys[0].trace) == L.fingerprint(ys[1].trace)
                             and ys[0].agent.rng.getstate() == ys[1].agent.rng.getstate())
                res['instrument_changes_nothing'] &= same_life
                rr[br][f'{b}|{n}'] = days
        res['reps'].append(rr)
    return res


def summarise_diag(jobs):
    """Per seed: clear-grown minus hard-grown (mean over neighbor levels and continuations), per day."""
    out = {}
    for arm in DIAG_ARMS:
        J = sorted((j for j in jobs if j['arm'] == arm), key=lambda j: j['seed'])
        A = {'instrument_changes_nothing_all': all(j['instrument_changes_nothing'] for j in J),
             'same_growth_all': all(j['same_growth'] for j in J)}
        keys = ('reads', 'S', 'I', 'conf', 'term', 'mem', 'plan', 'pref', 'gap', 'promote', 'suppress', 'learn_hours', 'gain_mean', 'dI')

        def grp(j, br, d, k, group):
            vals = [r[br][c][d][k] for r in j['reps'] for c in r[br] if c.startswith(group + '|')]
            vals = [v for v in vals if v is not None]
            return sum(vals) / len(vals) if vals else None
        for br in ('keep', 'read_change'):
            for k in keys:
                per_day = []
                for d in range(VS.COMMON2):
                    xs = []
                    for j in J:
                        c, h = grp(j, br, d, k, 'clear'), grp(j, br, d, k, 'hard')
                        xs.append(None if c is None or h is None else c - h)
                    per_day.append(L.describe(xs))
                A[f'{br}|{k}|gap_by_day'] = [{x: v.get(x) for x in ('mean', 'ci95', 'positive', 'negative')} for v in per_day]
                A[f'{br}|{k}|level_clear_by_day'] = [VR.mean([grp(j, br, d, k, 'clear') for j in J]) for d in range(VS.COMMON2)]
                A[f'{br}|{k}|level_hard_by_day'] = [VR.mean([grp(j, br, d, k, 'hard') for j in J]) for d in range(VS.COMMON2)]
            # exposure distribution per pet-continuation (nothing dropped)
            pets = [r[br][c] for j in J for r in j['reps'] for c in r[br]]
            reads = sorted(sum(d['reads'] for d in p) for p in pets)
            first10 = sorted(sum(d['reads'] for d in p[:10]) for p in pets)
            rdays = sorted(sum(1 for d in p if d['reads']) for p in pets)
            q = lambda xs: [xs[0], xs[len(xs) // 4], xs[len(xs) // 2], xs[3 * len(xs) // 4], xs[-1]]
            A[f'{br}|exposure'] = {'pets': len(pets), 'reads_30d_quantiles': q(reads), 'reads_first10d_quantiles': q(first10),
                                   'reading_days_quantiles': q(rdays), 'zero_reads_first10d': sum(x == 0 for x in first10),
                                   'zero_reads_30d': sum(x == 0 for x in reads)}
            dI = [d for p in pets for d in p]
            A[f'{br}|dI'] = {'consolidation_days': sum(d['dI_kind'] == 'consolidation' for d in dI),
                             'fading_days': sum(d['dI_kind'] == 'fading' for d in dI)}
        out[arm] = A
    return out


def same_as_round11(S):
    r11 = json.loads(ROUND11.read_text(encoding='utf-8'))['per_seed']
    out = {}
    for arm in ('ref', 'none', 'B'):
        a, b = S[arm]['per_seed'], r11[arm]
        out[arm] = all(json.dumps(a[sd], sort_keys=True, default=str) == json.dumps(b[str(sd)], sort_keys=True, default=str)
                       for sd in VS.DEV_SEEDS)
    return out


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_social_b2'
    dst.mkdir(parents=True, exist_ok=True)
    out_file = dst / 'social_b2_dev_result.json'
    if out_file.exists():
        raise SystemExit(f'{out_file} exists: results are never overwritten')
    patch()
    seeds = VS.DEV_SEEDS
    with Pool(14, initializer=patch) as pool:
        designs = pool.map(VS.design_job, [(sd, a) for a in ARMS for sd in seeds])
        catalogues = pool.map(VS.catalogue_job, [(sd, a) for a in CATALOGUE_ARMS for sd in seeds])
        safe = pool.map(VS.safe_job, [(sd, it, a) for a in CATALOGUE_ARMS for sd in VR.SAFE_SEEDS for it in VR.SAFE_ITEMS])
        diags = pool.map(diag_job, [(sd, a) for a in DIAG_ARMS for sd in seeds])
    S = VS.summarise(designs, catalogues, safe, seeds)
    v = VS.evaluate(S, seeds)
    compat = L.compat_check()
    final = {**{k: x for k, x in v.items() if not k.startswith('_')}, 'compat_v1_v6': compat['pass']}
    final['pass'] = all(x is True for x in final.values())
    chk = {'same_as_round11': same_as_round11(S)}
    D = summarise_diag(diags)
    pk = lambda a, b, k, f: VS.paired(S, a, b, k, f, seeds)
    comparison = {f'{a} - {b}': {k: {f: pk(a, b, k, f) for f in ('book', 'neighbor', 'interaction', 'level')}
                                 for k in ('C1|read', 'C1|spont_per_day', 'C1|explore_in_avail', 'C1|leisure', 'C1|share_garden',
                                           'C2|keep|read', 'C2|keep|spont_per_day')}
                  for a, b in (('B2', 'ref'), ('B2', 'B'), ('B', 'ref'))}
    comparison['R1'] = {f'{a} - {b}': VS.paired(S, a, b, 'R1', None, seeds) for a, b in (('B2', 'B'), ('B2', 'ref'))}
    comparison['R2'] = {f'{a} - {b}': VS.paired(S, a, b, 'R2', None, seeds) for a, b in (('B2', 'B'), ('B2', 'ref'))}
    report = {'seeds': seeds, 'config_id': CONFIG_ID, 'arms': ARMS, 'criteria': VS.CRITERIA, 'final': final, 'values': v['_values'],
              'checks': chk, 'compat': compat, 'comparison': comparison, 'diagnosis': D,
              'summary': {a: {k: x for k, x in o.items() if k not in ('per_seed', 'catalogue_fps')} for a, o in S.items()},
              'per_seed': {a: o['per_seed'] for a, o in S.items()}}
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'final': final, 'checks': chk,
                                'instrument': {a: D[a]['instrument_changes_nothing_all'] for a in D},
                                'values': {k: {x: y.get(x) for x in ('mean', 'ci95')} for k, y in v['_values'].items()}}),
                     ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
