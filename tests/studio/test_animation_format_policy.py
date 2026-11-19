"""Format-specific Unity animation transfer choices are explicit and fail closed."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "integrations/unreal", ROOT / "packages/studio",
                  ROOT / "packages/cinetwin"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import animation_format_policy as formats
import character_compatibility as compatibility
import transfer_backend


def _asset(path):
    return {"asset_id": "clip", "name": "Animation",
            "metadata": {"asset_path": path, "guid": "a"*32}}


@pytest.mark.parametrize(("path", "skeletal", "expected"), [
    ("Assets/Take.fbx", True, formats.CHARACTER_NATIVE),
    ("Assets/Take.fbx", False, formats.ACTOR_CURVES),
    ("Assets/Walk.anim", True, formats.SKELETAL_BAKE),
    ("Assets/Walk.anim", False, formats.ACTOR_CURVES),
    ("Assets/Model.glb", True, formats.EXTERNAL),
    ("Assets/Bones.bvh", True, formats.EXTERNAL),
    ("Assets/Scene.blend", False, formats.EXTERNAL),
    ("Assets/Special.unknown", True, formats.UNKNOWN),
    ("Assets/../Secrets.fbx", True, formats.UNKNOWN),
])
def test_known_and_unsupported_formats_have_exact_native_policies(path, skeletal, expected):
    decision = formats.classify(_asset(path), skeletal=skeletal)
    assert decision["policy"] == expected
    assert decision["native_conversion_approved"] is False


def test_native_unity_skeletal_anim_keeps_verified_hash_but_requires_pose_bake(monkeypatch):
    metadata = {
        "asset_path": "Assets/Character.anim", "guid": "a"*32,
        "source_sha256": "b"*64, "source_meta_sha256": "c"*64,
        "animation_clip": {"frame_rate": 24.0},
    }
    asset = {"asset_id": "clip", "name": "Walk", "metadata": metadata}
    called = []
    def check(context, record, suffix):
        called.append(suffix)
        return {"status": "EXACT", "guid": "a"*32, "sha256": "b"*64,
                "meta_sha256": "c"*64}
    monkeypatch.setattr(compatibility, "_asset", check)
    decision = compatibility._clip(
        {}, {"section_id": "clip-section"}, asset,
        {"assets": {"Walk": "/Game/Target/AS_Walk"}},
    )
    assert called == [".anim"]
    assert decision["source_format"] == ".anim"
    assert decision["status"] == formats.SKELETAL_BAKE
    assert "native skeletal pose" in decision["next_step"].casefold()


@pytest.mark.parametrize("extension", [".anim", ".bvh", ".glb", ".blend"])
def test_skeletal_unhandled_format_blocks_before_unreal_mutation(extension):
    src = {
        "schema_version": "0.1.0", "cutscene_id": "synthetic",
        "source": {"engine": "unity", "project_fingerprint": "p"},
        "timing": {
            "source_rate": {"numerator": 24, "denominator": 1},
            "duration_seconds": 1.0,
            "playback_start": {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
            "playback_end": {"value": 1, "rate": {"numerator": 1, "denominator": 1}},
        },
        "entities": [{"entity_id": "char", "name": "Character", "ced_type": "entity.character"}],
        "assets": [{**_asset("Assets/Walk" + extension), "ced_type": "animation.clip"}],
        "tracks": [{
            "track_id": "skeletal-track", "ced_type": "animation.track",
            "binding_entity_id": "char",
            "sections": [{
                "section_id": "clip", "start": {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
                "end": {"value": 1, "rate": {"numerator": 1, "denominator": 1}},
                "source_offset": {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
                "payload": {"asset_id": "clip", "animation": {"curves": []}},
            }],
        }],
    }
    target = {
        "entities": {"Character": {"actor_label": "TargetCharacter"}},
        "assets": {"Animation": "/Game/Target/AS_Animation"},
    }
    with pytest.raises(transfer_backend.TransferBackendError,
                       match="requires a verified native skeletal"):
        transfer_backend.compose(src, target)
    assert formats.inventory(src)["sections"][0]["format"] == extension
