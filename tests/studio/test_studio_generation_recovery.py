"""A successful native setup may be recovered without repeating asset import.

The fake engine here checks the Python preflight/recovery contract only;
real Unreal regeneration and save/reopen still require a backed-up editor test.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_studio_persistence_audit import Asset, _write, fixture

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "studio_generation_recovery",
    ROOT / "integrations" / "unreal" / "studio_generation_recovery.py",
)
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)


def prepared(tmp_path, monkeypatch):
    root, jobfile, candidate, fake, assets, actors = fixture(tmp_path)
    job = json.loads(jobfile.read_text(encoding="utf-8"))
    job_id = "abcdef0123456789abcdef0123456789"
    csir = tmp_path / "source.csir.json"
    mapping = tmp_path / "mapping.json"
    _write(csir, {"cutscene_id": "safe-fixture"})
    _write(mapping, {"sequence_asset_path": job["sequence_path"]})
    job.update({
        "job_id": job_id,
        "csir": str(csir),
        "mapping": str(mapping),
        "status": "BLOCKED_OR_FAILED",
        "generation_status": "NOT_STARTED",
        "setup_status": "SETUP_SAVED_UNVERIFIED",
        "error": ("cannot import name 'audit_files' from partially initialized "
                  "module 'transfer_readiness' (most likely due to a circular import)"),
        "automatic_setup_manifest": str(candidate / "automatic-setup.json"),
    })
    job.pop("receipt_file")
    job.pop("generated_sequence", None)
    _write(jobfile, job)
    (candidate / "runtime.json").unlink()
    for fname in ("coverage-report.json", "evidence.json"):
        _write(candidate / fname, {"kind": fname})
    manifest_path = candidate / "automatic-setup.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["ready"] = True
    manifest["source_project"] = str(tmp_path)
    manifest["source_scope"] = "Assets"
    _write(manifest_path, manifest)
    setup_path = candidate / "setup.json"
    setup = json.loads(setup_path.read_text(encoding="utf-8"))
    setup["level_saved"] = True
    setup["assets_imported"] = [
        {"path": row["target_asset_path"], "kind": row["kind"]}
        for row in manifest["imports"]
    ]
    setup["actors_created"] = [
        {"name": row["name"], "label": row["label"], "kind": row["kind"]}
        for row in manifest["actors"]
    ]
    _write(setup_path, setup)
    sequence = job["sequence_path"]
    assets.pop(sequence)
    fixture_folder = tmp_path / "Content" / "Testing"
    (fixture_folder / "LS_New.uasset").unlink()
    calls = {"generate": 0, "save": 0, "verify": 0}

    def verify_prepared(path):
        assert Path(path) == candidate
        calls["verify"] += 1
        return {"source": {"csir_path": str(csir)},
                "target": {"mapping_path": str(mapping), "sequence_asset_path": sequence}}

    def verify_assets(path, source, target, plan_path):
        assert Path(path) == manifest_path
        assert source == str(csir) and target == str(mapping)
        assert Path(plan_path) == candidate / "transfer-plan.json"
        return manifest

    def generate(*args, **kwargs):
        assert calls["verify"] == 1
        assert args[0:2] == (str(csir), str(mapping))
        assert args[-1] == str(candidate / ("unreal-runtime-receipt-" + job_id + ".json"))
        assert kwargs["expected_level_path"] == job["expected_level"]
        assert len(actors) == 2
        calls["generate"] += 1
        assets[sequence] = Asset("LevelSequence")
        (fixture_folder / "LS_New.uasset").write_bytes(b"generated-sequence")
        Path(args[-1]).write_text(json.dumps({"status": "GENERATED_UNVERIFIED"}))
        return NS(get_path_name=lambda: sequence + ".LS_New")

    def save(_api, level):
        assert level == job["expected_level"]
        calls["save"] += 1

    monkeypatch.setitem(sys.modules, "studio_auto_assets", NS(verify=verify_assets))
    monkeypatch.setitem(sys.modules, "prepared_transfer", NS(verify=verify_prepared))
    monkeypatch.setitem(sys.modules, "build_level_sequence",
                        NS(transfer_readiness=NS(audit=lambda *x: None),
                           build_prepared_files=generate))
    monkeypatch.setitem(sys.modules, "studio_auto_scene", NS(_save_level=save))
    return root, jobfile, candidate, fake, assets, calls


def test_generator_only_reuses_saved_imported_assets_once(tmp_path, monkeypatch):
    root, jobfile, candidate, fake, _assets, calls = prepared(tmp_path, monkeypatch)
    result = RECOVERY.recover_latest(root, unreal_api=fake)
    assert result["status"] == "GENERATED_UNVERIFIED"
    assert result["assets_reimported"] is False
    assert result["actors_respawned"] is False
    assert result["original_assets_verified"] == 2
    assert result["original_actors_verified"] == 2
    assert calls == {"generate": 1, "save": 1, "verify": 1}
    updated = json.loads(jobfile.read_text(encoding="utf-8"))
    assert updated["status"] == "RECOVERED_GENERATED_NOT_FIDELITY_VERIFIED"
    assert updated["generation_status"] == "GENERATED_UNVERIFIED"
    assert Path(updated["receipt_file"]).is_file()
    assert Path(updated["recovery_file"]).is_file()
    assert json.loads(next(candidate.glob("job-before-recovery-*.json")).read_text())["status"] == "BLOCKED_OR_FAILED"
    with pytest.raises(RECOVERY.GenerationRecoveryError, match="recovery attempt"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    assert calls["generate"] == 1


def test_wrong_project_never_triggers_recovery(tmp_path, monkeypatch):
    root, _jobfile, candidate, fake, _assets, calls = prepared(tmp_path, monkeypatch)
    fake.Paths.get_project_file_path = lambda: str(tmp_path / "Different.uproject")
    with pytest.raises(RECOVERY.GenerationRecoveryError, match="Wrong Unreal project"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    assert calls["generate"] == 0
    assert not list(candidate.glob("generation-recovery-*.json"))


def test_existing_sequence_is_not_overwritten(tmp_path, monkeypatch):
    root, _jobfile, candidate, fake, assets, calls = prepared(tmp_path, monkeypatch)
    assets["/Game/Testing/LS_New"] = Asset("LevelSequence")
    with pytest.raises(RECOVERY.GenerationRecoveryError, match="Target sequence already exists"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    assert calls["generate"] == 0
    assert not list(candidate.glob("generation-recovery-*.json"))


def test_source_asset_missing_prevents_generator(tmp_path, monkeypatch):
    root, _jobfile, candidate, fake, assets, calls = prepared(tmp_path, monkeypatch)
    assets.pop("/Game/Auto/Wave")
    with pytest.raises(RECOVERY.GenerationRecoveryError, match="Staged Unreal asset missing"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    assert calls["generate"] == 0
    assert not list(candidate.glob("generation-recovery-*.json"))


def test_unrelated_failure_cannot_use_special_recovery(tmp_path, monkeypatch):
    root, jobfile, candidate, fake, _assets, calls = prepared(tmp_path, monkeypatch)
    job = json.loads(jobfile.read_text())
    job["error"] = "Skeletal import failed or source mismatch"
    _write(jobfile, job)
    with pytest.raises(RECOVERY.GenerationRecoveryError, match="restricted"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    assert calls["generate"] == 0
    assert not list(candidate.glob("generation-recovery-*.json"))


def test_failed_generator_records_one_attempt_and_preserves_job(tmp_path, monkeypatch):
    root, jobfile, candidate, fake, _assets, calls = prepared(tmp_path, monkeypatch)
    def fail_generate(*args, **kwargs):
        calls["generate"] += 1
        raise RuntimeError("simulated native generation failure")
    monkeypatch.setitem(sys.modules, "build_level_sequence",
                        NS(transfer_readiness=NS(audit=lambda: None),
                           build_prepared_files=fail_generate))
    with pytest.raises(RuntimeError, match="simulated native"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    attempt = json.loads(next(candidate.glob("generation-recovery-*.json")).read_text())
    assert attempt["status"] == "GENERATION_RECOVERY_FAILED_MUST_INSPECT"
    assert json.loads(jobfile.read_text())["status"] == "BLOCKED_OR_FAILED"
    with pytest.raises(RECOVERY.GenerationRecoveryError, match="recovery attempt"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    assert calls["generate"] == 1


def test_missing_setup_receipt_and_no_real_assets_is_blocked(tmp_path, monkeypatch):
    root, jobfile, candidate, fake, _assets, calls = prepared(tmp_path, monkeypatch)
    (candidate / "setup.json").unlink()
    with pytest.raises(RECOVERY.GenerationRecoveryError, match="setup receipt"):
        RECOVERY.recover_latest(root, unreal_api=fake)
    assert calls["generate"] == 0
    assert json.loads(jobfile.read_text())["status"] == "BLOCKED_OR_FAILED"
