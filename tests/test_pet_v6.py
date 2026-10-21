"""Candidate rules 6 (NOT adopted, 2026-10-21): the neighbor rests 4 h after each shared
activity, and a run-down home may end a leisure plan early (pet/validate_v6.py, PET_VALIDATION.md).

It passed the home and social criteria on fresh seeds but missed the pre-set reading criterion,
so the default stays v5. These tests keep the candidate reproducible and v5 untouched.
"""
import copy
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet.engine import LEISURE_GOALS, RULES, Session

CANDIDATE = 6
from make_rules_baseline_v5 import _h, behavior_digest, explanation_records

BASELINE_V5_LONG = json.loads((ROOT / 'tests' / 'fixtures' / 'rules_baseline_v5_long.json').read_text(encoding='utf-8'))
APP = (ROOT / 'pet' / 'static' / 'app.js').read_text(encoding='utf-8')


def pet(seed=42, items=('garden',), invite=True, rules=CANDIDATE):
    s = Session(seed, rules)
    for item in items:
        s.apply({'kind': 'object', 'value': item})
    if invite:
        s.apply({'kind': 'invite', 'value': None})
    return s


def lowest_home(s, hours):
    low = s.agent.shelter
    for _ in range(hours):
        s.step()
        low = min(low, s.agent.shelter)
    return low


# ---------------------------------------------------------------- versions and replay
def test_candidate_is_not_offered_to_players():
    assert RULES == 5 and Session().archive()['version'] == 5
    with pytest.raises(ValueError):                      # no save can be on the candidate rules
        Session.restore({'version': CANDIDATE, 'seed': 42, 'commands': []})
    assert not (ROOT / 'start_pet_v6.bat').exists()


def test_candidate_sets_its_rules():
    a = Session(rules=CANDIDATE).agent
    assert (a.visit_cap, a.visit_rest_hours, a.home_interrupt) == (None, engine.V6_REST_HOURS, True)
    old = Session(rules=5).agent
    assert (old.visit_cap, old.visit_rest_hours, old.home_interrupt) == (engine.MILI_VISITS_PER_DAY, 0, False)


@pytest.mark.parametrize('case', BASELINE_V5_LONG, ids=lambda c: f"v5long-seed{c['archive']['seed']}-{c['scenario']}")
def test_v5_saves_replay_exactly_as_the_pre_v6_engine_did(case):
    # 60-day v5 plays written by the engine from before the v6 round; they pass the home dips.
    s = Session.restore(copy.deepcopy(case['archive']))
    assert s.rules == 5
    assert behavior_digest(s) == case['behavior']
    assert _h(explanation_records(s)) == case['explanation']


def test_v5_save_resumed_midway_continues_identically():
    case = BASELINE_V5_LONG[3]
    cut = len(case['archive']['commands']) // 2
    half = Session.restore({**case['archive'], 'commands': case['archive']['commands'][:cut]})
    resumed = Session.restore(json.loads(json.dumps(half.archive())))
    for command in case['archive']['commands'][cut:]:
        resumed.apply(command)
    assert behavior_digest(resumed) == case['behavior']


# ---------------------------------------------------------------- home interrupt
def leisure_planner(rules):
    """A pet with a fresh leisure plan, still inside the core's GOAL_MIN_DAYS lock."""
    s = pet(42, ('garden', 'book'), rules=rules)
    # The core forms goals in daily(day) as day `day` ends, so at tick 24*(day+1).
    for _ in range(60 * 24):
        s.step()
        if (s.tick % 24 == 0 and s.agent.goal and s.agent.goal['type'] in LEISURE_GOALS
                and s.agent.goal['created_day'] == s.tick // 24 - 1):
            return s
    raise AssertionError('no fresh leisure plan in 60 days')


def test_run_down_home_ends_a_leisure_plan_early():
    s = leisure_planner(6)
    a, day = s.agent, s.tick // 24                       # next morning: the plan is 1 day old
    a.shelter = 5.0
    plan, rng = a.goal['type'], a.rng.getstate()
    a.update_goal(day)
    assert a.goal['type'] == 'improve_home'
    assert a.goal_history[-1]['type'] == plan and a.goal_history[-1]['outcome'] == 'switched'
    assert a.rng.getstate() == rng                       # deciding draws no random number


def test_v5_keeps_the_locked_leisure_plan():
    s = leisure_planner(5)
    a, day = s.agent, s.tick // 24
    a.shelter = 5.0
    plan = a.goal['type']
    a.update_goal(day)
    assert a.goal['type'] == plan                        # the bug v6 fixes stays reproducible in v5


def test_interrupt_needs_the_core_switch_margin():
    s = leisure_planner(6)
    a, day = s.agent, s.tick // 24
    a.shelter = engine.HOME_CARE_FROM + 5                # no felt need: improve_home not clearly ahead
    plan = a.goal['type']
    a.update_goal(day)
    assert a.goal['type'] == plan


def test_interrupt_waits_until_the_home_is_really_low():
    # v6a cut plans at any felt need and nearly erased reading; v6 waits for HOME_INTERRUPT_BELOW.
    s = leisure_planner(6)
    a, day = s.agent, s.tick // 24
    a.shelter = engine.HOME_INTERRUPT_BELOW + 1
    plan = a.goal['type']
    pri = {g: p for g, p, _ in a.propose_goals(day)}
    assert pri['improve_home'] >= pri[plan] + engine.core.GOAL_SWITCH_MARGIN   # only the level holds it back
    a.update_goal(day)
    assert a.goal['type'] == plan


def test_interrupt_never_ends_a_need_goal():
    s = leisure_planner(6)
    a, day = s.agent, s.tick // 24
    a.goal = a._new_goal('stock_food', 0.5, 'test', day)
    a.shelter = 5.0
    a.update_goal(day + 1)
    assert a.goal['type'] == 'stock_food'                # only learn / see_the_world can be cut short


def test_interrupt_is_what_closes_the_rest_rule_home_gap():
    # The 2026-10-17 blocker: the rest rule without the interrupt let seed 42 (garden) fall to 2.9.
    without = pet(42)
    without.agent.home_interrupt = False
    assert lowest_home(without, 60 * 24) < 3
    assert lowest_home(pet(42), 60 * 24) >= 3


# ---------------------------------------------------------------- neighbor rest
def test_v6_neighbor_rests_instead_of_a_daily_cap():
    s = pet(42)
    for _ in range(30 * 24):
        s.step()
    reasons = {e.get('neighbor') for e in s.events if e.get('action') == 'garden'}
    assert 'rest' in reasons and 'full' not in reasons
    visits = [e['tick'] for e in s.events if e.get('action') == 'visit' and not e['invited']]
    assert visits and all(b - a > engine.V6_REST_HOURS - 1 for a, b in zip(visits, visits[1:]))
    for e in s.events:
        if e.get('neighbor') == 'rest':
            assert e['text'] == engine.NEIGHBOR_TEXT['rest']


def test_invitations_still_skip_the_rest_but_not_off_hours():
    a = pet(42).agent
    day = next(d for d in range(50) if random.Random(42 * 100003 + d).random() >= engine.MILI_AWAY_CHANCE)
    a.shared = [{'id': 1, 'tick': day * 24 + 9}]
    assert a.neighbor_status(day, 11) == 'rest' and a.neighbor_status(day, 13) == 'free'
    assert a.neighbor_status(day, 11, invited=True) == 'free'
    assert a.neighbor_status(day, 21, invited=True) == 'off_hours'


# ---------------------------------------------------------------- page
def test_page_describes_the_neighbor_rule_of_each_version():
    # Ready for the rest rule if a later version adopts it; v1-v5 pages keep the daily-cap text.
    assert APP.count('start_pet_v5.bat') == 2 and 'start_pet_v6.bat' not in APP
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js not installed; static checks above still ran')
    start = APP.index('const hh=')
    block = APP[start:APP.index('\n};', APP.index('const UI={')) + 3]
    script = block + 'console.log(JSON.stringify([5,6].flatMap(r=>[UI.zh.neighborRules(r),UI.es.neighborRules(r)])));'
    zh5, es5, zh6, es6 = json.loads(subprocess.run([node, '-e', script], capture_output=True, text=True,
                                                   encoding='utf-8', check=True).stdout)
    assert '两次' in zh5 and 'dos visitas' in es5
    assert '4 小时' in zh6 and '4 horas' in es6 and '两次' not in zh6 and 'dos visitas' not in es6
