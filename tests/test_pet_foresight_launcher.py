"""Round 9 (2026-10-25): the guarded validation launcher (pet/run_foresight_validation.py). Every test works
on a temporary copy of docs/pet_foresight with a FAKE runner: no validation seed is ever simulated here."""
import json
import os
import shutil
import threading
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet import run_foresight_validation as RV

REAL = ROOT / 'docs' / 'pet_foresight'


@pytest.fixture
def dst(tmp_path):
    d = tmp_path / 'pet_foresight'
    d.mkdir()
    for name in ('foresight_dev_result.json', RV.HASHES):
        shutil.copy(REAL / name, d / name)
    return d


def fake_ok(d):
    (d / RV.RESULT).write_text(json.dumps({'final': {'pass': True}}), encoding='utf-8')
    print('fake run')


def never(d):
    raise AssertionError('the runner must not be reached')


@pytest.mark.parametrize('mode', ['validation', 'dev', 'Run', 'chek', 'run '])
def test_unknown_modes_rejected_before_anything(mode, monkeypatch):
    monkeypatch.setattr(RV, 'run', lambda *a, **k: (_ for _ in ()).throw(AssertionError('reached')))
    with pytest.raises(SystemExit) as e:
        RV.main([mode])
    assert e.value.code != 0


def test_preflight_passes_on_the_frozen_files(dst):
    info = RV.preflight(dst)
    assert info['seeds'] == RV.SEEDS and not (dst / RV.RESERVATION).exists()


def test_hash_mismatch_refused(dst):
    t = (dst / RV.HASHES).read_text(encoding='utf-8')
    h = RV.registered_hashes(dst)['pet/engine.py']
    (dst / RV.HASHES).write_text(t.replace(h, '0' * 64), encoding='utf-8')
    with pytest.raises(RV.PreflightError, match='hash mismatch: pet/engine.py'):
        RV.run(dst, never)
    assert not (dst / RV.RESERVATION).exists()


@pytest.mark.parametrize('edit,msg', [(lambda r: r.update(config_id='x'), 'config_id'),
                                      (lambda r: r['criteria'].update(E1_min_gap=0.0), 'criteria'),
                                      (lambda r: r['final'].update(H2_phase_not_above_current=False, **{'pass': False}), 'did not pass'),
                                      (lambda r: r.update(sample='validation'), 'not a dev sample')])
def test_config_or_dev_problems_refused(dst, edit, msg):
    p = dst / 'foresight_dev_result.json'
    r = json.loads(p.read_text(encoding='utf-8'))
    edit(r)
    p.write_text(json.dumps(r), encoding='utf-8')
    with pytest.raises(RV.PreflightError, match=msg):
        RV.run(dst, never)
    assert not (dst / RV.RESERVATION).exists()


@pytest.mark.parametrize('name', [RV.RESERVATION, RV.STATUS, RV.LOG, RV.RESULT])
def test_any_earlier_validation_refused(dst, name):
    (dst / name).write_text('{}', encoding='utf-8')
    with pytest.raises(RV.PreflightError, match='earlier validation'):
        RV.run(dst, never)


def test_reservation_is_atomic_and_exclusive(dst):
    RV.reserve(dst, {'seeds': RV.SEEDS})
    with pytest.raises(FileExistsError):
        RV.reserve(dst, {'seeds': RV.SEEDS})


def test_concurrent_starts_only_one_reserves(dst):
    results = []

    def attempt():
        try:
            RV.reserve(dst, {'seeds': RV.SEEDS})
            results.append('ok')
        except FileExistsError:
            results.append('refused')
    ts = [threading.Thread(target=attempt) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(results) == ['ok'] + ['refused'] * 7


def test_success_records_and_forbids_a_second_run(dst):
    final = RV.run(dst, fake_ok)
    assert final == {'pass': True} and RV.state(dst) == 'done'
    assert not os.access(dst / RV.RESULT, os.W_OK)                       # result read-only
    assert 'fake run' in (dst / RV.LOG).read_text(encoding='utf-8')
    res = json.loads((dst / RV.RESERVATION).read_text(encoding='utf-8'))
    assert res['seeds'] == RV.SEEDS and res['config_id']
    with pytest.raises(RV.PreflightError, match='earlier validation'):
        RV.run(dst, never)
    os.chmod(dst / RV.RESULT, 0o666)                                     # let tmp_path clean up


def test_failure_after_start_keeps_everything_and_never_retries(dst):
    calls = []

    def crash(d):
        calls.append(1)
        (d / 'partial.json').write_text('{"part": 1}', encoding='utf-8')
        print('half way')
        raise RuntimeError('boom')
    with pytest.raises(RuntimeError, match='boom'):
        RV.run(dst, crash)
    assert calls == [1]
    assert (dst / RV.RESERVATION).exists() and (dst / 'partial.json').exists()
    s = json.loads((dst / RV.STATUS).read_text(encoding='utf-8'))
    assert s['state'] == 'failed' and 'boom' in s['traceback'] and 'partial.json' in s['files']
    log = (dst / RV.LOG).read_text(encoding='utf-8')
    assert 'half way' in log and 'boom' in log
    with pytest.raises(RV.PreflightError, match='earlier validation'):
        RV.run(dst, never)


def test_runner_without_result_counts_as_failed(dst):
    with pytest.raises(RuntimeError, match='no result file'):
        RV.run(dst, lambda d: None)
    assert RV.state(dst) == 'failed' and (dst / RV.RESERVATION).exists()
