"""Explicit one-time sequence-only recovery after the Studio readiness import bug.

No asset import, actor creation, blind retry or target overwrite. Requires a
successful saved staging receipt, byte-identical prepared sources, a real
matching Unreal project/level, ALL staged assets/actors and a nonexisting target
LevelSequence. Saves an immutable operation log before invoking the generator.
A failed recovery remains blocked for manual inspection, not a retry loop.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


class GenerationRecoveryError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise GenerationRecoveryError("Expected a JSON object: " + str(path))
    return obj


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _write_once(path: Path, obj: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def _replace_json(path: Path, obj: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _project_key(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(path).replace("/", "\\")))


def _class_name(value: Any) -> str:
    return str(value.get_class().get_name()) if value is not None else ""


def _check_identity(api: Any, job: dict[str, Any]) -> None:
    raw = str(api.Paths.get_project_file_path())
    converter = getattr(api.Paths, "convert_relative_path_to_full", None)
    project = str(converter(raw)) if callable(converter) else raw
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    level = str(world.get_path_name()).split(".")[0]
    if _project_key(project) != _project_key(job["expected_project"]):
        raise GenerationRecoveryError("Wrong Unreal project loaded; no modifications made.")
    if level != job["expected_level"]:
        raise GenerationRecoveryError("Wrong Unreal level loaded; no modifications made.")


def _saved_package(project: Path, name: str, suffix: str) -> bool:
    if not name.startswith("/Game/") or ".." in name.split("/"):
        raise GenerationRecoveryError("Invalid target /Game package name.")
    return (project.parent / "Content" / (name[6:] + suffix)).is_file()


def _preflight(api: Any, job: dict[str, Any], candidate: Path) -> tuple[dict, dict]:
    for name in ("transfer-plan.json", "coverage-report.json", "evidence.json",
                 "automatic-setup.json"):
        if not (candidate / name).is_file():
            raise GenerationRecoveryError("Missing prepared source evidence: " + name)
    if job.get("status") != "BLOCKED_OR_FAILED" or job.get("generation_status") != "NOT_STARTED":
        raise GenerationRecoveryError("Only an import-blocked, NOT_STARTED generation is recoverable.")
    if job.get("setup_status") != "SETUP_SAVED_UNVERIFIED":
        raise GenerationRecoveryError("A fully saved automatic staging receipt is required.")
    message = str(job.get("error") or "").lower()
    if not ("transfer_readiness" in message and
            ("partially initialized" in message or "audit_files" in message)):
        raise GenerationRecoveryError("Recovery is restricted to the confirmed readiness-import failure.")
    if job.get("receipt_file") or job.get("generated_sequence"):
        raise GenerationRecoveryError("Target has generation evidence; refusing to regenerate.")
    _check_identity(api, job)
    manifest_path = (candidate / "automatic-setup.json").resolve()
    if Path(job["automatic_setup_manifest"]).resolve() != manifest_path:
        raise GenerationRecoveryError("Unexpected staged manifest identity.")
    for part in ("tools", "packages/studio", "packages/learning",
                 "packages/cinetwin", "integrations/unreal"):
        entry = str(ROOT / part)
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import studio_auto_assets
    import prepared_transfer
    import build_level_sequence
    if not callable(getattr(build_level_sequence.transfer_readiness, "audit", None)):
        raise GenerationRecoveryError("Canonical generator readiness is unavailable.")
    prepared = prepared_transfer.verify(candidate)
    if (prepared["source"]["csir_path"] != job["csir"]
            or prepared["target"]["mapping_path"] != job["mapping"]
            or prepared["target"]["sequence_asset_path"] != job["sequence_path"]):
        raise GenerationRecoveryError("Prepared source/mapping/sequence differs from failed job.")
    manifest = studio_auto_assets.verify(
        manifest_path, job["csir"], job["mapping"], candidate / "transfer-plan.json"
    )
    if not manifest["ready"]:
        raise GenerationRecoveryError("Staged source manifest is not safe.")
    plan = _json(candidate / "transfer-plan.json")
    if plan.get("sequence_asset_path") != job["sequence_path"]:
        raise GenerationRecoveryError("Prepared plan references a different sequence.")
    receipt_path = Path(job["setup_receipt_file"]).resolve()
    if receipt_path.parent != candidate or not receipt_path.is_file():
        raise GenerationRecoveryError("The successful native setup receipt is unavailable.")
    receipt = _json(receipt_path)
    if receipt.get("status") != "SETUP_SAVED_UNVERIFIED" or not receipt.get("level_saved"):
        raise GenerationRecoveryError("Native asset/actor setup was not saved.")
    for key, target in (("target_sequence", job["sequence_path"]),
                        ("target_namespace", manifest["target_folder"])):
        if receipt.get(key) not in (None, "", target):
            raise GenerationRecoveryError("Setup receipt contradicts " + key)
    expected_imports = {str(row["target_asset_path"]): str(row["kind"])
                        for row in manifest["imports"]}
    actual_imports = {str(row["path"]): str(row["kind"])
                      for row in receipt.get("assets_imported", [])}
    expected_actors = {str(row["label"]): str(row["kind"])
                       for row in manifest["actors"]}
    actual_actors = {str(row["label"]): str(row["kind"])
                     for row in receipt.get("actors_created", [])}
    if (len(actual_imports) != len(receipt.get("assets_imported", []))
            or actual_imports != expected_imports
            or len(actual_actors) != len(receipt.get("actors_created", []))
            or actual_actors != expected_actors):
        raise GenerationRecoveryError("Staged imports/actors differ from original manifest.")
    project = Path(job["expected_project"])
    if not _saved_package(project, job["expected_level"], ".umap"):
        raise GenerationRecoveryError("Staged Unreal map is not persisted on disk.")
    current = {}
    for actor in api.get_editor_subsystem(api.EditorActorSubsystem).get_all_level_actors():
        current.setdefault(str(actor.get_actor_label()), []).append(actor)
    allowed_classes = {
        "entity.character": {"SkeletalMeshActor"},
        "entity.camera": {"CineCameraActor"},
        "entity.light": {"PointLight", "SpotLight", "DirectionalLight"},
        "entity.prop": {"Actor", "StaticMeshActor"},
    }
    for label, kind in expected_actors.items():
        found = current.get(label, [])
        if len(found) != 1 or _class_name(found[0]) not in allowed_classes.get(kind, set()):
            raise GenerationRecoveryError("Staged Unreal actor missing, duplicated or wrong class: " + label)
    for path, kind in expected_imports.items():
        if (not api.EditorAssetLibrary.does_asset_exist(path)
                or _class_name(api.load_asset(path)) != kind
                or not _saved_package(project, path, ".uasset")):
            raise GenerationRecoveryError("Staged Unreal asset missing or class/disk mismatch: " + path)
    if (api.EditorAssetLibrary.does_asset_exist(job["sequence_path"])
            or api.load_asset(job["sequence_path"]) is not None
            or _saved_package(project, job["sequence_path"], ".uasset")):
        raise GenerationRecoveryError("Target sequence already exists; refusing overwrite.")
    return manifest, receipt


def recover_latest(workspace: str | Path | None = None, *, unreal_api: Any = None) -> dict[str, Any]:
    """Explicitly generate the sequence ONCE, without repeating asset import."""
    api = unreal_api
    if api is None:
        import unreal as api
    root = (Path(workspace).resolve() if workspace else
            (Path.home() / ".cutsceneai-studio" / "runs").resolve())
    job_id = str(_json(root / "active-job.json")["job_id"])
    if len(job_id) != 32 or any(ch not in "0123456789abcdef" for ch in job_id):
        raise GenerationRecoveryError("Invalid active Studio job ID.")
    job_file = root / "jobs" / (job_id + ".json")
    job = _json(job_file)
    if job.get("job_id") != job_id:
        raise GenerationRecoveryError("Active job identity differs.")
    candidate = Path(job["candidate_dir"]).resolve()
    if not candidate.is_relative_to((root / "candidates").resolve()):
        raise GenerationRecoveryError("Job candidate is outside the Studio workspace.")
    attempt = candidate / ("generation-recovery-" + job_id + ".json")
    backup = candidate / ("job-before-recovery-" + job_id + ".json")
    receipt_path = candidate / ("unreal-runtime-receipt-" + job_id + ".json")
    if attempt.exists() or backup.exists() or receipt_path.exists():
        raise GenerationRecoveryError("A recovery attempt or generation receipt already exists; inspect it, do not replay.")
    manifest, setup = _preflight(api, job, candidate)
    import build_level_sequence
    import studio_auto_scene

    audit = {
        "kind": "cutsceneai.studio.generation_only_recovery",
        "schema_version": "0.1.0", "status": "GENERATION_NOT_STARTED",
        "job_id": job_id, "target_sequence": job["sequence_path"],
        "manifest_sha256": _digest(candidate / "automatic-setup.json"),
        "setup_receipt_sha256": _digest(Path(job["setup_receipt_file"])),
        "source_project": job["expected_project"], "source_level": job["expected_level"],
        "assets_reimported": False, "actors_respawned": False,
        "original_actors_verified": len(manifest["actors"]),
        "original_assets_verified": len(manifest["imports"]),
        "fidelity_verified": False,
    }
    # Preserve the original terminal job before any generation or metadata update.
    _write_once(backup, job)
    _write_once(attempt, audit)
    try:
        sequence = build_level_sequence.build_prepared_files(
            job["csir"], job["mapping"], str(candidate / "transfer-plan.json"),
            str(candidate / "coverage-report.json"), str(candidate / "evidence.json"),
            str(receipt_path), expected_project_path=job["expected_project"],
            expected_level_path=job["expected_level"],
        )
        if str(sequence.get_path_name()).split(".")[0] != job["sequence_path"]:
            raise GenerationRecoveryError("Generator returned a different sequence; manual inspection required.")
        # Builder creates the sequence and may update actor pose/attachments.
        # Persist the updated level just as the regular Studio worker does.
        studio_auto_scene._save_level(api, job["expected_level"])
        if (not api.EditorAssetLibrary.does_asset_exist(job["sequence_path"])
                or _class_name(api.load_asset(job["sequence_path"])) != "LevelSequence"
                or not _saved_package(Path(job["expected_project"]),
                                      job["sequence_path"], ".uasset")):
            raise GenerationRecoveryError("Generated Level Sequence was not persisted; manual inspection required.")
        audit["status"] = "GENERATED_UNVERIFIED"
        audit["generated_sequence"] = str(sequence.get_path_name())
        new_job = dict(job)
        new_job.update({
            "status": "RECOVERED_GENERATED_NOT_FIDELITY_VERIFIED",
            "generation_status": "GENERATED_UNVERIFIED",
            "generated_sequence": str(sequence.get_path_name()),
            "receipt_file": str(receipt_path), "recovery_file": str(attempt),
            "error": None, "fidelity_verified": False,
        })
        _replace_json(attempt, audit)
        _replace_json(job_file, new_job)
        print("[CutSceneAI Studio] RECOVERED_GENERATED_NOT_FIDELITY_VERIFIED")
        print("[CutSceneAI Studio] No asset reimport or actor respawn was performed.")
        print("[CutSceneAI Studio] Generation recovery report: " + str(attempt))
        return audit
    except Exception as exc:
        audit["status"] = "GENERATION_RECOVERY_FAILED_MUST_INSPECT"
        audit["error_type"] = type(exc).__name__
        audit["error"] = str(exc)
        audit["traceback"] = traceback.format_exc()
        _replace_json(attempt, audit)
        raise
