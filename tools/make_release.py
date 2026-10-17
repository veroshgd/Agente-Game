#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the release archive.

Two packaging mistakes have bitten this project before, and both are silent:

  1. __pycache__ / *.pyc leaking into the archive. `.gitignore` does not apply
     to `zip`, so any directory that has had pytest or an import run against it
     ships compiled bytecode. Inside `v3_frozen/` that is especially bad: a
     frozen model directory should contain exactly the 32 manifested files and
     nothing else.

  2. `docs/模拟实验记录.md` losing its name. Some zip tools write the filename in
     the local codepage instead of UTF-8, and some extractors then render it as
     `#U6a21#U62df...`. That file is referenced by name from `v2_frozen/README.md`
     and `v3_frozen/README.md`, so a mangled name breaks a documented cross-
     reference. Python's zipfile sets the UTF-8 flag on any non-ASCII name, which
     is why this script exists rather than a shell one-liner.

Usage:
    python tools/make_release.py                 # writes ../LifeEngine_v1.0.0.zip
    python tools/make_release.py --out PATH
    python tools/make_release.py --check-only    # verify without writing
"""

import argparse
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCNAME = "LifeEngine"

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", ".claude",
                "replay_out", ".idea", ".vscode"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".replay-backup", ".orig", ".rej")
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db"}

# Files that must be present, or the archive is not a valid release.
REQUIRED = [
    "README.md", "REPRODUCE.md", "CLAIMS.md", "ODD.md",
    "LICENSE", "LICENSE-DOCS.md", "NOTICE", "CITATION.cff", ".zenodo.json",
    ".gitattributes", "requirements.txt", "pytest.ini",
    "tools/verify_provenance.py", "tools/replay_paper_results.py",
    "tests/test_selfcheck.py",
    "docs/MEMORY_TRANSFER029_PREREGISTRATION.md",
    "docs/模拟实验记录.md",
    "v2_frozen/SHA256SUMS.txt", "v3_frozen/SHA256SUMS.txt",
    "final_confirm_result.txt", "final_027_result.txt",
    "final_028_result.txt", "final_029_result.txt",
    "final_028_STARTED.lock", "final_029_STARTED.lock",
    "interface028_frozen.json",
]


def collect():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for fn in sorted(filenames):
            if fn in EXCLUDE_NAMES or fn.endswith(EXCLUDE_SUFFIX):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            out.append((full, rel))
    return out


def check(files):
    rels = {r for _, r in files}
    problems = []

    missing = [r for r in REQUIRED if r not in rels]
    if missing:
        problems.append(("missing required file", missing))

    junk = [r for r in rels
            if "__pycache__" in r or r.endswith((".pyc", ".pyo"))]
    if junk:
        problems.append(("bytecode / cache leaked in", junk))

    # frozen directories must contain exactly manifest + README + the manifested files
    for d in ("v2_frozen", "v3_frozen"):
        manifest = os.path.join(ROOT, d, "SHA256SUMS.txt")
        if not os.path.isfile(manifest):
            continue
        listed = set()
        with open(manifest, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    listed.add(line.split(maxsplit=1)[1])
        present = {r.split("/", 1)[1] for r in rels
                   if r.startswith(d + "/")}
        extra = present - listed - {"SHA256SUMS.txt", "README.md"}
        if extra:
            problems.append((f"{d}/ contains unmanifested files", sorted(extra)))

    nonascii = [r for r in rels if any(ord(c) > 127 for c in r)]
    return problems, nonascii


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(ROOT), "LifeEngine_v1.0.0.zip"))
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()

    files = collect()
    problems, nonascii = check(files)

    print(f"files to package : {len(files)}")
    if nonascii:
        print(f"non-ASCII names  : {len(nonascii)} "
              f"(written with the UTF-8 flag set)")
        for r in nonascii:
            print(f"    {r}")

    if problems:
        print("\nPACKAGING CHECK FAILED")
        for label, items in problems:
            print(f"  {label}:")
            for i in items[:10]:
                print(f"    {i}")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more")
        return 1
    print("packaging check  : OK")

    if a.check_only:
        return 0

    out = os.path.abspath(a.out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in files:
            # zipfile sets the UTF-8 name flag automatically for non-ASCII
            z.write(full, f"{ARCNAME}/{rel}")

    # read back and confirm the encoding flag survived
    with zipfile.ZipFile(out) as z:
        infos = z.infolist()
        bad = [i.filename for i in infos
               if any(ord(c) > 127 for c in i.filename)
               and not (i.flag_bits & 0x800)]
    size = os.path.getsize(out) / 1024 / 1024
    print(f"\nwrote {out}  ({size:.1f} MB, {len(infos)} entries)")
    if bad:
        print("  ERROR: non-ASCII names written without the UTF-8 flag:")
        for b in bad:
            print(f"    {b}")
        return 1
    print("  UTF-8 filename flag verified on all non-ASCII entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
