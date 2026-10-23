"""Whole-life records for product experiments (2026-10-23).

Why (review of pet/validate_v6.py, 2026-10-21 round):
  * '82 lives' counted the social design's full lives AND the v5 design's lives, which are the
    same trajectories (same seed, route, rules, objects and invitations). Duplicates are no
    extra evidence: every life now carries an id, a trajectory fingerprint, and the unique
    trajectories are counted apart from the runs.
  * merge() kept the observation phase's upkeep / leisure / read / entropy / last week. Here
    every metric is computed from raw counts and hours over the whole life, then per phase.
  * Lives inside the social design (growth, invitations, washout, withdrawal, replicates)
    were never safety-checked. A TracedSession records every hour from birth; copies carry
    that history, so each branch is checked as the whole life it really had.
  * Verdicts use unrounded numbers; rounding is for display only.
The unit of statistical analysis is the birth seed (paired across versions); hours and
continuation replicates of one birth are never treated as independent samples.
"""
import hashlib
import math
import random
from collections import Counter

from . import engine
from .engine import Session

LEISURE = ('garden', 'visit', 'explore', 'read')     # outcome actions, as in validate_v6.life_check
UPKEEP = ('gather_material', 'build')
CATEGORIES = ('eat', 'sleep', 'read', 'garden', 'visit', 'explore', 'gather_material', 'build', 'gather_food')
PHASE_MIN_DAYS = 10            # share criteria are also applied to every phase at least this long

# The v4 safe-home standard (unchanged since 2026-10-17), applied to the whole life.
H = {'min_home': 3.0, 'max_below20_share': 0.08, 'max_upkeep_share': 0.15,
     'min_leisure_share': 0.30, 'min_condition': 99.0, 'min_kinds_last_week': 3}


class TracedSession(Session):
    """A Session that keeps one row per lived hour. Behavior is the parent's: step() runs
    first and nothing it records is read by the pet."""

    def __init__(self, seed=42, rules=engine.RULES):
        super().__init__(seed, rules)
        self.trace = []                    # (tick, action, core_action, home, condition)
        self.phases = [('growth', 0)]      # (name, index into trace)

    def step(self):
        super().step()
        e = self.events[-1]
        self.trace.append((e['tick'], e['action'], e['core_action'], self.agent.shelter, self.agent.condition))

    def phase(self, name):
        self.phases.append((name, len(self.trace)))


def fingerprint(trace):
    h = hashlib.sha256()
    for row in trace:
        h.update(repr(row).encode())
    return h.hexdigest()[:16]


def metrics(rows):
    """Raw counts and hours first; shares and entropy are computed from them."""
    n = len(rows)
    acts = Counter(r[1] for r in rows)
    homes = [r[3] for r in rows]
    last_week = {r[1] for r in rows[-7 * 24:]}
    return {'hours': n, 'counts': dict(acts),
            'min_home': min(homes), 'zero_hours': sum(h <= 0 for h in homes),
            'below20_hours': sum(h < 20 for h in homes), 'below20': sum(h < 20 for h in homes) / n,
            'upkeep': sum(acts[a] for a in UPKEEP) / n, 'leisure': sum(acts[a] for a in LEISURE) / n,
            'read': acts['read'] / n,
            'entropy': -sum(c / n * math.log2(c / n) for c in acts.values() if c),
            'min_condition': min(r[4] for r in rows), 'kinds_last_week': len(last_week),
            'last_week_hours': min(n, 7 * 24)}


def phase_slices(s):
    out = []
    for i, (name, start) in enumerate(s.phases):
        end = s.phases[i + 1][1] if i + 1 < len(s.phases) else len(s.trace)
        if end > start:
            out.append((name, start, end))
    return out


def h_fails(m, fears_hunger=False, phase=False):
    """Which parts of the safe-home standard a whole life (or a long phase) misses."""
    f = []
    if m['min_home'] < H['min_home']:
        f.append('min_home')
    if m['zero_hours']:
        f.append('zero')
    if m['below20'] > H['max_below20_share']:
        f.append('below20')
    if m['upkeep'] > H['max_upkeep_share']:
        f.append('upkeep')
    if m['leisure'] < H['min_leisure_share']:
        f.append('leisure')
    if m['min_condition'] < H['min_condition']:
        f.append('condition')
    if m['kinds_last_week'] < H['min_kinds_last_week']:
        f.append('kinds_last_week')
    if fears_hunger and not phase:
        f.append('fears_hunger')
    return f


def life_record(s, **ident):
    """Everything later analyses need from one whole life, under an explicit identity."""
    a = s.agent
    whole = metrics(s.trace)
    phases = {}
    for name, i, j in phase_slices(s):
        m = metrics(s.trace[i:j])
        m['fails'] = h_fails(m, phase=True) if (j - i) >= PHASE_MIN_DAYS * 24 else [
            k for k in h_fails(m, phase=True) if k in ('min_home', 'zero', 'condition')]
        phases[name] = m
    fears = 'fears_hunger' in a.flags
    rec = {**ident, 'fingerprint': fingerprint(s.trace), 'days': len(s.trace) / 24,
           'whole': whole, 'phases': phases, 'fears_hunger': fears,
           'fails': h_fails(whole, fears), 'phase_fails': sorted({k for p in phases.values() for k in p['fails']}),
           'first_meet_tick': a.shared[0]['tick'] if a.shared else None,
           'plan_log': list(a.plan_log), 'goal_by_day': list(a.goal_by_day),
           'goal_history': [{k: g.get(k) for k in ('type', 'created_day', 'closed_day', 'outcome', 'plan_id',
                                                     'resumes', 'paused_days')} for g in a.goal_history]}
    rec['h_pass'] = not rec['fails']
    rec['h_phase_pass'] = rec['h_pass'] and not rec['phase_fails']
    return rec


def dedupe(lives):
    """Unique trajectories (by fingerprint) with the runs that produced each one."""
    uniq = {}
    for m in lives:
        u = uniq.setdefault(m['fingerprint'], {**m, 'runs': []})
        u['runs'].append(m['life_id'])
    return list(uniq.values())


def safety_summary(lives):
    u = dedupe(lives)
    return {'runs': len(lives), 'unique_trajectories': len(u),
            'pass': sum(m['h_pass'] for m in u), 'phase_pass': sum(m['h_phase_pass'] for m in u),
            'all_pass': all(m['h_phase_pass'] for m in u),
            'min_home': min(m['whole']['min_home'] for m in u),
            'zero_hours': sum(m['whole']['zero_hours'] for m in u),
            'max_below20': max(m['whole']['below20'] for m in u),
            'max_phase_below20': max(p['below20'] for m in u for p in m['phases'].values()
                                     if p['hours'] >= PHASE_MIN_DAYS * 24),
            'upkeep_range': [min(m['whole']['upkeep'] for m in u), max(m['whole']['upkeep'] for m in u)],
            'min_leisure': min(m['whole']['leisure'] for m in u),
            'min_condition': min(m['whole']['min_condition'] for m in u),
            'min_kinds_last_week': min(m['whole']['kinds_last_week'] for m in u),
            'failing': [{'life': m['life_id'], 'also': m['runs'][1:], 'fails': m['fails'],
                         'phase_fails': {k: p['fails'] for k, p in m['phases'].items() if p['fails']}}
                        for m in u if not m['h_phase_pass']]}


# ---------------------------------------------------------------- statistics (birth seed = unit)
def boot_ci(values, n=10000, seed=12345):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(n))
    return [means[int(0.025 * n)], means[int(0.975 * n)]]


def describe(values):
    """Unrounded. `values` holds one number per birth seed (None = not defined, counted)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {'n': 0, 'missing': len(values)}
    srt = sorted(vals)
    mid = len(srt) // 2
    return {'n': len(vals), 'missing': len(values) - len(vals), 'mean': sum(vals) / len(vals),
            'median': srt[mid] if len(srt) % 2 else (srt[mid - 1] + srt[mid]) / 2,
            'positive': sum(v > 0 for v in vals), 'negative': sum(v < 0 for v in vals),
            'ci95': boot_ci(vals), 'per_seed': list(values)}


def rounded(x, nd=4):
    """Display copy of a result: floats rounded, structure kept. Never used for verdicts."""
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, dict):
        return {k: rounded(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rounded(v, nd) for v in x]
    return x


# ---------------------------------------------------------------- compatibility (part of every verdict)
def compat_check():
    """Replays every recorded baseline (v1-v3, v4, v5, v5 long, v6 candidate) with this engine and
    compares with the digests the older engines wrote. Same checks as the tests, in one place,
    so a verdict cannot be 'adopt' while an old version replays differently."""
    import copy
    import json
    import sys
    from pathlib import Path
    fx = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'
    sys.path.insert(0, str(fx))
    from make_rules_baseline import digest
    from make_rules_baseline_v4 import digest_v4
    from make_rules_baseline_v5 import _h, behavior_digest, explanation_records
    load = lambda name: json.loads((fx / name).read_text(encoding='utf-8'))
    out = {}
    out['v1-v3'] = [digest(Session.restore(copy.deepcopy(c['archive']))) == c['digest'] for c in load('rules_baseline.json')]
    out['v4'] = [digest_v4(Session.restore(copy.deepcopy(c['archive']))) == c['digest'] for c in load('rules_baseline_v4.json')]
    out['v5'] = [behavior_digest(Session.restore(copy.deepcopy(c['archive']))) == c['behavior'] for c in load('rules_baseline_v5.json')]
    out['v5_long'] = []
    for c in load('rules_baseline_v5_long.json'):
        s = Session.restore(copy.deepcopy(c['archive']))
        out['v5_long'].append(behavior_digest(s) == c['behavior'] and _h(explanation_records(s)) == c['explanation'])
    out['v6'] = []
    for c in load('rules_baseline_v6.json'):
        s = Session(c['seed'], 6)
        if c['scheme'] == 'cap2':
            s.agent.visit_cap, s.agent.visit_rest_hours = engine.MILI_VISITS_PER_DAY, 0
        for command in c['commands']:
            s.apply(command)
        out['v6'].append(behavior_digest(s) == c['behavior'] and _h(explanation_records(s)) == c['explanation']
                         and _h(s.agent.goal_history) == c['goal_history'])
    summary = {k: {'cases': len(v), 'identical': sum(v)} for k, v in out.items()}
    return {'by_version': summary, 'pass': all(all(v) for v in out.values())}
