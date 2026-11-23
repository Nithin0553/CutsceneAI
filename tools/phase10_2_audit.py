#!/usr/bin/env python3
"""Create or independently verify Phase 10.2's seven-workstream audit.

This tool reads the existing immutable Studio candidate and never runs an
engine or authorizes a repair. Without --write it prints the recomputed
source-only report. --write creates a once-only, byte-stable candidate receipt.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STUDIO=ROOT/"packages"/"studio"
if str(STUDIO) not in sys.path:
    sys.path.insert(0,str(STUDIO))

import phase10_2_consolidated_audit as phase10
import studio_element9_outcome as context


def generate(workspace: Path,job_id: str) -> tuple[Path,dict]:
    if not re.fullmatch(r"[0-9a-f]{32}",job_id):
        raise ValueError("Job ID must be exactly 32 lowercase hexadecimal characters.")
    root,candidate,job,csir,mapping,plan=context._context(workspace,job_id)
    if job.get("job_id")!=job_id or not candidate.is_relative_to(root/"candidates"):
        raise ValueError("Original Studio job and candidate identity differ.")
    return candidate/"phase10_2-consolidated-audit.json",phase10.audit(
        csir,mapping,plan,
    )


def main() -> int:
    parser=argparse.ArgumentParser(
        description="Recompute all seven Phase 10.2 source/action acceptance areas.",
    )
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--job-id",required=True)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument("--write",action="store_true")
    modes.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    path,report=generate(args.workspace,args.job_id)
    if args.verify:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Expected original seven-area audit file is unavailable.")
        saved=json.loads(path.read_text(encoding="utf-8"))
        if saved!=report:
            raise ValueError("Saved seven-area audit is stale or altered.")
    if args.write:
        if path.is_symlink() or path.exists():
            raise ValueError("Seven-area audit already exists; overwrite is forbidden.")
        path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation; a second process cannot silently replace the
        # same candidate's source-derived report.
        with path.open("x",encoding="utf-8") as stream:
            json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False)
            stream.write("\n")
    print(json.dumps({
        "kind":report["kind"],
        "schema_version":report["schema_version"],
        "canonical_report_sha256":report["canonical_report_sha256"],
        "source_occurrences_accounted":report["source_occurrences_accounted"],
        "workstream_count":report["workstream_count"],
        "fully_accepted_workstream_count":0,
        "real_editor_executed":False,
        "receipt_path":str(path) if args.write or args.verify else None,
        "report_only":not (args.write or args.verify),
    },sort_keys=True))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("Phase 10.2 audit refused: "+str(exc),file=sys.stderr)
        sys.exit(2)
