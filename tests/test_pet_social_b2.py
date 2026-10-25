"""Round 12 of 2026-10-25 (experiment, NOT a rule version): the scope-corrected social entry 'B2'
(pet/social_interest_b2.py) and its run module (pet/validate_social_b2.py)."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import validate_read as VR
from pet import validate_social as VS
from pet import validate_social_b2 as VB
from pet.social_interest_b2 import SocialSessionB2
from make_rules_baseline_v5 import behavior_digest

ARMS = {'ref': {}, 'B': {'entry': 'B'}, 'B2': {'entry': 'B2'}}


def agent(entry, garden=0.3, social=0.2, term=-0.5, hour=10, day=22):
    s = SocialSessionB2(3001, 5)
    saved = VS.ARMS
    VS.ARMS = {**saved, **ARMS}
    try:
        VS.configure(s, {'B2': 'B2', 'B': 'B', None: 'ref'}[entry])
    finally:
        VS.ARMS = saved
    for it in ('book', 'garden'):
        s.apply({'kind': 'object', 'value': it})
    a = s.agent
    a.prefs.update(garden=garden, social=social)
    a.hunger, a.energy, a.shelter, a.condition = 30.0, 80.0, 60.0, 100.0
    a.shared = [{'id': 1, 'tick': 0}]
    a.now = day * 24 + hour
    a.social_term = lambda: term
    return a, day


def free_day():
    a, _ = agent('B2')
    return next(d for d in range(22, 60) if a.neighbor_status(d, 10) == engine.NEIGHBOR_FREE)


@pytest.mark.parametrize('garden,social', [(0.3, 0.2), (0.2, 0.3), (0.0, 0.0)])
def test_negative_social_never_lowers_the_garden_option(garden, social):
    d = free_day()
    b2, _ = agent('B2', garden, social, -0.5, day=d)
    ref, _ = agent(None, garden, social, -0.5, day=d)
    assert b2.can_meet(d, 10, False)
    G = b2.need_gate() * (1 - b2.home_need())
    g, s = engine.PREF_WEIGHT * garden * G, engine.PREF_WEIGHT * social * G
    garden_only = ref.score('explore', d) - max(g, s) + g
    assert b2.score('explore', d) >= garden_only - 1e-9
    if g >= s:
        assert b2.score('explore', d) == pytest.approx(ref.score('explore', d))
    old, _ = agent('B', garden, social, -0.5, day=d)
    assert old.score('explore', d) < garden_only                    # round 11's B did lower it


def test_formula_and_positive_term():
    d = free_day()
    b2, _ = agent('B2', 0.3, 0.2, 0.4, day=d)
    ref, _ = agent(None, 0.3, 0.2, 0.4, day=d)
    G = b2.need_gate() * (1 - b2.home_need())
    g, s, t = (engine.PREF_WEIGHT * 0.3 * G, engine.PREF_WEIGHT * 0.2 * G, engine.READ_VALUE_WEIGHT * 0.4 * G)
    assert b2.score('explore', d) - ref.score('explore', d) == pytest.approx(max(g, s + t) - max(g, s))
    assert b2.score('read', d) == pytest.approx(ref.score('read', d))


def test_no_availability_no_effect():
    d = free_day()
    b2, _ = agent('B2', 0.1, 0.3, 0.5, hour=22, day=d)              # off hours
    ref, _ = agent(None, 0.1, 0.3, 0.5, hour=22, day=d)
    assert b2.social_option_delta('explore', d) == 0.0 and b2.score('explore', d) == pytest.approx(ref.score('explore', d))
    b2.shared = []                                                    # never met: no social option either
    b2.now = d * 24 + 10
    assert b2.social_option_delta('explore', d) == 0.0


def test_visit_chance_unchanged():
    d = free_day()
    b2, _ = agent('B2', 0.3, 0.6, 0.5, day=d)
    ref, _ = agent(None, 0.3, 0.6, 0.5, day=d)
    assert b2.visit_chance(1.0) == ref.visit_chance(1.0)


def test_zero_term_reproduces_the_reference():
    VB.patch()
    try:
        x, y = VB.new_pet(3001, 'ref'), VB.new_pet(3001, 'B2')
    finally:
        import importlib
        importlib.reload(VS)
    y.agent.social_term = lambda: 0.0
    for s in (x, y):
        s.apply({'kind': 'object', 'value': 'book'})
        s.apply({'kind': 'object', 'value': 'garden'})
        VR.run_hours(s, 30 * 24, invite_daily=True)
    assert behavior_digest(x) == behavior_digest(y) and x.agent.rng.getstate() == y.agent.rng.getstate()


def test_old_B_through_the_new_class_is_round11_B():
    x = VS.new_pet(3001, 'B')                                         # round 11's own class
    VB.patch()
    try:
        y = VB.new_pet(3001, 'B')
    finally:
        import importlib
        importlib.reload(VS)
    for s in (x, y):
        s.apply({'kind': 'object', 'value': 'book'})
        s.apply({'kind': 'object', 'value': 'garden'})
        VR.run_hours(s, 25 * 24, invite_daily=True)
    assert behavior_digest(x) == behavior_digest(y)
