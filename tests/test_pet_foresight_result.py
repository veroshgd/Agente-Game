"""Round 8 recorded development result (kept apart from tests/test_pet_foresight.py, whose sha256 was
registered before the run). The candidate is frozen for an independent run; it is NOT adopted."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pet.engine as engine
from pet import validate_foresight as VF
from pet import validate_interest as VI
from pet import run_foresight_validation as RV

D = ROOT / 'docs' / 'pet_foresight'


def test_recorded_dev_result():
    r = json.loads((D / 'foresight_dev_result.json').read_text(encoding='utf-8'))
    assert r['final']['pass'] and all(r['final'].values())
    assert r['checks'] == {'current_catalogue_is_validate_interest': True, 'reading_runs_are_round6': True}
    s = r['summary']
    assert (s['current']['safety']['phase_fails'], s['both']['safety']['phase_fails']) == (12, 4)
    assert all(f['phase_fails'] == ['leisure'] and '|route|' in f['life'] and f['life'].endswith('|control')
               for f in s['both']['safety']['failing'])                    # growth of the no-object route, also in current
    assert r['config_id'] == VF.CONFIG_ID


def test_candidate_frozen_and_not_adopted():
    lines = [l.split() for l in (D / 'sha256_criteria_fixed_before_any_run.txt').read_text().splitlines() if not l.startswith('#')]
    for h, name in lines:
        if name.lstrip('*') == 'pet/validate_foresight.py':
            assert hashlib.sha256((ROOT / 'pet' / 'validate_foresight.py').read_bytes()).hexdigest() == h
    assert engine.RULES == 5 and not engine.Session().agent.home_foresight
    # round 9: the one independent validation has run (guarded launcher); still not adopted
    assert RV.seeds_used_only_by_this_validation() and VF.VALIDATION_SEEDS[0] == 7041
    assert RV.state(D) == 'done' and (D / 'foresight_validation_result.json').exists()


def test_recorded_validation_result():
    """The one run on 7041-7060 (round 9). Recorded as it came out; nothing retuned."""
    r = json.loads((D / 'foresight_validation_result.json').read_text(encoding='utf-8'))
    assert r['sample'] == 'validation' and r['seeds'] == list(range(7041, 7061)) and r['config_id'] == VF.CONFIG_ID
    assert r['final']['pass'] and all(r['final'].values())
    s = r['summary']
    assert (s['current']['safety']['phase_fails'], s['both']['safety']['phase_fails']) == (11, 6)
    assert s['both']['safety']['pass'] == s['both']['safety']['unique_trajectories'] == 572
    assert all(f['phase_fails'] == ['leisure'] and f['life'].endswith('|control') for f in s['both']['safety']['failing'])
    st = json.loads((D / 'validation_status.json').read_text(encoding='utf-8'))
    assert st['state'] == 'done' and st['passed'] is True
    assert hashlib.sha256((D / 'foresight_validation_result.json').read_bytes()).hexdigest() == st['result_sha256']
