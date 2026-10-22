"""Review-gated cutscene mapping memory and optional fine-tuning dataset export.

All commands are pure local Python: no Unreal invocation or engine mutation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "learning"))

import case_memory


def _optional(path: Path | None) -> dict | None:
    return case_memory.read_json(path) if path else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI verified experience memory")
    commands = parser.add_subparsers(dest="command", required=True)

    fingerprint = commands.add_parser("review-template", help="Write an unapproved review template")
    fingerprint.add_argument("--csir", type=Path, required=True)
    fingerprint.add_argument("--mapping", type=Path, required=True)
    fingerprint.add_argument("--out", type=Path, required=True)

    capture = commands.add_parser("record", help="Record candidate/verified example")
    capture.add_argument("--csir", type=Path, required=True)
    capture.add_argument("--mapping", type=Path, required=True)
    capture.add_argument("--resolved", type=Path, required=True,
                         help="Adaptive resolver output, not a raw actor mapping")
    capture.add_argument("--validation", type=Path)
    capture.add_argument("--review", type=Path)
    capture.add_argument("--source-profile", type=Path)
    capture.add_argument("--target-profile", type=Path)
    capture.add_argument("--store", type=Path, required=True)

    recommend = commands.add_parser("suggest", help="Retrieve closest verified prior examples")
    recommend.add_argument("--csir", type=Path, required=True)
    recommend.add_argument("--store", type=Path, required=True)
    recommend.add_argument("--limit", type=int, default=5)
    recommend.add_argument("--output", type=Path)

    export = commands.add_parser("export", help="Export only verified mapping labels as JSONL")
    export.add_argument("--store", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)

    try:
        args = parser.parse_args(argv)
        if args.command == "review-template":
            csir = case_memory.read_json(args.csir)
            mapping = case_memory.read_json(args.mapping)
            template = {
                "approve_mapping_examples": False,
                "reviewer": "",
                "source_sha256": case_memory._digest(csir),
                "mapping_sha256": case_memory._digest(mapping),
                "notes": "Approve only after independent passing target readback "
                         "and human verification of mapping labels. Full visual/pose "
                         "fidelity is NOT implied by this approval.",
            }
            if args.out.exists():
                raise case_memory.LearningDataError("Review file already exists.")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
            print("[Learning] Review template (NOT APPROVED):", args.out)
        elif args.command == "record":
            case = case_memory.build_case(
                case_memory.read_json(args.csir),
                case_memory.read_json(args.mapping),
                case_memory.read_json(args.resolved),
                validation=_optional(args.validation),
                review=_optional(args.review),
                source_profile=_optional(args.source_profile),
                target_profile=_optional(args.target_profile),
            )
            path = case_memory.save_case(case, args.store)
            print("[Learning] Recorded", case["status"], case["case_id"], path)
            print("[Learning] Scope:", case["fidelity_scope"])
        elif args.command == "suggest":
            cases = case_memory.list_cases(args.store)
            proposals = case_memory.suggest(
                case_memory.read_json(args.csir), cases, limit=args.limit
            )
            output = {
                "kind": "cutsceneai.learning.mapping_suggestions",
                "proposal_only": True,
                "auto_applied": False,
                "suggestions": proposals,
            }
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
            print(json.dumps(output, indent=2))
        elif args.command == "export":
            count = case_memory.export_training_jsonl(
                case_memory.list_cases(args.store), args.output
            )
            print(f"[Learning] Exported {count} verified mapping examples to {args.output}")
            print("[Learning] Dataset only; no model fine-tuning was performed.")
        return 0
    except (case_memory.LearningDataError, OSError, ValueError, KeyError) as exc:
        print(f"[Learning] BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
