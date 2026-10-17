"""Regressions for rules v4, the decision record, rule versions and prototype limits.

Product tests only; never runs confirmatory research experiments.
"""
import copy
from collections import Counter
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet.engine import NEIGHBOR_TEXT, RULES, Session
from pet.server import catch_up, create_server, save_atomic, split_clock
from make_rules_baseline import digest

APP = (ROOT / 'pet' / 'static' / 'app.js').read_text(encoding='utf-8')
HTML = (ROOT / 'pet' / 'static' / 'index.html').read_text(encoding='utf-8')
BASELINE = json.loads((ROOT / 'tests' / 'fixtures' / 'rules_baseline.json').read_text(encoding='utf-8'))
LEISURE = ('garden', 'visit', 'explore', 'read')


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


# ---------------------------------------------------------------- 1. home upkeep
# Safe-home upkeep standard (rules v4), checked at every game hour of 60 days:
#  - the home never reaches 0, and its lowest point stays >= 3;
#  - at most 8% of hours below 20: a run-down home is a passing state, not a way of life;
#  - upkeep (gather_material + build) at most 15% of hours: it cares, it does not obsess;
#  - leisure (garden, visits, explore, read) keeps at least 30% of hours;
#  - hunger never harms the body (condition >= 99), and the last week shows >= 3 kinds
#    of action. The end state alone proves nothing, so the whole curve is checked.
HOME_SEEDS = (1, 42, 901, 7, 123, 2024)   # 1/42/901 from the review; the rest generalize


@pytest.mark.parametrize('items', [('garden',), ('garden', 'book', 'music')])
@pytest.mark.parametrize('seed', HOME_SEEDS)
def test_safe_home_upkeep_standard(seed, items):
    s = pet(seed, items)
    homes, condition = [], 100.0
    for _ in range(60 * 24):
        s.step()
        homes.append(s.agent.shelter)
        condition = min(condition, s.agent.condition)
    acts = Counter(e['action'] for e in s.events if e['kind'] == 'action')
    total = sum(acts.values())
    last_week = {e['action'] for e in s.events if e['kind'] == 'action' and e['tick'] >= 53 * 24}
    assert min(homes) >= 3 and 0 not in homes
    assert sum(h < 20 for h in homes) / len(homes) <= 0.08
    assert (acts['gather_material'] + acts['build']) / total <= 0.15
    assert sum(acts[a] for a in LEISURE) / total >= 0.30
    assert condition >= 99 and 'fears_hunger' not in s.agent.flags
    assert len(last_week) >= 3


def test_v3_branch_still_lets_the_home_run_down():
    # The bug v4 fixes stays reproducible under the v3 rules, which old saves keep.
    s = pet(42, rules=3)
    homes = []
    for _ in range(60 * 24):
        s.step()
        homes.append(s.agent.shelter)
    assert homes.count(0.0) > 24


def test_home_need_is_silent_when_the_home_is_fine():
    a = pet(42).agent
    a.shelter = engine.HOME_CARE_FROM + 1
    assert a.home_care('gather_material') == a.home_care('build') == 0
    a.shelter = 10
    assert a.home_care('build') > 0 and a.home_care('explore') == 0
    assert pet(42, rules=3).agent.home_care('build') == 0


# ---------------------------------------------------------------- 2. neighbor reasons
def test_neighbor_reasons_are_distinct_and_match_the_diary():
    seen = Counter()
    for seed in (1, 42, 901):
        s = pet(seed)
        hours(s, 30 * 24)
        for e in s.events:
            if e.get('action') != 'garden' or not e.get('neighbor'):
                continue
            day, hour = divmod(e['tick'], 24)
            away = random.Random(seed * 100003 + day).random() < engine.MILI_AWAY_CHANCE
            met = sum(1 for v in s.events if v.get('action') == 'visit'
                      and v['tick'] // 24 == day and v['id'] < e['id'])
            expected = ('off_hours' if not 8 <= hour < 20 else 'away' if away
                        else 'full' if met >= engine.MILI_VISITS_PER_DAY else None)
            assert e['neighbor'] == expected, e
            assert e['text'] == NEIGHBOR_TEXT[expected]
            seen[expected] += 1
    assert seen['away'] and seen['full'] and seen['off_hours']


def test_invitation_skips_away_and_full_but_not_off_hours():
    a = pet(42).agent
    away_day = next(d for d in range(100) if random.Random(42 * 100003 + d).random() < engine.MILI_AWAY_CHANCE)
    home_day = next(d for d in range(100) if random.Random(42 * 100003 + d).random() >= engine.MILI_AWAY_CHANCE)
    assert a.neighbor_status(away_day, 10) == 'away'
    assert a.neighbor_status(away_day, 10, invited=True) == 'free'
    assert a.neighbor_status(away_day, 21, invited=True) == 'off_hours'
    a.shared = [{'id': 1, 'tick': home_day * 24 + 9}, {'id': 2, 'tick': home_day * 24 + 10}]
    assert a.neighbor_status(home_day, 12) == 'full'
    assert a.neighbor_status(home_day, 12, invited=True) == 'free'
    old = pet(42, rules=2).agent
    old.shared = a.shared
    assert old.neighbor_status(away_day, 10) == old.neighbor_status(home_day, 12) == 'free'


def test_v4_never_writes_the_v3_catch_all_text():
    s = pet(1)
    hours(s, 30 * 24)
    assert not any('missed_neighbor' in e for e in s.events)
    assert not any(e['text'] == '想去找米粒，可她今天不在家，就自己照料了花园。' for e in s.events)


# ---------------------------------------------------------------- 3. decision record
def test_decision_record_uses_the_values_of_that_choice():
    s = pet(42)
    hours(s, 5 * 24)
    calls = {}
    original = s.agent.score

    def spy(action, day):
        value = original(action, day)
        calls.setdefault(action, value)    # first call per tick = the core's own scoring
        return value
    s.agent.score = spy
    for _ in range(72):
        calls.clear()
        s.step()
        e = s.events[-1]
        d = e['decision']
        chosen = calls[e['core_action']]
        assert d['final'] == pytest.approx(chosen, abs=1e-4)
        assert chosen == max(v for v in calls.values() if v is not None)
        rivals = [v for a, v in calls.items() if a != e['core_action'] and v is not None]
        assert d['runner_up'] == pytest.approx(max(rivals), abs=1e-4)


def test_decision_parts_add_up_and_cite_only_prior_shared_events():
    s = pet(42)
    hours(s, 20 * 24)
    visits = {e['id'] for e in s.events if e.get('action') == 'visit'}
    count = Counter()
    for e in s.events:
        if e['kind'] != 'action':
            continue
        d = e['decision']
        total = (d['core'] - d['boredom'] + d['eat_urgency'] + d['home_care']
                 + d['garden'] + d['invitation'] + d['memory'] + d.get('preference', 0.0))   # v5 term
        assert total == pytest.approx(d['final'], abs=2e-3)
        assert d['net'] == pytest.approx(d['final'] - d['core'], abs=2e-4)
        assert d['gated'] == pytest.approx(d['garden'] + d['invitation'] + d['memory'], abs=2e-3)
        assert 0 <= d['gate'] <= 1 and d['boredom'] >= 0
        assert d['memory'] == pytest.approx(d['memory_raw'] * d['gate'], abs=2e-3)
        assert e['score_bonus'] == pytest.approx(d['net'], abs=2e-3)
        if e['core_action'] == 'explore':
            assert e['cause_ids'] == d['memory_ids']
        for cause in e['cause_ids']:
            assert cause in visits and cause < e['id']
        if d['memory_decisive']:
            assert d['memory'] > 0 and d['final'] - d['memory'] < d['runner_up']
            count['decisive'] += 1
        elif d['memory'] > 0:
            assert d['final'] - d['memory'] >= d['runner_up']
            count['not_decisive'] += 1
        count['negative'] += d['net'] < 0
    assert count['negative'] and count['not_decisive']


def test_old_rule_saves_also_get_an_honest_decision_record():
    # Explanation only: their choices and diary texts are pinned by the baseline below.
    s = pet(42, rules=2)
    hours(s, 3 * 24)
    d = s.events[-1]['decision']
    assert d['boredom'] == 0 and d['home_care'] == 0
    assert 'neighbor' not in s.events[-1] and 'missed_neighbor' not in s.events[-1]


def test_ui_signs_negative_changes_and_drops_the_old_explore_label():
    assert '探索得分增加' not in APP and '+${b}' not in APP
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js not installed; static checks above still ran')
    line = re.search(r'^const signed=.*$', APP, re.M).group(0)
    out = subprocess.run([node, '-e', line + 'console.log([signed(-0.614),signed(2),signed(0)].join("|"))'],
                         capture_output=True, text=True, encoding='utf-8', check=True).stdout.strip()
    assert out == '−0.6|+2.0|+0.0'


# ---------------------------------------------------------------- 4. rule versions
@pytest.mark.parametrize('case', BASELINE, ids=lambda c: f"v{c['archive']['version']}-seed{c['archive']['seed']}-{len(c['archive']['commands'])}cmd")
def test_old_rule_saves_replay_exactly_as_the_old_code_did(case):
    # Baseline written by the pre-v4 engine (tests/fixtures/make_rules_baseline.py).
    s = Session.restore(copy.deepcopy(case['archive']))
    assert s.rules == case['archive']['version'] and digest(s) == case['digest']
    resumed = Session.restore({**copy.deepcopy(case['archive']), 'commands': case['archive']['commands'][:-10]})
    for command in case['archive']['commands'][-10:]:
        resumed.apply(command)
    assert resumed.rules == s.rules and digest(resumed) == case['digest']
    view = s.view()
    assert view['rules'] == case['archive']['version'] and view['latest_rules'] == RULES


def test_new_pets_use_the_latest_rules_and_unknown_versions_are_refused():
    assert RULES >= 4 and Session().archive()['version'] == RULES
    with pytest.raises(ValueError):
        Session.restore({'version': RULES + 1, 'seed': 42, 'commands': []})
    assert set(re.findall(r"rulesOld:", APP)) and 'rules-note' in HTML


# ---------------------------------------------------------------- 5/6. limits and catch-up
def serve(path):
    server = create_server(path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f'http://127.0.0.1:{server.server_port}'


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join()


def get(url):
    with urlopen(url) as response:
        return response.status, json.load(response)


def post(base, token, body):
    try:
        with urlopen(Request(base + '/api/command', json.dumps(body).encode(), headers={'X-Pet-Token': token})) as r:
            return r.status, json.load(r)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_at_the_command_limit_state_history_and_export_still_work(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'MAX_COMMANDS', 12)
    s = pet(42)
    for _ in range(10):
        s.apply({'kind': 'advance', 'value': 1})
    assert s.limits()['commands_left'] == 0
    path = tmp_path / 'pet.json'
    save_atomic(path, s, time.time() - 5 * 3600 - 60)
    server, thread, base = serve(path)
    try:
        status, data = get(base + '/api/state')        # used to drop the connection
        assert status == 200 and data['state']['tick'] == s.tick
        assert data['state']['limits']['can_advance'] is False
        assert data['away'] == {**data['away'], 'hours': 0, 'skipped_hours': 5, 'limit': 'commands'}
        assert len(data['state']['events']) == len(s.view()['events'])
        status, exported = get(base + '/api/export')
        assert status == 200 and exported == s.archive()
        saved = path.read_text(encoding='utf-8')
        for body in ({'kind': 'advance', 'value': 1}, {'kind': 'name', 'value': 'Otra'}):
            status, data = post(base, data.get('token') or get(base + '/api/state')[1]['token'], body)
            assert status == 409 and data['limit'] is True and data['error']
            assert data['state']['tick'] == s.tick and data['state']['name'] == s.name
        assert path.read_text(encoding='utf-8') == saved
    finally:
        stop(server, thread)


def test_catch_up_stops_at_the_tick_limit(monkeypatch):
    monkeypatch.setattr(engine, 'MAX_TICKS', 30)
    s = pet(42, invite=False)
    s.apply({'kind': 'advance', 'value': 24})
    s.apply({'kind': 'advance', 'value': 1})
    s.apply({'kind': 'advance', 'value': 1})
    away = catch_up(s, 10)
    assert s.tick == 30 and away['hours'] == 4 and away['skipped_hours'] == 6 and away['limit'] == 'ticks'
    assert not s.limits()['can_advance']
    assert catch_up(s, 3) == {**catch_up(copy.deepcopy(s), 3), 'hours': 0, 'skipped_hours': 3}
    with pytest.raises(engine.LimitReached):
        s.apply({'kind': 'advance', 'value': 1})


def test_catch_up_across_the_command_limit_is_one_transaction(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'MAX_COMMANDS', 4)
    s = pet(42, invite=False)
    s.apply({'kind': 'advance', 'value': 1})            # 2 commands used, 2 left
    path = tmp_path / 'pet.json'
    stamp = time.time() - 37 * 3600 - 20 * 60           # 37 h owed + 20 min left over
    save_atomic(path, s, stamp)
    server, thread, base = serve(path)
    try:
        status, data = get(base + '/api/state')
        assert status == 200
        assert data['away']['hours'] == 30 and data['away']['skipped_hours'] == 7   # 24 + 6, fewest commands
        saved = json.loads(path.read_text(encoding='utf-8'))
        assert saved['commands'] == s.commands + [{'kind': 'advance', 'value': 24}, {'kind': 'advance', 'value': 6}]
        assert saved['last_seen'] == pytest.approx(stamp + 37 * 3600)                # all owed hours consumed
        assert 19 * 60 < time.time() - saved['last_seen'] < 21 * 60                  # sub-hour remainder kept
        assert Session.restore(split_clock(saved)[0]).view() == data['state']
    finally:
        stop(server, thread)


def test_a_failed_command_commits_neither_itself_nor_the_catch_up(tmp_path):
    s = pet(42, invite=False)
    path = tmp_path / 'pet.json'
    save_atomic(path, s, time.time())
    server, thread, base = serve(path)
    try:
        token = get(base + '/api/state')[1]['token']         # nothing owed yet
        owed_since = time.time() - 3 * 3600 - 60
        server.last_seen = owed_since                        # now 3 h are owed
        before = path.read_text(encoding='utf-8')
        status, data = post(base, token, {'kind': 'object', 'value': 'code'})
        assert status == 400 and data['error']
        assert path.read_text(encoding='utf-8') == before
        assert server.session.tick == s.tick and server.last_seen == owed_since
        status, data = get(base + '/api/state')              # the owed time is still there
        assert data['state']['tick'] == s.tick + 3 and data['away']['hours'] == 3
    finally:
        stop(server, thread)


def test_api_reports_rule_versions_for_an_old_save(tmp_path):
    old = pet(42, rules=2)
    old.apply({'kind': 'advance', 'value': 6})
    path = tmp_path / 'pet.json'
    save_atomic(path, old, time.time())
    server, thread, base = serve(path)
    try:
        status, data = get(base + '/api/state')
        assert status == 200 and data['state']['rules'] == 2 and data['state']['latest_rules'] == RULES
        assert json.loads(path.read_text(encoding='utf-8'))['version'] == 2
    finally:
        stop(server, thread)


# ---------------------------------------------------------------- 7. Chinese / Spanish
ES_BLOCK = APP[APP.index('const ES={'):APP.index('\n};', APP.index('const ES={'))]
ES_KEYS = set(re.findall(r"'((?:[^'\\]|\\.)*)':'", ES_BLOCK))
PATTERNS = [re.compile('^' + p + '$', re.S) for p in re.findall(r'\[/\^(.*?)\$/s?,', APP)]


def translatable(text):
    return text in ES_KEYS or any(p.match(text) for p in PATTERNS)


def test_every_diary_text_and_error_has_spanish():
    texts = set(NEIGHBOR_TEXT.values())
    for rules in range(1, RULES + 1):
        for seed in (1, 42, 901):
            s = pet(seed, ('garden', 'book', 'music'), rules=rules)
            s.apply({'kind': 'name', 'value': 'Brote'})
            hours(s, 40 * 24)
            texts |= {e['title'] for e in s.events} | {e['text'] for e in s.events}
    source = (ROOT / 'pet' / 'engine.py').read_text(encoding='utf-8') + (ROOT / 'pet' / 'server.py').read_text(encoding='utf-8')
    texts |= set(re.findall(r"(?:ValueError|LimitReached)\('([^']+)'\)", source))
    texts |= set(re.findall(r"'error':'([^']+)'", source)) - {'Not found'}   # 404 for unknown paths; the page never shows it
    missing = sorted(t for t in texts if not translatable(t))
    assert not missing


def test_page_labels_have_spanish():
    labels = set(re.findall(r'data-i18n>([^<]+)<', HTML))
    assert '小屋' in labels
    assert not sorted(l for l in labels if l not in ES_KEYS)


def test_ui_message_sets_match_in_both_languages():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js not installed')
    start = APP.index('const hh=')
    block = APP[start:APP.index('\n};', APP.index('const UI={')) + 3]
    script = block + ('const keys=o=>Object.keys(o).sort().map(k=>typeof o[k]==="object"?k+"{"+keys(o[k])+"}":k).join(",");'
                      'console.log(JSON.stringify([keys(UI.zh),keys(UI.es)]));')
    zh, es = json.loads(subprocess.run([node, '-e', script], capture_output=True, text=True,
                                       encoding='utf-8', check=True).stdout)
    assert zh == es
    for key in ('rulesOld', 'limitNote', 'awaySkipped', 'neighborRules', 'scoreLine', 'memoryDecisive'):
        assert key in zh
