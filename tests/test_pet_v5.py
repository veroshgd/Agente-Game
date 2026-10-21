"""Regressions for rules v5: long-term preferences formed by lived activities.

Product tests only. The behavioral experiments (growth routes, probes, ablation) live in
pet/validate_v5.py because they take minutes; these tests pin the mechanism's contract.
"""
import copy
from collections import Counter
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet.engine import RULES, Session
from make_rules_baseline_v4 import digest_v4

BASELINE_V4 = json.loads((ROOT / 'tests' / 'fixtures' / 'rules_baseline_v4.json').read_text(encoding='utf-8'))


def pet(seed=42, items=('garden',), invite=True, rules=RULES):
    s = Session(seed, rules)
    for item in items:
        s.apply({'kind': 'object', 'value': item})
    if invite:
        s.apply({'kind': 'invite', 'value': None})
    return s


def hours(s, n):
    for _ in range(n):
        s.step()


# ---------------------------------------------------------------- versions and replay
def test_v5_pets_can_still_be_created():
    assert RULES == 5 and Session().archive()['version'] == 5
    assert Session(rules=5).archive()['version'] == 5


@pytest.mark.parametrize('case', BASELINE_V4, ids=lambda c: f"v4-seed{c['archive']['seed']}-{c['scenario']}")
def test_v4_saves_replay_exactly_as_the_v4_engine_did(case):
    # Baseline written by the pre-v5 engine (tests/fixtures/make_rules_baseline_v4.py).
    s = Session.restore(copy.deepcopy(case['archive']))
    assert s.rules == 4 and digest_v4(s) == case['digest']
    resumed = Session.restore({**copy.deepcopy(case['archive']), 'commands': case['archive']['commands'][:-7]})
    for command in case['archive']['commands'][-7:]:
        resumed.apply(command)
    assert digest_v4(resumed) == case['digest']
    assert s.view()['preferences'] is None
    assert all('enjoyment' not in e and 'preference' not in e.get('decision', {}) for e in s.events)


def test_v5_preferences_are_rebuilt_by_replay_and_resume():
    s = pet(901, ('garden', 'book'))
    for _ in range(12):
        s.apply({'kind': 'advance', 'value': 24})
    again = Session.restore(json.loads(json.dumps(s.archive())))
    assert again.agent.prefs == s.agent.prefs and again.agent.pref_evidence == s.agent.pref_evidence
    assert again.view() == s.view()
    half = Session.restore({**s.archive(), 'commands': s.archive()['commands'][:-5]})
    for command in s.archive()['commands'][-5:]:
        half.apply(command)
    assert half.agent.prefs == s.agent.prefs and half.view() == s.view()


# ---------------------------------------------------------------- formation rules
def test_preferences_start_neutral_and_options_alone_teach_nothing():
    births = {seed: pet(seed, invite=False).agent.prefs for seed in (1, 42, 901)}
    assert all(p == {'read': 0.0, 'garden': 0.0, 'social': 0.0} for p in births.values())
    s = pet(42, ('garden', 'book', 'music'), invite=True)       # objects + an invitation
    assert s.agent.prefs == {'read': 0.0, 'garden': 0.0, 'social': 0.0}


def test_only_lived_activities_move_preferences_each_with_its_own_trace():
    s = pet(42, ('garden', 'book'))
    hours(s, 15 * 24)
    a = s.agent
    acts = [e for e in s.events if e['kind'] == 'action']
    assert a.pref_evidence['read']['count'] == sum(e['action'] == 'read' for e in acts)
    assert a.pref_evidence['garden']['count'] == sum(e['action'] == 'garden' for e in acts)
    assert a.pref_evidence['social']['count'] == sum(bool(e.get('chance_to_meet')) for e in acts)
    for key, kind in (('read', 'read'), ('garden', 'garden')):
        for eid in a.pref_evidence[key]['recent_ids']:
            assert s.events[eid - 1]['action'] == kind
    for eid in a.pref_evidence['social']['recent_ids']:
        assert s.events[eid - 1]['action'] == 'visit'
    # Every change of a preference happened on an hour with a real leisure activity or chance.
    replay = pet(42, ('garden', 'book'))
    before = dict(replay.agent.prefs)
    for _ in range(15 * 24):
        replay.step()
        e = replay.events[-1]
        if replay.agent.prefs != before:
            assert e['core_action'] in engine.LEISURE or e.get('chance_to_meet')
        before = dict(replay.agent.prefs)


def test_learning_is_bounded_saturating_and_depends_on_enjoyment():
    a = pet(42).agent
    for i in range(5000):
        a.experience('read', i, 1.0)
    assert 0.99 < a.prefs['read'] <= 1.0 and a.prefs['garden'] < 1e-6
    first = pet(42).agent
    first.experience('read', 1, 1.0)
    assert first.prefs['read'] == pytest.approx(engine.PREF_RATE)       # one hour is a small step
    tired = pet(42).agent
    tired.experience('read', 1, 0.2)
    assert tired.prefs['read'] < first.prefs['read']
    social = pet(42).agent
    social.social_experience(True, 1, 0.8)
    up = social.prefs['social']
    social.social_experience(False, 2, 0.8)                              # solitude when she was free
    assert 0 < social.prefs['social'] < up


def test_repetition_and_needs_lower_enjoyment():
    s = pet(42, ('garden', 'book'))
    hours(s, 10 * 24)
    for e in s.events:
        if e['kind'] == 'action':
            assert 0.0 <= e['enjoyment'] <= 1.0
    a = copy.deepcopy(s.agent)
    a.hunger, a.energy = 20.0, 90.0
    a.recent = []
    fresh = a.need_gate() * (1 - engine.PREF_DULL * a.recent.count('read') / engine.BOREDOM_WINDOW)
    a.recent = ['read'] * 24
    dull = a.need_gate() * (1 - engine.PREF_DULL * a.recent.count('read') / engine.BOREDOM_WINDOW)
    assert dull < fresh
    a.hunger = 65.0
    assert a.need_gate() < 0.2


# ---------------------------------------------------------------- decisions
def test_preference_is_a_pull_not_an_order():
    a = pet(42, ('garden', 'book')).agent
    a.prefs = {'read': 1.0, 'garden': 0.0, 'social': 0.0}
    a.hunger, a.energy = 20.0, 90.0
    relaxed = a.preference_part('read', 0)[0]
    assert relaxed > 0
    a.hunger = 68.0                                           # nearly hungry enough to be harmed
    assert a.preference_part('read', 0)[0] < relaxed * 0.1
    a.hunger, a.shelter = 20.0, 0.0                           # a run-down home crowds it out
    assert a.preference_part('read', 0)[0] == 0
    a.shelter, a.hunger, a.energy = 80.0, 80.0, 50.0
    day = 0
    best = max((a.score(x, day), x) for x in engine.core.ACTIONS if a.score(x, day) is not None)[1]
    assert best == 'eat'


def test_explore_takes_the_best_available_liking_once():
    a = pet(42).agent
    a.hunger, a.energy, a.now = 20.0, 90.0, 10
    a.shared = [{'id': 1, 'tick': 0}]
    a.prefs = {'read': 0.0, 'garden': 0.3, 'social': 0.6}
    a.neighbor_status = lambda d, h, invited=False: engine.NEIGHBOR_FREE
    both, key = a.preference_part('explore', 0)
    assert key == 'social' and both == pytest.approx(engine.PREF_WEIGHT * 0.6)
    a.neighbor_status = lambda d, h, invited=False: engine.NEIGHBOR_AWAY
    alone, key = a.preference_part('explore', 0)
    assert key == 'garden' and alone == pytest.approx(engine.PREF_WEIGHT * 0.3)
    a.prefs['social'] = 0.1                                   # a second option adds nothing by itself
    a.neighbor_status = lambda d, h, invited=False: engine.NEIGHBOR_FREE
    assert a.preference_part('explore', 0) == (pytest.approx(engine.PREF_WEIGHT * 0.3), 'garden')


def test_decision_record_is_taken_from_the_choice_itself():
    s = pet(42, ('garden', 'book'))
    hours(s, 12 * 24)
    calls = {}
    original = s.agent.score

    def spy(action, day):
        value = original(action, day)
        calls.setdefault(action, value)
        return value
    s.agent.score = spy
    seen = 0
    for _ in range(96):
        calls.clear()
        prefs_before = dict(s.agent.prefs)
        s.step()
        e = s.events[-1]
        d = e['decision']
        assert d['final'] == pytest.approx(calls[e['core_action']], abs=1e-4)
        if d['pref_key']:
            seen += 1
            assert d['pref_value'] == pytest.approx(prefs_before[d['pref_key']], abs=1e-4)
            assert d['pref_experiences'] >= len(d['pref_recent_ids'])
            assert all(i < e['id'] for i in d['pref_recent_ids'])
            if d['preference'] > 0:
                # Decisive means the instant counterfactual chose another action category.
                cf = d['pref_counterfactual']
                assert cf['removed'] == d['pref_key'] and cf['scope'] == 'category'
                assert d['pref_decisive'] == (cf['choice_without'] != e['core_action'])
                if d['pref_decisive']:
                    assert d['final'] - d['preference'] < d['runner_up']   # necessary, not sufficient
    assert seen


# ---------------------------------------------------------------- the neighbor
def test_no_visits_without_ever_meeting_and_no_invented_memories():
    s = pet(42, ('garden',), invite=False)
    hours(s, 30 * 24)
    assert not s.agent.shared and not any(e.get('action') == 'visit' for e in s.events)
    assert s.agent.prefs['social'] == 0.0


def test_faded_memories_no_longer_forbid_seeking_her_out():
    # Same state for v4 and v5: they met once, 30 days ago; she is free; no invitation.
    for rules, expect in ((4, 0), (5, 1)):
        s = pet(42, rules=rules)
        hours(s, 30 * 24)
        visits = 0
        for trial in range(200):
            c = copy.deepcopy(s)
            a = c.agent
            a.shared = [{'id': 1, 'tick': 0}]
            a.invitation_until = -1
            a.now = c.tick - c.tick % 24 + 10
            a.neighbor_status = lambda d, h, invited=False: engine.NEIGHBOR_FREE
            a.rng.seed(trial)
            a.act('explore', c.tick // 24, 10)
            visits += a.last['action'] == 'visit'
        assert (visits > 0) == bool(expect)
        if rules == 5:
            assert visits >= 200 * engine.VISIT_BASE * 0.5


def test_seeds_that_stopped_visiting_in_v4_keep_in_touch_in_v5():
    # v4 audit: seeds 123 and 2024 (garden + one invitation) never visited after day 69 / 64.
    for seed in (123, 2024):
        old, new = pet(seed, rules=4), pet(seed)
        hours(old, 120 * 24)
        hours(new, 120 * 24)
        last = lambda s: max(m['tick'] for m in s.agent.shared) // 24
        assert last(old) < 70 and last(new) >= 110
        assert not any(e['invited'] for e in new.events if e.get('action') == 'visit' and e['tick'] > 24)


def test_diary_marks_a_visit_without_recent_memories_honestly():
    s = pet(123)
    hours(s, 90 * 24)
    for e in s.events:
        if e.get('action') == 'visit' and not e['invited']:
            if e['cause_ids']:
                assert e['text'].startswith('想起之前一起种花的经历')
            else:
                assert e['text'] == '有一阵子没见米粒了，主动去找她，一起种下一株花。'


# ---------------------------------------------------------------- explanation fix (2026-10-17)
from make_rules_baseline_v5 import behavior_digest, explanation_records

BASELINE_V5 = json.loads((ROOT / 'tests' / 'fixtures' / 'rules_baseline_v5.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', BASELINE_V5, ids=lambda c: f"v5-seed{c['archive']['seed']}-{c['scenario']}")
def test_explanation_fix_leaves_v5_behavior_untouched(case):
    # Baseline written by the v5 engine before the counterfactual fix.
    s = Session.restore(copy.deepcopy(case['archive']))
    assert behavior_digest(s) == case['behavior']        # actions, traits, prefs, body, rng
    new = [bool(d and d['pref_decisive']) for d in explanation_records(s)]
    # The only allowed change: 'decisive' claims withdrawn where another liking takes over.
    assert all(old or not now for old, now in zip(case['pref_decisive'], new))


def test_reported_case_another_liking_takes_over():
    # Review example: seed 2001, social growth route, uniform environment, tick 490.
    from pet import validate_v5 as V
    s = V.grow(2001, 'social')
    V.uniform(s)
    while s.tick < 490:
        s.step()
    before = copy.deepcopy(s)
    s.step()
    d = s.events[-1]['decision']
    assert s.events[-1]['core_action'] == 'explore' and d['pref_key'] == 'garden'
    assert d['final'] - d['preference'] < d['runner_up']             # the old rule said "decisive"
    assert d['pref_decisive'] is False
    assert d['pref_counterfactual'] == {'removed': 'garden', 'choice_without': 'explore', 'scope': 'category'}
    a = before.agent                                                  # independent check
    day = before.tick // 24
    a.now = before.tick
    a.prefs['garden'] = 0.0
    assert a.preference_part('explore', day)[1] == 'social'          # the other liking fills the max


def test_counterfactual_matches_an_independent_recheck_every_hour():
    s = pet(2002, ('garden', 'book'))
    hours(s, 6 * 24)
    seen = Counter()
    for _ in range(14 * 24):
        c = copy.deepcopy(s)
        real_act = c.agent.act
        checked = {}

        def act(action, day, hour=0, a=c.agent):
            p = a.score_parts(action, day)
            if p['preference'] > 0:
                saved = a.prefs[p['pref_key']]
                a.prefs[p['pref_key']] = 0.0
                scored = [(a.score(x, day), x) for x in engine.core.ACTIONS]
                checked['without'] = max((v, x) for v, x in scored if v is not None)[1]
                a.prefs[p['pref_key']] = saved
            return real_act(action, day, hour)
        c.agent.act = act
        c.step()
        s.step()
        d = s.events[-1]['decision']
        if 'without' in checked:
            assert d['pref_counterfactual']['choice_without'] == checked['without']
            assert d['pref_decisive'] == (checked['without'] != s.events[-1]['core_action'])
            seen['decisive' if d['pref_decisive'] else 'not'] += 1
            if not d['pref_decisive'] and d['final'] - d['preference'] < d['runner_up']:
                seen['takeover'] += 1
        else:
            assert d['pref_decisive'] is False
    assert seen['decisive'] and seen['not'] and seen['takeover']


def test_ties_use_the_core_rule():
    a = pet(42, ('garden', 'book')).agent
    a.score = lambda action, day: 10.0 if action in ('read', 'explore') else 1.0
    assert a.choose(0) == max([(10.0, 'explore'), (10.0, 'read')])[1] == 'read'


def test_counterfactual_has_no_side_effects():
    s = pet(901, ('garden', 'book'))
    hours(s, 8 * 24)
    a = s.agent
    a.prefs = {'read': 0.4, 'garden': 0.3, 'social': 0.2}
    state = (copy.deepcopy(a.prefs), copy.deepcopy(a.pref_evidence), a.rng.getstate(),
             s.world.rng.getstate(), len(s.events), a.hunger, a.energy, copy.deepcopy(a.goal))
    for key in ('read', 'garden', 'social'):
        a.choice_without(key, s.tick // 24)
    a.explain('explore', s.tick // 24, a.score_parts('explore', s.tick // 24))
    assert state == (a.prefs, a.pref_evidence, a.rng.getstate(), s.world.rng.getstate(), len(s.events),
                     a.hunger, a.energy, a.goal)


def test_v5_launcher_starts_a_separate_pet_and_keeps_it(tmp_path):
    bat = (ROOT / 'start_pet_v5.bat').read_text(encoding='utf-8')
    assert 'run_pet.py --save pet/data/v5-demo.json' in bat
    from pet.server import create_server
    path = tmp_path / 'v5-demo.json'
    server = create_server(path, 0, new_rules=5)          # first start creates a v5 pet (as the .bat does)
    try:
        assert server.session.rules == 5 and json.loads(path.read_text(encoding='utf-8'))['version'] == 5
    finally:
        server.server_close()
    again = create_server(path, 0, new_rules=5)           # later starts continue the same save
    try:
        assert again.session.rules == 5 and again.session.seed == server.session.seed
    finally:
        again.server_close()
