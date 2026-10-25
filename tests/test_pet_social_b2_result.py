"""Round 12 recorded result (kept apart from tests/test_pet_social_b2.py, registered before the run).
B2 FAILED P3, R1 and R2; nothing was retuned; no seed from 7061 was used."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet import validate_social_b2 as VB

D = ROOT / 'docs' / 'pet_social_b2'


def test_recorded_result():
    r = json.loads((D / 'social_b2_dev_result.json').read_text(encoding='utf-8'))
    assert r['config_id'] == VB.CONFIG_ID and r['checks'] == {'same_as_round11': {'ref': True, 'none': True, 'B': True}}
    assert [k for k, v in r['final'].items() if v is not True] == ['P3_social_persists', 'R1_reading_adapts', 'R2_social_adapts', 'pass']
    d = r['diagnosis']
    assert d['B']['instrument_changes_nothing_all'] and d['B2']['instrument_changes_nothing_all']
    g = d['B2']['read_change|term|gap_by_day']
    assert g[0]['mean'] > 0 > g[-1]['mean']                                  # the memory term did reverse
    assert d['B2']['read_change|I|gap_by_day'][-1]['mean'] > 0               # the long-term part had not yet


def test_fixed_files_unchanged():
    for line in (D / 'sha256_fixed_before_any_run.txt').read_text().splitlines():
        if not line.startswith('#'):
            h, name = line.split()
            assert hashlib.sha256((ROOT / name.lstrip('*')).read_bytes()).hexdigest() == h, name
