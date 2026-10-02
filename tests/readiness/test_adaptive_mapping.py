import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "packages" / "readiness"
sys.path.insert(0, str(READINESS))

import adaptive_mapping


def _profile(profile_id: str, engine: str, version: str, capabilities: list[str]) -> dict:
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
        "evidence": [],
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
    )
    target = _profile(
        "unreal-target",
        "unreal",
        "5.99-custom",
        ["rotator.semantic_fields"],
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


def test_camera_mapping_uses_project_capabilities_and_semantic_basis() -> None:
    source = _profile(
        "unity-source",
        "unity",
        "6000.3.8f1",
        ["camera.forward_up_basis", "rotation.canonical_quaternion"],
    )
    target = _profile(
        "unreal-target",
        "unreal",
        "5.8.3",
        ["camera.forward_up_basis", "rotator.semantic_fields"],
    )

    resolved = adaptive_mapping.resolve_dictionary(
        ["camera.transform"],
        source,
        target,
        _rules(),
    )
    entry = resolved["entries"][0]

    assert entry["resolver"] == "camera.orientation.from_forward_up"
    assert entry["parameters"]["preserve_authored_roll"] is True
    assert entry["parameters"]["zero_unobserved_roll"] is True
    assert entry["parameters"]["verify_horizon"] is True
