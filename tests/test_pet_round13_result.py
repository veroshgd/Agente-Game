"""Round 13 recorded diagnosis (kept apart from tests/test_pet_round13.py, registered before the run).
Diagnostics only: no candidate, no validation, no seed from 7061."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'docs' / 'pet_round13'


def test_recorded_checks_and_reading_result():
    r = json.loads((D / 'round13_result.json').read_text(encoding='utf-8'))
    c = r['checks']
    assert all(v is True for k, v in c.items() if k != 'social_trace_instrument_ok') and all(c['social_trace_instrument_ok'].values())
    assert r['compat']['pass']
    d = r['reading']['dR1']
    assert d['no_close']['ci95'][1] < -0.005 and d['no_close']['mean'] <= -0.005            # supported by the fixed rule
    assert d['no_sat']['ci95'][0] < 0 < d['no_sat']['ci95'][1]                             # not supported
    assert d['both'] == d['no_close']                                                      # predicted identical
    for k, v in r['reading'].items():
        if '|' in k:
            assert v['whole_life_fails'] == 0 and v['branch_phase_fails'] == 0


def test_social_interaction_is_subadditive_not_amplifying():
    r = json.loads((D / 'round13_result.json').read_text(encoding='utf-8'))
    inter = r['social_contrasts']['interaction']['R2']
    mains = (r['social_contrasts']['B2 - ref']['R2']['mean'], r['social_contrasts']['A - ref']['R2']['mean'])
    assert all(m < 0 for m in mains) and inter['ci95'][0] > 0       # opposite sign: not amplification by the written rule
    assert r['verdict']['social_amplification_flag'] is True        # the fixed code's flag ignored the sign (documented)


def test_protocol_files_unchanged():
    for line in (D / 'sha256_protocol_before_any_run.txt').read_text().splitlines():
        if not line.startswith('#'):
            h, name = line.split()
            assert hashlib.sha256((ROOT / name.lstrip('*')).read_bytes()).hexdigest() == h, name
