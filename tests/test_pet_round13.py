"""Round 13 of 2026-10-25 (diagnostics, NOT a rule version): plan-cycle switches, the A entry on top of B2 and
the pure social trace (pet/diag_round13.py)."""
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import diag_round13 as DR
from pet import validate_read as VR
from pet import validate_social as VS
from pet import validate_social_b2 as VB
from pet.engine import core
from make_rules_baseline_v5 import behavior_digest


@pytest.fixture(autouse=True)
def patched():
    saved = (VS.new_pet, VS.ARMS, VS.CATALOGUE_ARMS, VS.CANDIDATE, VS.FROZEN)
    yield
    VS.new_pet, VS.ARMS, VS.CATALOGUE_ARMS, VS.CANDIDATE, VS.FROZEN = saved


def lived(make, days=30):
    s = make()
    s.apply({'kind': 'object', 'value': 'book'})
    s.apply({'kind': 'object', 'value': 'garden'})
    VR.run_hours(s, days * 24, invite_daily=True)
    return s


def test_switches_off_is_B2_exactly():
    VB.patch()
    x = lived(lambda: VB.new_pet(3001, 'B2'))
    DR.patch()
    y = lived(lambda: DR.new_pet(3001, 'B2'))
    assert behavior_digest(x) == behavior_digest(y) and x.agent.rng.getstate() == y.agent.rng.getstate()
    a = DR.DiagSession(1, 5).agent
    assert not (a.learn_no_count_close or a.learn_no_done_satiation or a.entry_A or a.social_trace)


def learn_agent(**flags):
    DR.patch()
    s = DR.new_pet(3001, 'B2')
    s.apply({'kind': 'object', 'value': 'book'})
    a = s.agent
    for k, v in flags.items():
        setattr(a, k, v)
    a.goal = a._new_goal('learn', 0.8, 'x', 10)
    a.action_log['read'] += 12                    # the count is reached
    return a


def test_count_close_and_satiation_switches():
    a = learn_agent()
    a._update_goal_ordered(12)
    assert a.goal_history[-1]['outcome'] == 'done' and a.goal_satiation['learn'] == 12
    b = learn_agent(learn_no_done_satiation=True)
    b.goal_satiation['learn'] = 3
    b._update_goal_ordered(12)
    assert b.goal_history[-1]['outcome'] == 'done' and b.goal_satiation['learn'] == 3          # old value kept
    c = learn_agent(learn_no_count_close=True)
    for d in (12, 13, 14, 15):
        c._update_goal_ordered(d)
        if c.goal is None or c.goal['type'] != 'learn':
            break
    assert c.plan_log[0]['event'] == 'count_close_neutralized'
    if c.goal is not None and c.goal['type'] == 'learn':               # not switched meanwhile
        c._update_goal_ordered(16)                                       # 4 days without gain: the stall exit
    closed = [g for g in c.goal_history if g['type'] == 'learn']
    assert closed and closed[-1]['outcome'] in ('stalled', 'switched')
    if closed[-1]['outcome'] == 'stalled':
        assert c.goal_satiation['learn'] == closed[-1]['closed_day']        # stall satiation kept


def test_both_switches_equal_no_close():
    x = learn_agent(learn_no_count_close=True)
    y = learn_agent(learn_no_count_close=True, learn_no_done_satiation=True)
    for d in range(12, 20):
        x._update_goal_ordered(d)
        y._update_goal_ordered(d)
    assert x.goal_history == y.goal_history and x.goal_satiation == y.goal_satiation


def test_entry_A_on_B2_only_changes_the_visit_chance():
    DR.patch()
    s = DR.new_pet(3001, 'B2A')
    a = s.agent
    assert a.entry_A and a.social_entry == 'B2'
    a.s_V, a.s_n, a.s_I, a.shared = 0.9, 40.0, 0.8, [{'id': 1, 'tick': 0}]
    on = a.visit_chance(0.0)[0]
    a.entry_A = False
    off = a.visit_chance(0.0)[0]
    assert on == pytest.approx(min(engine.VISIT_MAX, off + engine.VISIT_PREF * a.social_term()))


def test_social_trace_is_pure():
    DR.patch()
    x = lived(lambda: DR.new_pet(6010, 'B2A'), 25)
    def traced():
        s = DR.new_pet(6010, 'B2A')
        s.agent.social_trace = True
        return s
    y = lived(traced, 25)
    assert behavior_digest(x) == behavior_digest(y) and x.agent.rng.getstate() == y.agent.rng.getstate()
    rows = y.agent.social_rows
    assert rows and all(r['delta'] == pytest.approx(max(r['g'], r['s'] + r['t']) - max(r['g'], r['s'])) for r in rows if r['avail'])
