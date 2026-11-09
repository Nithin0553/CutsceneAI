"""One provenance-linked source WAV -> Unreal import -> Studio transfer plan."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))
sys.path.insert(0, str(ROOT / "tests" / "studio"))

import asset_staging
import prepared_transfer
import stage_asset_import
from test_asset_staging import FakeAPI, setup_source


def _inputs(tmp_path):
    project, src, original_mapping, _audio = setup_source(tmp_path)
    doc = json.loads(src.read_text())
    doc["timing"] = {"source_rate": {"numerator": 24, "denominator": 1},
                     "duration_seconds": 1.0}
    doc["tracks"][0]["sections"] = [{
        "section_id": "a", "ced_type": "audio.section",
        "start": {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
        "end": {"value": 1, "rate": {"numerator": 1, "denominator": 1}},
        "payload": {"asset_id": "asset:a1", "audio": {}},
    }]
    src.write_text(json.dumps(doc), encoding="utf-8")
    manifest = asset_staging.compose_files(
        src, original_mapping, source_project=project,
        target_folder="/Game/CutSceneAI/Fresh_Import",
    )
    manifest_file = tmp_path / "manifest.json"
    asset_staging.write_new(manifest_file, manifest)
    target = tmp_path / "Target.uproject"
    api = FakeAPI(target)
    mapped = tmp_path / "mapped.json"
    receipt = tmp_path / "receipt.json"
    stage_asset_import.run(
        manifest_file, src, original_mapping,
        expected_project_path=str(target), resolved_mapping_path=mapped,
        runtime_receipt_path=receipt, rights_confirmed=True, unreal_api=api,
    )
    return src, original_mapping, manifest_file, receipt, mapped, target


def test_import_receipt_is_bound_to_real_source_asset_and_resulting_plan(tmp_path):
    src, original, manifest, receipt, mapped, target = _inputs(tmp_path)
    folder = tmp_path / "session"
    session = prepared_transfer.prepare(
        src, mapped, folder, target_project=target,
        asset_manifest_path=manifest,
        asset_receipt_path=receipt,
        asset_original_mapping_path=original,
    )
    assert session["asset_import"]["imported_count"] == 1
    assert session["asset_import"]["behavioral_fidelity_verified"] is False
    assert session["engine_generation_executed"] is False
    assert session["behavioral_fidelity_established"] is False
    assert prepared_transfer.verify(folder) == session
    actions = json.loads((folder / "transfer-plan.json").read_text())["actions"]
    paths = [x["unreal_asset_path"] for x in actions if x["kind"] == "audio"]
    assert paths == [json.loads(mapped.read_text())["assets"]["Whoosh"]]


@pytest.mark.parametrize("tampered", ["receipt", "manifest", "original", "mapped"])
def test_import_evidence_or_mappings_cannot_change_after_session(tmp_path, tampered):
    src, original, manifest, receipt, mapped, target = _inputs(tmp_path)
    folder = tmp_path / "session"
    prepared_transfer.prepare(
        src, mapped, folder, target_project=target, asset_manifest_path=manifest,
        asset_receipt_path=receipt, asset_original_mapping_path=original,
    )
    path = {"receipt": receipt, "manifest": manifest,
            "original": original, "mapped": mapped}[tampered]
    path.write_text(path.read_text() + " ", encoding="utf-8")
    with pytest.raises((prepared_transfer.PreparedTransferError,
                        asset_staging.AssetStagingError)):
        prepared_transfer.verify(folder)


def test_stale_import_receipt_cannot_feed_new_mapping(tmp_path):
    src, original, manifest, receipt, mapped, target = _inputs(tmp_path)
    doc = json.loads(mapped.read_text())
    doc["assets"]["Whoosh"] = "/Game/Wrong/OtherSound"
    mapped.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(prepared_transfer.PreparedTransferError, match="receipt mismatches"):
        prepared_transfer.prepare(
            src, mapped, tmp_path / "blocked", target_project=target,
            asset_manifest_path=manifest, asset_receipt_path=receipt,
            asset_original_mapping_path=original,
        )
    assert not (tmp_path / "blocked").exists()


def test_all_import_artifacts_and_matching_target_are_required(tmp_path):
    src, original, manifest, receipt, mapped, target = _inputs(tmp_path)
    with pytest.raises(prepared_transfer.PreparedTransferError, match="All three"):
        prepared_transfer.prepare(
            src, mapped, tmp_path / "blocked", target_project=target,
            asset_receipt_path=receipt,
        )
    with pytest.raises(prepared_transfer.PreparedTransferError, match="different Unreal"):
        prepared_transfer.prepare(
            src, mapped, tmp_path / "blocked", target_project=tmp_path / "Wrong.uproject",
            asset_manifest_path=manifest, asset_receipt_path=receipt,
            asset_original_mapping_path=original,
        )
    assert not (tmp_path / "blocked").exists()
