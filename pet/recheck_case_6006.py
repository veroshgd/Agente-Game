"""Correction record (round 8, 2026-10-25) for the 6006 / rep2 / hard / no_offtask case of
pet/recheck_plan_days.py: the values the morning goal update really saw.

    python -m pet.recheck_case_6006 [out_dir]      # default docs/pet_plan_components/correction_days

recheck_plan_days.case_study reported the home of the hour-0 DECISION, which is after that hour's ageing
(-0.35); sim.Agent.tick runs update_goal before it. Here PetAgent.update_goal is wrapped (on this run
only, restored after) to record at its entry: home, the open plan and its age, and the priorities the
ordered update compares (propose_goals after the same-morning done / stalled closes, read-only; the
wrapper calls it once more, which only rewrites goal_pref_boost before update_goal rewrites it again).
The life is checked to be the same as before (fingerprint, generator).
"""
import copy
import json
import sys
from contextlib import contextmanager
from pathlib import Path

from . import diag_plan as DP
from . import engine
from . import lifestats as L
from . import recheck_plan_days as R
from . import validate_read as VR
from .engine import core

DAYS = range(24, 38)


@contextmanager
def entry_recorder(log):
    orig = engine.PetAgent.update_goal

    def wrapped(self, day):
        g = self.goal
        prog = self.goal_progress(g) if g else None
        closes = self._core_closes(g, day) if g else None
        pri = {t: p for t, p, _ in self.propose_goals(day)}
        log.append({'day': day, 'home': self.shelter, 'goal': g['type'] if g else None,
                    'age': day - g['created_day'] if g else None, 'in_min_stay': bool(g) and day - g['created_day'] < core.GOAL_MIN_DAYS,
                    'core_closes': closes, 'progress': prog, 'pri': pri,
                    'trigger_home': self.shelter < engine.HOME_INTERRUPT_BELOW,
                    'repair_lead': (pri.get('improve_home', float('-inf')) - pri.get(g['type'], 0.0)) if g else None,
                    'margin': core.GOAL_SWITCH_MARGIN})
        return orig(self, day)
    engine.PetAgent.update_goal = wrapped
    try:
        yield
    finally:
        engine.PetAgent.update_goal = orig


def run(seed=6006, rep=2, pet='hard', cond='no_offtask'):
    pets0 = R.pets_at_common(seed)
    c = copy.deepcopy(pets0[pet])
    for k, v in DP.CONDITIONS[cond].items():
        setattr(c.agent, k, v)
    c.agent.read_audit = True
    if rep:
        c.agent.rng.seed(seed * 1000 + rep)
    log = []
    with entry_recorder(log):
        VR.run_hours(c, DP.VI.COMMON * 24)
    common = [x | {'common_day': x['day'] - DP.VI.GROW} for x in log if x['day'] - DP.VI.GROW in DAYS]
    return {'case': f'{seed}/rep{rep}/{pet}/{cond}', 'fingerprint': L.fingerprint(c.trace), 'rng': R.rng_digest(c), 'entries': common}


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_plan_components' / 'correction_days'
    prev = json.loads((dst / 'recheck_plan_days.json').read_text(encoding='utf-8'))['case']['lives']['no_offtask']
    out = run()
    out['same_life_as_recheck_plan_days'] = out['fingerprint'] == prev['fingerprint'] and out['rng'] == prev['rng']
    (dst / 'recheck_case_6006.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    for x in out['entries']:
        print(x['common_day'], round(x['home'], 2), x['goal'], x['age'], x['in_min_stay'], x['trigger_home'],
              None if x['repair_lead'] is None else round(x['repair_lead'], 3), x['core_closes'])
    print('same life:', out['same_life_as_recheck_plan_days'])


if __name__ == '__main__':
    main()
