"""Social diagnostics and neighbor-rule switches (validation tooling for v5).

Defaults must reproduce v5 exactly; diagnostics and probes must not change any pet.
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
from pet.engine import Session
from make_rules_baseline_v5 import behavior_digest

BASELINE_V5 = json.loads((ROOT / 'tests' / 'fixtures' / 'rules_baseline_v5.json').read_text(encoding='utf-8'))


def pet(seed=42, items=('garden',), invite=True):
    s = Session(seed)
    for item in items:
        s.apply({'kind': 'object', 'value': item})
    if invite:
        s.apply({'kind': 'invite', 'value': None})
    return s


@pytest.mark.parametrize('case', BASELINE_V5[:6], ids=lambda c: f"seed{c['archive']['seed']}-{c['scenario']}")
def test_diagnostics_on_or_off_never_change_behavior_or_rng(case):
    on = Session(case['archive']['seed'], case['archive']['version'])
    on.agent.diagnostics = True
    for command in case['archive']['commands']:
        on.apply(command)
    assert behavior_digest(on) == case['behavior']
    assert all('social_diag' in e for e in on.events if e['kind'] == 'action')
    off = Session.restore(case['archive'])
    assert all('social_diag' not in e for e in off.events)
    assert 'social_diag' not in json.dumps(on.archive())               # never saved


def test_a_wish_to_visit_is_only_recorded_when_a_real_draw_happened():
    s = pet(1)
    s.agent.diagnostics = True
    for _ in range(20 * 24):
        s.step()
    seen = set()
    for e in s.events:
        if e['kind'] != 'action':
            continue
        d = e['social_diag']
        if not d['chose_explore'] or not d['met'] and not d['invited']:
            assert d['drew'] is False
        if d['drew'] is False and not d['invited']:
            assert d['wanted'] is None                                     # no invented wish
        if e['action'] == 'visit':
            assert d['wanted'] is True and (d['available_uninvited'] or d['invited'])
        if d['drew'] and d['wanted'] and d['blocked']:
            assert e['action'] == 'garden' and e['neighbor'] == d['blocked']
            seen.add('blocked')
        seen.add(e['action'])
    assert {'visit', 'garden', 'blocked'} <= seen


def test_rest_interval_and_daily_cap_switches():
    a = pet(42).agent
    day = next(d for d in range(50) if not __import__('random').Random(42 * 100003 + d).random() < engine.MILI_AWAY_CHANCE)
    a.shared = [{'id': 1, 'tick': day * 24 + 9}]
    assert a.neighbor_status(day, 11) == 'free'                           # v5 defaults: no rest
    a.visit_rest_hours = 4
    assert a.neighbor_status(day, 11) == 'rest' and a.neighbor_status(day, 13) == 'free'
    assert a.neighbor_status(day, 11, invited=True) == 'free'             # invitations skip the rest
    a.visit_rest_hours, a.visit_cap = 0, 1
    assert a.neighbor_status(day, 12) == 'full'
    a.visit_cap = None
    assert a.neighbor_status(day, 12) == 'free'
    assert engine.NEIGHBOR_TEXT['rest'].startswith('想去找米粒')


def test_frozen_preferences_keep_acting_but_stop_learning():
    s = pet(901, ('garden', 'book'))
    for _ in range(10 * 24):
        s.step()
    s.agent.freeze_prefs = True
    before = dict(s.agent.prefs)
    count = s.agent.pref_evidence['garden']['count']
    for _ in range(5 * 24):
        s.step()
    assert s.agent.prefs == before and s.agent.pref_evidence['garden']['count'] > count
    assert any(e.get('decision', {}).get('preference') for e in s.events[-100:])


def test_probe_copies_leave_the_real_pet_untouched():
    from pet import validate_v5_social as X
    s = pet(3001, ('garden', 'book'))
    s.agent.diagnostics = True
    for _ in range(4 * 24):
        s.step()
    snapshot = (behavior_digest(s), len(s.events), s.agent.rng.getstate())
    points = [copy.deepcopy(s)]
    out = X.probe(points)
    assert set(out) == set(X.SCHEMES) and all(0 <= v['expected_visit'] <= 1 for v in out.values())
    assert (behavior_digest(s), len(s.events), s.agent.rng.getstate()) == snapshot
    assert (behavior_digest(points[0]), len(points[0].events)) == snapshot[:2]


def test_defaults_are_the_v5_rule():
    a = Session().agent
    assert (a.visit_cap, a.visit_rest_hours, a.freeze_prefs, a.diagnostics) == (2, 0, False, False)


def test_new_rules_option_only_affects_a_new_save(tmp_path):
    from pet.server import create_server
    path = tmp_path / 'demo.json'
    server = create_server(path, 0, new_rules=4)
    server.server_close()
    assert json.loads(path.read_text(encoding='utf-8'))['version'] == 4
    again = create_server(path, 0, new_rules=5)          # an existing save keeps its rules
    again.server_close()
    assert again.session.rules == 4 and json.loads(path.read_text(encoding='utf-8'))['version'] == 4
    bat = (ROOT / 'start_pet_v5.bat').read_text(encoding='utf-8')
    assert '--save pet/data/v5-demo.json --new-rules 5' in bat
