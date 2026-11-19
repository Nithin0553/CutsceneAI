import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "packages" / "readiness"
sys.path.insert(0, str(READINESS))

import adaptive_mapping


def _profile(
    profile_id: str,
    engine: str,
    version: str,
    capabilities: list[str],
    evidence_ids: list[str] | None = None,
) -> dict:
    return {
        "profile_version": "0.1.0",
        "profile_id": profile_id,
        "engine": {"name": engine, "version": version},
        "project": {"fingerprint": profile_id},
        "conventions": {},
        "capabilities": [
            {"id": capability, "state": "SUPPORTED", "details": {}, "evidence_ids": []}
            for capability in capabilities
        ],
        "settings": {},
        "evidence": [
            {
                "evidence_id": evidence_id,
                "source": "test",
                "value": True,
                "confidence": 1.0,
            }
            for evidence_id in (evidence_ids or [])
        ],
    }


def _rules() -> dict:
    path = ROOT / "packages" / "contracts" / "dictionary" / "adaptive-rules-v0.1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_rotation_mapping_is_capability_driven_not_exact_version_driven() -> None:
    source = _profile(
        "unity-source",
        "unity",
        "6000.3.8f1",
        ["rotation.canonical_quaternion"],
        ["source.coordinate_basis"],
    )
    target = _profile(
        "unreal-target",
        "unreal",
        "5.99-custom",
        ["rotator.semantic_fields"],
        ["target.rotation_semantics"],
    )

    resolved = adaptive_mapping.resolve_dictionary(
        ["transform.rotation"],
        source,
        target,
        _rules(),
    )
    entry = resolved["entries"][0]

    assert entry["status"] == "RESOLVED"
    assert entry["outcome"] == "CONVERTED"
    assert entry["resolver"] == "canonical.rotation.to_target_semantic_fields"
    assert entry["parameters"]["construct_by_named_fields"] is True
    assert entry["parameters"]["never_assume_constructor_position"] is True


def test_missing_required_target_capability_blocks_instead_of_guessing() -> None:
    source = _profile(
        "unity-source",
        "unity",
        "6000.3.8f1",
        ["rotation.canonical_quaternion"],
        ["source.coordinate_basis"],
    )
    target = _profile("unreal-target", "unreal", "5.8.3", [])

    resolved = adaptive_mapping.resolve_dictionary(
        ["transform.rotation"],
        source,
        target,
        _rules(),
    )
    entry = resolved["entries"][0]

    assert entry["status"] == "BLOCKED"
    assert entry["outcome"] == "BLOCKED"
    assert entry["resolver"] == "unresolved.no_matching_rule"


def test_matching_rule_with_missing_evidence_is_not_treated_as_ready() -> None:
    source = _profile(
        "unity-source",
        "unity",
        "6000.3.8f1",
        ["rotation.canonical_quaternion"],
    )
    target = _profile(
        "unreal-target",
        "unreal",
        "5.8.3",
        ["rotator.semantic_fields"],
    )

    entry = adaptive_mapping.resolve_dictionary(
        ["transform.rotation"],
        source,
        target,
        _rules(),
    )["entries"][0]

    assert entry["status"] == "NEEDS_EVIDENCE"
    assert set(entry["parameters"]["missing_evidence"]) == {
        "source.coordinate_basis",
        "target.rotation_semantics",
    }


def test_camera_mapping_preserves_canonical_orientation_and_named_fields() -> None:
    source = _profile(
        "unity-source",
        "unity",
        "6000.3.8f1",
        ["camera.forward_up_basis", "rotation.canonical_quaternion"],
        ["source.coordinate_basis", "source.camera_basis"],
    )
    target = _profile(
        "unreal-target",
        "unreal",
        "5.8.3",
        ["camera.forward_up_basis", "rotator.semantic_fields"],
        ["target.camera_basis", "target.rotation_semantics"],
    )

    entry = adaptive_mapping.resolve_dictionary(
        ["camera.transform"],
        source,
        target,
        _rules(),
    )["entries"][0]

    assert entry["status"] == "RESOLVED"
    assert entry["resolver"] == "canonical.rotation.to_target_semantic_fields"
    assert entry["parameters"]["preserve_full_canonical_orientation"] is True
    assert entry["parameters"]["construct_by_named_fields"] is True
    assert entry["parameters"]["never_assume_constructor_position"] is True


def test_root_motion_mapping_preserves_timing_and_allows_sampled_translation_correction() -> None:
    source = _profile(
        "unity-source",
        "unity",
        "6000.3.8f1",
        ["animation.root_motion_curves"],
        ["source.root_motion_delta"],
    )
    target = _profile(
        "unreal-target",
        "unreal",
        "5.8.3",
        ["animation.root_motion_sampling"],
        ["target.imported_root_motion_delta"],
    )

    entry = adaptive_mapping.resolve_dictionary(
        ["animation.root_motion"],
        source,
        target,
        _rules(),
    )["entries"][0]

    assert entry["status"] == "RESOLVED"
    assert entry["resolver"] == "animation.root_motion.align_from_measured_displacement"
    assert entry["parameters"]["calibrate_target_actor_world_yaw"] is True
    assert (
        entry["parameters"]["calibrate_target_actor_world_translation_from_samples"]
        is True
    )
    assert entry["parameters"]["preserve_animation_timing"] is True
    assert entry["parameters"]["modify_source_asset"] is False


def test_csir_context_promotes_observed_root_motion_capability() -> None:
    csir = {
        "cutscene_id": "benchmark",
        "source": {"engine": "unity"},
        "provenance": {"source_snapshot_hash": "abc"},
        "entities": [],
        "tracks": [
            {
                "ced_type": "animation.track",
                "sections": [
                    {
                        "section_id": "walk",
                        "source_offset": {
                            "value": 0,
                            "rate": {"numerator": 1_000_000, "denominator": 1},
                        },
                        "time_scale": 1.0,
                        "payload": {
                            "animation": {
                                "curves": [
                                    {"property_name": "RootT.x"},
                                    {"property_name": "RootT.y"},
                                    {"property_name": "RootT.z"},
                                ]
                            }
                        },
                    }
                ],
            }
        ],
    }
    context = adaptive_mapping.derive_source_context(csir, "unity-source")

    assert "animation.root_motion_curves" in context["observed_capabilities"]
    observation = next(
        item for item in context["semantic_observations"]
        if item["ced"] == "animation.root_motion"
    )
    assert observation["facts"]["root_translation_curves"] == [
        "RootT.x",
        "RootT.y",
        "RootT.z",
    ]



def test_wrong_engine_evidence_cannot_certify_mapping_readiness() -> None:
    source = _profile("source", "unity", "6000.3", [], [])
    target = _profile("target", "unreal", "5.8", [], [
        "source.coordinate_basis", "target.rotation_semantics",
    ])
    rules = {"rules": [{
        "rule_id": "bound", "ced": "transform.rotation", "priority": 100,
        "source": {"engine": "unity"}, "target": {"engine": "unreal"},
        "resolution": {"outcome": "CONVERTED", "resolver": "safe",
                       "required_evidence": [
                           "source.coordinate_basis", "target.rotation_semantics",
                       ]},
    }]}
    entry = adaptive_mapping.resolve_dictionary(
        ["transform.rotation"], source, target, rules,
    )["entries"][0]
    assert entry["status"] == "NEEDS_EVIDENCE"
    assert entry["parameters"]["missing_evidence"] == ["source.coordinate_basis"]


def test_evidence_from_source_cannot_pretend_to_verify_target_engine() -> None:
    source = _profile("source", "unity", "6000.3", [], [
        "source.coordinate_basis", "target.rotation_semantics",
    ])
    target = _profile("target", "unreal", "5.8", [], [])
    rules = {"rules": [{
        "rule_id": "bound", "ced": "transform.rotation",
        "source": {"engine": "unity"}, "target": {"engine": "unreal"},
        "resolution": {"outcome": "CONVERTED", "resolver": "safe",
                       "required_evidence": [
                           "source.coordinate_basis", "target.rotation_semantics",
                       ]},
    }]}
    entry = adaptive_mapping.resolve_dictionary(
        ["transform.rotation"], source, target, rules,
    )["entries"][0]
    assert entry["status"] == "NEEDS_EVIDENCE"
    assert entry["parameters"]["missing_evidence"] == ["target.rotation_semantics"]


def test_equal_priority_rules_with_different_evidence_must_refuse_ambiguity() -> None:
    import pytest

    source = _profile("source", "unity", "6000.3", [], [])
    target = _profile("target", "unreal", "5.8", [], [])
    base = {
        "ced": "transform.rotation",
        "source": {"engine": "unity"}, "target": {"engine": "unreal"},
        "resolution": {"outcome": "CONVERTED", "resolver": "safe",
                       "parameters": {"roll": "roll", "pitch": "pitch"}},
    }
    first = json.loads(json.dumps(base))
    first["rule_id"] = "first"
    first["resolution"]["required_evidence"] = ["source.coordinate_basis"]
    second = json.loads(json.dumps(base))
    second["rule_id"] = "second"
    second["resolution"]["required_evidence"] = ["target.rotation_semantics"]
    with pytest.raises(adaptive_mapping.MappingResolutionError, match="Ambiguous adaptive"):
        adaptive_mapping.resolve_dictionary(
            ["transform.rotation"], source, target, {"rules": [first, second]},
        )


def test_equal_priority_rules_with_reordered_parameters_agree() -> None:
    source = _profile("source", "unity", "6000.3", [], [])
    target = _profile("target", "unreal", "5.8", [], [])
    a = {"rule_id": "a", "ced": "transform.rotation", "priority": 2,
         "source": {"engine": "unity"}, "target": {"engine": "unreal"},
         "resolution": {"outcome": "CONVERTED", "resolver": "safe",
                        "parameters": {"roll": "roll", "pitch": "pitch"}}}
    b = json.loads(json.dumps(a))
    b["rule_id"] = "b"
    b["resolution"]["parameters"] = {"pitch": "pitch", "roll": "roll"}
    resolved = adaptive_mapping.resolve_dictionary(
        ["transform.rotation"], source, target, {"rules": [a, b]},
    )
    assert resolved["entries"][0]["status"] == "RESOLVED"
    assert resolved["entries"][0]["rule_id"] == "a"


def test_transfer_evidence_needs_external_transfer_gate_not_engine_claim() -> None:
    source = _profile("source", "unity", "6000.3", [], ["transfer.output_resolution"])
    target = _profile("target", "unreal", "5.8", [], [])
    rules = {"rules": [{
        "rule_id": "camera", "ced": "camera.fov",
        "source": {"engine": "unity"}, "target": {"engine": "unreal"},
        "resolution": {"outcome": "CONVERTED", "resolver": "camera.safe",
                       "required_evidence": ["transfer.output_resolution"]},
    }]}
    entry = adaptive_mapping.resolve_dictionary(
        ["camera.fov"], source, target, rules,
    )["entries"][0]
    assert entry["status"] == "NEEDS_EVIDENCE"



def test_camera_mapping_requires_validated_transfer_resolution_evidence() -> None:
    source = _profile("source", "unity", "6000.3", [], [
        "source.camera_fov_axis",
    ])
    target = _profile("target", "unreal", "5.8", [], [
        "target.camera_lens_model",
    ])
    rules = {"rules": [{
        "rule_id": "camera", "ced": "camera.fov", "priority": 1,
        "source": {"engine": "unity"}, "target": {"engine": "unreal"},
        "resolution": {"outcome": "CONVERTED", "resolver": "camera.safe",
                       "required_evidence": [
                           "source.camera_fov_axis", "target.camera_lens_model",
                           "transfer.output_resolution",
                       ]},
    }]}
    missing = adaptive_mapping.resolve_dictionary(
        ["camera.fov"], source, target, rules,
    )["entries"][0]
    assert missing["status"] == "NEEDS_EVIDENCE"
    invalid = adaptive_mapping.resolve_dictionary(
        ["camera.fov"], source, target, rules,
        transfer_context={"output_resolution": [0, 1080]},
    )["entries"][0]
    assert invalid["status"] == "NEEDS_EVIDENCE"
    valid = adaptive_mapping.resolve_dictionary(
        ["camera.fov"], source, target, rules,
        transfer_context={"output_resolution": [2048, 858]},
    )["entries"][0]
    assert valid["status"] == "RESOLVED"
    assert valid["confidence"] == 1.0
