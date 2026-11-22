#!/usr/bin/env python3
"""CutSceneAI CED local knowledge, evidence review and signed release commands.

Every network/publishing action is intentionally absent: explicit local
consent, human review and trusted publisher provisioning remain mandatory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for component in ("ced", "learning"):
    location = str(ROOT / "packages" / component)
    if location not in sys.path:
        sys.path.insert(0, location)


def _input(path: str, *, maximum: int = 128 * 1024 * 1024) -> dict:
    file = Path(path)
    if file.is_symlink() or not file.is_file() or not 0 < file.stat().st_size <= maximum:
        raise ValueError("Missing, oversized or redirected CED source evidence.")
    data = json.loads(file.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("CED inputs must be JSON objects.")
    return data


def _key_dict(path: str) -> dict[str, bytes]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    config = _input(path, maximum=32 * 1024)
    result = {}
    for name, filename in config.items():
        key_file = Path(filename)
        if key_file.is_symlink() or not key_file.is_file():
            raise ValueError("Reviewer trust key is missing or redirected.")
        key = serialization.load_pem_public_key(key_file.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("Only Ed25519 reviewer trust keys are supported.")
        result[name] = key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI hybrid CED knowledge")
    commands = parser.add_subparsers(dest="command", required=True)
    query = commands.add_parser("query", help="Inspect an exact source CED page")
    query.add_argument("--csir", required=True)
    query.add_argument("--target-capabilities", required=True)
    query.add_argument("--source-version", default="")
    query.add_argument("--target-version", default="")
    query.add_argument("--approved-store")
    query.add_argument("--case-store")
    query.add_argument("--feedback-store")
    query.add_argument("--page", type=int, default=0)
    query.add_argument("--page-size", type=int, default=48)
    query.add_argument("--all-pages", action="store_true")

    stage = commands.add_parser("stage-review", help="Create local inert shared proposal")
    stage.add_argument("--approved-store", required=True)
    stage.add_argument("--output", required=True)
    stage.add_argument("--candidate-id", action="append", required=True)
    stage.add_argument("--explicit-sharing-consent", action="store_true")

    enqueue = commands.add_parser("queue-review", help="Submit consented bundle to local queue")
    enqueue.add_argument("--bundle", required=True)
    enqueue.add_argument("--queue", required=True)
    enqueue.add_argument("--explicit-sharing-consent", action="store_true")

    review = commands.add_parser("sign-review", help="Sign independent human CED review")
    for name in ("bundle", "reviewer", "role", "private-key", "native-evidence",
                 "heldout-report", "regression-report", "output"):
        review.add_argument("--" + name, required=True)
    review.add_argument("--explicit-review-approval", action="store_true")

    publish = commands.add_parser("sign-release", help="Create reviewed signed release file")
    for name in ("bundle", "decisions", "reviewer-trust", "publisher-private-key",
                 "revision", "output"):
        publish.add_argument("--" + name, required=True)
    publish.add_argument("--previous-release-sha256")
    publish.add_argument("--revoke-rule", action="append", default=[])
    publish.add_argument("--explicit-release-consent", action="store_true")

    install = commands.add_parser("install-release", help="Install trusted signed revision")
    for name in ("release", "trusted-publisher-key", "store"):
        install.add_argument("--" + name, required=True)
    install.add_argument("--explicit-install-consent", action="store_true")

    native = commands.add_parser("review-native", help="Record independently reviewed native outcome")
    for name in ("comparison", "sampling-plan", "ledger", "ced", "rule-id",
                 "source-version", "target-version"):
        native.add_argument("--" + name, required=True)
    native.add_argument("--explicit-human-review", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "query":
        from knowledge_service import retrieve, retrieve_all
        opts = {
            "target_capabilities": _input(
                args.target_capabilities, maximum=4 * 1024 * 1024,
            ),
            "source_version": args.source_version,
            "target_version": args.target_version,
            "approved_store": Path(args.approved_store) if args.approved_store else None,
            "case_store": Path(args.case_store) if args.case_store else None,
            "feedback_store": Path(args.feedback_store) if args.feedback_store else None,
        }
        source = _input(args.csir)
        result = (retrieve_all(source, **opts) if args.all_pages
                  else retrieve(source, page=args.page,
                                page_size=args.page_size, **opts))
    elif args.command == "stage-review":
        from shared_review import stage_for_review
        staged = stage_for_review(
            args.approved_store, args.output,
            candidate_ids=args.candidate_id,
            explicit_sharing_consent=args.explicit_sharing_consent,
        )
        result = {"status": staged["status"],
                  "bundle_sha256": staged["bundle_sha256"],
                  "rule_count": len(staged["rules"]),
                  "shared_release_published": False}
    elif args.command == "queue-review":
        from review_queue import submit
        result = submit(Path(args.bundle), Path(args.queue),
                        explicit_consent=args.explicit_sharing_consent)
    elif args.command == "sign-review":
        from review_queue import sign_review
        result = sign_review(
            Path(args.bundle), reviewer=args.reviewer, role=args.role,
            reviewer_private_key=Path(args.private_key),
            native_evidence=Path(args.native_evidence),
            heldout_report=Path(args.heldout_report),
            regression_report=Path(args.regression_report),
            explicitly_approved=args.explicit_review_approval,
        )
        Path(args.output).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = {"status": "SIGNED_INDEPENDENT_REVIEW_RECORDED",
                  "review_record_role": result["role"]}
    elif args.command == "sign-release":
        from shared_distribution import sign_release
        decisions_path = Path(args.decisions)
        if decisions_path.is_symlink() or decisions_path.stat().st_size > 128 * 1024:
            raise ValueError("Reviewer decisions file must be local and bounded.")
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        release = sign_release(
            Path(args.bundle), review_decisions=decisions,
            trusted_reviewers=_key_dict(args.reviewer_trust),
            publisher_private_key=Path(args.publisher_private_key),
            revision=int(args.revision),
            previous_release_sha256=args.previous_release_sha256,
            revoked_rule_ids=args.revoke_rule,
            output_file=Path(args.output),
            explicit_release_consent=args.explicit_release_consent,
        )
        result = {"status": "SIGNED_RELEASE_CREATED_NOT_INSTALLED",
                  "revision": release["release_revision"]}
    elif args.command == "install-release":
        from shared_distribution import install_release
        result = install_release(
            Path(args.release), trust_key_file=Path(args.trusted_publisher_key),
            store=Path(args.store),
            explicit_install_consent=args.explicit_install_consent,
        )
    else:
        from ced_reinforcement import record_native_experience
        result = record_native_experience(
            args.comparison, args.sampling_plan, args.ledger,
            ced=args.ced, rule_id=args.rule_id,
            source_version=args.source_version,
            target_version=args.target_version,
            human_reviewed=args.explicit_human_review,
        )
        result = {"status": result["test_outcome"],
                  "native_readback_verified": result["native_readback_verified"],
                  "human_reviewed": result["human_reviewed"],
                  "runtime_native_authority": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
