"""Round 8 of 2026-10-25 (experiment, NOT a rule version): home foresight before starting a leisure plan
(engine PetAgent.home_foresight, pet/validate_foresight.py) and the corrected 6006 entry values."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import validate_foresight as VF
from pet import validate_interest as VI
from pet import validate_read as VR
from pet.engine import RULES, Session, core
from make_rules_baseline_v5 import behavior_digest

FLOOR, AGE = engine.HOME_FORESIGHT_FLOOR, engine.SHELTER_AGEING
EDGE = FLOOR + AGE * 24 * core.GOAL_MIN_DAYS          # 36.8: the lowest home that may start a leisure plan


def agent(cond='foresight', seed=3001):
    s = VF.configure(Session(seed, 5), cond)
    s.apply({'kind': 'object', 'value': 'book'})
    s.apply({'kind': 'object', 'value': 'garden'})
    return s.agent


def test_off_for_every_rule_version_and_constants():
    assert RULES == 5 and EDGE == pytest.approx(36.8)
    for rules in range(1, 7):
        assert not Session(rules=rules).agent.home_foresight


def test_ageing_constant_is_the_core_ageing():
    s = Session(42, 5)
    a = s.agent
    a.shelter = 50.0
    a.inventory['material'] = 0.0          # no build possible this hour
    before = a.shelter
    s.step()
    assert s.events[-1]['core_action'] != 'build' and before - a.shelter == pytest.approx(AGE)


def cands():
    return [('improve_home', 0.6, 'x'), ('stock_food', 0.5, 'x'), ('learn', 0.9, 'x'), ('see_the_world', 0.9, 'x')]


@pytest.mark.parametrize('home,kept', [(EDGE, 4), (EDGE + 1e-9, 4), (EDGE - 1e-9, 2), (20.0, 2)])
def test_boundary_projection_ge_floor_keeps_leisure(home, kept):
    a = agent()
    a.shelter, a.goal = home, None
    out = a._foresight_filter(cands(), 5)
    assert len(out) == kept and [c[0] for c in out][:2] == ['improve_home', 'stock_food']


def test_open_plan_is_never_cut_and_other_leisure_is_left_out():
    a = agent()
    a.shelter = 25.0
    a.goal = {'type': 'learn', 'priority': 0.9, 'created_day': 3, 'start': 0}
    assert [c[0] for c in a._foresight_filter(cands(), 5)] == ['improve_home', 'stock_food', 'learn']


def test_order_and_ties_of_the_rest_unchanged():
    a = agent()
    a.shelter, a.goal = 25.0, None
    c = [('stock_food', 0.7, 'x'), ('learn', 0.9, 'x'), ('improve_home', 0.7, 'x')]
    out = a._foresight_filter(c, 5)
    assert out == [('stock_food', 0.7, 'x'), ('improve_home', 0.7, 'x')]
    out.sort(key=lambda x: -x[1])
    assert out[0][0] == 'stock_food'                  # stable sort: the existing tie order


def test_no_candidate_left_means_no_new_plan():
    a = agent()
    a.shelter, a.goal = 80.0, None
    a.propose_goals = lambda day: [('learn', 0.9, 'x')]
    a.shelter = 30.0                                   # learn left out; nothing else proposed
    a._update_goal_ordered(5)
    assert a.goal is None and a.plan_log[-1]['event'] == 'foresight_excluded'


def test_pure_and_ordered_only():
    a = agent()
    a.shelter, a.goal = 25.0, None
    rng = a.rng.getstate()
    a._foresight_filter(cands(), 5)
    assert a.rng.getstate() == rng and a.shelter == 25.0
    # only the ordered update reads it: on the core update path (v5 default) the flag changes nothing
    x, y = Session(42, 5), Session(42, 5)
    y.agent.home_foresight = True
    for s in (x, y):
        s.apply({'kind': 'object', 'value': 'book'})
        for _ in range(20 * 24):
            s.step()
    assert not y.agent.ordered_goals and behavior_digest(x) == behavior_digest(y)


def test_switch_off_is_the_current_mechanism_exactly():
    x = VF.new_pet(3001, 'current')
    y = VI.new_pet(3001, 'interest')
    for s in (x, y):
        s.apply({'kind': 'object', 'value': 'book'})
        VR.run_hours(s, 30 * 24)
    assert behavior_digest(x) == behavior_digest(y)


def test_entry_values_6006():
    r = json.loads((ROOT / 'docs' / 'pet_plan_components' / 'correction_days' / 'recheck_case_6006.json').read_text(encoding='utf-8'))
    assert r['same_life_as_recheck_plan_days']
    e = {x['common_day']: x for x in r['entries']}
    assert e[27]['home'] == pytest.approx(15.2, abs=0.01) and not e[27]['trigger_home'] and e[27]['in_min_stay']
    assert e[35]['home'] == pytest.approx(14.0, abs=0.01) and e[35]['trigger_home']
    assert e[35]['repair_lead'] == pytest.approx(0.158, abs=1e-3) and e[35]['repair_lead'] < core.GOAL_SWITCH_MARGIN
    assert e[27]['goal'] == e[35]['goal'] == 'see_the_world' and e[27]['age'] == e[35]['age'] == 1
