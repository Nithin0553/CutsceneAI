"""Project-isolated, offline evaluation for verified CutSceneAI mapping decisions.

A held-out score measures policy-label selection, NOT rendered cinematic fidelity.
No engine access, model training, arbitrary execution, or automatic deployment.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

import case_memory

VERSION = "0.1.0"
LABEL_FIELDS = ("ced", "resolver", "outcome")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class EvaluationError(ValueError):
    """Invalid provenance, project isolation or evaluation evidence."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _labels(value: object) -> frozenset[tuple[str, str, str]]:
    if not isinstance(value, list):
        raise EvaluationError("Expected a list of structured CED mapping labels.")
    entries = []
    for item in value:
        if not isinstance(item, dict) or set(item) != set(LABEL_FIELDS):
            raise EvaluationError("Only ced/resolver/outcome fields are allowed in predictions.")
        triple = tuple(item[field] for field in LABEL_FIELDS)
        if any(not isinstance(v, str) or not _LABEL.fullmatch(v) for v in triple):
            raise EvaluationError("Mapping label contains an invalid semantic identifier.")
        entries.append(triple)
    if len(entries) != len(set(entries)):
        raise EvaluationError("Duplicate mapping labels are not allowed.")
    return frozenset(entries)


def _reference_labels(case: Mapping[str, Any]) -> frozenset[tuple[str, str, str]]:
    return _labels([
        {key: label.get(key) for key in LABEL_FIELDS}
        for label in case["mapping_labels"]
    ])


def _verified(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reject corrupted verified examples; ignore diagnostic-only case records."""
    filtered = []
    seen_ids = set()
    source_groups_by_sha = {}
    for case in cases:
        if case.get("status") != "MAPPING_VERIFIED":
            continue
        if (case.get("case_version") != case_memory.CASE_VERSION
                or case.get("review_approved") is not True
                or case.get("structural_validation_pass") is not True
                or case.get("unresolved_decisions") != 0
                or case.get("fidelity_scope") != "MAPPING_RULES_ONLY_NOT_FULL_CUTSCENE_PARITY"):
            raise EvaluationError("Verified mapping case lacks required review evidence.")
        expect = case_memory._digest({k: v for k, v in case.items() if k != "case_id"})[:24]
        case_id = case.get("case_id")
        if case_id != expect or case_id in seen_ids:
            raise EvaluationError("Duplicated or tampered case identity.")
        seen_ids.add(case_id)
        source = case.get("source") or {}
        target = case.get("target") or {}
        group = source.get("project_fingerprint")
        src_sha = source.get("sha256")
        if (source.get("engine") != "unity" or target.get("engine") != "unreal"
                or not isinstance(group, str) or not group
                or not isinstance(src_sha, str) or not src_sha
                or not isinstance(case.get("features"), list)
                or any(not isinstance(x, str) for x in case["features"])):
            raise EvaluationError("Verified case is missing source identity or feature evidence.")
        previous = source_groups_by_sha.setdefault(src_sha, group)
        if previous != group:
            raise EvaluationError("Same source evidence appears in different project groups.")
        if not _reference_labels(case):
            raise EvaluationError("A verified case must contain at least one mapping label.")
        filtered.append(case)
    return sorted(filtered, key=lambda item: item["case_id"])


def _groups(cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for case in cases:
        key = case["source"]["project_fingerprint"]
        groups.setdefault(key, []).append(case["case_id"])
    return {key: sorted(ids) for key, ids in sorted(groups.items())}


def build_manifest(cases: list[dict[str, Any]], *, seed: str = "cutsceneai-heldout-v1",
                   validation_fraction: float = 0.2, holdout_fraction: float = 0.2) -> dict:
    """Freeze complete source-project groups before any training/evaluation."""
    verified = _verified(cases)
    groups = _groups(verified)
    if len(groups) < 3:
        raise EvaluationError("At least three independent verified source projects are required.")
    if not isinstance(seed, str) or not seed or len(seed) > 128:
        raise EvaluationError("A bounded nonempty split seed is required.")
    if (not 0 < validation_fraction < 1 or not 0 < holdout_fraction < 1
            or validation_fraction + holdout_fraction >= 1
            or not all(math.isfinite(x) for x in (validation_fraction, holdout_fraction))):
        raise EvaluationError("Invalid source-group holdout fractions.")
    ordered = sorted(groups, key=lambda g: (_digest([seed, g]), g))
    count = len(ordered)
    n_holdout = max(1, round(count * holdout_fraction))
    n_validation = max(1, round(count * validation_fraction))
    if n_holdout + n_validation >= count:
        raise EvaluationError("Need at least one source project exclusively for training.")
    by_split = {
        "holdout": ordered[:n_holdout],
        "validation": ordered[n_holdout:n_holdout + n_validation],
        "train": ordered[n_holdout + n_validation:],
    }
    assignments = {
        split: {
            "project_fingerprints": sorted(names),
            "case_ids": sorted(cid for group in names for cid in groups[group]),
        }
        for split, names in by_split.items()
    }
    manifest = {
        "kind": "cutsceneai.learning.project_split",
        "version": VERSION,
        "seed": seed,
        "dataset_sha256": _digest([case["case_id"] for case in verified]),
        "verified_cases": len(verified),
        "source_projects": len(groups),
        "splits": assignments,
        "fidelity_scope": "MAPPING_RULES_ONLY_NOT_FULL_CUTSCENE_PARITY",
        "model_trained": False,
        "release_authorized": False,
    }
    manifest["manifest_sha256"] = _digest(manifest)
    return manifest


def _check_manifest(cases: list[dict[str, Any]], manifest: dict) -> list[dict[str, Any]]:
    verified = _verified(cases)
    canonical = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if (manifest.get("kind") != "cutsceneai.learning.project_split"
            or manifest.get("version") != VERSION
            or manifest.get("manifest_sha256") != _digest(canonical)
            or manifest.get("dataset_sha256") != _digest([c["case_id"] for c in verified])):
        raise EvaluationError("Split manifest or frozen dataset identity mismatch.")
    groups = _groups(verified)
    seen_groups = set()
    seen_ids = set()
    splits = manifest.get("splits")
    if not isinstance(splits, dict) or set(splits) != {"train", "validation", "holdout"}:
        raise EvaluationError("Malformed split manifest.")
    for split in ("train", "validation", "holdout"):
        part = splits[split]
        names = part.get("project_fingerprints")
        ids = part.get("case_ids")
        if (not isinstance(names, list) or not names
                or not isinstance(ids, list) or not ids or len(names) != len(set(names))):
            raise EvaluationError("Every split must contain distinct projects and cases.")
        if seen_groups.intersection(names) or set(names) - set(groups):
            raise EvaluationError("Source-project leakage between splits.")
        expected = sorted(cid for group in names for cid in groups[group])
        if ids != expected or seen_ids.intersection(ids):
            raise EvaluationError("Cases are misassigned across projects.")
        seen_groups.update(names)
        seen_ids.update(ids)
    if seen_groups != set(groups):
        raise EvaluationError("Split does not cover the frozen verified source projects.")
    return verified


def export_training(cases: list[dict[str, Any]], manifest: dict, output_dir: Path) -> dict:
    """Create new immutable artifacts; never export holdout labels for training."""
    verified = _check_manifest(cases, manifest)
    folder = Path(output_dir)
    if folder.exists() or folder.is_symlink():
        raise EvaluationError("Refusing to overwrite an existing evaluation directory.")
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    train = set(manifest["splits"]["train"]["case_ids"])
    # Train a mapping-policy selector, not an engine executor. Even validated
    # case_memory mapping labels may contain private paths or operation
    # parameters: keep only reviewed semantic IDs in this training export.
    training = [c for c in verified if c["case_id"] in train]
    with (folder / "train.jsonl").open("x", encoding="utf-8") as output:
        for case in training:
            row = {
                "task": "suggest_ced_transfer_mapping",
                "input": {
                    "source_engine": case["source"]["engine"],
                    "target_engine": case["target"]["engine"],
                    "source_features": case["features"],
                    "source_capabilities": case["source"]["capabilities"],
                    "target_capabilities": case["target"]["capabilities"],
                },
                "target": [
                    dict(zip(LABEL_FIELDS, item))
                    for item in sorted(_reference_labels(case))
                ],
                "group_id": case["source"]["project_fingerprint"],
                "case_id": case["case_id"],
                "scope": "mapping_policy_only_no_executable_parameters",
            }
            output.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    count = len(training)
    if count != len(train):
        raise EvaluationError("Training export count does not match the frozen split.")
    return {
        "status": "TRAINING_DATA_PREPARED",
        "training_examples": count,
        "validation_cases": len(manifest["splits"]["validation"]["case_ids"]),
        "holdout_cases": len(manifest["splits"]["holdout"]["case_ids"]),
        "model_trained": False,
        "fidelity_verified": False,
    }


def retrieval_predictions(cases: list[dict[str, Any]], manifest: dict, *,
                          split: str, min_similarity: float = 0.25) -> list[dict]:
    """Nearest-case proposal baseline using ONLY frozen training source projects."""
    verified = _check_manifest(cases, manifest)
    if split not in {"validation", "holdout"}:
        raise EvaluationError("Baseline split must be validation or holdout.")
    if not isinstance(min_similarity, (int, float)) or not 0 <= min_similarity <= 1:
        raise EvaluationError("Invalid similarity threshold.")
    by_id = {case["case_id"]: case for case in verified}
    train = [by_id[cid] for cid in manifest["splits"]["train"]["case_ids"]]
    proposals = []
    for cid in manifest["splits"][split]["case_ids"]:
        target = by_id[cid]
        features = set(target["features"])
        scored = []
        for exemplar in train:
            if exemplar["source"]["project_fingerprint"] == target["source"]["project_fingerprint"]:
                raise EvaluationError("Training and held-out project leakage detected.")
            ref = set(exemplar["features"])
            shared = features & ref
            score = len(shared) / len(features | ref) if shared else 0.0
            scored.append((score, exemplar["case_id"], exemplar))
        scored.sort(key=lambda item: (-item[0], item[1]))
        nearest = scored[0] if scored else None
        abstain = nearest is None or nearest[0] < min_similarity or nearest[0] == 0
        labels = [] if abstain else [
            dict(zip(LABEL_FIELDS, item))
            for item in sorted(_reference_labels(nearest[2]))
        ]
        proposals.append({"case_id": cid, "abstain": abstain, "labels": labels})
    return proposals


def evaluate_predictions(cases: list[dict[str, Any]], manifest: dict,
                         predictions: list[dict], *, split: str) -> dict:
    """Score mapping policy labels, not target cinematic or parameter fidelity."""
    verified = _check_manifest(cases, manifest)
    if split not in {"validation", "holdout"}:
        raise EvaluationError("Only unseen project splits may be evaluated.")
    expected = set(manifest["splits"][split]["case_ids"])
    if not isinstance(predictions, list) or len(predictions) != len(expected):
        raise EvaluationError("Provide exactly one prediction per frozen evaluation case.")
    provided = {}
    for row in predictions:
        if not isinstance(row, dict) or set(row) != {"case_id", "abstain", "labels"}:
            raise EvaluationError("Prediction contains unsupported fields.")
        cid = row["case_id"]
        if cid not in expected or cid in provided or type(row["abstain"]) is not bool:
            raise EvaluationError("Duplicate, wrong-split or malformed prediction.")
        labels = _labels(row["labels"])
        if row["abstain"] and labels:
            raise EvaluationError("Abstention cannot include executable mapping labels.")
        if not row["abstain"] and not labels:
            raise EvaluationError("Non-abstaining prediction must include mapping labels.")
        provided[cid] = (row["abstain"], labels)
    if set(provided) != expected:
        raise EvaluationError("Missing evaluation predictions.")
    refs = {case["case_id"]: _reference_labels(case) for case in verified if case["case_id"] in expected}
    attempted = exact = true_positive = false_positive = false_negative = 0
    for cid in sorted(expected):
        abstain, predicted = provided[cid]
        if abstain:
            continue
        attempted += 1
        expected_labels = refs[cid]
        exact += predicted == expected_labels
        true_positive += len(predicted & expected_labels)
        false_positive += len(predicted - expected_labels)
        false_negative += len(expected_labels - predicted)
    precision = true_positive / (true_positive + false_positive) if attempted else 0.0
    recall = true_positive / (true_positive + false_negative) if attempted else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "kind": "cutsceneai.learning.policy_evaluation",
        "schema_version": VERSION,
        "manifest_sha256": manifest["manifest_sha256"],
        "split": split,
        "held_out_source_projects": len(manifest["splits"][split]["project_fingerprints"]),
        "total_cases": len(expected),
        "attempted_cases": attempted,
        "abstained_cases": len(expected) - attempted,
        "coverage": round(attempted / len(expected), 6),
        "exact_match_on_attempted": round(exact / attempted, 6) if attempted else 0.0,
        "label_precision_on_attempted": round(precision, 6),
        "label_recall_on_attempted": round(recall, 6),
        "label_f1_on_attempted": round(f1, 6),
        "false_positive_labels": false_positive,
        "false_negative_labels_on_attempted": false_negative,
        "parameter_equivalence_tested": False,
        "engine_fidelity_tested": False,
        "model_finetuning_performed": False,
        "release_authorized": False,
    }


def load_predictions(path: Path) -> list[dict]:
    """Strict, bounded JSONL input from an external (future) strategy model."""
    source = Path(path)
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 10 * 1024 * 1024:
        raise EvaluationError("Invalid or oversized prediction file.")
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            if len(rows) >= 100_000:
                raise EvaluationError("Prediction file exceeds maximum number of rows.")
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise EvaluationError("Invalid prediction JSONL record.") from exc
    return rows


def write_new(path: Path, value: Mapping[str, Any]) -> None:
    """Never overwrite an earlier evaluation result."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf-8") as output:
        json.dump(value, output, sort_keys=True, indent=2)
        output.write("\n")
