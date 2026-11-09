"""Verified CutSceneAI case memory: examples, candidate retrieval and SFT export.

Deliberately deterministic and engine-independent. No model weights are updated
automatically. An example can enter a training export only after independent
validation AND explicit human approval of its mapping decisions.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

CASE_VERSION = "0.1.0"


class LearningDataError(ValueError):
    """Untrusted training input or incorrect evidence."""


def _canonical_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(data: Any) -> str:
    return hashlib.sha256(_canonical_bytes(data)).hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise LearningDataError("Expected one JSON object.")
    return data


def _track_features(csir: Mapping[str, Any]) -> dict[str, Any]:
    features: set[str] = set()
    counts: Counter[str] = Counter()
    for entity in csir.get("entities", []):
        kind = str(entity.get("ced_type", ""))
        if kind:
            features.add("entity:" + kind)
    for track in csir.get("tracks", []):
        if track.get("muted") is True or not track.get("sections"):
            continue
        kind = str(track.get("ced_type", ""))
        counts[kind] += 1
        features.add("track:" + kind)
        for section in track["sections"]:
            section_kind = str(section.get("ced_type", ""))
            if section_kind:
                features.add("section:" + section_kind)
            native = section.get("native_payload", {})
            if float(native.get("blend_in_seconds", 0.0) or 0.0) > 0 or float(
                native.get("blend_out_seconds", 0.0) or 0.0
            ) > 0:
                features.add("timeline:blending")
            for curve in section.get("payload", {}).get("animation", {}).get("curves", []):
                semantic = str(curve.get("canonical_semantic") or curve.get("property_name") or "")
                if semantic:
                    features.add("curve:" + semantic)
    return {"features": sorted(features), "track_counts": dict(sorted(counts.items()))}


def _mapping_labels(resolved: Mapping[str, Any]) -> list[dict[str, Any]]:
    labels = []
    for entry in resolved.get("entries", []):
        if entry.get("status") != "RESOLVED" or entry.get("outcome") == "BLOCKED":
            continue
        labels.append({
            "ced": str(entry["ced"]),
            "outcome": str(entry["outcome"]),
            "resolver": str(entry["resolver"]),
            "parameters": entry.get("parameters", {}),
        })
    return sorted(labels, key=lambda x: (x["ced"], x["resolver"], _digest(x["parameters"])))


def _validation_pass(validation: Mapping[str, Any] | None) -> bool:
    if not validation or validation.get("status") != "PASS":
        return False
    summary = validation.get("summary", {})
    if summary.get("failed") != 0 or summary.get("incomplete") != 0:
        return False
    checks = validation.get("checks", [])
    return bool(checks) and all(x.get("status") == "PASS" for x in checks)


def build_case(
    csir: dict[str, Any],
    mapping: dict[str, Any],
    resolved: dict[str, Any],
    *,
    validation: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    source_profile: dict[str, Any] | None = None,
    target_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a case; only independently validated + approved mapping labels train."""
    if csir.get("source", {}).get("engine") not in ("unity", "unreal"):
        raise LearningDataError("Unknown cutscene source engine.")
    if not isinstance(mapping.get("entities", {}), dict):
        raise LearningDataError("Invalid mapping.")
    if resolved.get("version") != CASE_VERSION:
        raise LearningDataError("Expected versioned resolved mapping dictionary.")
    if not isinstance(resolved.get("entries"), list):
        raise LearningDataError("Resolved mappings must contain entries.")
    source_profile = source_profile or {}
    target_profile = target_profile or {}
    src_engine = str(csir.get("source", {}).get("engine", "")).lower()
    tgt_engine = str(target_profile.get("engine", {}).get("name") or "unreal").lower()
    source_id = str(csir.get("cutscene_id", ""))
    src_group = str(
        source_profile.get("project", {}).get("fingerprint")
        or csir.get("source", {}).get("project_fingerprint")
        or ""
    )
    structural = _validation_pass(validation)
    source_sha = _digest(csir)
    mapping_sha = _digest(mapping)
    review_approved = bool(
        review and review.get("approve_mapping_examples") is True
        and review.get("source_sha256") == source_sha
        and review.get("mapping_sha256") == mapping_sha
        and review.get("resolved_sha256") == _digest(resolved)
        and validation is not None
        and review.get("validation_sha256") == _digest(validation)
        and isinstance(review.get("reviewer"), str)
        and str(review["reviewer"]).strip()
    )
    labels = _mapping_labels(resolved)
    unresolved_count = sum(
        1 for e in resolved["entries"] if e.get("status") != "RESOLVED"
    )
    # An incomplete dictionary must not be used as "this mapping always works".
    promotable = bool(structural and review_approved and labels
                      and unresolved_count == 0 and src_group)
    if promotable:
        status = "MAPPING_VERIFIED"
    elif validation and not structural:
        status = "DIAGNOSTIC_ONLY"
    else:
        status = "CANDIDATE"
    features = _track_features(csir)
    source_capabilities = sorted(
        str(c.get("id")) for c in source_profile.get("capabilities", [])
        if c.get("state") == "SUPPORTED" and c.get("id")
    )
    target_capabilities = sorted(
        str(c.get("id")) for c in target_profile.get("capabilities", [])
        if c.get("state") == "SUPPORTED" and c.get("id")
    )
    data = {
        "case_version": CASE_VERSION,
        "source": {"engine": src_engine, "cutscene_id": source_id,
                   "project_fingerprint": src_group, "sha256": source_sha,
                   "profile_id": source_profile.get("profile_id", ""),
                   "capabilities": source_capabilities},
        "target": {"engine": tgt_engine, "profile_id": target_profile.get("profile_id", ""),
                   "capabilities": target_capabilities},
        "mapping_sha256": mapping_sha,
        "resolved_sha256": _digest(resolved),
        "validation_sha256": _digest(validation) if validation is not None else None,
        "status": status,
        "structural_validation_pass": structural,
        "review_approved": review_approved,
        "unresolved_decisions": unresolved_count,
        "fidelity_scope": "MAPPING_RULES_ONLY_NOT_FULL_CUTSCENE_PARITY",
        "features": features["features"],
        "track_counts": features["track_counts"],
        "mapping_labels": labels,
    }
    # Hash the immutable complete record; a post-review promotion writes a
    # distinct approved case instead of mutating older candidate evidence.
    data["case_id"] = _digest(data)[:24]
    return data


def save_case(case: dict[str, Any], store: str | Path) -> Path:
    folder = Path(store)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (case["case_id"] + ".json")
    serialized = json.dumps(case, indent=2, ensure_ascii=False) + "\n"
    if target.exists():
        if target.read_text(encoding="utf-8") != serialized:
            raise LearningDataError("Existing case has conflicting content; refusing overwrite.")
        return target
    target.write_text(serialized, encoding="utf-8")
    return target


def list_cases(store: str | Path) -> list[dict[str, Any]]:
    folder = Path(store)
    if not folder.exists():
        return []
    cases = []
    for path in sorted(folder.glob("*.json")):
        data = read_json(path)
        if data.get("case_version") != CASE_VERSION:
            raise LearningDataError(f"Unsupported case format: {path}")
        copy = {key: value for key, value in data.items() if key != "case_id"}
        expected_id = _digest(copy)[:24]
        if data.get("case_id") != expected_id or path.stem != expected_id:
            raise LearningDataError(f"Case content identity failed verification: {path}")
        cases.append(data)
    return cases


def suggest(
    csir: dict[str, Any],
    stored_cases: list[dict[str, Any]],
    *,
    source_engine: str | None = None,
    target_engine: str = "unreal",
    limit: int = 5,
    exclude_project_fingerprint: str = "",
) -> list[dict[str, Any]]:
    """Return evidence-linked *proposals*, never mutate actual mapping decisions."""
    if limit < 1:
        raise LearningDataError("limit must be >= 1")
    features = set(_track_features(csir)["features"])
    source_engine = source_engine or str(csir.get("source", {}).get("engine", ""))
    choices = []
    for case in stored_cases:
        if case.get("status") != "MAPPING_VERIFIED":
            continue
        if (case.get("source", {}).get("engine") != source_engine
            or case.get("target", {}).get("engine") != target_engine):
            continue
        if (exclude_project_fingerprint
            and case.get("source", {}).get("project_fingerprint") == exclude_project_fingerprint):
            continue
        reference = set(case.get("features", []))
        intersection = features & reference
        union = features | reference
        score = len(intersection) / len(union) if union else 0.0
        if not intersection or not case.get("mapping_labels"):
            continue
        choices.append({
            "case_id": case["case_id"],
            "similarity": round(score, 4),
            "shared_features": sorted(intersection),
            "candidate_resolutions": case["mapping_labels"],
            "proposal_only": True,
            "fidelity_verified": False,
        })
    return sorted(choices, key=lambda x: (-x["similarity"], x["case_id"]))[:limit]


def export_training_jsonl(cases: list[dict[str, Any]], output: str | Path) -> int:
    """Export reviewed mapping labels, never failed targets or unverified cutscenes."""
    output = Path(output)
    if output.exists():
        raise LearningDataError("Refusing to overwrite an existing training dataset.")
    entries = []
    for case in sorted(cases, key=lambda x: x["case_id"]):
        if case.get("status") != "MAPPING_VERIFIED":
            continue
        # The grouped key is used for train/evaluation isolation; scenes within
        # one project must not be split randomly across training/evaluation.
        if not case.get("source", {}).get("project_fingerprint"):
            continue
        entries.append({
            "task": "suggest_ced_transfer_mapping",
            "input": {
                "source_engine": case["source"]["engine"],
                "target_engine": case["target"]["engine"],
                "source_features": case["features"],
                "source_capabilities": case["source"]["capabilities"],
                "target_capabilities": case["target"]["capabilities"],
            },
            "target": case["mapping_labels"],
            "group_id": case["source"]["project_fingerprint"],
            "case_id": case["case_id"],
            "scope": "mapping_only",
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in entries), encoding="utf-8")
    return len(entries)



def dataset_health(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure evidence and leakage risk before considering parametric fine-tuning."""
    status = Counter(case.get("status", "UNKNOWN") for case in cases)
    verified = [case for case in cases if case.get("status") == "MAPPING_VERIFIED"]
    source_projects = {
        case.get("source", {}).get("project_fingerprint") for case in verified
        if case.get("source", {}).get("project_fingerprint")
    }
    target_profiles = {
        case.get("target", {}).get("profile_id") for case in verified
        if case.get("target", {}).get("profile_id")
    }
    track_kinds = set()
    decisions = set()
    for case in verified:
        track_kinds.update(case.get("track_counts", {}))
        decisions.update(
            (label.get("ced"), label.get("resolver"))
            for label in case.get("mapping_labels", [])
        )
    # Grouped evaluation is impossible with <2 independent source projects.
    # Even with 2 projects, do not infer model improvement from a tiny sample.
    return {
        "verified_cases": len(verified),
        "candidate_cases": int(status.get("CANDIDATE", 0)),
        "diagnostic_cases": int(status.get("DIAGNOSTIC_ONLY", 0)),
        "distinct_source_projects": len(source_projects),
        "distinct_target_profiles": len(target_profiles),
        "distinct_track_types": len(track_kinds),
        "distinct_mapping_decisions": len(decisions),
        "independent_project_holdout_possible": len(source_projects) >= 2,
        "model_finetuning_performed": False,
        "recommendation": (
            "COLLECT_INDEPENDENT_PROJECTS"
            if len(source_projects) < 2 else "EVALUATE_RETRIEVAL_BASELINE_FIRST"
        ),
    }
