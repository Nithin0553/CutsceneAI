"""Source dataset must be independently captured, hash-checked and immutable."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "packages" / "dataset", ROOT / "packages" / "cinetwin"):
    sys.path.insert(0, str(directory))

import registry
import sampling_plan


def seconds(value):
    return {"value": value, "rate": {"numerator": 1, "denominator": 1}}


def make_source(tmp_path, *, group="project-a", name="scene-a"):
    folder = tmp_path / group / name
    folder.mkdir(parents=True)
    csir_path = folder / "scene.csir.json"
    plan_path = folder / "plan.json"
    capture_path = folder / "capture.json"
    csir = {
        "schema_version": "0.1.0", "cutscene_id": name,
        "source": {"engine": "unity", "engine_version": "6000-test",
                   "sequence_ref": name + ":Director",
                   "project_fingerprint": group},
        "timing": {"source_rate": {"numerator": 2, "denominator": 1},
                   "playback_start": seconds(0), "playback_end": seconds(1)},
        "entities": [{"entity_id": "prop", "name": "Item", "ced_type": "entity.prop",
                      "metadata": {}}],
        "tracks": [],
    }
    csir_path.write_text(json.dumps(csir), encoding="utf-8")
    plan = sampling_plan.plan_file(csir_path, plan_path)
    capture = {
        "kind": "cinetwin.behavior_capture",
        "cutscene_id": name,
        "source": plan["source"],
        "rigs": [],
        "capture_layers": [{
            "layer": c["layer"],
            "status": "CAPTURED" if c["status"] == "PLANNED" else "NOT_IMPLEMENTED",
        } for c in plan["capabilities"]],
        "samples": [{
            "time_seconds": item["time_seconds"],
            "skeletal_poses": [],
            "entities": [{
                "entity_id": "prop",
                "world_transform": {
                    "position_m": [item["time_seconds"], 0, 0],
                    "rotation_xyzw": [0, 0, 0, 1],
                    "scale_xyz": [1, 1, 1],
                },
            }],
        } for item in plan["samples"]],
        "errors": [],
    }
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    return csir_path, plan_path, capture_path


def register(root, paths, *, project="Project01", scene="Scene01"):
    return registry.register(root, project, scene, csir=paths[0],
                             plan=paths[1], capture=paths[2])


def test_registration_stores_real_measured_source_and_does_not_claim_fidelity(tmp_path):
    paths = make_source(tmp_path)
    root = tmp_path / "dataset"
    record = register(root, paths)
    assert record["capture_status"] == "INCOMPLETE"
    assert record["sampling_count"] == 3
    assert record["training_label_status"] == "UNLABELED"
    assert record["full_fidelity_established"] is False
    target = root / "projects" / "Project01" / "Scene01"
    assert registry.verify_record(target) == record
    assert register(root, paths) == record
    assert registry.dataset_report(root)["scene_count"] == 1


def test_changed_csir_is_rejected_when_plan_hash_no_longer_matches(tmp_path):
    paths = make_source(tmp_path)
    paths[0].write_text(paths[0].read_text() + " ", encoding="utf-8")
    with pytest.raises(registry.DatasetError, match="exact source CSIR"):
        register(tmp_path / "dataset", paths)


def test_incomplete_capture_is_rejected_not_used_as_training_data(tmp_path):
    paths = make_source(tmp_path)
    capture = json.loads(paths[2].read_text())
    capture["samples"].pop()
    paths[2].write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(registry.DatasetError, match="capture verification"):
        register(tmp_path / "dataset", paths)


def test_checksum_tampering_detected(tmp_path):
    root = tmp_path / "dataset"
    register(root, make_source(tmp_path))
    target = root / "projects" / "Project01" / "Scene01"
    with (target / "source.csir.json").open("a", encoding="utf-8") as stream:
        stream.write(" ")
    with pytest.raises(registry.DatasetError, match="checksum mismatch"):
        registry.verify_record(target)


def test_reusing_scene_id_with_different_source_is_rejected(tmp_path):
    root = tmp_path / "dataset"
    register(root, make_source(tmp_path, name="scene-a"))
    with pytest.raises(registry.DatasetError, match="different data"):
        register(root, make_source(tmp_path, name="scene-b"))


def test_project_fingerprint_leakage_detected(tmp_path):
    root = tmp_path / "dataset"
    register(root, make_source(tmp_path, group="project-a", name="scene-a"),
             scene="Scene01")
    register(root, make_source(tmp_path, group="project-b", name="scene-b"),
             project="Project02", scene="Scene02")
    report = registry.dataset_report(root)
    assert report["project_level_holdout_possible"] is True
    assert report["independent_source_fingerprint_count"] == 2
    assert report["verified_supervised_label_count"] == 0


def test_reused_display_project_id_with_two_distinct_sources_is_rejected(tmp_path):
    root = tmp_path / "dataset"
    register(root, make_source(tmp_path, group="project-a", name="scene-a"),
             scene="Scene01")
    register(root, make_source(tmp_path, group="project-b", name="scene-b"),
             scene="Scene02")
    with pytest.raises(registry.DatasetError, match="multiple source fingerprints"):
        registry.dataset_report(root)


def test_invalid_scene_identifiers_are_rejected(tmp_path):
    with pytest.raises(registry.DatasetError, match="IDs must be"):
        register(tmp_path / "data", make_source(tmp_path), scene="../outside")
