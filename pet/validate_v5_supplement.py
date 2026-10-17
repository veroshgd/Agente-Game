"""v5 validation: method corrections and supplementary analysis (v5 验证方法修正与补充分析).

    python -m pet.validate_v5_supplement dev [out_dir]       # seeds 1, 42, 901, 7, 123
    python -m pet.validate_v5_supplement review [out_dir]    # 2001-2010: already analysed -> review / exploratory
    python -m pet.validate_v5_supplement fresh [out_dir]     # 3001-3010: new seeds for the new criteria below

Rules and parameters are the v5 ones; nothing here changes behavior. The original
pet/validate_v5.py, its criteria and its results are kept as they were.

What this adds
1. Social differentiation measured in actual daily life: visits per game day, split into
   spontaneous and invited visits, per 10-day window. Also visits per *fixed* opportunity
   hour: 08-20 h on days the neighbor's schedule (seed and day only) has her at home. That
   denominator does not depend on how many visits the pet already made; her daily visit
   limit still applies in life. A window with no opportunity hour is reported as missing.
   The old ratio (visits / hours she was free, which shrinks once a pet uses up her daily
   visits) is kept for comparison only. The probe numbers are probes, not lived counts.
2. Whether each pet really met the neighbor: the shared invitation at day 20 is an
   opportunity, not a guaranteed meeting.
3. Plasticity with a paired control: from the same state after growth (reading route),
   branch A keeps the uniform environment, branch B also gets an invitation every morning
   for 30 days; then both get 30 more days with no extra invitations (withdrawal).
"""
import copy
import json
import sys
from collections import Counter
from pathlib import Path

from . import engine
from .validate_v5 import (DEV_SEEDS, GROW, ROUTES, VALIDATION_SEEDS, grow, mean, mili_away,
                          probe, uniform)

REVIEW_SEEDS = VALIDATION_SEEDS            # 2001-2010: seen and analysed, no longer independent
FRESH_SEEDS = [3001, 3002, 3003, 3004, 3005, 3006, 3007, 3008, 3009, 3010]
OBSERVE, WINDOW = 60, 10
PHASE, WITHDRAW = 30, 30                   # plasticity: 30 days with/without daily invites, 30 days after

# ---- New tentative criteria (product thresholds). Written after the exploratory review of
# 2001-2010 and BEFORE any run on 3001-3010. Product reason for the unit: one extra visit a
# week (1/7 per day) is about the smallest change a player who checks in daily could notice
# in the diary; it is a product guess, not a validated perception threshold.
NEW_CRITERIA = {
    'social_visits_per_day_gap': 1 / 7,   # social - garden route, mean over the 60 uniform days
    'windows_positive': 4,                # of 6 ten-day windows with a positive gap
    'invite_social_pref_gap': 0.10,       # branch B - branch A change of the 'social' liking after 30 days
    'withdrawal_spont_gap': 1 / 7,        # B - A spontaneous visits a day in the 30 days after invitations stop
    'seed_share': 0.7,
}


def observe(s, days, seed, invite_daily=False):
    rows, offered = [], 0
    for _ in range(days * 24):
        a = s.agent
        day, hour = divmod(s.tick, 24)
        if invite_daily and hour == 8 and s.tick >= a.invitation_until and s.world.has('garden'):
            s.apply({'kind': 'invite', 'value': None})
            offered += 1
        visits_today = sum(1 for m in a.shared if m['tick'] // 24 == day)
        fixed_opp = 8 <= hour < 20 and not mili_away(seed, day)            # schedule only
        legacy_free = fixed_opp and bool(a.shared) and visits_today < engine.MILI_VISITS_PER_DAY
        s.step()
        e = s.events[-1]
        rows.append({'action': e['action'], 'invited': bool(e.get('invited')), 'fixed_opp': fixed_opp,
                     'legacy_free': legacy_free})
    windows = []
    for w in range(0, len(rows), WINDOW * 24):
        part = rows[w:w + WINDOW * 24]
        n_days = len(part) / 24
        visits = [r for r in part if r['action'] == 'visit']
        opp = sum(r['fixed_opp'] for r in part)
        legacy = sum(r['legacy_free'] for r in part)
        windows.append({
            'visits_per_day': len(visits) / n_days,
            'spontaneous_per_day': sum(not r['invited'] for r in visits) / n_days,
            'invited_per_day': sum(r['invited'] for r in visits) / n_days,
            'fixed_opp_hours': opp,
            'visits_per_fixed_opp_hour': len([r for r in visits if r['fixed_opp']]) / opp if opp else None,
            'legacy_free_hours': legacy,
            'legacy_ratio': sum(r['action'] == 'visit' and r['legacy_free'] for r in part) / legacy if legacy else None,
            'read_share': sum(r['action'] == 'read' for r in part) / len(part),
            'prefs_end': None,
        })
    return windows, offered


def observe_windows(s, days, seed, invite_daily=False):
    """observe() in window-sized steps so each window records the preferences at its end."""
    out, offered = [], 0
    for _ in range(days // WINDOW):
        w, o = observe(s, WINDOW, seed, invite_daily)
        w[0]['prefs_end'] = {k: round(v, 4) for k, v in s.agent.prefs.items()}
        out += w
        offered += o
    return out, offered


def met_record(s, since_tick):
    visits = [e for e in s.events if e.get('action') == 'visit']
    after = [e for e in visits if e['tick'] >= since_tick]
    return {'met_during_growth': any(e['tick'] < since_tick for e in visits),
            'accepted_shared_invitation': any(e['invited'] for e in after if e['tick'] < since_tick + 24),
            'first_visit_after_day20': after[0]['tick'] if after else None,
            'never_met_by_end': not visits}


def run_seed(seed):
    out = {'routes': {}, 'plasticity': {}}
    for route in ROUTES:
        s = grow(seed, route)
        uniform(s)
        since = s.tick
        probes = {s.tick // 24: probe(s)}
        windows, _ = observe_windows(s, OBSERVE // 2, seed)
        probes[s.tick // 24] = probe(s)
        w2, _ = observe_windows(s, OBSERVE // 2, seed)
        windows += w2
        probes[s.tick // 24] = probe(s)
        out['routes'][route] = {'windows': windows, 'probes': probes, 'met': met_record(s, since)}
    # Paired plasticity from one grown state.
    base = grow(seed, 'reading')
    uniform(base)
    start = {k: round(v, 4) for k, v in base.agent.prefs.items()}
    for name, daily in (('A_uniform', False), ('B_daily_invites', True)):
        s = copy.deepcopy(base)
        phase, offered = observe_windows(s, PHASE, seed, invite_daily=daily)
        after_phase = {k: round(v, 4) for k, v in s.agent.prefs.items()}
        withdraw, _ = observe_windows(s, WITHDRAW, seed, invite_daily=False)
        out['plasticity'][name] = {'start_prefs': start, 'prefs_after_phase': after_phase,
                                   'prefs_end': {k: round(v, 4) for k, v in s.agent.prefs.items()},
                                   'invitations_offered': offered, 'phase': phase, 'withdrawal': withdraw}
    return out


def analyse(per_seed):
    seeds = {}
    for seed, r in per_seed.items():
        R = r['routes']
        gap = lambda key, a='social', b='garden': [
            None if x[key] is None or y[key] is None else x[key] - y[key]
            for x, y in zip(R[a]['windows'], R[b]['windows'])]
        per_day = gap('visits_per_day')
        P = r['plasticity']
        A, B = P['A_uniform'], P['B_daily_invites']
        d = lambda br, k: br['prefs_after_phase'][k] - br['start_prefs'][k]
        spont = lambda br, part: mean([w['spontaneous_per_day'] for w in br[part]])
        seeds[seed] = {
            'visits_per_day_gap': [round(x, 3) for x in per_day],
            'visits_per_day_gap_mean': round(mean(per_day), 3),
            'spontaneous_gap_mean': round(mean([x for x in gap('spontaneous_per_day')]), 3),
            'invited_gap_mean': round(mean([x for x in gap('invited_per_day')]), 3),
            'fixed_opp_gap': [None if x is None else round(x, 3) for x in gap('visits_per_fixed_opp_hour')],
            'legacy_ratio_gap': [None if x is None else round(x, 3) for x in gap('legacy_ratio')],
            'missing_windows': {k: sum(w['visits_per_fixed_opp_hour'] is None for w in v['windows']) for k, v in R.items()},
            'probe_visit_gap': {day: round(R['social']['probes'][day]['visit'] - R['garden']['probes'][day]['visit'], 3)
                                for day in R['social']['probes']},
            'met': {k: v['met'] for k, v in R.items()},
            'social_new_criterion': mean(per_day) >= NEW_CRITERIA['social_visits_per_day_gap']
                                    and sum(x is not None and x > 0 for x in per_day) >= NEW_CRITERIA['windows_positive'],
            'plasticity': {
                'delta_A': {k: round(d(A, k), 3) for k in ('read', 'garden', 'social')},
                'delta_B': {k: round(d(B, k), 3) for k in ('read', 'garden', 'social')},
                'delta_B_minus_A': {k: round(d(B, k) - d(A, k), 3) for k in ('read', 'garden', 'social')},
                'invitations_offered_B': B['invitations_offered'],
                'invited_visits_B_phase': round(sum(w['invited_per_day'] for w in B['phase']) * WINDOW, 1),
                'spont_phase': {'A': round(spont(A, 'phase'), 3), 'B': round(spont(B, 'phase'), 3)},
                'spont_withdrawal': {'A': round(spont(A, 'withdrawal'), 3), 'B': round(spont(B, 'withdrawal'), 3)},
                'withdrawal_windows_spont_gap': [round(b['spontaneous_per_day'] - a['spontaneous_per_day'], 3)
                                                 for a, b in zip(A['withdrawal'], B['withdrawal'])],
                'withdrawal_social_pref_gap': round(B['prefs_end']['social'] - A['prefs_end']['social'], 3),
                'read_share': {'A': [round(w['read_share'], 3) for w in A['phase'] + A['withdrawal']],
                               'B': [round(w['read_share'], 3) for w in B['phase'] + B['withdrawal']]},
                # Old v5 "transformation" rule, for both branches: liking for the new activities
                # overtakes reading and reading's liking falls.
                'old_rule': {name: (max(br['prefs_after_phase']['garden'], br['prefs_after_phase']['social']) > br['prefs_after_phase']['read']
                                    and br['prefs_after_phase']['read'] < br['start_prefs']['read'])
                             for name, br in (('A', A), ('B', B))},
            },
        }
        p = seeds[seed]['plasticity']
        seeds[seed]['invite_effect'] = p['delta_B_minus_A']['social'] >= NEW_CRITERIA['invite_social_pref_gap']
        seeds[seed]['withdrawal_effect'] = (p['spont_withdrawal']['B'] - p['spont_withdrawal']['A']) >= NEW_CRITERIA['withdrawal_spont_gap']
    S = list(seeds.values())
    n = len(S)
    summary = {
        'n_seeds': n,
        'visits_per_day_gap_mean': round(mean([s['visits_per_day_gap_mean'] for s in S]), 3),
        'visits_per_week_gap_mean': round(7 * mean([s['visits_per_day_gap_mean'] for s in S]), 2),
        'spontaneous_gap_mean': round(mean([s['spontaneous_gap_mean'] for s in S]), 3),
        'invited_gap_mean': round(mean([s['invited_gap_mean'] for s in S]), 3),
        'fixed_opp_gap_mean': round(mean([x for s in S for x in s['fixed_opp_gap'] if x is not None]), 3),
        'legacy_ratio_gap_mean': round(mean([x for s in S for x in s['legacy_ratio_gap'] if x is not None]), 3),
        'missing_fixed_opp_windows': sum(sum(s['missing_windows'].values()) for s in S),
        'never_met': [(seed, route) for seed, s in seeds.items() for route, m in s['met'].items() if m['never_met_by_end']],
        'shared_invitation_declined': [(seed, route) for seed, s in seeds.items() for route, m in s['met'].items()
                                       if not m['accepted_shared_invitation']],
        'social_new_criterion_seeds': sum(s['social_new_criterion'] for s in S),
        'plasticity': {
            'delta_A_mean': {k: round(mean([s['plasticity']['delta_A'][k] for s in S]), 3) for k in ('read', 'garden', 'social')},
            'delta_B_mean': {k: round(mean([s['plasticity']['delta_B'][k] for s in S]), 3) for k in ('read', 'garden', 'social')},
            'delta_B_minus_A_mean': {k: round(mean([s['plasticity']['delta_B_minus_A'][k] for s in S]), 3) for k in ('read', 'garden', 'social')},
            'old_rule_A': sum(s['plasticity']['old_rule']['A'] for s in S), 'old_rule_B': sum(s['plasticity']['old_rule']['B'] for s in S),
            'spont_phase_mean': {b: round(mean([s['plasticity']['spont_phase'][b] for s in S]), 3) for b in 'AB'},
            'spont_withdrawal_mean': {b: round(mean([s['plasticity']['spont_withdrawal'][b] for s in S]), 3) for b in 'AB'},
            'withdrawal_social_pref_gap_mean': round(mean([s['plasticity']['withdrawal_social_pref_gap'] for s in S]), 3),
            'invite_effect_seeds': sum(s['invite_effect'] for s in S),
            'withdrawal_effect_seeds': sum(s['withdrawal_effect'] for s in S),
        },
    }
    k = NEW_CRITERIA['seed_share'] * n
    verdict = {'social_actual_visits': summary['social_new_criterion_seeds'] >= k,
               'invitations_change_social_liking': summary['plasticity']['invite_effect_seeds'] >= k,
               'effect_survives_withdrawal': summary['plasticity']['withdrawal_effect_seeds'] >= k}
    return {'criteria': NEW_CRITERIA, 'summary': summary, 'verdict': verdict, 'seeds': seeds}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    seeds = {'dev': DEV_SEEDS, 'review': REVIEW_SEEDS, 'fresh': FRESH_SEEDS}[which]
    per_seed = {seed: run_seed(seed) for seed in seeds}
    result = analyse(per_seed)
    result['sample'] = {'dev': 'development seeds', 'review': 'review / exploratory sample (already analysed)',
                        'fresh': 'new seeds, criteria fixed before this run'}[which]
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / 'pet_validation_out'
    out.mkdir(parents=True, exist_ok=True)
    (out / f'v5_supplement_{which}_raw.json').write_text(json.dumps(per_seed, ensure_ascii=False), encoding='utf-8')
    (out / f'v5_supplement_{which}_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'sample': result['sample'], 'summary': result['summary'], 'verdict': result['verdict']}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
