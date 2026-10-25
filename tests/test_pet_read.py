"""Round 3 of 2026-10-23 (NOT adopted): the A3 correction, the 'new leisure plan blocks the repair'
regression, the base2 repair candidate (not adopted), and the reading result mechanism with its
value (pet/validate_read.py, docs/pet_read_validation/). v1-v6 replays are pinned elsewhere."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import validate_eval as VE
from pet import validate_pause as VP
from pet import validate_read as VR
from pet import validate_v6 as V6
from pet.engine import RULES, Session, core
from make_rules_baseline_v5 import behavior_digest


def pet(arm='read_value', seed=42, items=('book',), clarity=None):
    s = VR.configure(Session(seed, 5), arm)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    if clarity is not None:
        s.world.p['book_clarity'] = clarity
    return s


def live(s, days):
    for _ in range(days * 24):
        s.step()
    return s


# ---------------------------------------------------------------- A3 correction (saved results only)
def test_a3_as_written_fails_on_the_phase_a_validation():
    r = json.loads((ROOT / 'docs' / 'pet_eval_validation' / 'eval_validation_result.json').read_text(encoding='utf-8'))
    v = [r['per_seed']['base'][str(s)]['pair_B_minus_A_spont'] for s in r['seeds']]
    assert sum(x >= 1 / 7 for x in v) == 13                 # the written criterion needs 14
    assert sum(x > 0 for x in v) == 19 and r['final']['A3_social_kept'] is True   # what the frozen code checked
    assert (ROOT / 'docs' / 'pet_eval_validation' / 'CORRECTION_A3.md').exists()


# ---------------------------------------------------------------- 'new leisure plan blocks the repair'
def morning_state(seed, design, day):
    """Lived eval-arm life (round 2) just before the morning goal update of `day`."""
    s = VE.grow(seed, 'reading' if design == 'plastic' else 'social', 'eval')
    while s.tick < day * 24:
        s.step()
    s.agent.now = s.tick
    return s


@pytest.mark.parametrize('seed,design,day,home', [(6006, 'plastic', 105, 12.0), (6006, 'social', 68, 14.8)])
def test_regression_new_leisure_plan_blocks_the_repair(seed, design, day, home):
    s = morning_state(seed, design, day)
    a = s.agent
    assert a.shelter == pytest.approx(home, abs=0.05) and a.goal['type'] == 'see_the_world'
    kept = copy.deepcopy(a)
    kept.update_goal(day)
    assert kept.goal['type'] == 'see_the_world'            # the frozen base keeps the leisure plan
    fixed = copy.deepcopy(a)
    fixed.emergency_no_margin = True
    fixed.update_goal(day)
    assert fixed.goal['type'] == 'improve_home'            # base2: the repair only has to be ahead
    assert fixed.goal_history[-1]['outcome'] == 'switched'


def test_base2_is_not_adopted_and_reading_arms_use_the_frozen_base():
    r = json.loads((ROOT / 'docs' / 'pet_read_validation' / 'base2_verification.json').read_text(encoding='utf-8'))
    assert r['dev']['verdict']['phase_fails_not_above_base'] is False
    assert all(not VR.ARMS[a].get('no_margin') for a in ('read_nodecision', 'read_value', 'read_flat'))


# ---------------------------------------------------------------- reading result mechanism
def test_flags_are_off_for_every_rule_version():
    assert RULES == 5
    for rules in range(1, 7):
        a = Session(rules=rules).agent
        assert not (a.reading_outcome or a.emergency_no_margin)


def test_only_reading_hours_give_a_result_from_the_same_rule():
    s = live(pet('read_nodecision', 3001, ('book', 'garden'), clarity=0.9), 10)
    for e in s.events:
        if e['kind'] != 'action':
            continue
        if e['core_action'] == 'read':
            r = e['read_outcome']
            assert r['clarity'] == 0.9 and r['gain'] == pytest.approx(0.9 * r['focus']) and 0 <= r['focus'] <= 1
        else:
            assert e['read_outcome'] is None
    a = s.agent
    reads = [e['read_outcome']['gain'] for e in s.events if e.get('core_action') == 'read']
    assert a.read_evidence['count'] == len(reads) and a.book_progress == pytest.approx(sum(reads))


def test_gain_never_depends_on_how_much_was_read():
    a, b = pet().agent, pet().agent
    for _ in range(80):
        b.read_experience('read', 1, {'gain': 0.5})
    a.energy = b.energy = 70.0
    a.hunger = b.hunger = 20.0
    ga = a.read_clarity() * a.need_gate()
    gb = b.read_clarity() * b.need_gate()
    assert ga == gb                                         # 0 vs 80 readings: same result for the same hour


def test_unread_is_not_disliked_and_the_value_is_bounded_and_reversible():
    a = pet().agent
    assert a.read_n == 0 and a.read_value_term() == 0.0
    a.read_experience('garden', 1, None)                     # gardening is no reading experience
    assert a.read_n == 0 and a.read_V == 0.0
    for _ in range(40):
        a.read_experience('read', 1, {'gain': 0.9})
    high = a.read_value_term()
    for _ in range(40):
        a.read_experience('read', 1, {'gain': 0.2})
    assert high > 0 > a.read_value_term() and -1 <= a.read_value_term() <= 1


def test_unread_time_fades_confidence_not_the_value():
    a = pet().agent
    for _ in range(20):
        a.read_experience('read', 1, {'gain': 0.8})
    v, n = a.read_V, a.read_n
    for d in range(30):
        a.daily(d)
    assert a.read_V == v and a.read_n == pytest.approx(n * engine.EVAL_KEEP ** 30)


def test_the_term_enters_only_the_read_score_with_needs_first():
    s = live(pet('read_value', 42, ('book', 'garden'), clarity=0.9), 20)
    a, day = s.agent, s.tick // 24
    for x in core.ACTIONS:
        p = a.score_parts(x, day)
        if p is None:
            continue
        want = (engine.READ_VALUE_WEIGHT * a.read_value_term() * a.need_gate() * (1 - a.home_need())) if x == 'read' else 0.0
        assert p['read_value'] == pytest.approx(want)
    flat = copy.deepcopy(a)
    flat.read_value_flat = True
    assert flat.score_parts('explore', day)['read_value'] == pytest.approx(flat.score_parts('read', day)['read_value'])
    goals = {g: p for g, p, _ in a.propose_goals(day)}
    a.reading_outcome = False
    assert goals == {g: p for g, p, _ in a.propose_goals(day)}            # goals untouched


def test_no_decision_control_is_the_frozen_base_exactly():
    x = live(VE.configure(Session(3001, 5), 'base'), 0)
    for it in ('book', 'garden'):
        x.apply({'kind': 'object', 'value': it})
    y = pet('read_nodecision', 3001, ('book', 'garden'), clarity=0.9)
    assert behavior_digest(live(x, 40)) == behavior_digest(live(y, 40))


def test_counterfactual_and_no_random_draw():
    s = live(pet('read_value', 3001, ('book', 'garden'), clarity=0.9), 30)
    checked = 0
    for e in s.events:
        d = e.get('decision') or {}
        if d.get('read_value'):
            assert d['read_value_decisive'] == (d['read_value_choice_without'] != e['core_action'])
            checked += 1
    assert checked
    a, day = s.agent, s.tick // 24
    rng = a.rng.getstate()
    off = copy.deepcopy(a)
    off.reading_outcome = False
    assert a.choice_without_read_value(day) == off.choose(day) and a.rng.getstate() == rng


def test_matched_growth_reads_the_same_hours_with_different_results():
    res, _ = VR.matched(3001, 'read_value')
    assert res['growth_identical'] and res['growth_reads']['clear'] == res['growth_reads']['hard'] > 0
    assert res['value_start']['clear']['V'] > res['value_start']['hard']['V']
    assert res['probe_day0']['value_off'] == 0.0                         # state-matched: only the value differs


def test_probe_copies_never_touch_the_life():
    s = live(pet('read_value', 42, ('book', 'garden'), clarity=0.9), 20)
    before = behavior_digest(s), s.agent.read_V
    VR.probe(s.agent, copy.deepcopy(s.agent), s.tick // 24)
    assert (behavior_digest(s), s.agent.read_V) == before


def test_criteria_fixed_and_validation_seeds_unused():
    used = (set(VE.DEV_SEEDS) | set(VE.VALIDATION_SEEDS) | set(VP.VALIDATION_SEEDS) | set(V6.VALIDATION_SEEDS)
            | set(V6.SPENT_SEEDS) | set(VR.DEV_SEEDS))
    assert not set(VR.VALIDATION_SEEDS) & used and VR.VALIDATION_SEEDS[0] == 7041   # no earlier round used them
    from pet import run_foresight_validation as RV
    assert RV.seeds_used_only_by_this_validation()        # round 9: used once since, by the foresight validation
    assert VR.CRITERIA['K1_min_gap'] == 0.01 and VR.CANDIDATE == 'read_value'
