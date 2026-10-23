"""Generated ONCE, on 2026-10-23, with the engine of commit 2fab702 (before the pause round).

The candidate rules 6 (rest4 + home interrupt) are not a save version, so these are direct
Session(seed, 6) plays, plus the same plays with the old daily cap ('cap2': the
'interrupt only' arm of the 2026-10-23 experiments). They pass the home dips where the
interrupt acts, so they show that the pause experiment left v6 exactly as it was.
Do not regenerate with newer code.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pet.engine import Session, MILI_VISITS_PER_DAY
from make_rules_baseline_v5 import _h, behavior_digest, explanation_records

SEEDS = (1, 42, 901, 7, 123, 2024)
SCENARIOS = {'garden_invite': ['garden', 'invite'], 'all_invite': ['garden', 'book', 'music', 'invite']}
SCHEMES = {'rest4': None, 'cap2': (MILI_VISITS_PER_DAY, 0)}
DAYS = 80

def play(seed, items, scheme):
    s = Session(seed, 6)
    if SCHEMES[scheme]:
        s.agent.visit_cap, s.agent.visit_rest_hours = SCHEMES[scheme]
    for it in items:
        s.apply({'kind': 'invite', 'value': None} if it == 'invite' else {'kind': 'object', 'value': it})
    for d in range(DAYS):
        s.apply({'kind': 'advance', 'value': 24})
        if d in (12, 40) and s.tick >= s.agent.invitation_until:
            s.apply({'kind': 'invite', 'value': None})
    return s

if __name__ == '__main__':
    cases = []
    for seed in SEEDS:
        for name, items in SCENARIOS.items():
            for scheme in SCHEMES:
                s = play(seed, items, scheme)
                cases.append({'seed': seed, 'scenario': name, 'scheme': scheme, 'commands': s.commands,
                              'behavior': behavior_digest(s), 'explanation': _h(explanation_records(s)),
                              'goal_history': _h(s.agent.goal_history)})
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('rules_baseline_v6.json')
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=0), encoding='utf-8')
    print(len(cases), 'cases ->', out)
