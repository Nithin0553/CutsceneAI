"""Read-only Studio persistence verification; these mocks do NOT prove Unreal fidelity."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "studio_persistence_audit",
    ROOT / "integrations" / "unreal" / "studio_persistence_audit.py",
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class Actor:
    def __init__(self, label: str, klass: str):
        self.label = label
        self.klass = klass

    def get_actor_label(self):
        return self.label

    def get_class(self):
        return NS(get_name=lambda: self.klass)

    def get_attach_parent_actor(self):
        return None


class Asset:
    def __init__(self, klass: str, *, expose_tracks: bool = True):
        self.klass = klass
        if expose_tracks:
            self.get_bindings = lambda: [object()]
            self.get_tracks = lambda: [object(), object()]

    def get_class(self):
        return NS(get_name=lambda: self.klass)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def fixture(tmp_path):
    root = tmp_path / "runs"
    candidate = root / "candidates" / "candidate-01"
    job_id = "abcdef0123456789abcdef0123456789"
    project = tmp_path / "Target.uproject"
    project.write_text("{}", encoding="utf-8")
    level = "/Game/Testing/L_Test"
    seq = "/Game/Testing/LS_New"
    asset_paths = ["/Game/Auto/Hero", "/Game/Auto/Wave"]
    manifest = {
        "kind": "cutsceneai.studio.automatic_setup_plan",
        "target_folder": "/Game/Auto",
        "imports": [{"target_asset_path": asset_paths[0], "kind": "SkeletalMesh"},
                    {"target_asset_path": asset_paths[1], "kind": "AnimSequence"}],
        "actors": [{"name": "Hero", "label": "CSAI_Hero", "kind": "entity.character"},
                   {"name": "CAM", "label": "CSAI_CAM", "kind": "entity.camera"}],
    }
    _write(candidate / "automatic-setup.json", manifest)
    _write(candidate / "transfer-plan.json", {"sequence_asset_path": seq})
    setup = _write(candidate / "setup.json", {
        "kind": "cutsceneai.studio.automatic_setup_receipt",
        "status": "SETUP_SAVED_UNVERIFIED", "target_sequence": seq,
        "target_namespace": "/Game/Auto",
    })
    generation = _write(candidate / "runtime.json", {
        "kind": "cutsceneai.unreal.best_effort_receipt",
        "status": "GENERATED_UNVERIFIED", "stage": "complete",
        "generated_sequence": seq + ".LS_New",
    })
    job = {
        "kind": "cutsceneai.studio.local_unreal_job",
        "candidate_dir": str(candidate), "sequence_path": seq,
        "expected_project": str(project), "expected_level": level,
        "setup_receipt_file": str(setup), "receipt_file": str(generation),
    }
    jobfile = _write(root / "jobs" / (job_id + ".json"), job)
    _write(root / "active-job.json", {"job_id": job_id})
    for package, suffix in [(level, ".umap"), (seq, ".uasset"),
                            (asset_paths[0], ".uasset"), (asset_paths[1], ".uasset")]:
        path = tmp_path / "Content" / (package[6:] + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"saved-native-package")
    assets = {asset_paths[0]: Asset("SkeletalMesh"),
              asset_paths[1]: Asset("AnimSequence"),
              seq: Asset("LevelSequence")}
    actors = [Actor("CSAI_Hero", "SkeletalMeshActor"), Actor("CSAI_CAM", "CineCameraActor")]
    fake = NS(
        EditorAssetLibrary=NS(does_asset_exist=lambda p: p in assets),
        load_asset=lambda p: assets.get(p),
        UnrealEditorSubsystem=object(),
        EditorActorSubsystem=object(),
        get_editor_subsystem=lambda kind: (
            NS(get_editor_world=lambda: NS(get_path_name=lambda: level + ".L_Test"))
            if kind == fake.UnrealEditorSubsystem
            else NS(get_all_level_actors=lambda: actors)
        ),
        Paths=NS(get_project_file_path=lambda: str(project)),
    )
    return root, jobfile, candidate, fake, assets, actors


def test_reads_actual_native_classes_and_saved_packages_without_mutating(tmp_path):
    root, _jobfile, candidate, fake, _assets, _actors = fixture(tmp_path)
    report = AUDIT.audit_latest(root, unreal_api=fake)
    assert report["status"] == "STRUCTURAL_READBACK_PASS_RESTART_UNVERIFIED"
    assert report["fidelity_verified"] is False
    assert report["restart_verified"] is False
    assert report["level_file_exists"] is True
    assert report["assets_class_and_disk_verified"] == 2
    assert report["sequence"]["binding_count"] == 1
    assert report["sequence"]["root_track_count"] == 2
    assert all(row["class_matches"] for row in report["actors"])
    assert len(list(candidate.glob("post-reopen-audit-*.json"))) == 1


def test_missing_saved_asset_is_failed_even_when_editor_loads_it(tmp_path):
    _root, jobfile, candidate, fake, _assets, _actors = fixture(tmp_path)
    (tmp_path / "Content" / "Auto" / "Hero.uasset").unlink()
    result = AUDIT.audit(jobfile, candidate / "audit.json", unreal_api=fake)
    assert result["status"] == "STRUCTURAL_READBACK_FAIL"
    assert result["assets"][0]["saved_file_exists"] is False


def test_unknown_track_readback_is_incomplete_not_success(tmp_path):
    _root, jobfile, candidate, fake, assets, _actors = fixture(tmp_path)
    assets["/Game/Testing/LS_New"] = Asset("LevelSequence", expose_tracks=False)
    result = AUDIT.audit(jobfile, candidate / "audit.json", unreal_api=fake)
    assert result["status"] == "STRUCTURAL_READBACK_INCOMPLETE"


def test_duplicate_actor_is_failure(tmp_path):
    _root, jobfile, candidate, fake, _assets, actors = fixture(tmp_path)
    actors.append(Actor("CSAI_CAM", "CineCameraActor"))
    result = AUDIT.audit(jobfile, candidate / "audit.json", unreal_api=fake)
    assert result["status"] == "STRUCTURAL_READBACK_FAIL"
    assert result["actors"][1]["matches"] == 2


def test_wrong_project_and_reused_receipt_never_trigger_editor_mutation(tmp_path):
    root, jobfile, candidate, fake, _assets, _actors = fixture(tmp_path)
    fake.Paths.get_project_file_path = lambda: str(tmp_path / "Wrong.uproject")
    with pytest.raises(AUDIT.PersistenceAuditError, match="Wrong Unreal project"):
        AUDIT.audit(jobfile, candidate / "audit.json", unreal_api=fake)
    assert not (candidate / "audit.json").exists()
    fake.Paths.get_project_file_path = lambda: str(tmp_path / "Target.uproject")
    first = AUDIT.audit_latest(root, unreal_api=fake)
    assert first["status"] == "STRUCTURAL_READBACK_PASS_RESTART_UNVERIFIED"
    with pytest.raises(AUDIT.PersistenceAuditError, match="already exists"):
        AUDIT.audit_latest(root, unreal_api=fake)


def test_incomplete_generation_receipt_cannot_be_claimed_saved(tmp_path):
    _root, jobfile, candidate, fake, _assets, _actors = fixture(tmp_path)
    receipt = candidate / "runtime.json"
    body = json.loads(receipt.read_text(encoding="utf-8"))
    body["status"] = "BLOCKED"
    _write(receipt, body)
    with pytest.raises(AUDIT.PersistenceAuditError, match="completed engine generation"):
        AUDIT.audit(jobfile, candidate / "audit.json", unreal_api=fake)
    assert not (candidate / "audit.json").exists()
