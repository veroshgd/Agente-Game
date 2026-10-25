"""Round 4 of 2026-10-23 (experiment, NOT a rule version): the corrected phase-share counting of
pet/validate_read.py (pet/recheck_read_phases.py) and the reading-interest candidate (engine
INTEREST_*, pet/validate_interest.py). v1-v6 replays are pinned elsewhere."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
import pet.engine as engine
from pet import recheck_read_phases as RP
from pet import validate_interest as VI
from pet import run_foresight_validation as RV
from pet import validate_read as VR
from pet.engine import RULES, Session
from make_rules_baseline_v5 import behavior_digest

REF = engine.READ_VALUE_REF


def pet(arm='interest', seed=42, items=('book',), clarity=None):
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


# ---------------------------------------------------------------- phase-share correction
@pytest.mark.parametrize('arm', ['base', 'base2'])
def test_plastic_6006_away_intervention_fails_once_phases_are_marked(arm):
    frozen = VR.plastic_life(6006, arm)
    phased = RP.plastic_life_phased(6006, arm)
    assert [m['fingerprint'] for m in frozen] == [m['fingerprint'] for m in phased]     # nothing lived changes
    assert all(list(m['phases']) == ['growth'] for m in frozen)                         # frozen: one 110-day phase
    away = next(m for m in phased if m['branch'] == 'away')
    assert list(away['phases']) == ['growth', 'common', 'intervention', 'recovery']
    assert away['phases']['intervention']['below20'] == pytest.approx(0.1056, abs=5e-5)
    assert away['phases']['intervention']['fails'] == ['below20'] and away['h_pass']    # whole life still passes
    assert not next(m for m in frozen if m['fingerprint'] == away['fingerprint'])['phase_fails']


def test_union_dedupe_keeps_checks_of_every_run():
    def rec(life, fp, phase_fails):
        return {'life_id': life, 'fingerprint': fp, 'fails': [], 'h_pass': True, 'phase_fails': phase_fails,
                'phases': {'growth': {'fails': []}, **({'swap': {'fails': phase_fails}} if phase_fails else {})}}
    lives = [rec('keep', 'x', []), rec('swap', 'x', ['below20']), rec('other', 'y', [])]
    assert L_safety(lives)['phase_pass'] == 2                            # first-run dedupe loses the swap check
    u = RP.safety_union(lives)
    assert u['phase_fails'] == 1 and u['checks_lost_by_first_run_dedupe'][0]['lost'] == ['below20']


def L_safety(lives):
    groups = {}
    for m in lives:
        groups.setdefault(m['fingerprint'], m)
    return {'phase_pass': sum(m['h_pass'] and not m['phase_fails'] for m in groups.values())}


def test_correction_record_counts():
    r = json.loads((ROOT / 'docs' / 'pet_read_validation' / 'correction_phases_recheck.json').read_text(encoding='utf-8'))
    c = lambda sample, arm, step: r[sample]['counts'][arm][step]['phase_fails']
    assert (c('base2_dev', 'base', 'frozen'), c('base2_dev', 'base2', 'frozen'), c('read_dev', 'read_value', 'frozen')) == (9, 10, 13)
    assert (c('base2_dev', 'base', 'phases_union'), c('base2_dev', 'base2', 'phases_union')) == (10, 11)
    assert (c('read_dev', 'read_value', 'phases_union'), c('read_dev', 'read_nodecision', 'phases_union')) == (13, 10)
    assert all(r[k]['behaviour_unchanged'] == {'fingerprints_identical': True, 'rng_end_identical': True}
               for k in ('base2_dev', 'base2_review_7021_7040', 'read_dev'))
    assert r['verdicts']['base2_dev_phase_not_above_base']['phases_union'] is False
    assert r['verdicts']['read_dev_H_phase_not_above_control']['phases_union'] is False
    assert (ROOT / 'docs' / 'pet_read_validation' / 'CORRECTION_PHASES.md').exists()


# ---------------------------------------------------------------- interest mechanism
def test_flags_are_off_for_every_rule_version():
    assert RULES == 5
    for rules in range(1, 7):
        a = Session(rules=rules).agent
        assert not a.read_interest and a.read_alpha_min == engine.EVAL_ALPHA_MIN and a.read_I == REF


def test_unread_pet_has_no_interest_and_no_term():
    s = live(pet('interest', 42, ('garden',)), 5)
    a = s.agent
    assert a.read_n == 0 and a.read_I == REF and a.read_value_term() == 0.0


def test_interest_learns_only_from_clear_short_term_results():
    a = pet().agent
    for _ in range(40):
        a.read_experience('read', 1, {'gain': REF})       # neutral results: no evidence either way
    a.daily(0)
    assert a.read_I == REF
    b = pet().agent
    for _ in range(40):
        b.read_experience('read', 1, {'gain': 0.9})
    w = b.interest_weight()
    b.daily(0)
    assert b.read_I == pytest.approx(REF + engine.INTEREST_RATE * w * (0.9 - REF), rel=1e-9)


def test_interest_fades_without_reading_and_is_changed_by_contrary_results():
    a = pet().agent
    for d in range(20):
        for _ in range(3):
            a.read_experience('read', 1, {'gain': 0.9})
        a.daily(d)
    high = a.read_I
    c = copy.deepcopy(a)
    for d in range(20, 50):
        c.daily(d)                                         # no reading days
    assert REF < c.read_I < high and c.read_I - REF == pytest.approx((high - REF) * engine.EVAL_KEEP ** 30)
    for d in range(20, 60):
        for _ in range(3):
            a.read_experience('read', 1, {'gain': 0.1})
        a.daily(d)
    assert a.read_I < REF < high                           # contrary results reverse it: no lock


def test_one_term_with_the_same_bound():
    for arm in ('read_value', 'interest', 'read_lowrate', 'interest_flat'):
        a = pet(arm).agent
        for V, I in ((1.0, 1.0), (0.0, 0.0), (1.0, 0.0)):
            a.read_V, a.read_n, a.read_I = V, 1e9, I
            assert -0.5 - 1e-9 <= a.read_value_term() <= 0.5 + 1e-9
    a = pet('interest').agent
    a.read_V, a.read_n, a.read_I = 0.9, 30.0, 0.7
    short = 30 / 40 * (0.9 - REF)
    assert a.read_value_term() == pytest.approx((short + 0.2) / 2)
    a.read_interest_in_decision = False
    assert a.read_value_term() == pytest.approx(short)


def test_consolidation_draws_no_random_number():
    s = live(pet('interest', 3001, ('book', 'garden'), clarity=0.9), 10)
    a = s.agent
    rng = a.rng.getstate()
    a.read_today = 3
    a.consolidate_interest()
    assert a.rng.getstate() == rng


def test_long_term_part_off_is_the_current_mechanism_exactly():
    x = live(pet('read_value', 3001, ('book', 'garden'), clarity=0.9), 40)
    y = live(pet('interest_nodecision', 3001, ('book', 'garden'), clarity=0.9), 40)
    assert behavior_digest(x) == behavior_digest(y) and y.agent.read_I != REF


def test_lowrate_control_is_only_the_floor():
    a, b = pet('read_value').agent, pet('read_lowrate').agent
    assert b.read_alpha_min == 0.01 and not b.read_interest
    for x in (a, b):
        for _ in range(200):
            x.read_experience('read', 1, {'gain': 0.8})
        x.read_experience('read', 1, {'gain': 0.0})
    assert a.read_V == pytest.approx(0.8 * (1 - 0.05)) and b.read_V == pytest.approx(0.8 * (1 - 0.01))


def test_probe_isolates_the_reading_memory_and_never_touches_the_life():
    res, _ = VI.matched(9999, 'interest')
    assert res['growth_identical'] and res['probe_day0']['memory_off'] == 0.0
    assert res['memory_start']['clear']['I'] > REF > res['memory_start']['hard']['I']
    s = live(pet('interest', 42, ('book', 'garden'), clarity=0.9), 20)
    t = live(pet('interest', 42, ('book', 'garden'), clarity=0.3), 20)
    before = behavior_digest(s), s.agent.read_I
    VI.probe(s.agent, t.agent, s.tick // 24)
    assert (behavior_digest(s), s.agent.read_I) == before


def test_criteria_fixed_and_validation_seeds_unused():
    # 2026-10-25 round 9: 7041-7060 are no longer free; no earlier round listed them, and they were used once,
    # only by the guarded foresight validation (reservation record).
    assert RV.seeds_used_only_by_this_validation() and VI.VALIDATION_SEEDS[0] == 7041
    assert VI.CANDIDATE == 'interest' and VI.CRITERIA['P1_min_late_gap'] == 0.005
    assert VI.CRITERIA['C1_min_keep_minus_swap'] == 0.01
