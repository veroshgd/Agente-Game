"""Round 5 of 2026-10-25 (diagnostics, NOT a rule version): the full counterfactual of the reading
term, the candidate-level audit, the liking / plan ablation switches and the isolated memory replays
(engine PetAgent.read_audit etc., pet/diag_interest.py). v1-v6 replays are pinned elsewhere."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import diag_interest as DI
from pet import validate_interest as VI
from pet import run_foresight_validation as RV
from pet import validate_read as VR
from pet.engine import RULES, Session
from make_rules_baseline_v5 import behavior_digest

RESULT = ROOT / 'docs' / 'pet_goal_interest' / 'diag_interest_result.json'


def pet(arm='interest', seed=42, items=('book', 'garden'), clarity=None):
    s = VI.configure(Session(seed, 5), arm)
    for it in items:
        s.apply({'kind': 'object', 'value': it})
    if clarity is not None:
        s.world.p['book_clarity'] = clarity
    return s


def live(s, days):
    for _ in range(days * 24):
        s.step()
    return s


def test_switches_are_off_for_every_rule_version():
    assert RULES == 5
    for rules in range(1, 7):
        a = Session(rules=rules).agent
        assert not (a.read_audit or a.pref_score_off or a.pref_goal_off or a.goal_read_bonus_off)


@pytest.mark.parametrize('seed,expected', [(3001, 51), (6006, 35), (6010, 74)])
def test_hard_book_suppression_was_missed_by_the_old_log(seed, expected):
    """The old record re-chose only when the CHOSEN action carried the term: 0 logged. Re-making the
    whole choice every hour finds the hours a negative term kept the hard-book pet from reading."""
    s = VI.book_pet(seed, 'interest', VI.HARD)
    s.agent.read_audit = True
    n0 = len(s.events)
    VR.run_hours(s, VI.COMMON * 24)
    rows = DI.hour_rows(s, n0)
    promote, suppress, other = DI.count_effects(rows)
    assert (promote, suppress, other) == (0, expected, 0)
    assert sum(r['logged'] for r in rows) == 0


def test_audit_changes_no_behaviour_and_no_random_state():
    x = VI.book_pet(3001, 'interest', VI.CLEAR)
    y = copy.deepcopy(x)
    y.agent.read_audit = True
    VR.run_hours(x, 10 * 24)
    VR.run_hours(y, 10 * 24)
    assert behavior_digest(x) == behavior_digest(y)
    assert x.agent.rng.getstate() == y.agent.rng.getstate()
    assert (x.agent.read_V, x.agent.read_n, x.agent.read_I, x.agent.prefs) == (y.agent.read_V, y.agent.read_n, y.agent.read_I, y.agent.prefs)


def test_audit_record_is_pure_and_restores_every_switch():
    s = live(pet('interest', 3001, clarity=0.9), 25)
    a = s.agent
    before = (a.rng.getstate(), a.read_n, a.read_I, a.read_value_in_decision, a.pref_score_off, a.goal_read_bonus_off,
              copy.deepcopy(a.goal), dict(a.prefs))
    rec = a.read_audit_record(a.choose(s.tick // 24), s.tick // 24)
    assert (a.rng.getstate(), a.read_n, a.read_I, a.read_value_in_decision, a.pref_score_off, a.goal_read_bonus_off,
            a.goal, a.prefs) == before
    assert set(rec['without']) == set(DI.FACTORS) and rec['read_rank'] >= 1
    s_, i_ = a.read_term_parts()
    assert s_ + i_ == pytest.approx(a.read_value_term())


def test_effect_labels_and_exact_decomposition():
    s = VI.book_pet(6010, 'interest', VI.CLEAR)
    s.agent.read_audit = True
    n0 = len(s.events)
    VR.run_hours(s, 20 * 24)
    rows = DI.hour_rows(s, n0)
    for r in rows:
        w = r['without']['term']
        assert r['effect']['term'] == ('promote' if r['chosen'] == 'read' and w != 'read' else
                                       'suppress' if r['chosen'] != 'read' and w == 'read' else None)
    d = DI.decompose(rows)
    assert d['real'] == pytest.approx(d['state'] + d['instant'], abs=1e-12)


def test_ablation_switches_split_the_channels():
    a = live(pet('interest', 3001, clarity=0.9), 25).agent
    day = a.now // 24
    a.prefs['read'], a.hunger, a.energy, a.shelter, a.condition = 0.4, 30.0, 80.0, 60.0, 100.0
    a.inventory['food'] = 6.0
    on = a.preference_part('read', day)[0]
    goals_on = dict((g, p) for g, p, _ in a.propose_goals(day))
    a.pref_score_off = True
    assert a.preference_part('read', day)[0] == 0.0 and on > 0
    assert dict((g, p) for g, p, _ in a.propose_goals(day)) == goals_on        # goals keep the liking
    a.pref_score_off, a.pref_goal_off = False, True
    assert a.preference_part('read', day)[0] == on                            # scores keep the liking
    if 'learn' in goals_on:
        assert dict((g, p) for g, p, _ in a.propose_goals(day))['learn'] < goals_on['learn']
    a.pref_goal_off = False
    a.goal = {'type': 'learn', 'priority': 1.0, 'created_day': day, 'start': 0}
    others = {x: a.goal_bonus(x) for x in engine.core.ACTIONS}
    a.goal_read_bonus_off = True
    assert a.goal_bonus('read') == 0.0 and others['read'] > 0
    assert all(a.goal_bonus(x) == v for x, v in others.items() if x != 'read')


def test_isolated_memory_replay_reproduces_the_real_memory():
    real = DI.real_lives(9999, 'interest')
    pets0 = {n: VI.book_pet(9999, 'interest', cl) for n, cl in (('clear', VI.CLEAR), ('hard', VI.HARD))}
    m = DI.memory_job(9999, pets0, real)
    assert m['clear']['real_replay_exact'] and m['hard']['real_replay_exact']
    none = m['clear']['traj']['none (artificial)']
    assert none[-1][0] == none[0][0] and engine.READ_VALUE_REF < none[-1][2] < none[0][2]   # only fading
    assert m['clear']['I_split']['I_end'] == pytest.approx(m['clear']['I_split']['I_start']
                                                          + m['clear']['I_split']['consolidation'] + m['clear']['I_split']['fading'])


def test_recorded_result_and_rule():
    r = json.loads(RESULT.read_text(encoding='utf-8'))
    assert r['verdict'] == {'G1_systematic': False, 'G2_not_the_term': True, 'G3_through_plans': False,
                            'goal_entry_supported': False}
    I = r['summary']['interest']
    assert all(r['summary'][a]['audit_changes_nothing_all'] for a in DI.ARMS)
    assert I['from30_rep0']['all']['gap']['mean'] == pytest.approx(-0.0130556, abs=1e-6)     # the round-4 -1.31 pp
    assert I['keep_late_decomp_gap']['state']['mean'] < 0 < I['keep_late_decomp_gap']['instant']['mean']
    assert I['from30']['all']['gap']['ci95'][0] < 0 < I['from30']['all']['gap']['ci95'][1]
    assert I['memory']['clear_exact'] and I['memory']['hard_exact']
    assert (ROOT / 'docs' / 'pet_goal_interest' / 'CORRECTION_STRENGTH.md').exists()
    assert RV.seeds_used_only_by_this_validation() and VI.VALIDATION_SEEDS[0] == 7041   # round 9: used once, by the foresight validation
