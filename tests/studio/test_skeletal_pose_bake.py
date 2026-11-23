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

    rest = NS(
        translation=NS(x=0, y=0, z=0),
        rotation=NS(x=0, y=0, z=0, w=1),
        scale3d=NS(x=1, y=1, z=1),
    )
    pose_api = NS(
        get_reference_pose=lambda _: object(),
        get_bone_names=lambda _: ["pelvis"],
        get_bone_pose=lambda _pose, _name: rest,
    )
    api = NS(
        AnimPoseExtensions=pose_api,
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



def test_native_writer_saved_animation_stays_pending_readback(tmp_path):
    csir, capture, approved = _fixture()
    project = tmp_path / "Test.uproject"
    project.write_text("{}", encoding="utf-8")
    approved["target"]["unreal_project_identity_sha256"] = hashlib.sha256(
        str(project.resolve()).encode() + b"\0" + project.read_bytes()
    ).hexdigest()
    staged = _compile(csir, capture, approved)
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(staged), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    calls = []

    class Asset:
        def __init__(self, path, kind, skeleton=None, controller=None):
            self.path, self.kind = path, kind
            self.skeleton, self.controller = skeleton, controller

        def get_path_name(self):
            return self.path + "." + self.path.rsplit("/", 1)[-1]

        def get_class(self):
            return NS(get_name=lambda: self.kind)

        def get_editor_property(self, name):
            return self.skeleton if name == "skeleton" else self.controller

        def get_controller(self):
            return self.controller

    class Controller:
        def set_frame_rate(self, rate, notify):
            calls.append(("rate", rate))

        def set_number_of_frames(self, frames, notify):
            calls.append(("frame_count", frames))

        def add_bone_track(self, bone, notify):
            calls.append(("bone", bone))
            return 0  # Valid native track index, not a failure.

        def set_bone_track_keys(self, bone, positions, rotations, scales, notify):
            calls.append(("keys", bone, len(positions), len(rotations), len(scales)))
            return True

    skeleton = Asset("/Game/Rigs/Sk_Test", "Skeleton")
    rest = NS(translation=NS(x=0, y=0, z=0),
              rotation=NS(x=0, y=0, z=0, w=1),
              scale3d=NS(x=1, y=1, z=1))
    extensions = NS(
        get_reference_pose=lambda _: object(),
        get_bone_names=lambda _: ["pelvis"],
        get_bone_pose=lambda _pose, _name: rest,
    )
    anim = Asset("/Game/Staging/AS_Baked", "AnimSequence", skeleton, Controller())

    class Tools:
        def create_asset(self, name, folder, cls, factory):
            calls.append(("created", name, folder))
            return anim

    class Library:
        @staticmethod
        def does_asset_exist(path):
            return False

        @staticmethod
        def save_loaded_asset(asset):
            calls.append(("saved", asset.path))
            return True

    api = NS(
        Paths=NS(get_project_file_path=lambda: str(project)),
        SystemLibrary=NS(get_engine_version=lambda: "5.8.1"),
        AnimPoseExtensions=extensions,
        load_asset=lambda path: skeleton,
        EditorAssetLibrary=Library,
        AssetToolsHelpers=NS(get_asset_tools=lambda: Tools()),
        AnimSequenceFactory=lambda: NS(set_editor_property=lambda *args: None),
        AnimSequence=object,
        FrameRate=lambda n, d: (n, d),
        FrameNumber=lambda n: n,
        Vector=lambda *v: v, Quat=lambda *q: q,
    )
    result = writer.execute(path, receipt, api=api, explicit_native_approval=True)
    assert result["status"] == "NATIVE_SAVED_PENDING_INDEPENDENT_READBACK"
    assert result["native_target_readback_verified"] is False
    assert result["fidelity_verified"] is False
    assert ("keys", "pelvis", 3, 3, 3) in calls
    assert ("created", "AS_Baked", "/Game/Staging") in calls
    assert ("saved", "/Game/Staging/AS_Baked") in calls
    with pytest.raises(writer.NativePoseBakeError, match="receipt"):
        writer.execute(path, receipt, api=api, explicit_native_approval=True)


def test_native_writer_refuses_stale_approved_skeleton_without_creating_asset(tmp_path):
    csir, capture, approved = _fixture()
    project = tmp_path / "Test.uproject"
    project.write_text("{}")
    approved["target"]["unreal_project_identity_sha256"] = hashlib.sha256(
        str(project.resolve()).encode() + b"\0" + project.read_bytes()
    ).hexdigest()
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(_compile(csir, capture, approved)))
    receipt = tmp_path / "receipt.json"

    class Asset:
        def get_path_name(self):
            return "/Game/Rigs/Sk_Test.Sk_Test"

        def get_class(self):
            return NS(get_name=lambda: "Skeleton")

    api = NS(
        Paths=NS(get_project_file_path=lambda: str(project)),
        SystemLibrary=NS(get_engine_version=lambda: "5.8.1"),
        load_asset=lambda _path: Asset(),
        AnimPoseExtensions=NS(
            get_reference_pose=lambda _: object(),
            get_bone_names=lambda _: ["wrong_bone"],
            get_bone_pose=lambda *args: None,
        ),
    )
    with pytest.raises(writer.NativePoseBakeError, match="bone mapping"):
        writer.execute(path, receipt, api=api, explicit_native_approval=True)
    assert not receipt.exists()



def test_skeletal_pose_cli_binds_actual_source_capture_bytes_and_refuses_reuse(tmp_path):
    import importlib.util

    path = ROOT / "tools" / "studio_compile_skeletal_pose.py"
    spec = importlib.util.spec_from_file_location("studio_compile_skeletal_pose", path)
    entry = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(entry)
    source, capture, approved = _fixture()
    source_file = tmp_path / "unity.csir.json"
    capture_file = tmp_path / "unity.behavior.json"
    approval_file = tmp_path / "approved-reference.json"
    output_file = tmp_path / "skeletal-bake.json"
    source_file.write_text(json.dumps(source), encoding="utf-8")
    actual_source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    capture["source"]["csir_sha256"] = actual_source_hash
    capture_file.write_text(json.dumps(capture), encoding="utf-8")
    actual_capture_hash = hashlib.sha256(capture_file.read_bytes()).hexdigest()
    approved["source_identity"]["csir_sha256"] = actual_source_hash
    approved["source_capture_sha256"] = actual_capture_hash
    approval_file.write_text(json.dumps(approved), encoding="utf-8")
    compiled = entry.compile_files(source_file, capture_file, approval_file, output_file)
    assert compiled["source_identity"]["csir_sha256"] == actual_source_hash
    assert compiled["source_capture_sha256"] == actual_capture_hash
    assert writer._read_bake(output_file)["sampled_keys"] == 3
    with pytest.raises(bake.PoseBakeError, match="nonexistent output"):
        entry.compile_files(source_file, capture_file, approval_file, output_file)

    capture["samples"][0]["skeletal_poses"][0]["bones"][0][
        "world_transform"]["position_m"][0] = 12.0
    capture_file.write_text(json.dumps(capture))
    with pytest.raises(bake.PoseBakeError, match="stale"):
        entry.compile_files(
            source_file, capture_file, approval_file, tmp_path / "another-bake.json",
        )


def test_phase10_2_bone_parent_ancestry_rejects_missing_self_or_cycle():
    csir,capture,approval=_fixture()
    for parent in ("hips","missing"):
        sample=copy.deepcopy(capture)
        sample["rigs"][0]["bones"][0]["parent_bone_id"]=parent
        with pytest.raises(bake.PoseBakeError,match="parent"):
            _compile(csir,sample,approval)
    sample=copy.deepcopy(capture)
    sample["rigs"][0]["bones"][0]["parent_bone_id"]="wrist"
    sample["rigs"][0]["bones"].append({
        "bone_id":"wrist","native_bone_name":"Wrist","parent_bone_id":"hips",
    })
    for frame in sample["samples"]:
        frame["skeletal_poses"][0]["bones"].append({
            "bone_id":"wrist","local_transform":_transform(),
            "world_transform":_transform(),
        })
    adjusted=copy.deepcopy(approval)
    adjusted["bone_map"]["wrist"]="hand_r"
    adjusted["reference"]["wrist"]=copy.deepcopy(adjusted["reference"]["hips"])
    with pytest.raises(bake.PoseBakeError,match="cyclic"):
        _compile(csir,sample,adjusted)


def test_phase10_2_baked_quaternion_hemisphere_is_continuous():
    csir,capture,approval=_fixture()
    # Same physical source rotation encoded with the opposite quaternion sign.
    q=capture["samples"][1]["skeletal_poses"][0]["bones"][0][
        "local_transform"]["rotation_xyzw"]
    capture["samples"][1]["skeletal_poses"][0]["bones"][0][
        "local_transform"]["rotation_xyzw"]=[-x for x in q]
    keys=_compile(csir,capture,approval)["bone_tracks"][0]["rotation_keys_xyzw"]
    assert len(keys)==3
    assert all(sum(a*b for a,b in zip(first,second)) >= 0
               for first,second in zip(keys,keys[1:]))
