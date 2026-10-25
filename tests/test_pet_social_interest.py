"""Round 11 of 2026-10-25 (experiment, NOT a rule version): the social memory extension
(pet/social_interest.py) and the reading + social design (pet/validate_social.py)."""
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import social_interest as SI
from pet import validate_foresight as VF
from pet import validate_read as VR
from pet import validate_social as VS
from pet.engine import RULES, Session
from make_rules_baseline_v5 import behavior_digest

REF = engine.READ_VALUE_REF


def pet(arm='B', seed=3001, items=('book', 'garden')):
    s = VS.new_pet(seed, arm)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    return s


def test_default_product_untouched():
    assert RULES == 5 and not hasattr(Session(42, 5).agent, 'social_memory')
    a = SI.SocialSession(42, 5).agent
    assert not a.social_memory and a.social_entry is None and a.frozen is None and not a.explore_offtask_off


@pytest.mark.parametrize('arm', ['ref', 'none'])
def test_reference_arm_is_the_validated_candidate_exactly(arm):
    x = VF.new_pet(3001, 'both')
    y = VS.new_pet(3001, 'ref')
    for s in (x, y):
        s.apply({'kind': 'object', 'value': 'book'})
        s.apply({'kind': 'object', 'value': 'garden'})
        VR.run_hours(s, 30 * 24, invite_daily=True)
    assert behavior_digest(x) == behavior_digest(y) and x.agent.rng.getstate() == y.agent.rng.getstate()
    assert y.agent.s_n > 0 and y.agent.s_V != 0                         # it learnt, it never decided


def test_social_memory_uses_the_reading_rule():
    a = pet().agent
    a._focus, a.now = 0.8, 100
    a.world.p['neighbor_warmth'] = 0.9
    a.social_result(False)
    assert a.s_V == pytest.approx(0.72) and a.s_n == 1 and a.social_log[-1] == (100, pytest.approx(0.72), False)
    w = 1 / (1 + engine.EVAL_N0) * abs(0.72 - REF) / REF
    a.daily(0)
    assert a.s_I == pytest.approx(REF + engine.INTEREST_RATE * w * (0.72 - REF)) and a.s_n == pytest.approx(engine.EVAL_KEEP)
    b = pet().agent
    for d in range(30):
        b.daily(d)                                                       # no visits: fades, stays neutral
    assert b.s_I == REF and b.s_n == 0 and b.social_term() == 0.0


def test_term_bound_and_entries():
    a = pet('B').agent
    for V, n, I in ((1.0, 1e9, 1.0), (0.0, 1e9, 0.0)):
        a.s_V, a.s_n, a.s_I = V, n, I
        assert -0.5 - 1e-12 <= a.social_term() <= 0.5 + 1e-12
    a.s_V, a.s_n, a.s_I = 0.9, 40.0, 0.8
    a.hunger, a.energy, a.shelter = 30.0, 80.0, 60.0
    a.shared = [{'id': 1, 'tick': 0}]
    day, hour = 21, 10
    a.now = day * 24 + hour
    assert a.can_meet(day, hour, False) or a.neighbor_status(day, hour) != engine.NEIGHBOR_FREE
    part = a.social_score_part('explore', day)
    if a.can_meet(day, hour, False):
        assert part == pytest.approx(engine.READ_VALUE_WEIGHT * a.social_term() * a.need_gate() * (1 - a.home_need()))
    assert a.social_score_part('read', day) == 0.0
    a.now = day * 24 + 22                                                # off hours: she cannot meet
    assert a.social_score_part('explore', day) == 0.0
    b = pet('A').agent
    b.s_V, b.s_n, b.s_I, b.shared = 0.9, 40.0, 0.8, [{'id': 1, 'tick': 0}]
    p_a, _ = b.visit_chance(0.0)
    c = pet('ref').agent
    p_ref, _ = c.visit_chance(0.0)
    assert p_a == pytest.approx(min(engine.VISIT_MAX, p_ref + engine.VISIT_PREF * b.social_term()))
    assert b.social_score_part('explore', day) == 0.0                    # A never touches the explore score
    b.exp_decide = False
    assert b.visit_chance(0.0)[0] == p_ref


def test_freeze_snapshots_the_terms_and_keeps_the_gates_live():
    a = pet('B_frozen').agent
    a.read_V, a.read_n, a.read_I, a.s_V, a.s_n, a.s_I = 0.8, 30.0, 0.7, 0.2, 20.0, 0.3
    a.freeze()
    t_read, t_soc = a.read_value_term(), a.social_term()
    a.read_V, a.read_n, a.read_I, a.s_V, a.s_n, a.s_I = 0.1, 99.0, 0.1, 0.9, 99.0, 0.9
    assert (a.read_value_term(), a.social_term()) == (t_read, t_soc)
    a.hunger, a.energy = 30.0, 80.0
    g1 = a.read_value_part('read')[0]
    a.energy = 10.0
    assert abs(a.read_value_part('read')[0]) < abs(g1)                   # need gate still live


def test_explore_exemption_is_only_for_explore():
    a = pet('B_sym').agent
    a.hunger, a.energy, a.condition = 30.0, 80.0, 100.0
    a.goal = {'type': 'learn', 'priority': 1.0, 'created_day': 0, 'start': 0}
    b = copy.deepcopy(a)
    b.explore_offtask_off = False
    assert a.goal_bonus('explore') == 0.0 and b.goal_bonus('explore') < 0
    assert all(a.goal_bonus(x) == b.goal_bonus(x) for x in engine.core.ACTIONS if x != 'explore')


def test_growth_is_identical_and_none_arm_lives_identically():
    pets, same, mem = VS.grow(9999, 'B')
    assert same and mem['clear|warm']['s_V'] > mem['clear|cold']['s_V'] and mem['clear|warm']['read_V'] > mem['hard|warm']['read_V']
    j = VS.design_job((9999, 'none'))
    assert j['same_growth'] and j['none_identical']


def test_window_separates_spontaneous_and_invited_visits():
    s = pet('ref', 42)
    s.apply({'kind': 'invite', 'value': None})
    n0, t0 = len(s.events), s.tick
    VR.run_hours(s, 3 * 24, invite_daily=True)
    w = VS.window(s, n0, t0)
    ev = [e for e in s.events[n0:] if e['kind'] == 'action' and e['action'] == 'visit']
    assert w['invited_per_day'] * 3 == sum(e['invited'] for e in ev)
    assert w['spont_per_day'] * 3 == sum(not e['invited'] for e in ev)
    assert w['social_results'] == len(ev)
