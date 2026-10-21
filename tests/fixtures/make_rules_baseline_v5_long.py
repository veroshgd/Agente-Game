"""Generated ONCE, on 2026-10-21, with the v5 engine from before the v6 round (commit a0cc58a).

v6 changes goal choice when the home runs down. These 60-day v5 plays pass through the
home dips the v6 fix targets (goal locks around days 30-50), so they show that v5 saves
still replay exactly as before. Behavior and explanation digests as in
make_rules_baseline_v5.py. Do not regenerate with newer code.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pet.engine import Session
from make_rules_baseline_v5 import _h, behavior_digest, explanation_records

SEEDS = (1, 42, 901, 7, 123, 2024)
SCENARIOS = {'garden_invite': ['garden', 'invite'], 'all_invite': ['garden', 'book', 'music', 'invite']}

def play(seed, items):
    s = Session(seed, 5)
    for it in items:
        s.apply({'kind': 'invite', 'value': None} if it == 'invite' else {'kind': 'object', 'value': it})
    for i, step in enumerate([1] * 5 + [6] * 3 + [24] * 59):
        s.apply({'kind': 'advance', 'value': step})
        if i in (12, 40) and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
    return s

if __name__ == '__main__':
    cases = []
    for seed in SEEDS:
        for name, items in SCENARIOS.items():
            s = play(seed, items)
            cases.append({'scenario': name, 'archive': s.archive(), 'behavior': behavior_digest(s),
                          'explanation': _h(explanation_records(s))})
    out = Path(__file__).with_name('rules_baseline_v5_long.json')
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=0), encoding='utf-8')
    print(len(cases), 'cases ->', out)
