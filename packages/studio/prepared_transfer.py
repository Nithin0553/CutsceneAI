"""Immutable Studio handoff: existing CSIR + mapping -> best-effort Unreal artifacts.

Does not load Unreal, import assets, mutate engine projects or claim fidelity.
Reuses the audited best-effort planner and its cross-runtime source verification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import asset_staging
import case_memory
import transfer_backend

VERSION = "0.1.0"


class PreparedTransferError(ValueError):
    """Unsafe or stale Studio transfer handoff."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise PreparedTransferError(f"Expected a JSON object: {path}")
    return data


def _serialize(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _identity(source: str, mapping: str, capture: str | None, target: str | None) -> str:
    data = {"source_sha256": source, "mapping_sha256": mapping,
            "source_capture_sha256": capture, "target_project": target}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:20]



def _check_asset_import(
    source_file: Path,
    new_mapping_file: Path,
    target_project: str | None,
    manifest_file: Path,
    receipt_file: Path,
    original_mapping_file: Path,
) -> dict[str, Any]:
    """Bind engine import evidence to the exact unchanged inputs, without claiming fidelity."""
    if target_project is None:
        raise PreparedTransferError("Target project is required when attaching import evidence.")
    manifest = asset_staging.read_json(manifest_file)
    receipt = asset_staging.read_json(receipt_file)
    if manifest.get("kind") != "cutsceneai.studio.asset_import_manifest":
        raise PreparedTransferError("Unexpected asset import manifest type.")
    if (receipt.get("kind") != "cutsceneai.unreal.asset_import_receipt"
        or receipt.get("stage") != "complete"
        or receipt.get("status") not in {"IMPORTED_PARTIAL", "IMPORTED_UNVERIFIED"}
        or receipt.get("behavioral_fidelity_verified") is not False
        or receipt.get("source_assets_modified") is not False):
        raise PreparedTransferError("Asset import was not a completed, unverified engine receipt.")
    asset_staging.verify_files(manifest, source_file, original_mapping_file)
    if (receipt.get("manifest_sha256") != _sha(manifest_file)
        or receipt.get("source_csir_sha256") != _sha(source_file)
        or receipt.get("resolved_mapping_sha256") != _sha(new_mapping_file)):
        raise PreparedTransferError("Asset receipt mismatches manifest, source or resolved mapping.")
    if Path(str(receipt.get("target_project") or "")).resolve() != Path(target_project).resolve():
        raise PreparedTransferError("Asset import was for a different Unreal project.")
    original = asset_staging.read_json(original_mapping_file)
    proposed = asset_staging.read_json(new_mapping_file)
    expected = json.loads(json.dumps(original))
    expected.setdefault("assets", {})
    rows = [row for row in manifest["assets"] if row["status"] == "READY_WAV_IMPORT"]
    observed = {
        str(row["asset_id"]): row for row in receipt.get("imported", [])
        if isinstance(row, dict) and row.get("asset_id")
    }
    if len(observed) != len(receipt.get("imported", [])) or set(observed) != {
        row["asset_id"] for row in rows
    }:
        raise PreparedTransferError("Asset receipt lacks exact imported source IDs.")
    for row in rows:
        record = observed[row["asset_id"]]
        if (record.get("status") != "IMPORTED_NATIVE_UNVERIFIED"
            or record.get("source_sha256") != row["source_sha256"]
            or record.get("target_asset_path") != row["target_asset_path"]
            or record.get("target_class") != "SoundWave"):
            raise PreparedTransferError("Imported asset provenance differs from source manifest.")
        expected["assets"][row["name"]] = row["target_asset_path"]
    if proposed != expected:
        raise PreparedTransferError("Resolved mapping was not produced solely by verified imports.")
    return {
        "manifest_path": str(manifest_file), "manifest_sha256": _sha(manifest_file),
        "receipt_path": str(receipt_file), "receipt_sha256": _sha(receipt_file),
        "original_mapping_path": str(original_mapping_file),
        "original_mapping_sha256": _sha(original_mapping_file),
        "imported_count": len(rows), "status": receipt["status"],
        "behavioral_fidelity_verified": False,
    }

def prepare(
    csir_path: str | Path,
    mapping_path: str | Path,
    output_dir: str | Path,
    *,
    capture_path: str | Path | None = None,
    target_project: str | Path | None = None,
    case_store: str | Path | None = None,
    strict_ced: bool = False,
    asset_manifest_path: str | Path | None = None,
    asset_receipt_path: str | Path | None = None,
    asset_original_mapping_path: str | Path | None = None,
) -> dict[str, Any]:
    """Make a new, checkable engine handoff; fail before creating any output on preflight errors."""
    source_file = Path(csir_path).resolve()
    mapping_file = Path(mapping_path).resolve()
    capture_file = Path(capture_path).resolve() if capture_path is not None else None
    out = Path(output_dir)
    if out.exists() or out.is_symlink():
        raise PreparedTransferError("Refusing to reuse or overwrite a Studio transfer directory.")
    source = _read(source_file)
    mapping = _read(mapping_file)
    if mapping.get("overwrite_sequence") is True:
        raise PreparedTransferError("A fresh target Level Sequence is required (overwrite=false).")
    sequence = mapping.get("sequence_asset_path")
    if (not isinstance(sequence, str) or not sequence.startswith("/Game/")
        or sequence.endswith("/") or ".." in sequence.split("/")):
        raise PreparedTransferError("Target sequence must be a new /Game/... asset path.")

    plan, report, evidence = transfer_backend.compose_files(
        source_file, mapping_file, capture_path=capture_file,
    )
    if strict_ced and not report["ced_preflight"]["strict_transfer_allowed"]:
        raise PreparedTransferError("CED preflight requires review; strict transfer blocked.")

    cases = case_memory.list_cases(case_store) if case_store is not None else []
    # Held-out evaluation must not recommend using its own source-project examples.
    fingerprint = str(source.get("source", {}).get("project_fingerprint") or "")
    proposals = case_memory.suggest(
        source, cases, exclude_project_fingerprint=fingerprint,
    )
    suggestions = {
        "kind": "cutsceneai.learning.suggestions",
        "schema_version": VERSION,
        "auto_applied": False,
        "fidelity_verified": False,
        "suggestions": proposals,
        "exclusion": "same_source_project",
    }
    source_hash = _sha(source_file)
    mapping_hash = _sha(mapping_file)
    capture_hash = _sha(capture_file) if capture_file is not None else None
    target_name = str(Path(target_project).resolve()) if target_project is not None else None
    import_inputs = (asset_manifest_path, asset_receipt_path, asset_original_mapping_path)
    if any(value is not None for value in import_inputs) and not all(
        value is not None for value in import_inputs
    ):
        raise PreparedTransferError("All three asset import evidence files are required together.")
    import_evidence = None
    if all(value is not None for value in import_inputs):
        import_evidence = _check_asset_import(
            source_file, mapping_file, target_name,
            Path(asset_manifest_path).resolve(), Path(asset_receipt_path).resolve(),
            Path(asset_original_mapping_path).resolve(),
        )
    docs = {
        "transfer-plan.json": plan,
        "coverage-report.json": report,
        "evidence.json": evidence,
        "suggestions.json": suggestions,
    }
    artifact_hashes = {
        name: hashlib.sha256(_serialize(doc).encode("utf-8")).hexdigest()
        for name, doc in docs.items()
    }
    session = {
        "kind": "cutsceneai.studio.prepared_transfer",
        "schema_version": VERSION,
        "session_id": _identity(source_hash, mapping_hash, capture_hash, target_name),
        "cutscene_id": source.get("cutscene_id"),
        "source": {"csir_path": str(source_file), "sha256": source_hash,
                   "engine": source.get("source", {}).get("engine"),
                   "project_fingerprint": fingerprint},
        "target": {"mapping_path": str(mapping_file), "mapping_sha256": mapping_hash,
                   "project_path": target_name, "sequence_asset_path": sequence},
        "source_capture": (
            {"path": str(capture_file), "sha256": capture_hash}
            if capture_file is not None else None
        ),
        "stage": "AWAITING_UNREAL_PREFLIGHT",
        "ced_preflight": report["ced_preflight_status"],
        "track_coverage": report["outcomes"],
        "learning_case_count": len(proposals),
        "asset_import": import_evidence,
        "learning_applied": False,
        "asset_import_executed": False,
        "engine_generation_executed": False,
        "target_readback_verified": False,
        "behavioral_fidelity_established": False,
        "training_example_approved": False,
        "artifact_sha256": artifact_hashes,
    }
    # Explicit 'x' creates fail closed on accidental races, rather than modifying artifacts.
    out.mkdir(parents=True, exist_ok=False)
    for name, doc in {**docs, "session.json": session}.items():
        with (out / name).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_serialize(doc))
    return session


def verify(output_dir: str | Path) -> dict[str, Any]:
    """Read-only: prove immutable handoff still matches original CSIR/mapping/capture."""
    folder = Path(output_dir)
    session = _read(folder / "session.json")
    if (session.get("kind") != "cutsceneai.studio.prepared_transfer"
        or session.get("schema_version") != VERSION):
        raise PreparedTransferError("Unknown Studio handoff schema.")
    source = session["source"]
    target = session["target"]
    capture = session.get("source_capture")
    src_path, map_path = Path(source["csir_path"]), Path(target["mapping_path"])
    cap_path = Path(capture["path"]) if capture is not None else None
    if _sha(src_path) != source["sha256"] or _sha(map_path) != target["mapping_sha256"]:
        raise PreparedTransferError("Original CSIR or mapping changed since session preparation.")
    if cap_path is not None and _sha(cap_path) != capture["sha256"]:
        raise PreparedTransferError("Original CineTwin source capture has changed.")
    if session["session_id"] != _identity(
        source["sha256"], target["mapping_sha256"],
        capture["sha256"] if capture else None, target.get("project_path"),
    ):
        raise PreparedTransferError("Session identity mismatch.")
    attached = session.get("asset_import")
    if attached is not None:
        refreshed = _check_asset_import(
            src_path, map_path, target.get("project_path"),
            Path(attached["manifest_path"]), Path(attached["receipt_path"]),
            Path(attached["original_mapping_path"]),
        )
        if refreshed != attached:
            raise PreparedTransferError("Linked asset import provenance changed.")
    for name, expected in session["artifact_sha256"].items():
        if name not in {
            "transfer-plan.json", "coverage-report.json", "evidence.json", "suggestions.json"
        } or _sha(folder / name) != expected:
            raise PreparedTransferError(f"Prepared artifact modified or missing: {name}")
    if set(session["artifact_sha256"]) != {
        "transfer-plan.json", "coverage-report.json", "evidence.json", "suggestions.json"
    }:
        raise PreparedTransferError("Incomplete or unexpected artifact manifest.")
    plan, report, evidence = transfer_backend.compose_files(
        src_path, map_path, capture_path=cap_path,
    )
    transfer_backend.verify_prepared_artifacts(
        _read(folder / "transfer-plan.json"),
        _read(folder / "coverage-report.json"),
        _read(folder / "evidence.json"),
        plan, report, evidence,
    )
    if (session["target"]["sequence_asset_path"] != plan["sequence_asset_path"]
        or session["track_coverage"] != report["outcomes"]
        or session["ced_preflight"] != report["ced_preflight_status"]):
        raise PreparedTransferError("Session summary differs from prepared transfer.")
    if (session.get("engine_generation_executed") is not False
        or session.get("learning_applied") is not False):
        raise PreparedTransferError("Prepared handoff cannot assert execution or learned action.")
    return session
