"""Reproducible project-held-out mapping evaluation, without engine/tool access."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "learning"))

import case_memory
import heldout_evaluation as evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CutSceneAI independently grouped mapping-policy evaluation"
    )
    parser.add_argument("--store", type=Path, required=True,
                        help="Existing case_memory approved/candidate case store")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("prepare", help="Prepare frozen split and training-only export")
    create.add_argument("--out", type=Path, required=True)
    create.add_argument("--seed", default="cutsceneai-heldout-v1")
    create.add_argument("--validation-fraction", type=float, default=0.2)
    create.add_argument("--holdout-fraction", type=float, default=0.2)

    baseline = commands.add_parser("baseline", help="Score deterministic retrieval baseline")
    baseline.add_argument("--manifest", type=Path, required=True)
    baseline.add_argument("--split", choices=("validation", "holdout"), required=True)
    baseline.add_argument("--out", type=Path, required=True)
    baseline.add_argument("--min-similarity", type=float, default=0.25)

    score = commands.add_parser("score", help="Score external offline mapping predictions")
    score.add_argument("--manifest", type=Path, required=True)
    score.add_argument("--split", choices=("validation", "holdout"), required=True)
    score.add_argument("--predictions", type=Path, required=True)
    score.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        cases = case_memory.list_cases(args.store)
        if args.command == "prepare":
            manifest = evaluation.build_manifest(
                cases, seed=args.seed,
                validation_fraction=args.validation_fraction,
                holdout_fraction=args.holdout_fraction,
            )
            result = evaluation.export_training(cases, manifest, args.out)
            result["manifest_sha256"] = manifest["manifest_sha256"]
        else:
            manifest = case_memory.read_json(args.manifest)
            if args.command == "baseline":
                predictions = evaluation.retrieval_predictions(
                    cases, manifest, split=args.split,
                    min_similarity=args.min_similarity,
                )
            else:
                predictions = evaluation.load_predictions(args.predictions)
            result = evaluation.evaluate_predictions(
                cases, manifest, predictions, split=args.split,
            )
            evaluation.write_new(args.out, result)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (case_memory.LearningDataError, evaluation.EvaluationError,
            ValueError, OSError, KeyError, TypeError) as exc:
        print("CutSceneAI learning evaluation BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
