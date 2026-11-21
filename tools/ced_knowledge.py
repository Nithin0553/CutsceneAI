#!/usr/bin/env python3
"""Inspect contextual CED knowledge or stage reviewed local knowledge.

Read-only for the source/target engines. The review subcommand creates a
privacy-screened local proposal only; it does not publish a shared release.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "ced"))


def _input(path: str, *, maximum: int = 128 * 1024 * 1024) -> dict:
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > maximum:
        raise ValueError("Missing, oversized or redirected CED source evidence.")
    payload = json.loads(file.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("CED inputs must be JSON objects.")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI hybrid CED knowledge")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("query", help="Inspect one source-grounded CED page")
    inspect.add_argument("--csir", required=True)
    inspect.add_argument("--target-capabilities", required=True)
    inspect.add_argument("--source-version", default="")
    inspect.add_argument("--target-version", default="")
    inspect.add_argument("--approved-store")
    inspect.add_argument("--case-store")
    inspect.add_argument("--page", type=int, default=0)
    inspect.add_argument("--page-size", type=int, default=48)
    stage = sub.add_parser("stage-review", help="Prepare a non-executable shared review bundle")
    stage.add_argument("--approved-store", required=True)
    stage.add_argument("--output", required=True)
    stage.add_argument("--candidate-id", action="append", required=True)
    stage.add_argument("--explicit-sharing-consent", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "query":
        from knowledge_service import retrieve
        answer = retrieve(
            _input(args.csir), target_capabilities=_input(
                args.target_capabilities, maximum=4 * 1024 * 1024,
            ),
            source_version=args.source_version,
            target_version=args.target_version,
            approved_store=Path(args.approved_store) if args.approved_store else None,
            case_store=Path(args.case_store) if args.case_store else None,
            page=args.page, page_size=args.page_size,
        )
        print(json.dumps(answer, indent=2, sort_keys=True))
    else:
        from shared_review import stage_for_review
        result = stage_for_review(
            args.approved_store, args.output,
            candidate_ids=args.candidate_id,
            explicit_sharing_consent=args.explicit_sharing_consent,
        )
        print(json.dumps({
            "status": result["status"],
            "bundle_sha256": result["bundle_sha256"],
            "rule_count": len(result["rules"]),
            "shared_release_published": False,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
