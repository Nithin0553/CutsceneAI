"""Operator CLI for local CED mapping proposals, QA approval and offline RL.

Never runs engine code, overwrites native assets or automatically promotes
learned mappings. Proposals can come from Studio users or test discoveries.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "packages" / "readiness", ROOT / "packages" / "learning"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import ced_reinforcement
import ced_rulebook


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main(argv=None):
    cli = argparse.ArgumentParser(description="Local, evidence-gated CED mapping rulebook")
    default = Path.home() / ".cutsceneai-studio" / "ced-knowledge"
    cli.add_argument("--store", type=Path, default=default)
    commands = cli.add_subparsers(dest="command", required=True)

    commands.add_parser("coverage", help="Inventory every CED concept and missing rule")
    propose = commands.add_parser("propose", help="Record a proposed mapping without activating it")
    propose.add_argument("--rule", type=Path, required=True)
    propose.add_argument("--origin", choices=["USER", "TRAINING", "TESTING"], default="USER")
    propose.add_argument("--feature-sha256", required=True)

    approve = commands.add_parser("approve", help="Human-review a QA-verified native mapping")
    approve.add_argument("--candidate-id", required=True)
    approve.add_argument("--evidence-name", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--held-out-passed", action="store_true")
    approve.add_argument("--regressions-passed", action="store_true")

    commands.add_parser("list-approved", help="Show persistent, QA-approved rules")

    feedback = commands.add_parser("record-feedback", help="Save a native QA trial outcome as RL feedback")
    feedback.add_argument("--comparison", type=Path, required=True)
    feedback.add_argument("--sampling-plan", type=Path, required=True)
    feedback.add_argument("--feedback", type=Path, required=True)
    feedback.add_argument("--ced", required=True)
    feedback.add_argument("--rule-id", required=True)
    feedback.add_argument("--source-version", required=True)
    feedback.add_argument("--target-version", required=True)
    feedback.add_argument("--human-reviewed", action="store_true")

    train = commands.add_parser("train", help="Train offline one-step RL suggestions")
    train.add_argument("--feedback", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--minimum-cases", type=int, default=3)

    args = cli.parse_args(argv)
    if args.command == "coverage":
        approved = ced_rulebook.approved_rules(args.store)
        result = ced_rulebook.coverage(approved)
        result["approved_user_rules"] = len(approved)
    elif args.command == "propose":
        candidate_id = ced_rulebook.propose(
            args.store, _json(args.rule), origin=args.origin,
            feature_sha256=args.feature_sha256)
        result = {"candidate_id": candidate_id, "status": "PROPOSED_NOT_EXECUTABLE"}
    elif args.command == "approve":
        result = ced_rulebook.promote(
            args.store, args.candidate_id, evidence_name=args.evidence_name,
            reviewer=args.reviewer, held_out_passed=args.held_out_passed,
            regression_passed=args.regressions_passed)
    elif args.command == "list-approved":
        rules = ced_rulebook.approved_rules(args.store)
        result = {"approved_rule_ids": [row["rule_id"] for row in rules],
                  "count": len(rules)}
    elif args.command == "record-feedback":
        result = ced_reinforcement.record_native_experience(
            args.comparison, args.sampling_plan, args.feedback,
            ced=args.ced, rule_id=args.rule_id,
            source_version=args.source_version, target_version=args.target_version,
            human_reviewed=args.human_reviewed)
    else:
        result = ced_reinforcement.export_policy(
            args.feedback, args.output, minimum_cases=args.minimum_cases)
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError) as exc:
        cli = sys.argv[0]
        print(f"{cli}: {exc}", file=sys.stderr)
        sys.exit(2)
