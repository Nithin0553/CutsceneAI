"""Pure-function regression tests for source-authenticated CineTwin diagnosis."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))

import diagnose_cinetwin_parity as diagnosis


def source_pair():
    csir = {
        "cutscene_id": "scene:001",
        "source": {
            "sequence_ref": "UnityTimeline",
            "project_fingerprint": "fingerprint",
        },
        "timing": {"display_rate": {"numerator": 24, "denominator": 1}},
    }
    hash_value = hashlib.sha256(json.dumps(csir).encode()).hexdigest()
    capture = {
        "cutscene_id": "scene:001",
        "source": {
            "csir_sha256": hash_value,
            "sequence_ref": "UnityTimeline",
            "project_fingerprint": "fingerprint",
        },
        "samples": [
            {"time_seconds": 0.0, "entities": [], "skeletal_poses": []},
            {"time_seconds": 1 / 24, "entities": [], "skeletal_poses": []},
            # Valid intentional quarter-frame sample must not overwrite frame 1.
            {"time_seconds": 1.25 / 24, "entities": [], "skeletal_poses": []},
            {"time_seconds": 2 / 24, "entities": [], "skeletal_poses": []},
        ],
    }
    return csir, capture, hash_value


def test_canonical_unity_to_unreal_axes_meters_to_centimeters():
    assert diagnosis.canonical_to_unreal_cm([1.5, 2, -3]) == (300, 150, 200)


@pytest.mark.parametrize("source", [
    "Timeline[0]/mixamorig9:Hips[7]",
    "Hips[0]",
    "CHARACTER_A[1]/Hips",
])
def test_source_bone_paths_normalize_to_unreal_hips(source):
    assert diagnosis._bone_alias(source) == "hips"


def test_source_frame_index_excludes_subframe_transition_samples():
    csir, capture, hash_value = source_pair()
    frames, missing, fps = diagnosis._get_source_index(csir, capture, hash_value)
    assert list(sorted(frames)) == [0, 1, 2]
    assert missing == []
    assert fps == 24
    assert frames[1]["time_seconds"] == pytest.approx(1 / 24)


def test_missing_source_frames_remain_explicit():
    csir, capture, hash_value = source_pair()
    capture["samples"].pop(1)
    frames, missing, _ = diagnosis._get_source_index(csir, capture, hash_value)
    assert set(frames) == {0, 2}
    assert missing == [1]


@pytest.mark.parametrize("tamper", ["csir_hash", "cutscene_id", "project_fingerprint"])
def test_source_capture_provenance_tampering_blocks(tamper):
    csir, capture, hash_value = source_pair()
    if tamper == "csir_hash":
        hash_value = "incorrect"
    elif tamper == "cutscene_id":
        capture["cutscene_id"] = "another"
    else:
        capture["source"]["project_fingerprint"] = "other"
    with pytest.raises(diagnosis.ParityDiagnosticError):
        diagnosis._get_source_index(csir, capture, hash_value)


def test_world_pose_differences_separate_initial_offset_and_motion_error():
    samples = [
        {"frame": 0, "source_cm": (1090, 151, 95), "target_cm": (1004, 154, 95)},
        {"frame": 24, "source_cm": (953, 151, 89), "target_cm": (870, 154, 89)},
        {"frame": 48, "source_cm": (817, 152, 94), "target_cm": (736, 155, 94)},
    ]
    report = diagnosis._summarize(samples)
    assert report["status"] == "MEASURED_NOT_FIDELITY_VERIFIED"
    assert report["initial_offset_target_minus_source_cm"] == (-86, 3, 0)
    assert report["max_offset_removed_motion_error_cm"] == pytest.approx(5)
    assert report["max_offset_removed_motion_error_frame"] == 48
    assert report["first_to_last_source_displacement_cm"] == (-273, 1, -1)
    assert report["first_to_last_target_displacement_cm"] == (-268, 1, -1)
    assert len(report["checkpoints"]) == 3


def test_source_world_entity_and_hips_are_distinct_semantics():
    sample = {
        "entities": [{
            "entity_id": "a",
            "world_transform": {"position_m": [1, 2, -3]},
        }],
        "skeletal_poses": [{
            "entity_id": "a",
            "bones": [{
                "bone_id": "Actor[0]/mixamorig9:Hips[7]",
                "world_transform": {"position_m": [1, 2.95, -3.4]},
            }],
        }],
    }
    assert diagnosis._source_entity(sample, "a") == (300, 100, 200)
    point, bone = diagnosis._source_bone(sample, "a", "Hips")
    assert bone == "Actor[0]/mixamorig9:Hips[7]"
    assert point == pytest.approx((340, 100, 295))
    assert diagnosis._source_bone(sample, "other", "Hips") == (None, None)


def test_ambiguous_source_bone_names_are_not_guessed():
    sample = {
        "skeletal_poses": [{
            "entity_id": "a",
            "bones": [
                {"bone_id": "Rig/Hips[0]", "world_transform": {"position_m": [0, 0, 0]}},
                {"bone_id": "Other/Hips[0]", "world_transform": {"position_m": [0, 0, 0]}},
            ],
        }],
    }
    assert diagnosis._source_bone(sample, "a", "Hips") == (None, None)


def test_bom_json_is_read_without_modifying_source(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"entities": {}}')
    original = path.read_bytes()
    assert diagnosis._load(path) == {"entities": {}}
    assert path.read_bytes() == original


def test_empty_summary_does_not_claim_fidelity():
    assert diagnosis._summarize([]) == {
        "status": "NO_MATCHED_POSES", "sample_count": 0,
    }
