"""Round 6 of 2026-10-25 (diagnostics, NOT a rule version): the plan's effect on 'read' split into the
off-task penalty and the 'learn' bonus (engine goal_read_offtask_off / goal_read_learn_bonus_off,
pet/diag_plan.py). v1-v6 replays are pinned elsewhere."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import diag_plan as DP
from pet import validate_interest as VI
from pet import run_foresight_validation as RV
from pet import validate_read as VR
from pet.engine import RULES, Session
from make_rules_baseline_v5 import behavior_digest

RESULT = ROOT / 'docs' / 'pet_plan_components' / 'diag_plan_result.json'


def agent_with_goal(gtype):
    s = VI.configure(Session(3001, 5), 'interest')
    s.apply({'kind': 'object', 'value': 'book'})
    a = s.agent
    a.hunger, a.energy, a.condition = 30.0, 80.0, 100.0
    a.goal = {'type': gtype, 'priority': 1.0, 'created_day': 0, 'start': 0}
    return a


def test_switches_off_for_every_rule_version():
    assert RULES == 5
    for rules in range(1, 7):
        a = Session(rules=rules).agent
        assert not (a.goal_read_offtask_off or a.goal_read_learn_bonus_off)


@pytest.mark.parametrize('gtype', ['learn', 'see_the_world', 'improve_home', 'stock_food', 'recover'])
def test_each_switch_changes_only_its_part_on_read(gtype):
    a = agent_with_goal(gtype)
    base = {x: a.goal_bonus(x) for x in engine.core.ACTIONS}
    assert (base['read'] > 0) == (gtype == 'learn') and base['read'] != 0
    for flag, hits in (('goal_read_offtask_off', gtype != 'learn'), ('goal_read_learn_bonus_off', gtype == 'learn')):
        b = copy.deepcopy(a)
        setattr(b, flag, True)
        assert b.goal_bonus('read') == (0.0 if hits else base['read'])
        assert all(b.goal_bonus(x) == base[x] for x in engine.core.ACTIONS if x != 'read')


def test_both_switches_reproduce_goal_read_bonus_off():
    x = VI.book_pet(6010, 'interest', VI.CLEAR)
    y = copy.deepcopy(x)
    x.agent.goal_read_bonus_off = True
    y.agent.goal_read_offtask_off = y.agent.goal_read_learn_bonus_off = True
    VR.run_hours(x, 20 * 24)
    VR.run_hours(y, 20 * 24)
    assert behavior_digest(x) == behavior_digest(y) and x.agent.rng.getstate() == y.agent.rng.getstate()


def test_recorded_result_follows_the_fixed_rule():
    r = json.loads(RESULT.read_text(encoding='utf-8'))
    v, S = r['verdict'], r['summary']
    assert S['checks'] == {'current_rep0_is_round4': True, 'both_is_goal_read_bonus_off': True}
    D = S['paired_vs_current']['both']['gap_state_all']
    assert v['R0_replicated'] is (D['mean'] > 0 and D['ci95'][0] > 0) is False
    assert v['conclusion'] == 'not replicated: no component conclusion'
    assert set(v['components'].values()) == {'not evaluated (R0 failed)'}
    assert all(s['pass'] == s['unique_trajectories'] for s in S['safety'].values())
    assert RV.seeds_used_only_by_this_validation() and VI.VALIDATION_SEEDS[0] == 7041   # round 9: used once, by the foresight validation
