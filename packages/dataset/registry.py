"""Reproducible CutSceneAI source dataset: verified, immutable Unity captures.

This creates a source-only dataset and DOES NOT mark transfers as successful
training labels. It uses the CineTwin sampling/capture verifier already in repo.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from sampling_plan import validate_capture

MANIFEST_VERSION = "0.1.0"
FILES = {"csir": "source.csir.json", "plan": "sampling-plan.json",
         "capture": "source-behavior.json", "profile": "source-project-profile.json"}


class DatasetError(ValueError):
    pass


def _slug(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}", value):
        raise DatasetError("IDs must be 2-64 ASCII letters, numbers, underscores or dashes.")
    return value


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise DatasetError(f"Expected JSON object: {path}")
    return data


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def _required_sources(csir: Path, plan: Path, capture: Path,
                      profile: Path | None) -> dict[str, Path]:
    paths = {"csir": csir, "plan": plan, "capture": capture}
    if profile is not None:
        paths["profile"] = profile
    for kind, path in paths.items():
        if not path.is_file():
            raise DatasetError(f"{kind} does not exist: {path}")
    return paths


def _audit_sources(paths: dict[str, Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    csir = _json(paths["csir"])
    plan = _json(paths["plan"])
    capture = _json(paths["capture"])
    expected_sha = _sha(paths["csir"])
    if plan.get("source", {}).get("csir_sha256") != expected_sha:
        raise DatasetError("Sampling plan does not match the exact source CSIR file bytes.")
    verification = validate_capture(plan, capture)
    if verification["failures"]:
        raise DatasetError(
            f"CineTwin capture verification found {len(verification['failures'])} errors: "
            + "; ".join(verification["failures"][:3])
        )
    if csir.get("cutscene_id") != plan.get("cutscene_id"):
        raise DatasetError("CSIR cutscene identity differs from sampling plan.")
    if csir.get("source", {}).get("project_fingerprint") != plan.get("source", {}).get("project_fingerprint"):
        raise DatasetError("Source project identity differs from sampling plan.")
    if not csir.get("source", {}).get("project_fingerprint"):
        raise DatasetError("Missing source project fingerprint: dataset cannot be split safely.")
    if "profile" in paths:
        profile = _json(paths["profile"])
        p_engine = profile.get("engine", {}).get("name")
        if p_engine and str(p_engine).lower() != str(csir.get("source", {}).get("engine", "")).lower():
            raise DatasetError("Source project profile engine conflicts with CSIR.")
    return csir, verification


def register(
    root: str | Path,
    project_id: str,
    scene_id: str,
    *,
    csir: str | Path,
    plan: str | Path,
    capture: str | Path,
    profile: str | Path | None = None,
) -> dict[str, Any]:
    """Copy frozen source evidence into an immutable per-scene dataset record."""
    project_id = _slug(project_id)
    scene_id = _slug(scene_id)
    root = Path(root)
    inputs = _required_sources(
        Path(csir), Path(plan), Path(capture), Path(profile) if profile else None)
    source, verification = _audit_sources(inputs)

    hashes = {name: _sha(path) for name, path in inputs.items()}
    record = {
        "manifest_version": MANIFEST_VERSION,
        "kind": "cutsceneai.dataset.source_record",
        "project_id": project_id,
        "scene_id": scene_id,
        "source_engine": source["source"]["engine"],
        "cutscene_id": source["cutscene_id"],
        "source_project_fingerprint": source["source"]["project_fingerprint"],
        "sampling_count": verification["expected_samples"],
        "rig_count": verification["skeletal_rig_count"],
        "capture_status": verification["status"],
        "unverified_layers": verification["not_verified"],
        "training_label_status": "UNLABELED",
        "full_fidelity_established": False,
        "artifacts": {
            key: {"file": FILES[key], "sha256": hashes[key],
                  "size_bytes": inputs[key].stat().st_size}
            for key in sorted(inputs)
        },
    }
    destination = root / "projects" / project_id / scene_id
    manifest = destination / "manifest.json"
    if destination.exists():
        if not manifest.is_file() or _json(manifest) != record:
            raise DatasetError("Scene record already exists with different data. Use a new scene ID.")
        # Avoid trusting a potentially tampered previous dataset record.
        verify_record(destination)
        return record
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for key, path in inputs.items():
            shutil.copyfile(path, destination / FILES[key])
            if _sha(destination / FILES[key]) != hashes[key]:
                raise DatasetError(f"Copy failed checksum verification: {key}")
        manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(destination)
        raise
    return record


def verify_record(directory: str | Path) -> dict[str, Any]:
    directory = Path(directory)
    manifest = _json(directory / "manifest.json")
    if manifest.get("kind") != "cutsceneai.dataset.source_record":
        raise DatasetError("Unknown dataset manifest format.")
    _slug(manifest.get("project_id", ""))
    _slug(manifest.get("scene_id", ""))
    artifacts = manifest.get("artifacts", {})
    if not {"csir", "plan", "capture"} <= set(artifacts):
        raise DatasetError("Dataset source record requires source CSIR, plan and capture.")
    inputs: dict[str, Path] = {}
    for kind, metadata in artifacts.items():
        if kind not in FILES or metadata.get("file") != FILES[kind]:
            raise DatasetError(f"Unexpected dataset artifact identifier: {kind}")
        path = directory / FILES[kind]
        if not path.is_file() or _sha(path) != metadata["sha256"]:
            raise DatasetError(f"Dataset checksum mismatch: {kind}")
        inputs[kind] = path
    source, verification = _audit_sources(inputs)
    if (source.get("cutscene_id") != manifest.get("cutscene_id")
        or source["source"].get("project_fingerprint") != manifest.get("source_project_fingerprint")
        or verification["status"] != manifest.get("capture_status")
        or verification["expected_samples"] != manifest.get("sampling_count")):
        raise DatasetError("Dataset manifest disagrees with independently verified source capture.")
    if manifest.get("training_label_status") != "UNLABELED":
        raise DatasetError("Source registry does not accept self-declared successful training labels.")
    return manifest


def dataset_report(root: str | Path) -> dict[str, Any]:
    base = Path(root) / "projects"
    records = []
    if base.exists():
        for manifest in sorted(base.glob("*/*/manifest.json")):
            entry = verify_record(manifest.parent)
            records.append(entry)
    project_ids: dict[str, str] = {}
    for entry in records:
        identifier = entry["project_id"]
        fingerprint = entry["source_project_fingerprint"]
        if identifier in project_ids and project_ids[identifier] != fingerprint:
            raise DatasetError(f"One project ID is assigned multiple source fingerprints: {identifier}")
        project_ids[identifier] = fingerprint
    fingerprints = set(project_ids.values())
    return {
        "kind": "cutsceneai.dataset.status",
        "scene_count": len(records),
        "project_id_count": len(project_ids),
        "independent_source_fingerprint_count": len(fingerprints),
        "project_level_holdout_possible": len(fingerprints) >= 2,
        "unlabeled_scene_count": len(records),
        "verified_supervised_label_count": 0,
        "records": [
            {"project_id": r["project_id"], "scene_id": r["scene_id"],
             "capture_status": r["capture_status"],
             "sampling_count": r["sampling_count"],
             "rig_count": r["rig_count"]}
            for r in records
        ],
    }
