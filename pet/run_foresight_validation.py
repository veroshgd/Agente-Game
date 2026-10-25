"""Guarded launcher for the ONE independent validation of the frozen round-8 candidate (2026-10-25, round 9).
pet/validate_foresight.py, pet/engine.py and tests/test_pet_foresight.py are frozen (sha256 registered
before the development run) and are NOT edited; this module only checks, reserves, runs and records.

    python -m pet.run_foresight_validation check     # preflight only: nothing is reserved or simulated
    python -m pet.run_foresight_validation run       # preflight, atomic reservation, then the validation ONCE

Any other mode (or a misspelling) is rejected before anything is read or written.
Preflight (both modes): the frozen files match their registered sha256; the configuration (CONFIG_ID,
conditions, parameters, criteria, seeds 7041-7060) equals the development result's; development passed
every criterion; no earlier validation exists in any state (reservation, status, log or result); and no
earlier round's seed list contains 7041-7060.
Run: the reservation file is created with O_CREAT | O_EXCL (atomic; a second or concurrent start fails)
and fsynced BEFORE any simulation. The protocol is validate_foresight.main('validation') itself, unchanged;
stdout / stderr go to a log. Its result file is then made read-only. If anything fails after the
reservation, the reservation, the log, the traceback and whatever was written are kept, and nothing is
retried: the seeds count as used whatever the outcome. validate_foresight keeps all results in memory
until its end, so a crash leaves no partial result file beyond the log.
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import stat
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DST = ROOT / 'docs' / 'pet_foresight'
MODES = ('check', 'run')
SEEDS = list(range(7041, 7061))
RESERVATION = 'VALIDATION_7041_7060_RESERVED.json'
STATUS = 'validation_status.json'
LOG = 'foresight_validation_console.txt'
RESULT = 'foresight_validation_result.json'
HASHES = 'sha256_criteria_fixed_before_any_run.txt'


class PreflightError(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def registered_hashes(dst):
    out = {}
    for line in (dst / HASHES).read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.startswith('#'):
            h, name = line.split()
            out[name.lstrip('*')] = h
    return out


def preflight(dst=DST, root=ROOT):
    from . import validate_foresight as VF
    from . import validate_interest as VI
    problems = []
    reg = registered_hashes(dst)
    for name in ('pet/validate_foresight.py', 'pet/engine.py', 'tests/test_pet_foresight.py'):
        if name not in reg:
            problems.append(f'no registered hash for {name}')
        elif sha(root / name) != reg[name]:
            problems.append(f'hash mismatch: {name}')
    dev_path = dst / 'foresight_dev_result.json'
    if not dev_path.exists():
        problems.append('no development result')
    else:
        dev = json.loads(dev_path.read_text(encoding='utf-8'))
        if dev.get('sample') != 'dev':
            problems.append('development result is not a dev sample')
        if not (dev.get('final', {}).get('pass') is True and all(v is True for v in dev['final'].values())):
            problems.append('development did not pass every criterion')
        for key, now in (('config_id', VF.CONFIG_ID), ('criteria', VF.CRITERIA), ('params', VF.PARAMS),
                         ('conditions', VF.CONDITIONS)):
            if json.dumps(dev.get(key), sort_keys=True) != json.dumps(now, sort_keys=True):
                problems.append(f'configuration differs from development: {key}')
    if list(VF.VALIDATION_SEEDS) != SEEDS:
        problems.append('validation seeds are not 7041-7060')
    if not VI.seeds_unused():
        problems.append('an earlier round lists 7041-7060')
    for name in (RESERVATION, STATUS, LOG, RESULT):
        if (dst / name).exists():
            problems.append(f'earlier validation found: {name}')
    if problems:
        raise PreflightError('; '.join(problems))
    return {'hashes': {k: reg[k] for k in sorted(reg)}, 'config_id': VF.CONFIG_ID, 'seeds': SEEDS}


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def reserve(dst, info):
    """Atomic: fails if the reservation already exists (second or concurrent start)."""
    path = dst / RESERVATION
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'reserved_at': now(), 'pid': os.getpid(), **info,
                   'note': 'seeds 7041-7060 are used from this moment, whatever the outcome; never delete'}, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    return path


def write_status(dst, **status):
    tmp = dst / (STATUS + '.tmp')
    tmp.write_text(json.dumps({'updated_at': now(), **status}, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, dst / STATUS)


def real_runner(dst):
    from . import validate_foresight as VF
    saved = sys.argv
    sys.argv = ['validate_foresight', 'validation', str(dst)]
    try:
        VF.main()
    finally:
        sys.argv = saved


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for x in self.streams:
            x.write(s)
            x.flush()

    def flush(self):
        for x in self.streams:
            x.flush()


def run(dst=DST, runner=real_runner, root=ROOT):
    info = preflight(dst, root)
    reserve(dst, info)
    write_status(dst, state='started', started_at=now())
    with open(dst / LOG, 'x', encoding='utf-8') as log:
        out, err = Tee(sys.__stdout__, log), Tee(sys.__stderr__, log)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                runner(dst)
        except BaseException as e:
            log.write(traceback.format_exc())
            write_status(dst, state='failed', error=repr(e), traceback=traceback.format_exc(),
                         files=sorted(p.name for p in dst.iterdir()), retry='never: the seeds are used')
            raise
    res = dst / RESULT
    if not res.exists():
        write_status(dst, state='failed', error='runner finished without a result file', retry='never')
        raise RuntimeError('no result file')
    os.chmod(res, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    final = json.loads(res.read_text(encoding='utf-8')).get('final', {})
    write_status(dst, state='done', finished_at=now(), result_sha256=sha(res), passed=final.get('pass'))
    return final


def state(dst=DST):
    """'none' / 'started' / 'failed' / 'done' (a reservation without status counts as started)."""
    if (dst / STATUS).exists():
        return json.loads((dst / STATUS).read_text(encoding='utf-8'))['state']
    return 'started' if (dst / RESERVATION).exists() else 'none'


def seeds_used_only_by_this_validation(dst=DST):
    """7041-7060: in no earlier round's seed list, and reserved by this validation."""
    from . import validate_interest as VI
    return VI.seeds_unused() and (dst / RESERVATION).exists() and \
        json.loads((dst / RESERVATION).read_text(encoding='utf-8'))['seeds'] == SEEDS


def main(argv=None):
    p = argparse.ArgumentParser(prog='run_foresight_validation')
    p.add_argument('mode', choices=MODES)
    a = p.parse_args(argv)
    if a.mode == 'check':
        print(json.dumps(preflight(), indent=1))
        print('preflight OK: nothing reserved, nothing simulated')
        return
    final = run()
    print(json.dumps({'validation_pass': final.get('pass')}, indent=1))


if __name__ == '__main__':
    main()
