"""Read-only, post-reopen structural audit for one Studio-generated Unreal target.

Run this explicitly AFTER closing/reopening the staging project. Runtime identity,
assets, actors, level and saved sequence are checked from the editor itself.
The report never claims that a process restart or cross-engine parity was proven.
No Unreal mutations or generator imports occur here.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
from pathlib import Path
from typing import Any


class PersistenceAuditError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise PersistenceAuditError("Expected JSON object: " + str(path))
    return data


def _sha(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            state.update(block)
    return state.hexdigest()


def _project_key(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(path).replace("/", "\\")))


def _asset_class(value: Any) -> str:
    if value is None:
        return ""
    return str(value.get_class().get_name())


def _package_file(project: Path, game_path: str, suffix: str) -> Path:
    if not game_path.startswith("/Game/") or ".." in game_path.split("/"):
        raise PersistenceAuditError("Unsafe Unreal /Game asset path.")
    return project.parent / "Content" / (game_path[6:] + suffix)


def _loaded_level(api: Any) -> str:
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    return str(world.get_path_name()).split(".")[0]


def _loaded_project(api: Any) -> str:
    raw = str(api.Paths.get_project_file_path())
    convert = getattr(api.Paths, "convert_relative_path_to_full", None)
    return str(convert(raw)) if callable(convert) else raw


def _checks(sequence: Any) -> dict[str, Any]:
    observed = {}
    for name, method in (("binding_count", "get_bindings"), ("root_track_count", "get_tracks")):
        getter = getattr(sequence, method, None)
        try:
            observed[name] = len(list(getter())) if callable(getter) else None
        except Exception:
            observed[name] = None
    return observed


def audit(job_path: str | Path, report_path: str | Path, *, unreal_api: Any = None) -> dict[str, Any]:
    """Observe only the loaded editor and on-disk receipts; write a new report."""
    api = unreal_api
    if api is None:
        import unreal as api
    job_file, output = Path(job_path).resolve(), Path(report_path).resolve()
    if output.exists() or not output.parent.is_dir():
        raise PersistenceAuditError("Audit output already exists or parent folder is missing.")
    job = _json(job_file)
    if job.get("kind") != "cutsceneai.studio.local_unreal_job":
        raise PersistenceAuditError("Not a Studio prepared Unreal job.")
    candidate_dir = Path(job["candidate_dir"]).resolve()
    if job_file.parent.name != "jobs" or job_file.parent.parent != candidate_dir.parent.parent:
        raise PersistenceAuditError("Job and candidate do not belong to the same workspace.")
    for filename in ("transfer-plan.json", "automatic-setup.json"):
        if not (candidate_dir / filename).is_file():
            raise PersistenceAuditError("Missing immutable prepared evidence: " + filename)
    setup_file = Path(job.get("setup_receipt_file") or "").resolve()
    runtime_file = Path(job.get("receipt_file") or "").resolve()
    if (setup_file.parent != candidate_dir or runtime_file.parent != candidate_dir
            or not setup_file.is_file() or not runtime_file.is_file()):
        raise PersistenceAuditError("Native setup or generation receipt is missing or outside candidate.")
    setup, manifest = _json(setup_file), _json(candidate_dir / "automatic-setup.json")
    runtime = _json(runtime_file)
    if (runtime.get("kind") != "cutsceneai.unreal.best_effort_receipt"
            or runtime.get("status") != "GENERATED_UNVERIFIED"
            or runtime.get("stage") != "complete"):
        raise PersistenceAuditError("Generation receipt does not prove completed engine generation.")
    plan = _json(candidate_dir / "transfer-plan.json")
    if (manifest.get("kind") != "cutsceneai.studio.automatic_setup_plan"
            or setup.get("kind") != "cutsceneai.studio.automatic_setup_receipt"
            or setup.get("status") != "SETUP_SAVED_UNVERIFIED"
            or setup.get("target_sequence") != job.get("sequence_path")
            or plan.get("sequence_asset_path") != job.get("sequence_path")
            or setup.get("target_namespace") != manifest.get("target_folder")):
        raise PersistenceAuditError("Setup or sequence evidence does not match this candidate.")
    expected_project, expected_level = str(job["expected_project"]), str(job["expected_level"])
    observed_project, observed_level = _loaded_project(api), _loaded_level(api)
    if _project_key(observed_project) != _project_key(expected_project):
        raise PersistenceAuditError("Wrong Unreal project loaded. No report or asset changes made.")
    if observed_level != expected_level:
        raise PersistenceAuditError("Wrong Unreal level loaded. Open the generated target level first.")
    project = Path(expected_project)
    rows = []
    found = []
    for item in manifest.get("imports", []):
        path, expected = str(item["target_asset_path"]), str(item["kind"])
        exists = bool(api.EditorAssetLibrary.does_asset_exist(path))
        loaded = api.load_asset(path) if exists else None
        actual = _asset_class(loaded)
        saved_file = _package_file(project, path, ".uasset").is_file()
        matched = exists and actual == expected and saved_file
        rows.append({"path": path, "expected_class": expected, "actual_class": actual,
                     "exists": exists, "saved_file_exists": saved_file, "pass": matched})
        if matched:
            found.append(path)
    actor_list = api.get_editor_subsystem(api.EditorActorSubsystem).get_all_level_actors()
    by_label: dict[str, list[Any]] = {}
    for actor in actor_list:
        by_label.setdefault(str(actor.get_actor_label()), []).append(actor)
    actor_rows = []
    for item in manifest.get("actors", []):
        label = str(item["label"])
        matches = by_label.get(label, [])
        actual = _asset_class(matches[0]) if len(matches) == 1 else ""
        kind = str(item["kind"])
        expected_classes = {
            "entity.character": {"SkeletalMeshActor"},
            "entity.camera": {"CineCameraActor"},
            "entity.light": {"PointLight", "SpotLight", "DirectionalLight"},
            "entity.prop": {"Actor", "StaticMeshActor"},
        }.get(kind, set())
        class_ok = len(matches) == 1 and actual in expected_classes
        parent = None
        if len(matches) == 1:
            getter = getattr(matches[0], "get_attach_parent_actor", None)
            if callable(getter):
                parent_actor = getter()
                parent = str(parent_actor.get_actor_label()) if parent_actor else None
        actor_rows.append({"name": item["name"], "label": label, "matches": len(matches),
                           "expected_kind": kind, "actual_class": actual,
                           "class_matches": class_ok, "observed_parent_label": parent})
    sequence_path = str(job["sequence_path"])
    if str(runtime.get("generated_sequence") or "").split(".")[0] != sequence_path:
        raise PersistenceAuditError("Generation receipt points to another sequence.")
    exists = bool(api.EditorAssetLibrary.does_asset_exist(sequence_path))
    sequence = api.load_asset(sequence_path) if exists else None
    sequence_class = _asset_class(sequence)
    sequence_disk = _package_file(project, sequence_path, ".uasset").is_file()
    sequence_rows = {
        "path": sequence_path, "actual_class": sequence_class,
        "saved_file_exists": sequence_disk,
        **(_checks(sequence) if sequence is not None else
           {"binding_count": None, "root_track_count": None}),
    }
    level_disk = _package_file(project, expected_level, ".umap").is_file()
    all_assets = len(rows) == len(manifest["imports"]) and all(r["pass"] for r in rows)
    all_actors = len(actor_rows) == len(manifest["actors"]) and all(r["class_matches"] for r in actor_rows)
    sequence_ok = sequence_class == "LevelSequence" and sequence_disk
    enumerable = sequence_rows["binding_count"] is not None and sequence_rows["root_track_count"] is not None
    if not level_disk or not sequence_ok or not all_assets or not all_actors:
        status = "STRUCTURAL_READBACK_FAIL"
    elif not enumerable:
        status = "STRUCTURAL_READBACK_INCOMPLETE"
    else:
        status = "STRUCTURAL_READBACK_PASS_RESTART_UNVERIFIED"
    report = {
        "kind": "cutsceneai.studio.persistence_audit", "schema_version": "0.1.0",
        "status": status, "fidelity_verified": False, "restart_verified": False,
        "engine_generated": True, "no_editor_mutation": True,
        "expected_project": expected_project, "observed_project": observed_project,
        "expected_level": expected_level, "observed_level": observed_level,
        "level_file_exists": level_disk, "sequence": sequence_rows,
        "assets": rows, "actors": actor_rows,
        "asset_count": len(rows), "assets_class_and_disk_verified": len(found),
        "actor_count": len(actor_rows),
        "source_manifest_sha256": _sha(candidate_dir / "automatic-setup.json"),
        "transfer_plan_sha256": _sha(candidate_dir / "transfer-plan.json"),
        "setup_receipt_sha256": _sha(setup_file),
        "generation_receipt_sha256": _sha(runtime_file),
        "limitations": [
            "Editor snapshot cannot independently prove process restart.",
            "Structural readback is not source-to-target pose, camera, audio or rendered-frame parity.",
            "Actor parent labels are observations only, not verified against Unity hierarchy.",
        ],
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return report


def audit_latest(workspace: str | Path | None = None, *, unreal_api: Any = None) -> dict[str, Any]:
    """Audit the most recently submitted Studio job. Invoke after reopening Unreal."""
    root = Path(workspace).resolve() if workspace is not None else (
        Path.home() / ".cutsceneai-studio" / "runs")
    pointer = _json(root / "active-job.json")
    job_id = str(pointer["job_id"])
    if len(job_id) != 32 or any(ch not in "0123456789abcdef" for ch in job_id):
        raise PersistenceAuditError("Invalid Studio job id.")
    target = root / "jobs" / (job_id + ".json")
    out = root / "candidates" / _json(target)["candidate_id"] / (
        "post-reopen-audit-" + job_id + ".json")
    report = audit(target, out, unreal_api=unreal_api)
    print("[CutSceneAI Studio] " + report["status"] + " (fidelity and restart not proven)")
    print("[CutSceneAI Studio] Audit JSON: " + str(out))
    return report
