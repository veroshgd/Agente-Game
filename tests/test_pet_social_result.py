"""Round 11 recorded development result (kept apart from tests/test_pet_social_interest.py, registered
before the run). Development FAILED on R1 only; nothing was retuned and no seed from 7061 was used."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet import validate_social as VS

D = ROOT / 'docs' / 'pet_social'


def test_recorded_dev_result():
    r = json.loads((D / 'social_dev_result.json').read_text(encoding='utf-8'))
    assert r['config_id'] == VS.CONFIG_ID and r['checks'] == {'ref_catalogue_is_validated_candidate': True}
    assert r['final']['pass'] is False
    assert [k for k, v in r['final'].items() if v is not True] == ['R1_reading_adapts', 'pass']
    assert -0.01 < r['values']['R1']['mean'] < 0 and r['values']['R1']['ci95'][1] < 0      # right direction, too small
    E = r['summary']['B_frozen']['effects']
    assert E['R1']['mean'] == 0 and E['R2']['mean'] == 0          # frozen: the new results reach nothing else (by construction)


def test_frozen_files_unchanged():
    for line in (D / 'sha256_criteria_fixed_before_any_run.txt').read_text().splitlines():
        if line.startswith('#'):
            continue
        h, name = line.split()
        assert hashlib.sha256((ROOT / name.lstrip('*')).read_bytes()).hexdigest() == h, name
