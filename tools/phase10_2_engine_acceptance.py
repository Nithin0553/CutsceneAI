#!/usr/bin/env python3
"""Verify full seven-area Phase 10.2 workstation native evidence bundle.

This is a read-only verifier. It never launches Unity/Unreal, writes native
assets, or certifies editor execution from synthetic/source-only receipts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STUDIO=ROOT/"packages"/"studio"
if str(STUDIO) not in sys.path:
    sys.path.insert(0,str(STUDIO))

import phase10_2_engine_acceptance_suite as suite


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("Will not overwrite an existing acceptance review.")
    manifest=suite.engine_acceptance_matrix._json_bound(
        args.manifest,args.workspace.resolve(),
    )
    try:
        report=suite.evaluate(manifest,args.workspace)
    except (suite.Phase10_2EngineAcceptanceError,ValueError,OSError) as exc:
        parser.error(str(exc))
    output=args.output.resolve()
    if not output.parent.is_dir():
        parser.error("Review output directory must already exist.")
    if output==args.manifest.resolve():
        parser.error("Review cannot overwrite original acceptance manifest.")
    with output.open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write("\n")
    print(report["status"])
    print("Independent reviewer and actual editor/render/audio proof still required.")
    return 0


if __name__=="__main__":
    sys.exit(main())
