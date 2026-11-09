"""Engine-agnostic CutSceneAI Studio orchestration: source → plan → staging gate.

Prepares immutable conversion evidence; DOES NOT import Unreal or save assets.
Runtime realization/readback are separate adapter stages with independent proofs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import case_memory
import csir_plan
import transfer_readiness


class StudioError(ValueError):
    pass


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise StudioError(f"Expected one JSON object: {path}")
    return value


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_write(path: Path, data: dict[str, Any]) -> None:
    encoded = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise StudioError(f"Refusing to overwrite an existing session artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def prepare(
    csir_path: str | Path,
    mapping_path: str | Path,
    output_dir: str | Path,
    *,
    target_project: str | Path | None = None,
    verified_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan and label feature coverage. Never call an engine or apply AI guesses."""
    source_file, mapping_file = Path(csir_path), Path(mapping_path)
    source, mapping = _json(source_file), _json(mapping_file)
    source_sha, mapping_sha = _hash(source_file), _hash(mapping_file)
    readiness = transfer_readiness.audit(source, mapping)
    plan: dict[str, Any] | None = None
    if readiness["generation"] == "READY_FOR_ENGINE_PREFLIGHT":
        plan = csir_plan.build_plan(source, mapping)
    proposals = case_memory.suggest(source, verified_cases or [])
    session_identity = {
        "source_sha256": source_sha,
        "mapping_sha256": mapping_sha,
        "target_project": str(target_project) if target_project else None,
    }
    session_id = hashlib.sha256(
        json.dumps(session_identity, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    session = {
        "schema_version": "0.1.0",
        "kind": "cutsceneai.studio.session",
        "session_id": session_id,
        "cutscene_id": source.get("cutscene_id"),
        "source": {
            "csir_path": str(source_file.resolve()),
            "sha256": source_sha,
            "engine": source.get("source", {}).get("engine"),
            "project_fingerprint": source.get("source", {}).get("project_fingerprint"),
        },
        "target": {
            "mapping_path": str(mapping_file.resolve()),
            "mapping_sha256": mapping_sha,
            "project_path": str(target_project) if target_project else None,
            "sequence_asset_path": mapping.get("sequence_asset_path"),
            "overwrite_sequence": mapping.get("overwrite_sequence", False),
        },
        "source_coverage": readiness["generation"],
        "partial_feature_count": readiness["unverified_behavior_count"],
        "proposed_mapping_cases": len(proposals),
        "stage": ("BLOCKED_SOURCE_COVERAGE"
                  if readiness["generation"] == "BLOCKED"
                  else "AWAITING_REAL_ENGINE_PREFLIGHT"),
        "engine_generation_executed": False,
        "target_readback_verified": False,
        "behavioral_fidelity_established": False,
        "training_example_approved": False,
    }
    if mapping.get("overwrite_sequence") is True:
        raise StudioError(
            "Studio staging refuses overwrite_sequence=true. "
            "Select a new target sequence asset instead."
        )
    folder = Path(output_dir)
    # Do not partially overwrite older session contents on conflicting input.
    files = {"session.json": session, "readiness.json": readiness,
             "suggestions.json": {"kind": "cutsceneai.learning.suggestions",
                                  "auto_applied": False, "suggestions": proposals}}
    if plan is not None:
        files["transfer-plan.json"] = plan
    for name, document in files.items():
        path = folder / name
        if path.exists():
            expected = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            if path.read_text(encoding="utf-8") != expected:
                raise StudioError(f"Session directory already contains conflicting {name}.")
    for name, document in files.items():
        _safe_write(folder / name, document)
    return session
