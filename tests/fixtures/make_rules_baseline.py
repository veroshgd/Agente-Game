"""Generated the rules baseline ONCE, on 2026-10-17, with the pre-v4 engine (rules 1-3).

Do not regenerate it with newer code: its job is to prove that new code still replays
old saves exactly as the old code did. Digest = the fields old engines produced.
"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pet.engine import Session

OLD_EVENT_FIELDS = ('id', 'tick', 'kind', 'title', 'text', 'action', 'core_action', 'cause_ids',
                    'memory_bonus', 'score_bonus', 'invited', 'before', 'after', 'missed_neighbor')

def digest(s):
    a = s.agent
    data = {'events': [{k: e[k] for k in OLD_EVENT_FIELDS if k in e} for e in s.events],
            'traits': a.traits, 'shelter': a.shelter, 'hunger': a.hunger, 'energy': a.energy,
            'condition': a.condition, 'inventory': a.inventory, 'name': s.name, 'tick': s.tick}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def play(rules, seed, items):
    s = Session(seed, rules)
    s.apply({'kind': 'name', 'value': 'Prueba'})
    for it in items:
        s.apply({'kind': 'invite', 'value': None} if it == 'invite' else {'kind': 'object', 'value': it})
    for step in [1] * 5 + [6] * 3 + [24] * 20:
        s.apply({'kind': 'advance', 'value': step})
    return s

if __name__ == '__main__':
    cases = []
    for rules in (1, 2, 3):
        for seed in (1, 42, 901):
            for items in ([], ['garden', 'invite'], ['garden', 'book', 'music', 'invite']):
                s = play(rules, seed, items)
                cases.append({'archive': s.archive(), 'digest': digest(s), 'tick': s.tick,
                              'shelter': round(s.agent.shelter, 3)})
    out = Path(__file__).with_name('rules_baseline.json')
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=0), encoding='utf-8')
    print(len(cases), 'cases ->', out)
