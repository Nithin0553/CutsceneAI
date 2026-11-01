"""Inspect all registered CED v0.2 features and executable adapter gaps.

An inventory is a coverage target, not proof of conversion. This tool never
imports Unreal, changes editor projects or treats native actions as verified.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
import feature_dispatch


def build() -> dict:
    catalog = feature_dispatch.catalog()
    semantic_rows = []
    grouped = {}
    for semantic in sorted(catalog["_domain_for"]):
        rule = feature_dispatch.recipe(semantic, features=catalog)
        builder = [
            kind for kind in rule.get("potential_builder_actions", ())
            if kind in feature_dispatch.BUILDER_ACTIONS
        ]
        semantic_rows.append({
            "ced": semantic,
            "source_domain": catalog["_domain_for"][semantic],
            "candidate_route": rule["candidate_route"],
            "builder_action_candidates": builder,
            "native_construction_verified": False,
            "source_target_behavior_verified": False,
            "adapter_required": not bool(builder),
        })
        key = catalog["_domain_for"][semantic]
        group = grouped.setdefault(key, {"concepts": 0, "action_candidates": 0})
        group["concepts"] += 1
        group["action_candidates"] += bool(builder)
    family_rows = [
        {"family_id": f["id"], "semantic_domains": f["ced_domains"],
         "target_fidelity_verified": False}
        for f in catalog["feature_families"]
    ]
    totals = Counter("HAS_ACTION_CANDIDATE" if x["builder_action_candidates"]
                     else "NEEDS_ADAPTER" for x in semantic_rows)
    return {
        "kind": "cutsceneai.ced.capability_matrix",
        "schema_version": "0.2.0",
        "catalog_sha256": catalog["_sha256"],
        "total_semantics": len(semantic_rows),
        "total_families": len(family_rows),
        "total_domains": len(grouped),
        "states": dict(sorted(totals.items())),
        "domains": dict(sorted(grouped.items())),
        "families": family_rows,
        "semantics": semantic_rows,
        "fully_verified_semantics": 0,
        "source_target_parity_verified": False,
        "limitations": [
            "A candidate builder action can still be source-dependent and lossy.",
            "Engine-specific adapter implementation and real readback are separate tasks.",
            "Open-ended new plugin types are registered via explicit adapter handlers.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect CED v0.2 engine adapter gaps")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists() or args.out.is_symlink():
        parser.error("Refusing to overwrite an existing CED capability report.")
    result = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("[CutSceneAI] CED features:", result["total_semantics"])
    print("[CutSceneAI] Industry feature families:", result["total_families"])
    print("[CutSceneAI] Candidate native action IDs:", result["states"].get(
        "HAS_ACTION_CANDIDATE", 0))
    print("[CutSceneAI] Adapter implementation tasks:", result["states"].get(
        "NEEDS_ADAPTER", 0))
    print("[CutSceneAI] Conversion fidelity: NOT VERIFIED BY CATALOG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
