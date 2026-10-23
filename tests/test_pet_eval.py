"""Round 2026-10-24 (NOT adopted as a rule version): phase A base with goal endings in order
plus one home-emergency rule, and the experiment 'evaluation' (activity evaluation Q for read
and garden). pet/validate_eval.py, PET_VALIDATION.md. These tests pin both mechanisms and keep
v1-v6 untouched (their replays are pinned in test_pet_v4 / v5 / v6 / pause)."""
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import validate_eval as VE
from pet import validate_pause as VP
from pet import validate_v6 as V6
from pet.engine import LEISURE_GOALS, RULES, Session, core
from make_rules_baseline_v5 import behavior_digest


def pet(arm='base', seed=42, items=('garden', 'book')):
    s = VE.configure(Session(seed, 5), arm)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    s.apply({'kind': 'invite', 'value': None})
    return s


def planner(arm='base'):
    """Next morning of a fresh leisure plan (1 day old)."""
    s = pet(arm)
    for _ in range(60 * 24):
        s.step()
        if (s.tick % 24 == 0 and s.agent.goal and s.agent.goal['type'] in LEISURE_GOALS
                and s.agent.goal['created_day'] == s.tick // 24 - 1):
            return s, s.agent, s.tick // 24
    raise AssertionError('no fresh leisure plan')


def finish(a):
    act, target = a.GOAL_COUNT_TARGET[a.goal['type']]
    a.action_log[act] = a.goal['start'] + target


# ---------------------------------------------------------------- not a rule version
def test_new_flags_are_off_for_every_rule_version():
    assert RULES == 5
    for rules in range(1, 7):
        a = Session(rules=rules).agent
        assert not (a.ordered_goals or a.home_emergency_unmute or a.evaluation)
    assert VE.CANDIDATE == 'eval' and VE.CONTROL == 'base' and not (ROOT / 'start_pet_v7.bat').exists()


def test_validation_seeds_new_and_criteria_fixed():
    used = set(VE.DEV_SEEDS) | set(VP.VALIDATION_SEEDS) | set(VP.DEV_SEEDS) | set(V6.VALIDATION_SEEDS) | set(V6.SPENT_SEEDS)
    assert not set(VE.VALIDATION_SEEDS) & used and len(VE.VALIDATION_SEEDS) == 20
    assert VE.CRITERIA is not None and VE.DEV_DECISION['sent_to_validation'] is False
    assert set(VE.VALIDATION_ARMS) == {'v5', 'v6', 'base'}


# ---------------------------------------------------------------- phase A: endings in order
def test_a_finished_plan_ends_done_once_even_under_the_home_trigger():
    s, a, day = planner('base')
    plan = a.goal['type']
    finish(a)
    a.shelter = 5.0
    rng, n = a.rng.getstate(), len(a.goal_history)
    a.update_goal(day)
    closed = a.goal_history[n:]
    assert [(g['type'], g['outcome']) for g in closed] == [(plan, 'done')]      # not 'switched', once
    assert a.goal_satiation[plan] == day and a.memories[-1]['tags'][-1] == 'done'
    assert a.goal['type'] == 'improve_home' and a.rng.getstate() == rng


def test_v6_keeps_ending_finished_plans_as_switched():
    s, a, day = planner('v6')
    finish(a)
    a.shelter = 5.0
    a.update_goal(day)
    assert a.goal_history[-1]['outcome'] == 'switched'                          # as recorded


def test_a_really_stalled_plan_ends_stalled():
    s, a, day = planner('base')
    g = a.goal
    g['best_progress'], g['last_gain_day'] = a.goal_progress(g), day - core.GOAL_STALL_DAYS
    a.update_goal(day)
    assert a.goal_history[-1]['outcome'] == 'stalled' and a.goal_satiation[g['type']] == day


def test_only_an_open_plan_is_switched_by_the_trigger():
    s, a, day = planner('base')
    plan = a.goal['type']
    a.shelter = 5.0
    a.update_goal(day)
    assert a.goal_history[-1]['type'] == plan and a.goal_history[-1]['outcome'] == 'switched'
    assert a.goal['type'] == 'improve_home'


def test_candidates_are_re_proposed_after_an_ending():
    # The core picked the next goal from priorities of BEFORE the ending: a plan finished this
    # morning had no satiation yet and could be re-picked at once. Here the satiation counts.
    s, a, day = planner('base')
    plan = a.goal['type']
    other = 'see_the_world' if plan == 'learn' else 'learn'
    finish(a)
    a.shelter = 70.0
    a.propose_goals = lambda d: [(plan, 1.0 - a._satiation(plan, d), 't'), (other, 0.5, 't')]
    a.update_goal(day)
    assert a.goal['type'] == other                       # 1.0 - 0.9 < 0.5
    s2, b, day2 = planner('ordered_only')
    b.ordered_goals = False                              # the core order, for comparison
    plan2 = b.goal['type']
    finish(b)
    b.shelter = 70.0
    other2 = 'see_the_world' if plan2 == 'learn' else 'learn'
    b.propose_goals = lambda d: [(plan2, 1.0 - b._satiation(plan2, d), 't'), (other2, 0.5, 't')]
    b.update_goal(day2)
    assert b.goal['type'] == plan2                       # re-picked the same morning


def test_every_goal_ends_once_in_a_long_life():
    s = pet('base', 6008)
    for _ in range(80 * 24):
        s.step()
    ids = [(g['type'], g['created_day']) for g in s.agent.goal_history]
    assert len(ids) == len(set(ids))


def test_home_emergency_lifts_only_the_repair_satiation():
    s, a, day = planner('base')
    a.goal_satiation['improve_home'] = day - 1
    a.shelter = engine.HOME_INTERRUPT_BELOW - 1
    low = {g: p for g, p, _ in a.propose_goals(day)}
    a.home_emergency_unmute = False
    muted = {g: p for g, p, _ in a.propose_goals(day)}
    assert low['improve_home'] == pytest.approx(muted['improve_home'] + a._satiation('improve_home', day))
    assert {g: p for g, p in low.items() if g != 'improve_home'} == {g: p for g, p in muted.items() if g != 'improve_home'}
    a.home_emergency_unmute = True
    a.shelter = engine.HOME_INTERRUPT_BELOW + 1
    a2 = {g: p for g, p, _ in a.propose_goals(day)}
    a.home_emergency_unmute = False
    assert a2 == {g: p for g, p, _ in a.propose_goals(day)}                     # no effect above the level


@pytest.mark.parametrize('seed,design', [(7009, 'route_social'), (6008, 'plastic_stay'), (6009, 'plastic_away')])
def test_known_home_failures_are_fixed_by_the_base(seed, design):
    if design.startswith('route'):
        s = VE.grow(seed, 'social', 'base')
        VE.run_hours(s, VE.COMMON * 24)
    else:
        s = VE.grow(seed, 'reading', 'base')
        VE.run_hours(s, VE.PL_COMMON * 24)
        VE.run_hours(s, VE.PL_AWAY * 24, invite_daily=design.endswith('away'))
        VE.run_hours(s, VE.PL_AFTER * 24)
    homes = [r[3] for r in s.trace]
    assert min(homes) >= 3 and sum(h < 20 for h in homes) / len(homes) <= 0.08


# ---------------------------------------------------------------- phase B: evaluation
def lived_eval(arm='eval', days=30, seed=42):
    s = pet(arm, seed)
    for _ in range(days * 24):
        s.step()
    return s


def test_initial_evaluation_is_the_same_for_every_birth():
    for seed in (1, 42, 3001):
        a = pet('eval', seed).agent
        assert a.Q == {'read': 0.0, 'garden': 0.0} and a.eval_n == {'read': 0.0, 'garden': 0.0}
        assert a.eval_base is None and a.eval_term('read') == a.eval_term('garden') == 0.0


def test_only_the_lived_activity_gets_evidence():
    a = pet('eval').agent
    a.evaluate_experience('garden', 1, 0.9, 0.9)
    assert a.eval_n['read'] == 0 and a.Q['read'] == 0.0 and a.eval_n['garden'] == 1
    a.evaluate_experience('visit', 2, 0.2, 0.2)               # social hour: baseline only
    assert a.eval_n['garden'] == 1 and a.eval_base != 0.9


def test_never_lived_differs_from_disliked_and_is_bounded():
    a = pet('eval').agent
    for _ in range(30):
        a.evaluate_experience('garden', 1, 0.9, 0.9)
    for _ in range(30):
        a.evaluate_experience('read', 1, 0.1, 0.1)
    assert a.eval_term('read') < 0 and a.eval_n['read'] > 0
    b = pet('eval').agent
    b.evaluate_experience('garden', 1, 0.9, 0.9)
    assert b.eval_term('read') == 0.0 and b.eval_n['read'] == 0       # unknown, not disliked
    assert all(-1 <= a.eval_term(k) <= 1 for k in engine.EVAL_KEYS)


def test_later_opposite_experience_changes_the_evaluation():
    a = pet('eval').agent
    for _ in range(40):
        a.evaluate_experience('read', 1, 0.95, 0.95)
    high = a.Q['read']
    for _ in range(40):
        a.evaluate_experience('read', 1, 0.3, 0.3)
    assert a.Q['read'] < 0.5 < high


def test_unlived_time_fades_confidence_not_the_evaluation():
    a = pet('eval').agent
    for _ in range(20):
        a.evaluate_experience('read', 1, 0.9, 0.9)
    q, n = a.Q['read'], a.eval_n['read']
    for d in range(30):
        a.daily(d)
    assert a.Q['read'] == q and a.eval_n['read'] == pytest.approx(n * engine.EVAL_KEEP ** 30)


def test_signal_is_the_pre_action_comfort_and_never_reads_q():
    s = lived_eval(days=10)
    for e in s.events:
        if e['kind'] == 'action' and e['core_action'] in engine.LEISURE:
            assert 0.0 <= e['comfort'] <= 1.0
    a, b = copy.deepcopy(s), copy.deepcopy(s)
    b.agent.Q = {'read': 1.0, 'garden': -1.0}                 # extreme Q in a copy
    b.agent.eval_in_decision = a.agent.eval_in_decision = False   # same action, compare the signal only
    a.step(); b.step()
    assert a.events[-1]['comfort'] == b.events[-1]['comfort']


def test_the_term_enters_only_activity_scores_and_respects_needs():
    s = lived_eval(days=25)
    a, day = s.agent, s.tick // 24
    for x in core.ACTIONS:
        p = a.score_parts(x, day)
        if p is None:
            continue
        if x in ('read', 'explore'):
            assert p['evaluation'] == pytest.approx(engine.EVAL_WEIGHT * a.eval_term(p['eval_key'])
                                                    * a.need_gate() * (1 - a.home_need()))
        else:
            assert p['evaluation'] == 0.0
    before = {g: p for g, p, _ in a.propose_goals(day)}
    a.evaluation = False
    assert before == {g: p for g, p, _ in a.propose_goals(day)}            # goals untouched


def test_no_decision_ablation_equals_the_base_and_frozen_learns_nothing():
    x, y = lived_eval('base', 40, 3001), lived_eval('eval_nodecision', 40, 3001)
    assert behavior_digest(x) == behavior_digest(y)
    s = lived_eval('eval', 10)
    s.agent.eval_learning = False
    q, n = dict(s.agent.Q), dict(s.agent.eval_n)
    for _ in range(5 * 24):
        s.step()
    assert s.agent.Q == q and s.agent.eval_n == n


def test_flat_ablation_gives_both_activities_the_same_term():
    s = lived_eval('eval_flat', 25)
    a, day = s.agent, s.tick // 24
    pr, pe = a.score_parts('read', day), a.score_parts('explore', day)
    assert pr['evaluation'] == pytest.approx(pe['evaluation'])


def test_counterfactual_is_the_whole_legal_choice_without_the_term():
    s = lived_eval('eval', 40, 3001)
    checked = 0
    for e in s.events:
        d = e.get('decision') or {}
        if d.get('evaluation'):
            assert d['eval_decisive'] == (d['eval_choice_without'] != e['core_action'])
            checked += 1
    assert checked
    a, day = s.agent, s.tick // 24
    off = copy.deepcopy(a)
    off.evaluation = False
    assert a.choice_without_evaluation(day) == off.choose(day)


def test_evaluation_draws_no_random_number():
    s = lived_eval('eval', 20)
    rng = s.agent.rng.getstate()
    a = s.agent
    a.evaluate_experience('read', 1, 0.5, 0.5)
    a.score_parts('read', s.tick // 24)
    a.choice_without_evaluation(s.tick // 24)
    VE.swap_diag(s)
    assert a.rng.getstate() == rng


def test_isolated_diagnostics_never_touch_the_real_life():
    s = lived_eval('eval', 25)
    before = behavior_digest(s), dict(s.agent.Q)
    VE.swap_diag(s)
    VE.probe_read(s.agent, s.tick // 24)
    assert (behavior_digest(s), dict(s.agent.Q)) == before
