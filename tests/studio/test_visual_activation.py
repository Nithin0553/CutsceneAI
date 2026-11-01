"""ActivationTrack visual-only mapping is optional and never gameplay parity."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for part in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    sys.path.insert(0, str(ROOT / part))

import transfer_backend
import visual_activation


def rt(seconds):
    return {"value": round(seconds * 1000000),
            "rate": {"numerator": 1000000, "denominator": 1}}


def sample():
    csir = {
        "schema_version": "0.1.0",
        "cutscene_id": "activation-fixture",
        "source": {"engine": "unity"},
        "timing": {
            "source_rate": {"numerator": 24, "denominator": 1},
            "playback_start": rt(0),
            "playback_end": rt(6),
            "duration_seconds": 6,
        },
        "assets": [],
        "entities": [{
            "entity_id": "hero", "name": "Hero", "ced_type": "entity.prop",
            "metadata": {"world_transform": {
                "position": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "scale": {"x": 1, "y": 1, "z": 1},
            }},
        }],
        "tracks": [{
            "track_id": "act", "name": "Activation", "ced_type": "event.state",
            "binding_entity_id": "hero",
            "metadata": {"native_type": "UnityEngine.Timeline.ActivationTrack"},
            "sections": [
                {"section_id": "s1", "ced_type": "event.state",
                 "start": rt(1), "end": rt(2),
                 "payload": {"activation": {"active": True,
                                            "post_playback_state": "Revert"}}},
                {"section_id": "s2", "ced_type": "event.state",
                 "start": rt(4), "end": rt(5),
                 "payload": {"activation": {"active": True,
                                            "post_playback_state": "Revert"}}},
            ],
        }],
    }
    mapping = {
        "sequence_asset_path": "/Game/Testing/LS_Activation",
        "overwrite_sequence": False,
        "entities": {"Hero": {"actor_label": "CSAI_Hero"}},
        "assets": {},
    }
    return csir, mapping


def test_optin_activation_creates_one_visual_only_native_track():
    source, mapping = sample()
    before_source = copy.deepcopy(source)
    before_mapping = copy.deepcopy(mapping)
    mapping["enable_actor_visibility_fallback"] = True
    plan, report = transfer_backend.compose(source, mapping)
    visibility = [a for a in plan["actions"] if a["kind"] == "actor_visibility"]
    assert len(visibility) == 1
    assert visibility[0]["keys"] == [
        {"frame": 0, "hidden": True},
        {"frame": 24, "hidden": False},
        {"frame": 48, "hidden": True},
        {"frame": 96, "hidden": False},
        {"frame": 120, "hidden": True},
    ]
    assert visibility[0]["fidelity_status"] == "RENDER_ONLY_PARTIAL_UNVERIFIED"
    assert visibility[0]["semantic_losses"]
    assert report["tracks"][0]["outcome"] == "BAKED_PARTIAL"
    assert report["feature_dispatch"]["full_conversion_verified"] is False
    assert report["feature_dispatch"]["unknown_action_kinds"] == []
    assert source == before_source
    assert {k: v for k, v in mapping.items()
            if k != "enable_actor_visibility_fallback"} == before_mapping


def test_optout_activation_does_not_invent_a_native_track():
    source, mapping = sample()
    plan, report = transfer_backend.compose(source, mapping)
    assert not any(a["kind"] == "actor_visibility" for a in plan["actions"])
    assert report["tracks"][0]["outcome"] == "SKIPPED"
    assert report["no_full_fidelity_claim"] is True


@pytest.mark.parametrize("corruption", [
    "missing_bind", "invalid_post", "missing_payload", "out_of_bounds",
    "wrong_native", "empty_sections", "invalid_rate",
])
def test_unsafe_activation_data_is_rejected_not_approximated(corruption):
    source, mapping = sample()
    mapping["enable_actor_visibility_fallback"] = True
    track = source["tracks"][0]
    section = track["sections"][0]
    if corruption == "missing_bind":
        track["binding_entity_id"] = "unknown"
    elif corruption == "invalid_post":
        section["payload"]["activation"]["post_playback_state"] = "Vendor"
    elif corruption == "missing_payload":
        section["payload"] = {}
    elif corruption == "out_of_bounds":
        section["end"] = rt(99)
    elif corruption == "wrong_native":
        track["metadata"]["native_type"] = "MyVendor.ToggleTrack"
    elif corruption == "empty_sections":
        track["sections"] = []
    elif corruption == "invalid_rate":
        source["timing"]["source_rate"]["denominator"] = 0
    with pytest.raises(visual_activation.VisualActivationError):
        visual_activation.build_action(source, mapping, track)


def test_adjacent_activation_sections_are_merged():
    source, mapping = sample()
    source["tracks"][0]["sections"][1]["start"] = rt(2)
    action = visual_activation.build_action(source, mapping, source["tracks"][0])
    assert action["keys"] == [
        {"frame": 0, "hidden": True},
        {"frame": 24, "hidden": False},
        {"frame": 120, "hidden": True},
    ]


def test_existing_ue_builder_contains_native_visibility_realizer():
    code = (ROOT / "integrations" / "unreal" / "build_level_sequence.py"
            ).read_text(encoding="utf-8")
    assert "unreal.MovieSceneVisibilityTrack" in code or '"MovieSceneVisibilityTrack"' in code
    assert 'elif kind == "actor_visibility"' in code
    assert "bHidden" in code
    assert "VISUAL ONLY (partial)" in code


def test_preflight_declares_partial_only_when_visual_fallback_opted_in():
    import ced_preflight

    source, mapping = sample()
    without = ced_preflight.audit(source, mapping)
    track = next(row for row in without["findings"] if row["kind"] == "track")
    assert track["state"] == "KNOWN_UNSUPPORTED"
    mapping["enable_actor_visibility_fallback"] = True
    opted = ced_preflight.audit(source, mapping)
    rows = [row for row in opted["findings"]
            if row["kind"] in {"track", "section"} and row["ced"] == "event.state"]
    assert len(rows) == 3
    assert all(row["state"] == "KNOWN_PARTIAL" for row in rows)
    assert all("visibility" in row["reason"] for row in rows)
    assert opted["strict_transfer_allowed"] is False
