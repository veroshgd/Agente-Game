"""Round 5 of 2026-10-25: why the reading memory still favours reading while behaviour reverses.
Diagnostics only (NOT a rule version, no new mechanism; default stays v5). Development seeds of
pet/validate_interest.py (3001-3010, 6001-6010), which were already looked at: nothing here is a
validation. The frozen round-4 result (docs/pet_interest_validation/) is kept as it is; corrections
are written to docs/pet_goal_interest/.

    python -m pet.diag_interest [out_dir]            # default docs/pet_goal_interest

The lives are those of validate_interest.matched (same calls, same order) with PetAgent.read_audit on:
the fingerprint of every life and the end state of its generator are checked against the round-4
run (audit off).
  1. Full counterfactual (correction of explain_read_value): every common hour, the whole choice
     with and without the reading term; promote = reads only because of it, suppress = does not
     read only because of it. Per pet, of all hours and of hours where reading is legal.
  2. Strength on every legal candidate: read's rank, its gap to the chosen action, its parts
     S (short-term evaluation), I (long-term interest), prefs (v5 liking), plan (goal bonus), and
     the choice re-made without each of them. The old metric (|term| of the CHOSEN action) is
     reported beside it.
  3. The late reversal (candidate 'interest', keep, days 30-60):
     a. first divergent hour of each pair and what tipped it; daily goals, learn satiation, body,
        prefs, memory after it;
     b. exact decomposition along the real lives: read share = share the pet would read with the
        term removed at that hour (state / trajectory part) + (promote - suppress) (instant part);
     c. continuations from the real day-30 state, the actual one plus REPS reseeded ones (the same
        reseed for both pets of a pair), with in both pets: all on / term off / prefs out of scores /
        prefs out of goals / plan off for reading; and the same from common day 0.
  4. Forgetting vs reverse learning, ISOLATED memory replays from each pet's real day-0 reading
     memory (artificial inputs, labelled): no new reading (forgetting only), neutral results at the
     pet's real reading hours, the real results (must reproduce the real memory exactly), the
     contrary book at the real hours. Plus the real I change split into consolidation and fading.

DECISION RULE, FIXED 2026-10-25 BEFORE ANY RUN OF THIS MODULE (sha256 in docs/pet_goal_interest/).
Goal entry ('learn' goal formation) is tried only if ALL hold, on the 20 dev seeds, candidate
'interest', keep branch, days 30-60, unit = birth seed, CI = bootstrap 95 %:
  G1 systematic: the late gap averaged over the day-30 continuations (actual + reseeded) < 0 with
     CI upper < 0 (the reversal is reproducible, not one draw);
  G2 not the term itself: in those continuations the instant part (clear - hard of promote -
     suppress, pp of hours) has mean >= 0, and the state part has mean < 0 (the reversal is carried
     by the state the pets are in, not by the term pushing the clear pet away from reading);
  G3 through plans: with the plan's effect on reading off in both pets ('goal' continuations) the
     mean late gap is at least 50 % closer to 0 than with all on, AND closer to 0 than with prefs out
     of scores ('pref_score').
Otherwise the diagnosis is reported and the round stops without a new mechanism.
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
from . import validate_interest as VI
from . import validate_read as VR

DEV_SEEDS = VI.DEV_SEEDS
ARMS = ('read_value', 'interest', 'read_lowrate', 'interest_flat')
FACTORS = ('term', 'S', 'I', 'pref', 'goal')
REPS = 5
CONDITIONS = {'all': {}, 'term': {'read_value_in_decision': False}, 'pref_score': {'pref_score_off': True},
              'pref_goal': {'pref_goal_off': True}, 'goal': {'goal_read_bonus_off': True}}
RULE = {'G1': 'late gap over day-30 continuations < 0, CI upper < 0',
        'G2': 'instant part mean >= 0 and state part mean < 0 (same continuations)',
        'G3': "|gap| with plan off for reading <= 0.5 |gap all on| and < |gap| with prefs out of scores"}
BOUND = engine.READ_VALUE_WEIGHT * 0.5


def rng_digest(s):
    return hashlib.sha256(repr(s.agent.rng.getstate()).encode()).hexdigest()[:16]


def hour_rows(s, i0):
    """Compact audit rows of the action events from event index i0."""
    out = []
    for e in s.events[i0:]:
        if e['kind'] != 'action':
            continue
        d = e['decision']
        a = d.get('audit') or {}
        out.append({'tick': e['tick'], 'chosen': e['core_action'], 'logged': d.get('read_value_decisive', False),
                    'chosen_term': d.get('read_value', 0.0), **{k: a.get(k) for k in (
                        'read_rank', 'read_gap', 'S', 'I', 'pref', 'goal', 'goal_type', 'boredom', 'gate', 'body')},
                    'effect': a.get('effect', {}), 'without': a.get('without', {}), 'legal': 'read' in a.get('scores', {})})
    return out


def day_state(a):
    g = a.goal
    return {'goal': g['type'] if g else None, 'learn_sat': a._satiation('learn', a.now // 24),
            'learn_done': sum(1 for h in a.goal_history if h['type'] == 'learn' and h.get('outcome') == 'done'),
            'pref_read': a.prefs['read'], 'pref_garden': a.prefs['garden'], 'pref_social': a.prefs['social'],
            'V': a.read_V, 'n': a.read_n, 'I': a.read_I, 'term': a.read_value_term(),
            'hunger': a.hunger, 'energy': a.energy, 'shelter': a.shelter, 'traits': dict(a.traits),
            'know_books': a.know('books'), 'reads': a.read_evidence['count']}


def live(s, days, rows, days_out):
    for _ in range(days):
        n0 = len(s.events)
        VR.run_hours(s, 24)
        rows.extend(hour_rows(s, n0))
        days_out.append(day_state(s.agent))


# ---------------------------------------------------------------- 1-3a, 3b: the real lives
def real_lives(seed, arm, audit=True):
    """validate_interest.matched, same calls and order, with the audit; returns the rows."""
    pets = {n: VI.book_pet(seed, arm, cl) for n, cl in (('clear', VI.CLEAR), ('hard', VI.HARD))}
    for p in pets.values():
        p.agent.read_audit = audit
        p.phase('common')
    rows = {n: [] for n in pets}
    days = {n: [day_state(p.agent)] for n, p in pets.items()}
    for n, p in pets.items():
        live(p, VI.SPLIT, rows[n], days[n])
    split = {n: copy.deepcopy(p) for n, p in pets.items()}
    out = {'day0_memory': None, 'split': split}
    for branch in ('keep', 'swap'):
        for n, p in pets.items():
            c = copy.deepcopy(p)
            if branch == 'swap':
                c.world.p['book_clarity'] = VI.HARD if n == 'clear' else VI.CLEAR
                c.phase('swap')
            r, dd = list(rows[n]), list(days[n])
            live(c, VI.COMMON - VI.SPLIT, r, dd)
            out[(branch, n)] = {'rows': r, 'days': dd, 'fingerprint': L.fingerprint(c.trace), 'rng': rng_digest(c),
                                'reads': c.agent.read_evidence['count']}
    return out


def count_effects(rows, key='term'):
    c = Counter(r['effect'].get(key) for r in rows)
    return c['promote'], c['suppress'], c['other']


def share(n, d):
    return n / d if d else None


def strength(rows):
    """Per pet: strength of each part on the READ candidate, and how often it decides."""
    R = [r for r in rows if r['legal']]
    nr = [r for r in R if r['chosen'] != 'read']
    gaps = sorted(r['read_gap'] for r in nr)
    out = {'hours': len(rows), 'legal_hours': len(R), 'read_hours': len(R) - len(nr),
           'gate_on_hours': sum(1 for r in R if r['gate'] > 0),
           'old_mean_abs_chosen_term': VR.mean([abs(r['chosen_term']) for r in rows]),
           'logged_decisive': sum(1 for r in rows if r['logged']),
           'rank': dict(Counter(r['read_rank'] for r in R)),
           'gap_not_chosen_median': gaps[len(gaps) // 2] if gaps else None,
           'not_chosen_within_bound': share(sum(1 for g in gaps if g > -BOUND), len(gaps)),
           'not_chosen_within_10': share(sum(1 for g in gaps if g > -10), len(gaps))}
    for k in ('S', 'I', 'pref', 'goal'):
        out[f'mean_abs_{k}'] = VR.mean([abs(r[k]) for r in R])
        out[f'mean_{k}'] = VR.mean([r[k] for r in R])
    out['mean_abs_term'] = VR.mean([abs(r['S'] + r['I']) for r in R])
    out['mean_term'] = VR.mean([r['S'] + r['I'] for r in R])
    for k in FACTORS:
        p, s_, o = count_effects(rows, k)
        out[f'{k}_promote'], out[f'{k}_suppress'], out[f'{k}_other'] = p, s_, o
        out[f'{k}_pivotal_share_all'] = share(p + s_ + o, len(rows))
        out[f'{k}_pivotal_share_legal'] = share(p + s_ + o, len(R))
    out['read_under_learn'] = sum(1 for r in R if r['chosen'] == 'read' and r['goal_type'] == 'learn')
    out['hours_learn_plan'] = sum(1 for r in R if r['goal_type'] == 'learn')
    return out


def decompose(rows):
    """read share = (share read with the term removed at that hour) + (promote - suppress) / hours."""
    n = len(rows)
    real = sum(r['chosen'] == 'read' for r in rows) / n
    state = sum(r['without']['term'] == 'read' for r in rows) / n
    p, s_, _ = count_effects(rows)
    assert abs(real - (state + (p - s_) / n)) < 1e-12
    return {'real': real, 'state': state, 'instant': (p - s_) / n}


def first_divergence(rc, rh):
    for x, y in zip(rc, rh):
        if x['chosen'] != y['chosen']:
            pick = lambda r: {k: r[k] for k in ('tick', 'chosen', 'read_rank', 'read_gap', 'S', 'I', 'pref', 'goal',
                                                 'goal_type', 'body')} | {'effect': r['effect'], 'without': r['without']}
            return {'clear': pick(x), 'hard': pick(y), 'day': x['tick'] // 24 - VI.GROW,
                    'tipped_by_term': x['without']['term'] == y['without']['term']}
    return None


def plan_stats(days, d0, d1):
    D = days[d0:d1]
    return {'learn_days': sum(d['goal'] == 'learn' for d in D), 'see_days': sum(d['goal'] == 'see_the_world' for d in D),
            'home_days': sum(d['goal'] == 'improve_home' for d in D),
            'learn_done': days[d1 - 1]['learn_done'] - days[d0]['learn_done'],
            'learn_sat_days': sum(d['learn_sat'] > 0 for d in D)}


# ---------------------------------------------------------------- 3c: continuations
def continue_pair(pets, days, cond, rep, seed):
    out = {}
    for n, p in pets.items():
        c = copy.deepcopy(p)
        for k, v in CONDITIONS[cond].items():
            setattr(c.agent, k, v)
        c.agent.read_audit = True
        if rep:
            c.agent.rng.seed(seed * 1000 + rep)
        rows = []
        live(c, days, rows, [])
        last = rows[-(VI.COMMON - VI.SPLIT) * 24:]
        out[n] = {'late': decompose(last), 'all_days': VR.read_share([(0, r['chosen']) for r in rows])}
    return {'gap': out['clear']['late']['real'] - out['hard']['late']['real'],
            'state': out['clear']['late']['state'] - out['hard']['late']['state'],
            'instant': out['clear']['late']['instant'] - out['hard']['late']['instant'],
            'gap_all_days': out['clear']['all_days'] - out['hard']['all_days']}


# ---------------------------------------------------------------- 4: isolated memory replays
def replay(agent, schedule, gain_of, days):
    """Reading memory only (read_experience / consolidation / n decay, in the engine's order).
    schedule[d] = list of (focus, real gain) of the pet's real reading hours that day."""
    a = copy.deepcopy(agent)
    traj = [(a.read_V, a.read_n, a.read_I, a.read_value_term())]
    for d in range(days):
        for focus, g in schedule[d] if gain_of else []:
            a.read_experience('read', 0, {'gain': gain_of(focus, g)})
        if a.read_interest:
            a.consolidate_interest()
        a.read_n *= engine.EVAL_KEEP
        traj.append((a.read_V, a.read_n, a.read_I, a.read_value_term()))
    return traj


def interest_split(days):
    """Real I change split into consolidation (reading days) and fading (days without reading)."""
    learn = fade = 0.0
    for d0, d1 in zip(days, days[1:]):
        dI = d1['I'] - d0['I']
        if d1['reads'] > d0['reads']:
            learn += dI
        else:
            fade += dI
    return {'consolidation': learn, 'fading': fade, 'I_start': days[0]['I'], 'I_end': days[-1]['I']}


def memory_job(seed, pets0, real):
    out = {}
    for n, p in pets0.items():
        rows = real[('keep', n)]['rows']
        sched = [[] for _ in range(VI.COMMON)]
        for r in rows:
            if r['chosen'] == 'read':
                sched[r['tick'] // 24 - VI.GROW].append((r['gate'], VI.STANDARD * r['gate']))
        contrary = VI.HARD if n == 'clear' else VI.CLEAR
        sc = {'none (artificial)': None,
              'neutral (artificial)': lambda f, g: engine.READ_VALUE_REF,
              'real': lambda f, g: g,
              'contrary book (artificial)': lambda f, g: contrary * f}
        tr = {k: replay(p.agent, sched, fn, VI.COMMON) for k, fn in sc.items()}
        rd = real[('keep', n)]['days']
        ok = all(abs(tr['real'][d][2] - rd[d]['I']) < 1e-9 and abs(tr['real'][d][0] - rd[d]['V']) < 1e-9 for d in range(len(rd)))
        out[n] = {'traj': {k: v[::10] for k, v in tr.items()}, 'real_replay_exact': ok,
                  'mean_gain_real': VR.mean([g for d in sched for _, g in d]), 'reading_days': sum(1 for d in sched if d),
                  'reads': sum(len(d) for d in sched), 'I_split': interest_split(rd)}
    return out


# ---------------------------------------------------------------- per seed
def seed_job(args):
    seed, arm = args
    real = real_lives(seed, arm)
    frozen, flives = VI.matched(seed, arm)
    fps = {(m['branch'], m['book']): m['fingerprint'] for m in flives}
    plain = real_lives(seed, arm, audit=False)
    same = all(real[k]['fingerprint'] == fps[k] == plain[k]['fingerprint'] and real[k]['rng'] == plain[k]['rng']
               for k in fps)
    res = {'seed': seed, 'arm': arm, 'audit_changes_nothing': same, 'frozen_gap_late': frozen['keep']['clear']['late'] - frozen['keep']['hard']['late']}
    for b in ('keep', 'swap'):
        for n in ('clear', 'hard'):
            R = real[(b, n)]['rows']
            res[f'{b}_{n}'] = {'common': strength(R), 'late': strength(R[VI.SPLIT * 24:]),
                               'late_decomp': decompose(R[VI.SPLIT * 24:]), 'all_decomp': decompose(R)}
    if arm != 'interest':
        return res
    kc, kh = real[('keep', 'clear')], real[('keep', 'hard')]
    res['first_divergence'] = first_divergence(kc['rows'], kh['rows'])
    res['first_goal_divergence'] = next(({'day': d, 'clear': x['goal'], 'hard': y['goal']}
                                         for d, (x, y) in enumerate(zip(kc['days'], kh['days'])) if x['goal'] != y['goal']), None)
    res['plans_late'] = {n: plan_stats(real[('keep', n)]['days'], VI.SPLIT, VI.COMMON + 1) for n in ('clear', 'hard')}
    res['plans_early'] = {n: plan_stats(real[('keep', n)]['days'], 0, VI.SPLIT + 1) for n in ('clear', 'hard')}
    res['daily'] = {n: [{k: v for k, v in d.items() if k != 'traits'} | {'curiosity': d['traits']['curiosity']}
                        for d in real[('keep', n)]['days']] for n in ('clear', 'hard')}
    split = real['split']
    res['from30'] = {c: [continue_pair(split, VI.COMMON - VI.SPLIT, c, rep, seed) for rep in range(REPS + 1)] for c in CONDITIONS}
    pets0 = {n: VI.book_pet(seed, arm, cl) for n, cl in (('clear', VI.CLEAR), ('hard', VI.HARD))}
    for p in pets0.values():
        p.phase('common')
    res['from0'] = {c: [continue_pair(pets0, VI.COMMON, c, rep, seed) for rep in range(REPS + 1)] for c in CONDITIONS}
    assert abs(res['from0']['all'][0]['gap'] - res['frozen_gap_late']) < 1e-12      # rep 0 = the real lives
    res['memory'] = memory_job(seed, pets0, real)
    return res


# ---------------------------------------------------------------- summary
D = L.describe


def summarise(jobs):
    S = {}
    for arm in ARMS:
        J = sorted((j for j in jobs if j['arm'] == arm), key=lambda j: j['seed'])
        a = {'audit_changes_nothing_all': all(j['audit_changes_nothing'] for j in J)}
        for b in ('keep', 'swap'):
            for n in ('clear', 'hard'):
                for per in ('common', 'late'):
                    rows = [j[f'{b}_{n}'][per] for j in J]
                    a[f'{b}_{n}_{per}'] = {k: D([r[k] for r in rows]) for k in rows[0] if k != 'rank'}
                    a[f'{b}_{n}_{per}']['rank_total'] = dict(sum((Counter(r['rank']) for r in rows), Counter()))
            for per in ('late_decomp', 'all_decomp'):
                a[f'{b}_{per}_gap'] = {k: D([j[f'{b}_clear'][per][k] - j[f'{b}_hard'][per][k] for j in J])
                                       for k in ('real', 'state', 'instant')}
        S[arm] = a
    J = sorted((j for j in jobs if j['arm'] == 'interest'), key=lambda j: j['seed'])
    I = S['interest']
    I['first_divergence'] = {j['seed']: j['first_divergence'] for j in J}
    I['first_goal_divergence'] = {j['seed']: j['first_goal_divergence'] for j in J}
    I['plans'] = {f'{per}_{k}': D([j[f'plans_{per}']['clear'][k] - j[f'plans_{per}']['hard'][k] for j in J])
                  for per in ('early', 'late') for k in J[0]['plans_late']['clear']}
    for w in ('from30', 'from0'):
        I[w] = {c: {k: D([sum(r[k] for r in j[w][c]) / len(j[w][c]) for j in J]) for k in ('gap', 'state', 'instant', 'gap_all_days')}
                for c in CONDITIONS}
        I[w + '_rep0'] = {c: {k: D([j[w][c][0][k] for j in J]) for k in ('gap', 'state', 'instant')} for c in CONDITIONS}
    days = range(VI.COMMON + 1)
    keys = [k for k in J[0]['daily']['clear'][0] if k != 'goal']
    I['daily_gap'] = {k: [VR.mean([j['daily']['clear'][d][k] - j['daily']['hard'][d][k] for j in J]) for d in days] for k in keys}
    I['daily_learn_goal'] = {n: [sum(j['daily'][n][d]['goal'] == 'learn' for j in J) for d in days] for n in ('clear', 'hard')}
    I['memory'] = {}
    for n in ('clear', 'hard'):
        sc = J[0]['memory'][n]['traj']
        I['memory'][n] = {k: [[VR.mean([j['memory'][n]['traj'][k][t][x] for j in J]) for x in range(4)]
                              for t in range(len(sc[k]))] for k in sc}
        I['memory'][n + '_exact'] = all(j['memory'][n]['real_replay_exact'] for j in J)
        I['memory'][n + '_mean_gain'] = D([j['memory'][n]['mean_gain_real'] for j in J])
        I['memory'][n + '_I_split'] = {k: D([j['memory'][n]['I_split'][k] for j in J]) for k in J[0]['memory'][n]['I_split']}
    I['memory']['term_gap'] = {k: [VR.mean([j['memory']['clear']['traj'][k][t][3] - j['memory']['hard']['traj'][k][t][3] for j in J])
                                   for t in range(len(J[0]['memory']['clear']['traj'][k]))] for k in J[0]['memory']['clear']['traj']}
    return S


def verdict(S):
    I = S['interest']
    f30 = I['from30']
    g = lambda c: f30[c]['gap']['mean']
    v = {'G1_systematic': f30['all']['gap']['mean'] < 0 and f30['all']['gap']['ci95'][1] < 0,
         'G2_not_the_term': f30['all']['instant']['mean'] >= 0 and f30['all']['state']['mean'] < 0,
         'G3_through_plans': abs(g('goal')) <= 0.5 * abs(g('all')) and abs(g('goal')) < abs(g('pref_score'))}
    v['goal_entry_supported'] = all(v.values())
    return v


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_goal_interest'
    dst.mkdir(parents=True, exist_ok=True)
    with Pool(14) as pool:
        jobs = pool.map(seed_job, [(sd, arm) for arm in ARMS for sd in DEV_SEEDS])
    S = summarise(jobs)
    v = verdict(S)
    per_seed = {f"{j['arm']}|{j['seed']}": {k: x for k, x in j.items() if k not in ('daily',)} for j in jobs}
    (dst / 'diag_interest_result.json').write_text(json.dumps({'rule': RULE, 'verdict': v, 'summary': S, 'per_seed': per_seed},
                                                              ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'verdict': v}), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
