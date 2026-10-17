"""Generated the v4 baseline ONCE, on 2026-10-17, with the pre-v5 engine (rules 4).

Do not regenerate it with newer code: it proves new code replays v4 saves exactly as the
v4 engine did, including v4's diary reasons and decision records. rules_baseline.json
(v1-v3) stays as it was.
"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pet.engine import Session

V4_EVENT_FIELDS = ('id', 'tick', 'kind', 'title', 'text', 'action', 'core_action', 'cause_ids',
                   'memory_bonus', 'score_bonus', 'invited', 'before', 'after', 'neighbor', 'decision')

def digest_v4(s):
    a = s.agent
    data = {'events': [{k: e[k] for k in V4_EVENT_FIELDS if k in e} for e in s.events],
            'traits': a.traits, 'shelter': a.shelter, 'hunger': a.hunger, 'energy': a.energy,
            'condition': a.condition, 'inventory': a.inventory, 'name': s.name, 'tick': s.tick,
            'goal': a.goal, 'shared': a.shared}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

SCENARIOS = {
    'empty': [],
    'book': ['book'],
    'garden_invite': ['garden', 'invite'],
    'all_invite': ['garden', 'book', 'music', 'invite'],
}

def play(seed, items):
    s = Session(seed, 4)
    s.apply({'kind': 'name', 'value': 'Prueba'})
    for it in items:
        s.apply({'kind': 'invite', 'value': None} if it == 'invite' else {'kind': 'object', 'value': it})
    for i, step in enumerate([1] * 5 + [6] * 3 + [24] * 30):
        s.apply({'kind': 'advance', 'value': step})
        if i == 20 and s.world.has('garden') and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})       # a second invitation mid-way
    return s

if __name__ == '__main__':
    cases = []
    for seed in (1, 42, 901, 7, 2024):
        for name, items in SCENARIOS.items():
            s = play(seed, items)
            cases.append({'scenario': name, 'archive': s.archive(), 'digest': digest_v4(s),
                          'tick': s.tick, 'shelter': round(s.agent.shelter, 3)})
    out = Path(__file__).with_name('rules_baseline_v4.json')
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=0), encoding='utf-8')
    print(len(cases), 'cases ->', out)
