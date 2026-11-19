"""Fit and verify CED-grounded conversion/transfer *proposal* policy.

This command does not update neural weights, invoke external providers,
assert native equivalence or train RL without reviewed engine rewards.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "learning"))
import ced_pretraining


def _write_new(path: Path, value: dict):
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ced_pretraining.CEDPretrainingError(
            "Training artifacts require a new filename in an existing directory.")
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Train or inspect a safe CED mapping proposal model")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train", help="Fit 735 CED concepts and registered native mappings")
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--summary", type=Path, required=True)
    check = commands.add_parser("verify", help="Check model checksum and exact CED corpus")
    check.add_argument("--model", type=Path, required=True)
    search = commands.add_parser("suggest", help="Suggest CED semantics; never execute a mapping")
    search.add_argument("--model", type=Path, required=True)
    search.add_argument("--engine", required=True, choices=["unity", "unreal"])
    search.add_argument("--native-name", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "train":
            if args.output == args.summary:
                raise ced_pretraining.CEDPretrainingError("Model and summary paths must differ.")
            if any(p.exists() or p.is_symlink() for p in (args.output, args.summary)):
                raise ced_pretraining.CEDPretrainingError("Refusing to overwrite training artifacts.")
            model = ced_pretraining.train()
            ced_pretraining.validate(model)
            summary = {
                "kind": "cutsceneai.ced.pretraining_report", "schema_version": "1",
                "model_payload_sha256": model["payload_sha256"],
                "training_type": model["training_type"],
                "sources": model["training_input_sha256"],
                "stats": model["stats"], "evaluation": model["evaluation"],
                "trained_native_reinforcement_policy": False,
                "notes": [
                    "Native alias labels come from draft Unity/Unreal dictionaries.",
                    "Five adaptive rules supply allowed resolver IDs, not real-engine rewards.",
                    "The model only proposes CED/native semantic matches.",
                    "Calibrated retarget, rendering, Timeline and native equivalence remain separate acceptance gates.",
                ],
            }
            _write_new(args.output, model)
            _write_new(args.summary, summary)
            print(json.dumps(summary, indent=2))
        else:
            path = args.model
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise ced_pretraining.CEDPretrainingError("Trained model is missing or unsafe.")
            model = ced_pretraining.validate(json.loads(path.read_text(encoding="utf-8-sig")))
            if args.command == "verify":
                print(json.dumps({
                    "valid": True, "model_payload_sha256": model["payload_sha256"],
                    "source_hashes_match": True,
                    "native_conversion_authorized": False,
                }, indent=2))
            else:
                print(json.dumps({
                    "kind": "cutsceneai.ced.mapping_suggestions",
                    "proposal_only": True, "engine": args.engine,
                    "suggestions": ced_pretraining.suggest(
                        model, args.native_name, engine=args.engine),
                }, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        print("[CED pretraining] BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
