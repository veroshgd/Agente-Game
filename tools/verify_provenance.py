#!/usr/bin/env python3
"""
Path-independent provenance verifier.

Purpose
-------
`final_029.py` is the historical one-shot confirmation runner for Experiment 029.
It is deliberately left byte-unchanged, including its absolute `PREREG_PATH`,
which points at the desktop path of the machine used at confirmation time.
That path does not exist in a fresh clone, so the runner's own preflight prints
"cannot find" for the preregistration line.

This script does NOT modify the historical runner. It independently recomputes
the SHA-256 of the artifacts that live in this repository and compares them with
the constants the runner recorded before the confirmatory run. It can be executed
from a fresh clone with no configuration.

Usage
-----
    python3 tools/verify_provenance.py

Exit code 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(label: str, want: str, got: str, results: list) -> None:
    ok = want == got
    results.append(ok)
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"         declared {want}")
        print(f"         actual   {got}")


def declared_constants(runner: pathlib.Path) -> tuple[str, dict[str, str]]:
    """Extract PREREG_SHA256 and FROZEN_MODULES from the historical runner."""
    src = runner.read_text(encoding="utf-8")

    m = re.search(r'PREREG_SHA256\s*=\s*\(\s*"([0-9a-f]+)"\s*"?\s*\n?\s*"([0-9a-f]+)"\s*\)', src)
    if not m:
        raise SystemExit("could not parse PREREG_SHA256 from final_029.py")
    prereg = m.group(1) + m.group(2)

    block = re.search(r"FROZEN_MODULES\s*=\s*\{(.*?)\n\}", src, re.S)
    if not block:
        raise SystemExit("could not parse FROZEN_MODULES from final_029.py")
    modules = dict(re.findall(r'"([\w.]+\.py)"\s*:\s*"([0-9a-f]+)"', block.group(1)))
    return prereg, modules


def main() -> int:
    results: list[bool] = []
    runner = ROOT / "final_029.py"

    print("Provenance verification for Experiment 029")
    print(f"repository root: {ROOT}")
    print()

    prereg_declared, modules_declared = declared_constants(runner)

    print("preregistration (authoritative Chinese original)")
    prereg_file = ROOT / "docs" / "MEMORY_TRANSFER029_PREREGISTRATION.md"
    check("docs/MEMORY_TRANSFER029_PREREGISTRATION.md",
          prereg_declared, sha256(prereg_file), results)
    print()

    print("frozen runtime modules recorded by final_029.py")
    for name, want in sorted(modules_declared.items()):
        path = ROOT / name
        got = sha256(path)[: len(want)] if path.exists() else "<missing>"
        check(name, want, got, results)
    print()

    print("frozen model directories")
    for directory in ("v2_frozen", "v3_frozen"):
        manifest = ROOT / directory / "SHA256SUMS.txt"
        if not manifest.exists():
            print(f"  [FAIL] {directory}/SHA256SUMS.txt missing")
            results.append(False)
            continue
        ok = bad = 0
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            want, name = line.split(None, 1)
            target = ROOT / directory / name.strip()
            # v2_frozen records truncated (16 hex) digests; compare by prefix.
            if target.exists() and sha256(target).startswith(want):
                ok += 1
            else:
                bad += 1
                print(f"  [FAIL] {directory}/{name.strip()}")
        results.append(bad == 0)
        print(f"  [{'PASS' if bad == 0 else 'FAIL'}] {directory}: {ok} verified, {bad} failed")
    print()

    print("run-time anchors (digests recorded on the original machine)")
    print("  these are independent: they were written into the lock files at run")
    print("  time, so agreement cannot be produced by regenerating a manifest")
    lock029 = (ROOT / "final_029_STARTED.lock").read_text(encoding="utf-8")
    lock_mods = dict(re.findall(r"module (\S+) ([0-9a-f]+)", lock029))
    n_ok = 0
    for name, want in sorted(lock_mods.items()):
        got = sha256(ROOT / name)[:len(want)]
        if got == want:
            n_ok += 1
        else:
            print(f"  [FAIL] {name}: lock {want} vs disk {got}")
    ok = n_ok == len(lock_mods) and len(lock_mods) == 6
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] 029 lock vs frozen runtime modules: "
          f"{n_ok}/{len(lock_mods)} identical")

    m = re.search(r"prereg_sha256 ([0-9a-f]+)", lock029)
    check("029 lock vs preregistration digest", m.group(1),
          sha256(ROOT / "docs" / "MEMORY_TRANSFER029_PREREGISTRATION.md"), results)

    lock028 = (ROOT / "final_028_STARTED.lock").read_text(encoding="utf-8")
    want028 = re.search(r"interface_sha=([0-9a-f]+)", lock028).group(1)
    iface_data = json.loads((ROOT / "interface028_frozen.json").read_text(encoding="utf-8"))
    check("028 lock vs frozen interface digest", want028, iface_data["sha256"], results)
    print()

    print("frozen interface (Experiment 028)")
    iface = ROOT / "interface028_frozen.json"
    data = json.loads(iface.read_text(encoding="utf-8"))
    want = data.pop("sha256")
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    check("interface028_frozen.json self-hash",
          want, hashlib.sha256(payload.encode()).hexdigest(), results)
    print()

    passed = all(results)
    print(f"{'ALL CHECKS PASSED' if passed else 'SOME CHECKS FAILED'} "
          f"({sum(results)}/{len(results)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
