"""Source-bound, distinct-process Unreal saved AnimSequence readback tests.

These are synthetic Unreal Python API contracts, not evidence of executing
the Unreal 5.8 Editor. Native integration acceptance remains separate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))

import studio_skeletal_pose_readback as readback


def _write(path, data):
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Asset:
    def __init__(self, path, kind, **properties):
        self.path = path
        self.kind = kind
        self.properties = properties

    def get_path_name(self):
        return self.path + "." + self.path.rsplit("/", 1)[-1]

    def get_class(self):
        return NS(get_name=lambda: self.kind)

    def get_editor_property(self, name):
        return self.properties[name]


class NativeLibrary:
    def __init__(self, raw):
        self.raw = raw

    def get_num_frames(self, _asset):
        return 1

    def get_num_keys(self, _asset):
        return 2

    def get_raw_track_data(self, _asset, name):
        return self.raw[name]


def _case(tmp_path):
    project = tmp_path / "Target.uproject"
    project.write_bytes(b"{}")
    identity = hashlib.sha256(
        str(project.resolve()).encode("utf-8") + b"\0" + project.read_bytes()
    ).hexdigest()
    target = {
        "skeleton_asset_path": "/Game/Rig/Sk_Test",
        "animation_asset_path": "/Game/Staging/AS_Test",
        "unreal_project_identity_sha256": identity,
    }
    keys = {
        "position_keys_cm": [[0, 0, 0], [100, 0, 0]],
        "rotation_keys_xyzw": [[0, 0, 0, 1], [0, 0, 1, 0]],
        "scale_keys_xyz": [[1, 1, 1], [1, 1, 1]],
    }
    baked = {
        "kind": "cutsceneai.studio.skeletal_pose_bake", "schema_version": "1",
        "source_entity_id": "character", "target": target,
        "sampled_frames": 1, "sampled_keys": 2,
        "display_rate": {"numerator": 24, "denominator": 1},
        "bone_tracks": [{
            "bone_name": "pelvis", "approved_target_local_reference": {
                "position_cm": [0, 0, 0],
                "rotation_xyzw": [0, 0, 0, 1],
                "scale_xyz": [1, 1, 1],
            },
            **keys,
        }],
    }
    payload = json.dumps(baked, sort_keys=True, separators=(",", ":"), allow_nan=False)
    baked["canonical_payload_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
    bake_path = tmp_path / "bake.json"
    source_hash = _write(bake_path, baked)
    receipt = {
        "kind": "cutsceneai.studio.native_skeletal_pose_bake_receipt",
        "schema_version": "1",
        "source_sha256": source_hash,
        "source_entity_id": "character",
        "target_project_identity_sha256": identity,
        "target_skeleton_asset_path": target["skeleton_asset_path"],
        "target_animation_asset_path": target["animation_asset_path"],
        "status": "NATIVE_SAVED_PENDING_INDEPENDENT_READBACK",
        "native_asset_writes_possible": True,
        "fidelity_verified": False, "native_target_readback_verified": False,
        "saved_bone_count": 1, "saved_key_count_per_bone": 2,
        "generation_editor_pid": 12345,
    }
    receipt_path = tmp_path / "native-write.json"
    _write(receipt_path, receipt)
    skeleton = Asset(target["skeleton_asset_path"], "Skeleton")
    model = NS(
        get_editor_property=lambda name: NS(numerator=24, denominator=1),
        get_bone_track_names=lambda: ["pelvis"],
    )
    animation = Asset(target["animation_asset_path"], "AnimSequence",
                      skeleton=skeleton, data_model_interface=model)
    def vector(xyz):
        return NS(**dict(zip(("x", "y", "z"), xyz)))

    def quat(xyzw):
        return NS(**dict(zip(("x", "y", "z", "w"), xyzw)))

    raw = {"pelvis": (
        [vector(row) for row in keys["position_keys_cm"]],
        [quat(row) for row in keys["rotation_keys_xyzw"]],
        [vector(row) for row in keys["scale_keys_xyz"]],
    )}
    library = NativeLibrary(raw)
    api = NS(
        Paths=NS(get_project_file_path=lambda: str(project)),
        SystemLibrary=NS(get_engine_version=lambda: "5.8.1"),
        AnimationLibrary=library,
        load_asset=lambda path: animation if path == target["animation_asset_path"] else None,
    )
    output = tmp_path / "readback.json"
    return NS(bake=bake_path, receipt=receipt_path, output=output,
              data=receipt, model=model, asset=animation, api=api,
              raw=raw, library=library)


def test_saved_native_raw_bone_key_readback_is_verified_without_mutating_asset(tmp_path):
    case = _case(tmp_path)
    result = readback.verify(case.bake, case.receipt, case.output, api=case.api)
    assert result["status"] == "NATIVE_SAVED_BONE_KEY_READBACK_PASS"
    assert result["native_bone_key_readback_verified"] is True
    assert result["full_cutscene_fidelity_verified"] is False
    assert result["generation_editor_pid"] == 12345
    assert result["observation_editor_pid"] != 12345
    assert result["bone_count"] == 1
    assert case.output.is_file()
    assert json.loads(case.output.read_text()) == result
    assert json.loads(case.receipt.read_text()) == case.data


def test_mismatched_saved_rotation_is_reported_not_certified(tmp_path):
    case = _case(tmp_path)
    case.raw["pelvis"][1][1].w = 1.0
    case.raw["pelvis"][1][1].z = 0.0
    result = readback.verify(case.bake, case.receipt, case.output, api=case.api)
    assert result["status"] == "NATIVE_SAVED_BONE_KEY_READBACK_FAIL"
    assert result["native_bone_key_readback_verified"] is False
    assert result["max_rotation_error_degrees"] > 100
    assert result["mismatches"][0]["channel"] == "rotation"


def test_unmatched_writer_receipt_and_same_editor_process_are_rejected(tmp_path, monkeypatch):
    case = _case(tmp_path)
    changed = copy.deepcopy(case.data)
    changed["source_sha256"] = "b" * 64
    _write(case.receipt, changed)
    with pytest.raises(readback.NativePoseReadbackError, match="receipt"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)
    _write(case.receipt, case.data)
    monkeypatch.setattr(readback.os, "getpid", lambda: 12345)
    with pytest.raises(readback.NativePoseReadbackError, match="different Unreal Editor"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)
    assert not case.output.exists()


def test_missing_native_key_and_extra_bone_are_fail_closed(tmp_path):
    case = _case(tmp_path)
    case.raw["pelvis"][0].pop()
    with pytest.raises(readback.NativePoseReadbackError, match="missing/contracted"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)
    case = _case(tmp_path)
    case.model.get_bone_track_names = lambda: ["pelvis", "another"]
    with pytest.raises(readback.NativePoseReadbackError, match="bone tracks"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)


def test_frame_rate_and_project_identity_drift_fail_closed(tmp_path):
    case = _case(tmp_path)
    case.model.get_editor_property = lambda name: NS(numerator=30, denominator=1)
    with pytest.raises(readback.NativePoseReadbackError, match="frame rate"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)
    case = _case(tmp_path)
    (tmp_path / "Target.uproject").write_text('{"changed":true}')
    with pytest.raises(readback.NativePoseReadbackError, match="Reopened Unreal project"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)


def test_native_api_unavailable_and_output_reuse_are_rejected(tmp_path):
    case = _case(tmp_path)
    case.api.AnimationLibrary = NS()
    with pytest.raises(readback.NativePoseReadbackError, match="APIs unavailable"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)
    case = _case(tmp_path)
    case.output.write_text("prior evidence", encoding="utf-8")
    with pytest.raises(readback.NativePoseReadbackError, match="new"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)
    assert case.output.read_text() == "prior evidence"


def test_unapproved_writer_failure_receipt_never_gets_readback_pass(tmp_path):
    case = _case(tmp_path)
    changed = copy.deepcopy(case.data)
    changed["status"] = "PARTIAL_NATIVE_WRITE_NO_AUTORETRY"
    _write(case.receipt, changed)
    with pytest.raises(readback.NativePoseReadbackError, match="receipt"):
        readback.verify(case.bake, case.receipt, case.output, api=case.api)
