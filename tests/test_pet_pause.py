"""Experiment 'pause' (2026-10-23, NOT adopted as a rule version): an urgent repair stashes a
leisure plan instead of ending it, and the plan is re-weighed once the emergency is over
(pet/validate_pause.py). Also the 2026-10-23 statistics fix of pet/validate_v6.py
(pet/lifestats.py). These tests pin the mechanism's rules and keep v1-v6 untouched.
"""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import lifestats as L
from pet import validate_pause as VP
from pet import validate_v6 as V6
from pet import validate_v5_social as vs
from pet.engine import LEISURE_GOALS, RULES, Session, core
from make_rules_baseline_v5 import _h, behavior_digest, explanation_records

BASELINE_V6 = json.loads((ROOT / 'tests' / 'fixtures' / 'rules_baseline_v6.json').read_text(encoding='utf-8'))
OTHER = {'learn': 'see_the_world', 'see_the_world': 'learn'}


def pet(seed=42, arm='pause_rest4', items=('garden', 'book'), traced=False):
    s = (L.TracedSession if traced else Session)(seed, 5)
    VP.configure(s, arm)
    for item in items:
        s.apply({'kind': 'object', 'value': item})
    s.apply({'kind': 'invite', 'value': None})
    return s


def planner(arm='pause_rest4'):
    """Next morning of a fresh leisure plan (1 day old, still in the core's GOAL_MIN_DAYS lock)."""
    s = pet(arm=arm)
    for _ in range(60 * 24):
        s.step()
        if (s.tick % 24 == 0 and s.agent.goal and s.agent.goal['type'] in LEISURE_GOALS
                and s.agent.goal['created_day'] == s.tick // 24 - 1):
            return s, s.agent, s.tick // 24
    raise AssertionError('no fresh leisure plan in 60 days')


def fixed(a, pri):
    """Stub the goal proposals so a test controls which goal is best."""
    a.propose_goals = lambda day: [(g, p, 'test') for g, p in pri.items()]


def paused():
    s, a, day = planner()
    a.shelter = 5.0
    a.update_goal(day)
    assert a.paused_goal is not None
    return s, a, day, a.paused_goal['goal']


def untouched(a):
    return (a.rng.getstate(), len(a.memories), dict(a.goal_satiation))


# ---------------------------------------------------------------- not a rule version
def test_pause_is_an_experiment_never_a_save_version():
    assert RULES == 5 and Session().archive()['version'] == 5
    for rules in range(1, 7):
        a = Session(rules=rules).agent
        assert a.goal_pause is False and a.interrupt_open_only is False and a.paused_goal is None
    assert VP.CANDIDATE in VP.ARMS and VP.ARMS[VP.CANDIDATE] == ('rest4', 'pause')
    assert not (ROOT / 'start_pet_v7.bat').exists()


@pytest.mark.parametrize('case', BASELINE_V6, ids=lambda c: f"v6-seed{c['seed']}-{c['scenario']}-{c['scheme']}")
def test_v6_candidate_replays_as_the_engine_before_this_round(case):
    # Baseline written by commit 2fab702's engine (tests/fixtures/make_rules_baseline_v6.py).
    s = Session(case['seed'], 6)
    if case['scheme'] == 'cap2':
        s.agent.visit_cap, s.agent.visit_rest_hours = engine.MILI_VISITS_PER_DAY, 0
    for command in case['commands']:
        s.apply(command)
    assert behavior_digest(s) == case['behavior']
    assert _h(explanation_records(s)) == case['explanation'] and _h(s.agent.goal_history) == case['goal_history']


def test_v6_arm_is_the_v6_candidate():
    for seed in (42, 3008):
        a, b = pet(seed, 'v6'), Session(seed, 6)
        for item in ('garden', 'book'):
            b.apply({'kind': 'object', 'value': item})
        b.apply({'kind': 'invite', 'value': None})
        for _ in range(60 * 24):
            a.step()
            b.step()
        assert behavior_digest(a) == behavior_digest(b)


@pytest.mark.parametrize('arm', ['v5', 'v6', 'pause_rest4', 'end_open_cap2'])
def test_diagnostics_change_no_behavior_and_draw_no_number(arm):
    runs = []
    for diag in (False, True):
        s = pet(3001, arm)
        s.agent.diagnostics = diag
        for _ in range(60 * 24):
            s.step()
        runs.append(s)
    assert behavior_digest(runs[0]) == behavior_digest(runs[1])
    real = lambda s: [e for e in s.agent.plan_log if e['event'] != 'trigger_kept']
    assert real(runs[0]) == real(runs[1])
    if arm == 'v5':
        assert not real(runs[0]) and runs[1].agent.plan_log      # v5 only logs, never acts


# ---------------------------------------------------------------- pause
def test_pause_stashes_the_plan_without_any_outcome():
    s, a, day = planner()
    g, n_hist, before = a.goal, len(a.goal_history), None
    before = untouched(a)
    a.shelter = 5.0
    a.update_goal(day)
    P = a.paused_goal
    assert a.goal['type'] == 'improve_home' and P['goal'] is g
    assert (P['day'], P['reason'], P['progress']) == (day, 'home_low', a.goal_progress(g))
    assert g['plan_id'] == f"{g['type']}@{g['created_day']}"
    assert len(a.goal_history) == n_hist                 # no done / stalled / switched record
    assert untouched(a) == before                        # no memory, satiation or random draw
    assert a.plan_log[-1]['event'] == 'paused'


def test_v5_and_v6_keep_their_recorded_rules():
    s, a, day = planner('v5')
    plan = a.goal['type']
    a.shelter = 5.0
    a.update_goal(day)
    assert a.goal['type'] == plan and a.paused_goal is None
    s, a, day = planner('v6')
    plan = a.goal['type']
    a.shelter = 5.0
    a.update_goal(day)
    assert a.goal_history[-1]['type'] == plan and a.goal_history[-1]['outcome'] == 'switched' and a.paused_goal is None


@pytest.mark.parametrize('arm,expected', [('pause_rest4', 'done'), ('end_open_rest4', 'done'), ('v6', 'switched')])
def test_a_finished_plan_is_closed_by_the_core_not_paused(arm, expected):
    # v6 ends it as 'switched' (no 'done' memory, no satiation): kept as recorded, measured.
    s, a, day = planner(arm)
    act, target = a.GOAL_COUNT_TARGET[a.goal['type']]
    a.action_log[act] = a.goal['start'] + target
    a.shelter = 5.0
    a.update_goal(day)
    assert a.goal_history[-1]['outcome'] == expected and a.paused_goal is None


def test_a_stalled_plan_is_closed_by_the_core_not_paused():
    s, a, day = planner()
    g = a.goal
    g['best_progress'], g['last_gain_day'] = a.goal_progress(g), day - core.GOAL_STALL_DAYS
    a.shelter = 5.0
    a.update_goal(day)
    assert a.goal_history[-1]['outcome'] == 'stalled' and a.paused_goal is None


def test_pause_keeps_the_v6_trigger():
    s, a, day = planner()
    a.shelter = engine.HOME_INTERRUPT_BELOW + 1          # same level rule as v6
    plan = a.goal['type']
    a.update_goal(day)
    assert a.goal['type'] == plan and a.paused_goal is None
    s, a, day = planner()
    fixed(a, {a.goal['type']: 0.6, 'improve_home': 0.6 + core.GOAL_SWITCH_MARGIN - 1e-6})
    a.shelter = 5.0
    a.update_goal(day)                                   # margin not met: nothing happens
    assert a.paused_goal is None


def test_resume_freezes_progress_and_shifts_age_and_stall_clock():
    s, a, day, g = paused()
    typ = g['type']
    act = a.GOAL_COUNT_TARGET[typ][0]
    progress, created, gain = a.paused_goal['progress'], g['created_day'], g.get('last_gain_day')
    a.action_log[act] += 3                               # done while paused: not the plan's progress
    a.shelter = 60.0
    fixed(a, {typ: 0.9, 'improve_home': 0.3})
    before = untouched(a)
    a.update_goal(day + 1)                               # repair goal still in GOAL_MIN_DAYS: kept by the core
    assert a.goal is g and a.paused_goal is None and untouched(a) == before
    assert a.goal_history[-1]['type'] == 'improve_home' and a.goal_history[-1]['outcome'] == 'switched'
    assert a.goal_progress(g) == progress and g['priority'] == 0.9           # fresh priority
    assert g['created_day'] == created + 1 and g['resumes'] == 1 and g['paused_days'] == 1
    if gain is not None:
        assert g['last_gain_day'] == gain + 1
    a.update_goal(day + 2)                               # no false 'stalled' right after resuming
    assert a.goal is g


def test_resume_replaces_a_same_type_plan_the_core_formed_this_morning():
    s, a, day, g = paused()
    a.shelter = 60.0
    fixed(a, {g['type']: 0.9, 'improve_home': 0.3})
    a.update_goal(day + 2)                               # the core itself switches today
    assert a.goal is g and a.plan_log[-1]['event'] == 'resumed'


def test_waits_while_the_home_is_below_the_resume_level():
    s, a, day, g = paused()
    a.shelter = engine.PAUSE_RESUME_AT - 1               # above 15: hysteresis, no flip-flop
    fixed(a, {g['type']: 0.9, 'improve_home': 0.3})
    a.update_goal(day + 1)
    assert a.paused_goal['goal'] is g and a.plan_log[-1]['event'] == 'waiting'


@pytest.mark.parametrize('need', ['recover', 'stock_food', 'improve_home'])
def test_body_and_home_needs_come_first(need):
    s, a, day, g = paused()
    a.shelter = 60.0
    fixed(a, {need: 1.2, g['type']: 0.5})
    a.update_goal(day + 1)
    assert a.paused_goal['goal'] is g and a.plan_log[-1]['reason'] == need


@pytest.mark.parametrize('case', ['replaced', 'expired', 'invalid'])
def test_a_stashed_plan_can_be_dropped_without_an_outcome(case):
    s, a, day, g = paused()
    a.shelter = 60.0
    when = day + 1
    if case == 'replaced':
        fixed(a, {OTHER[g['type']]: 1.0, g['type']: 0.5})
    elif case == 'expired':
        fixed(a, {g['type']: 0.9})
        when = day + engine.PAUSE_MAX_DAYS + 1
    else:
        fixed(a, {'improve_home': 0.4})                  # e.g. the book is gone: no 'learn' proposal
    n_hist, before = len(a.goal_history), untouched(a)
    a.update_goal(when)
    assert a.paused_goal is None and a.plan_log[-1]['event'] == 'dropped' and a.plan_log[-1]['reason'] == case
    assert all(h.get('plan_id') != g['plan_id'] for h in a.goal_history[n_hist:])
    assert untouched(a) == before


def test_repeated_interrupts_end_the_plan_after_the_resume_limit():
    s, a, day = planner()
    a.goal['resumes'] = engine.PAUSE_MAX_RESUMES
    a.shelter = 5.0
    a.update_goal(day)
    assert a.paused_goal is None and a.goal_history[-1]['outcome'] == 'switched'
    assert a.plan_log[-1]['event'] == 'ended' and a.plan_log[-1]['reason'] == 'resume_limit'


def test_at_most_one_stashed_plan():
    s, a, day, g = paused()
    a.goal = a._new_goal(OTHER[g['type']], 0.5, 'test', day + 1)
    a.shelter = 5.0
    fixed(a, {'improve_home': 1.5, a.goal['type']: 0.5, g['type']: 0.4})
    a.update_goal(day + 2)
    assert a.paused_goal['goal']['type'] == OTHER[g['type']]
    assert [e['reason'] for e in a.plan_log if e['event'] == 'dropped'] == ['superseded']


@pytest.mark.parametrize('seed,route,fate', [(6003, 'control', 'resumed_then_done'), (3002, 'garden', 'dropped_replaced')])
def test_lived_pause_episodes_have_a_traceable_fate(seed, route, fate):
    # Dev lives with a lived pause (development sample only): one resumed, one given up.
    rec = VP.route_life(seed, route, 'pause_rest4')
    fates = rec['plan_fates']
    assert fates and all(p['fate'] != 'unknown' for p in fates.values())
    assert fate in {p['fate'] for p in fates.values()}
    assert all(p['pauses'] <= engine.PAUSE_MAX_RESUMES + 1 and p['repause_within_2d'] == 0 for p in fates.values())
    for e in rec['episodes']:
        assert e['status'] in ('related_action', 'no_related_action', 'not_repaired')
        assert (e['wait'] is None) == (e['status'] != 'related_action')


# ---------------------------------------------------------------- whole-life statistics
def test_whole_life_metrics_come_from_raw_counts():
    s = pet(42, 'v6', traced=True)
    for _ in range(20 * 24):
        s.step()
    s.phase('common')
    for _ in range(30 * 24):
        s.step()
    rec = L.life_record(s, life_id='t')
    g, c, w = rec['phases']['growth'], rec['phases']['common'], rec['whole']
    assert w['hours'] == g['hours'] + c['hours'] == 50 * 24
    for k in set(g['counts']) | set(c['counts']):
        assert w['counts'][k] == g['counts'].get(k, 0) + c['counts'].get(k, 0)
    assert w['upkeep'] == (w['counts'].get('gather_material', 0) + w['counts'].get('build', 0)) / w['hours']
    assert w['min_home'] == min(g['min_home'], c['min_home']) and w['below20_hours'] == g['below20_hours'] + c['below20_hours']
    tail = {r[1] for r in s.trace[-7 * 24:]}
    assert w['kinds_last_week'] == len(tail)             # the life's real last week


def test_the_old_82_lives_held_duplicate_trajectories():
    a = V6.social_route_job((6001, 'garden', 'rest4'))
    b = V6.v5_route_job((6001, 'garden', 6))
    assert a['fingerprint'] == b['fingerprint']           # same life counted twice before 2026-10-23
    u = L.dedupe([a, b])
    assert len(u) == 1 and u[0]['runs'] == [a['life_id'], b['life_id']]


def test_traced_social_design_reproduces_validate_v5_social(monkeypatch):
    # Same copies, same random streams, same results; probes stubbed (they only read copies).
    monkeypatch.setattr(vs, 'probe', lambda points: {'n': len(points)})
    monkeypatch.setattr(vs, 'probe_points', lambda s, days: [len(vs.live(s, days))])
    monkeypatch.setattr(vs, 'REPS', 2)
    plain = vs.run_seed(3002)
    traced, lives = V6.run_seed_traced(3002)
    assert json.dumps(plain, sort_keys=True, default=str) == json.dumps(traced, sort_keys=True, default=str)
    assert {m['design'] for m in lives} == {'S_probe_path', 'S_withdrawal', 'S_full_route', 'S_full_pair'}
    wd = [m for m in lives if m['design'] == 'S_withdrawal']
    assert all({'growth', 'intervention', 'washout', 'withdrawal'} <= set(m['phases']) for m in wd)


def test_describe_keeps_unrounded_values_and_missing_seeds():
    d = L.describe([0.0049, None, -0.001])
    assert d['mean'] == (0.0049 - 0.001) / 2 and d['missing'] == 1 and d['positive'] == 1 and d['negative'] == 1


# ---------------------------------------------------------------- samples and criteria
def test_validation_seeds_are_new_and_criteria_fixed():
    used = set(VP.DEV_SEEDS) | set(V6.VALIDATION_SEEDS) | set(V6.SPENT_SEEDS) | set(vs.VALIDATION_SEEDS) \
        | set(vs.DEV_SEEDS) | set(engine_validation_seeds()) | set(VP.SAFE_SEEDS)
    assert not set(VP.VALIDATION_SEEDS) & used and len(VP.VALIDATION_SEEDS) == 20
    assert VP.CRITERIA is not None and VP.CRITERIA['reference'] == 'v6'


def engine_validation_seeds():
    from pet import validate_v5 as v5
    return v5.DEV_SEEDS + v5.VALIDATION_SEEDS
