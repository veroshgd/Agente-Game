"""Round 7 of 2026-10-25 (correction, NOT a rule version): day-level plan metrics read after the morning
goal update (pet/recheck_plan_days.py), and the 6006 / rep2 / hard / no_offtask case."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet import diag_interest as DI
from pet import recheck_plan_days as R
from pet import validate_interest as VI
from pet import validate_read as VR

RESULT = ROOT / 'docs' / 'pet_plan_components' / 'correction_days' / 'recheck_plan_days.json'


def test_morning_record_is_after_the_goal_update_and_catches_same_morning_closes():
    s = R.pets_at_common(3001)['clear']
    s.agent.read_audit = True
    rows, mornings, old_end = [], [], []
    a = s.agent
    for d in range(VI.COMMON):
        closed_before = len(a.goal_history)
        R.live_morning(s, 1, rows, mornings)            # asserts goal == goal_by_day == hour-0 decision
        m = mornings[-1]
        new_closes = [g for g in a.goal_history[closed_before:] if g['closed_day'] == m['day']]
        if any(g['type'] == 'learn' and g['outcome'] in ('done', 'stalled') for g in new_closes):
            assert m['learn_sat'] == 0.9                     # closed this morning: full satiation today
        old_end.append(DI.day_state(a))
    # the goal the pet acted under on day d is what the old record wrote at the END of day d (= old days[d + 1])
    assert [m['goal'] for m in mornings] == [x['goal'] for x in old_end]


def test_recording_changes_no_life_and_no_generator_state():
    pets0 = R.pets_at_common(9999)
    for cond in ('current', 'no_offtask'):
        old, new = R.run_original(pets0, 9999, cond, 1), R.run_fixed(pets0, 9999, cond, 1)
        assert all(old[n]['fingerprint'] == new[n]['fingerprint'] and old[n]['rng'] == new[n]['rng'] for n in pets0)


def test_recorded_correction_and_named_cases():
    r = json.loads(RESULT.read_text(encoding='utf-8'))
    assert r['summary']['same_lives_all'] and r['summary']['old_equals_saved']
    a = r['checks']['6006/no_offtask/rep2/hard']
    assert (a['old']['learn_days'], a['new']['learn_days'], a['old']['sat_days'], a['new']['sat_days']) == (12, 11, 35, 41)
    b = r['checks']['6001/no_offtask/rep0/clear']
    assert (b['old']['read_on_sat_days_out_learn'], b['new']['read_on_sat_days_out_learn']) == (64, 69)
    assert a['same_life'] and b['same_life']


def test_recorded_case_6006():
    c = json.loads(RESULT.read_text(encoding='utf-8'))['case']
    assert c['matches_diag_plan_lives'] == {'current': True, 'no_offtask': True}
    f = c['first_divergence']
    assert f['identical_before'] and f['current']['tick'] == 515 and (f['current']['core'], f['no_offtask']['core']) == ('explore', 'read')
    direct = c['direct_changes']['no_offtask']
    assert len(direct) == 4 and all(x['core'] == 'read' and x['other_rule'] in ('explore', 'eat') for x in direct)
    assert c['below20_hours'] == {'current': 68, 'no_offtask': 122}
    assert abs(c['counts']['current']['build'] - c['counts']['no_offtask']['build']) <= 1
