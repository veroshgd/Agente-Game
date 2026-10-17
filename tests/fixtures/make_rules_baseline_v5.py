"""Generated ONCE, on 2026-10-17, with the v5 engine before the explanation fix.

Two digests per case: 'behavior' (actions, traits, preferences, body, goal, rng states)
must never change for v5 saves; 'explanation' (decision records) is kept so changes to
explanations can be listed explicitly instead of hidden by regenerating everything.
Do not regenerate with newer code.
"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pet.engine import Session

BEHAVIOR_EVENT_FIELDS = ('id', 'tick', 'kind', 'title', 'text', 'action', 'core_action', 'cause_ids',
                         'memory_bonus', 'score_bonus', 'invited', 'before', 'after', 'neighbor',
                         'enjoyment', 'chance_to_meet', 'visit_chance')

def _h(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

def behavior_digest(s):
    a = s.agent
    return _h({'events': [{k: e[k] for k in BEHAVIOR_EVENT_FIELDS if k in e} for e in s.events],
               'traits': a.traits, 'prefs': a.prefs, 'pref_evidence': a.pref_evidence,
               'shelter': a.shelter, 'hunger': a.hunger, 'energy': a.energy, 'condition': a.condition,
               'inventory': a.inventory, 'goal': a.goal, 'shared': a.shared, 'name': s.name, 'tick': s.tick,
               'rng': repr(a.rng.getstate()), 'world_rng': repr(s.world.rng.getstate())})

def explanation_records(s):
    return [e.get('decision') for e in s.events if e['kind'] == 'action']

SCENARIOS = {
    'garden_invite': ['garden', 'invite'],
    'all_invite': ['garden', 'book', 'music', 'invite'],
    'book': ['book'],
}

def play(seed, items):
    s = Session(seed, 5)
    for it in items:
        s.apply({'kind': 'invite', 'value': None} if it == 'invite' else {'kind': 'object', 'value': it})
    for i, step in enumerate([1] * 5 + [6] * 3 + [24] * 30):
        s.apply({'kind': 'advance', 'value': step})
        if i in (12, 25) and s.world.has('garden') and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
    return s

if __name__ == '__main__':
    cases = []
    for seed in (1, 42, 901, 2001):
        for name, items in SCENARIOS.items():
            s = play(seed, items)
            cases.append({'scenario': name, 'archive': s.archive(), 'behavior': behavior_digest(s),
                          'explanation': _h(explanation_records(s)),
                          'pref_decisive': [bool(d and d.get('pref_decisive')) for d in explanation_records(s)]})
    out = Path(__file__).with_name('rules_baseline_v5.json')
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=0), encoding='utf-8')
    print(len(cases), 'cases ->', out)
