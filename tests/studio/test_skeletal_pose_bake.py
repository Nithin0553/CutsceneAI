"""Source-bound skeletal pose baking and guarded Unreal native AnimSequence writing."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/cinetwin", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import sampling_plan
import skeletal_pose_bake as bake
import studio_skeletal_pose_bake as writer


def _time(value: int):
    return {"value": value, "rate": {"numerator": 1, "denominator": 1}}


def _transform(x: float = 0.0, angle: float = 0.0):
    half = math.radians(angle) / 2
    return {"position_m": [x, 0, 0],
            "rotation_xyzw": [0, 0, math.sin(half), math.cos(half)],
            "scale_xyz": [1, 1, 1]}


def _fixture():
    csir = {
        "schema_version": "0.1.0", "cutscene_id": "blend-test",
        "source": {"engine": "unity", "engine_version": "6000.3.10f1",
                   "sequence_ref": "Assets/Timeline.playable",
                   "project_fingerprint": "test-fingerprint"},
        "timing": {
            "source_rate": {"numerator": 2, "denominator": 1},
            "display_rate": {"numerator": 2, "denominator": 1},
            "duration_seconds": 1.0, "playback_start": _time(0),
            "playback_end": _time(1),
        },
        "entities": [{"entity_id": "rig", "name": "Character",
                      "ced_type": "entity.character"}],
        "assets": [{"asset_id": "clip", "name": "Source.anim",
                    "ced_type": "animation.clip"}],
        "tracks": [{
            "track_id": "skeletal", "ced_type": "animation.track",
            "binding_entity_id": "rig",
            "sections": [{
                "section_id": "section", "ced_type": "animation.section",
                "start": _time(0), "end": _time(1),
                "source_offset": _time(0), "time_scale": 1,
                "payload": {"asset_id": "clip", "animation": {"curves": []}},
            }],
        }],
    }
    plan = sampling_plan.build_plan(csir, csir_sha256="a"*64)
    capture = {
        "kind": "cinetwin.behavior_capture",
        "cutscene_id": csir["cutscene_id"],
        "source": plan["source"],
        "capture_layers": [
            {"layer": row["layer"], "status":
             ("CAPTURED" if row["status"] == "PLANNED" else "NOT_IMPLEMENTED")}
            for row in plan["capabilities"]
        ],
        "rigs": [{"entity_id": "rig", "bones": [
            {"bone_id": "hips", "native_bone_name": "Hips", "parent_bone_id": ""},
        ]}],
        "samples": [],
        "errors": [],
    }
    for row in plan["samples"]:
        timestamp = row["time_seconds"]
        pose = _transform(timestamp, timestamp * 90)
        capture["samples"].append({
            "time_seconds": timestamp,
            "entities": [{"entity_id": "rig", "world_transform": _transform()}],
            "skeletal_poses": [{"entity_id": "rig", "bones": [
                {"bone_id": "hips", "local_transform": pose,
                 "world_transform": pose},
            ]}],
        })
    reference = {
        "source_local_reference": _transform(),
        "target_local_reference_unreal": {
            "position_cm": [0, 0, 0],
            "rotation_xyzw": [0, 0, 0, 1],
            "scale_xyz": [1, 1, 1],
        },
        "axis_alignment_canonical_xyzw": [0, 0, 0, 1],
        "translation_scale": 1.0,
    }
    approved = {
        "kind": "cutsceneai.studio.approved_skeletal_pose_bake",
        "schema_version": "1", "reviewed_rest_and_bone_axes": True,
        "source_identity": {
            "csir_sha256": "a"*64, "project_fingerprint": "test-fingerprint",
            "sequence_ref": "Assets/Timeline.playable",
        },
        "source_capture_sha256": "b"*64,
        "source_entity_id": "rig",
        "bone_map": {"hips": "pelvis"},
        "reference": {"hips": reference},
        "target": {
            "skeleton_asset_path": "/Game/Rigs/Sk_Test",
            "animation_asset_path": "/Game/Staging/AS_Baked",
            "unreal_project_identity_sha256": "c"*64,
        },
    }
    return csir, capture, approved


def _compile(csir, capture, approval):
    return bake.compile_baked_pose(
        csir, capture, approval, csir_sha256="a"*64,
        capture_sha256="b"*64,
    )


def test_unity_evaluated_skeletal_local_motion_produces_native_axis_keys():
    csir, capture, approval = _fixture()
    result = _compile(csir, capture, approval)
    assert result["sampled_keys"] == 3
    assert result["sampled_frames"] == 2
    assert result["native_asset_generation_status"] == "NOT_EXECUTED"
    assert result["native_skeleton_or_playback_fidelity_verified"] is False
    track, = result["bone_tracks"]
    assert track["bone_name"] == "pelvis"
    assert track["position_keys_cm"][0] == [0.0, 0.0, 0.0]
    assert track["position_keys_cm"][-1] == pytest.approx([0.0, 100.0, 0.0])
    assert track["rotation_keys_xyzw"][-1][0] == pytest.approx(math.sqrt(0.5))
    assert track["rotation_keys_xyzw"][-1][-1] == pytest.approx(math.sqrt(0.5))
    assert writer._read_bake(_artifact_file(result))["canonical_payload_sha256"] == result[
        "canonical_payload_sha256"
    ]


def _artifact_file(value):
    # All native-writer tests get a separate temporary artifact from a
    # pytest fixture; this helper is replaced below with a local real file.
    import tempfile
    path = Path(tempfile.mkdtemp(prefix="synthetic-pose-bake-")) / "bake.json"
    path.write_text(json.dumps(value))
    return path


def test_approved_source_evidence_must_be_complete_and_unmodified():
    csir, capture, approved = _fixture()
    changed = copy.deepcopy(approved)
    changed["source_capture_sha256"] = "d"*64
    with pytest.raises(bake.PoseBakeError, match="stale"):
        _compile(csir, capture, changed)
    changed = copy.deepcopy(approved)
    changed["reference"]["hips"]["axis_alignment_canonical_xyzw"] = [0, 0, 0, 0]
    with pytest.raises(ValueError, match="unit length"):
        _compile(csir, capture, changed)
    changed = copy.deepcopy(approved)
    changed["bone_map"]["hips"] = "wrong_bone"
    assert _compile(csir, capture, changed)["bone_tracks"][0]["bone_name"] == "wrong_bone"
    # The target skeleton must independently reject an unapproved bone name
    # at native preflight/readback; the source cannot infer target skeleton bones.


def test_missing_source_frame_and_animated_bone_scale_refuse():
    csir, capture, approved = _fixture()
    broken = copy.deepcopy(capture)
    broken["samples"].pop()
    with pytest.raises(bake.PoseBakeError, match="capture"):
        _compile(csir, broken, approved)
    broken = copy.deepcopy(capture)
    broken["samples"][1]["skeletal_poses"][0]["bones"][0]["local_transform"]["scale_xyz"] = [2, 1, 1]
    with pytest.raises(bake.PoseBakeError, match="scale"):
        _compile(csir, broken, approved)


def test_native_writer_rejects_unapproved_and_tampered_payload(tmp_path):
    csir, capture, approved = _fixture()
    baked = _compile(csir, capture, approved)
    path = tmp_path / "bake.json"
    path.write_text(json.dumps(baked))
    receipt = tmp_path / "native-receipt.json"
    with pytest.raises(writer.NativePoseBakeError, match="approval"):
        writer.execute(path, receipt)
    assert not receipt.exists()
    assert writer._read_bake(path)["sampled_keys"] == 3
    baked["bone_tracks"][0]["position_keys_cm"][0][0] = 13
    path.write_text(json.dumps(baked))
    with pytest.raises(writer.NativePoseBakeError, match="checksum"):
        writer._read_bake(path)


def test_native_writer_fail_closed_after_possible_asset_creation(tmp_path):
    csir, capture, approved = _fixture()
    project = tmp_path / "Test.uproject"
    project.write_text("{}")
    identity = hashlib.sha256(
        str(project.resolve()).encode() + b"\0" + project.read_bytes()
    ).hexdigest()
    approved["target"]["unreal_project_identity_sha256"] = identity
    baked = _compile(csir, capture, approved)
    source = tmp_path / "pose-bake.json"
    source.write_text(json.dumps(baked))
    receipt = tmp_path / "native-receipt.json"

    class Asset:
        def __init__(self, path, kind):
            self.path, self.kind = path, kind

        def get_path_name(self):
            return self.path + "." + self.path.rsplit("/", 1)[-1]

        def get_class(self):
            return NS(get_name=lambda: self.kind)

        def get_editor_property(self, name):
            return self.skeleton if name == "skeleton" else None

    skeleton = Asset("/Game/Rigs/Sk_Test", "Skeleton")
    class Tools:
        def create_asset(self, *args):
            animation = Asset("/Game/Staging/AS_Baked", "AnimSequence")
            animation.skeleton = skeleton
            return animation

    class Factory:
        def set_editor_property(self, *args):
            return None

    class EditorAssetLibrary:
        @staticmethod
        def does_asset_exist(path):
            return False

        @staticmethod
        def save_loaded_asset(asset):
            raise AssertionError("Unverified controller must not reach native save")

    api = NS(
        Paths=NS(get_project_file_path=lambda: str(project)),
        SystemLibrary=NS(get_engine_version=lambda: "5.8.1"),
        load_asset=lambda path: skeleton,
        EditorAssetLibrary=EditorAssetLibrary,
        AssetToolsHelpers=NS(get_asset_tools=lambda: Tools()),
        AnimSequenceFactory=Factory, AnimSequence=object, FrameRate=object,
        FrameNumber=object, Vector=object, Quat=object,
    )
    with pytest.raises(writer.NativePoseBakeError, match="DO NOT replay"):
        writer.execute(source, receipt, api=api, explicit_native_approval=True)
    recorded = json.loads(receipt.read_text())
    assert recorded["status"] == "PARTIAL_NATIVE_WRITE_NO_AUTORETRY"
    assert recorded["native_asset_writes_possible"] is True
    with pytest.raises(writer.NativePoseBakeError, match="receipt"):
        writer.execute(source, receipt, api=api, explicit_native_approval=True)
