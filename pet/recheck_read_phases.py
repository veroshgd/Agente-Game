"""Correction record (round 4, 2026-10-23) for the phase-share safety check of pet/validate_read.py.
validate_read.py is frozen (sha256 in docs/pet_read_validation/sha256_before_read_dev.txt) and is NOT
edited; this module re-runs the same lives and recounts.

    python -m pet.recheck_read_phases [out_dir]     # default docs/pet_read_validation

Two defects of the frozen counting:
  1. plastic_life() marks no phase after growth: its 110 days (growth 20 + common 20 + intervention
     30 + recovery 40) were checked as ONE 'growth' phase, so a bad 30-day intervention was averaged
     away by the whole life. Both of its branches also share one life_id.
     Fix here: the same calls in the same order, plus s.phase('common' / 'intervention' / 'recovery').
     phase() only appends a marker (no state, no random draw): the trace fingerprint of every life
     must stay identical (checked below, and in tests/test_pet_interest.py).
  2. lifestats.dedupe() keeps the FIRST run of a trajectory with its phase marks. Runs of the same
     trajectory with other marks (e.g. a 'swap' phase of a read_nodecision pet, which behaves exactly
     like its 'keep' twin) lost their phase checks. Fix here: per unique trajectory, the phase
     failures are the union over all its runs.
The counts are reported for each step separately: frozen, + phase marks, + union.
"""
import copy
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

from . import lifestats as L
from . import validate_read as VR
from . import validate_v5 as v5

STEPS = ('frozen', 'phases', 'phases_union')


def rng_digest(s):
    return hashlib.sha256(repr(s.agent.rng.getstate()).encode()).hexdigest()[:16]


def plastic_life_phased(seed, arm):
    """validate_read.plastic_life with phase marks (and the branch in the id). Same calls, same order."""
    s = VR.new_pet(seed, arm)
    s.apply({'kind': 'object', 'value': 'book'})
    VR.run_hours(s, VR.GROW * 24)
    v5.uniform(s)
    out = []
    s.phase('common')
    VR.run_hours(s, VR.PL_COMMON * 24)
    for branch in ('stay', 'away'):
        c = copy.deepcopy(s)
        c.phase('intervention')
        VR.run_hours(c, VR.PL_AWAY * 24, invite_daily=branch == 'away')
        c.phase('recovery')
        VR.run_hours(c, VR.PL_AFTER * 24)
        rec = L.life_record(c, life_id=f'{arm}|plastic|{seed}|{branch}', arm=arm, design='plastic', seed=seed, branch=branch)
        rec['rng_end'] = rng_digest(c)
        out.append(rec)
    return out


def plastic_rng_frozen(seed, arm):
    """rng end states of the frozen plastic_life (for the 'no behaviour change' check)."""
    s = VR.new_pet(seed, arm)
    s.apply({'kind': 'object', 'value': 'book'})
    VR.run_hours(s, VR.GROW * 24)
    v5.uniform(s)
    VR.run_hours(s, VR.PL_COMMON * 24)
    out = []
    for branch in ('stay', 'away'):
        c = copy.deepcopy(s)
        VR.run_hours(c, VR.PL_AWAY * 24, invite_daily=branch == 'away')
        VR.run_hours(c, VR.PL_AFTER * 24)
        out.append(rng_digest(c))
    return out


def job(args):
    seed, arm, with_read = args
    j = VR.seed_job(args)                       # frozen lives (frozen plastic_life included)
    j['plastic_phased'] = plastic_life_phased(seed, arm)
    j['plastic_rng_frozen'] = plastic_rng_frozen(seed, arm)
    return j


def safety_union(lives):
    """safety_summary with the phase failures of a trajectory = union over all its runs."""
    groups = {}
    for m in lives:
        groups.setdefault(m['fingerprint'], []).append(m)
    uniq, lost, multi_marks = [], [], 0
    for fp, runs in groups.items():
        first = runs[0]
        assert all(r['fails'] == first['fails'] for r in runs)          # same trace -> same whole life
        union = sorted({k for r in runs for k in r['phase_fails']})
        marks = {tuple(sorted(r['phases'])) for r in runs}
        multi_marks += len(marks) > 1
        extra = [k for k in union if k not in first['phase_fails']]
        if extra:
            lost.append({'life': first['life_id'], 'also': [r['life_id'] for r in runs[1:]], 'lost': extra,
                         'from': {r['life_id']: {p: v['fails'] for p, v in r['phases'].items() if v['fails']}
                                  for r in runs if r['phase_fails']}})
        uniq.append({'life_id': first['life_id'], 'runs': [r['life_id'] for r in runs], 'h_pass': first['h_pass'],
                     'phase_pass': first['h_pass'] and not union, 'phase_fails': union})
    return {'runs': len(lives), 'unique_trajectories': len(uniq), 'pass': sum(u['h_pass'] for u in uniq),
            'phase_pass': sum(u['phase_pass'] for u in uniq), 'phase_fails': sum(not u['phase_pass'] for u in uniq),
            'trajectories_with_several_phase_marks': multi_marks, 'checks_lost_by_first_run_dedupe': lost,
            'failing': [{'life': u['life_id'], 'also': u['runs'][1:], 'phase_fails': u['phase_fails']}
                        for u in uniq if not u['phase_pass']]}


def lives_of(j, step):
    plastic = j['plastic'] if step == 'frozen' else j['plastic_phased']
    return j['routes'] + j['pair'] + plastic + j.get('matched_lives', []) + j.get('natural_lives', [])


def count(jobs, safe, arm, step):
    lives = [m for j in jobs if j['arm'] == arm for m in lives_of(j, step)] + [m for m in safe if m['arm'] == arm]
    if step == 'phases_union':
        return safety_union(lives)
    s = L.safety_summary(lives)
    return {'runs': s['runs'], 'unique_trajectories': s['unique_trajectories'], 'pass': s['pass'],
            'phase_pass': s['phase_pass'], 'phase_fails': s['unique_trajectories'] - s['phase_pass'],
            'failing': [{'life': f['life'], 'also': f['also'], 'phase_fails': f['phase_fails']} for f in s['failing']]}


def same_behaviour(jobs):
    """Phase marks change nothing lived: same fingerprints and rng end states as the frozen lives."""
    fp = all([m['fingerprint'] for m in j['plastic']] == [m['fingerprint'] for m in j['plastic_phased']] for j in jobs)
    rng = all(j['plastic_rng_frozen'] == [m['rng_end'] for m in j['plastic_phased']] for j in jobs)
    return {'fingerprints_identical': fp, 'rng_end_identical': rng}


def plastic_6006(jobs):
    out = {}
    for j in jobs:
        if j['seed'] != 6006:
            continue
        for m in j['plastic_phased']:
            out[f"{j['arm']}|{m['branch']}"] = {p: {'below20': v['below20'], 'min_home': v['min_home'], 'fails': v['fails']}
                                                for p, v in m['phases'].items()}
    return out


def run(arms, seeds, with_read):
    with Pool(14) as pool:
        jobs = pool.map(job, [(sd, arm, with_read) for arm in arms for sd in seeds])
        safe = pool.map(VR.safe_job, [(sd, it, arm) for arm in arms for sd in VR.SAFE_SEEDS for it in VR.SAFE_ITEMS])
    res = {arm: {step: count(jobs, safe, arm, step) for step in STEPS} for arm in arms}
    return res, same_behaviour(jobs), plastic_6006(jobs)


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'docs' / 'pet_read_validation'
    dst.mkdir(parents=True, exist_ok=True)
    report = {'config_id': VR.CONFIG_ID, 'steps': STEPS}
    for name, arms, seeds, with_read in (('base2_dev', ('base', 'base2'), VR.DEV_SEEDS, False),
                                         ('base2_review_7021_7040', ('base', 'base2'), VR.REVIEW_SEEDS, False),
                                         ('read_dev', ('read_nodecision', 'read_value', 'read_flat'), VR.DEV_SEEDS, True)):
        res, same, p6006 = run(arms, seeds, with_read)
        report[name] = {'counts': res, 'behaviour_unchanged': same, 'plastic_6006': p6006}
    b, r = report['base2_dev']['counts'], report['read_dev']['counts']
    report['verdicts'] = {
        'base2_dev_phase_not_above_base': {s: b['base2'][s]['phase_fails'] <= b['base'][s]['phase_fails'] for s in STEPS},
        'read_dev_H_phase_not_above_control': {s: r['read_value'][s]['phase_fails'] <= r['read_nodecision'][s]['phase_fails']
                                               for s in STEPS}}
    (dst / 'correction_phases_recheck.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                                                        encoding='utf-8')
    show = {k: ({a: {s: {x: c[s][x] for x in ('unique_trajectories', 'pass', 'phase_fails')} for s in STEPS}
                 for a, c in v['counts'].items()} | {'behaviour_unchanged': v['behaviour_unchanged']})
            for k, v in report.items() if isinstance(v, dict) and 'counts' in v}
    show['verdicts'] = report['verdicts']
    show['plastic_6006'] = report['base2_dev']['plastic_6006']
    show['lost_by_dedupe'] = {k: {a: c['phases_union']['checks_lost_by_first_run_dedupe'] for a, c in v['counts'].items()}
                              for k, v in report.items() if isinstance(v, dict) and 'counts' in v}
    print(json.dumps(L.rounded(show), ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
