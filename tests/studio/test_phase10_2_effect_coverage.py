"""Phase 10.2 cinematic-effect source coverage tests; no native fidelity claims."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "packages" / "studio"))

import phase10_2_effects_coverage as coverage


def _source():
    return {
        "source":{"engine":"unity"},"cutscene_id":"effects",
        "assets":[
            {"asset_id":"shader","ced_type":"shader.custom","name":"Shader"},
            {"asset_id":"effect","ced_type":"vfx.particles","name":"Smoke"},
        ],
        "entities":[
            {"entity_id":"light","ced_type":"entity.light","name":"KeyLight"},
            {"entity_id":"character","ced_type":"entity.character","name":"Hero"},
        ],
        "tracks":[
            {"track_id":"lights","ced_type":"light.intensity","name":"LightTrack"},
            {"track_id":"music","ced_type":"audio.track","name":"MusicTrack"},
            {"track_id":"trigger","ced_type":"event.trigger","name":"SignalTrack"},
            {"track_id":"collision","ced_type":"physics.collider","name":"Collision"},
        ],
        "relationships":[],
    }


def test_all_six_cinematic_behavior_families_accounted_without_native_claims():
    csir=_source()
    plan={"actions":[
        {"kind":"light_intensity","source_location":"tracks[0]"},
        {"kind":"audio","source_location":"tracks[1]"},
        {"kind":"marker","source_location":"tracks[2]"},
        {"kind":"collider_primitive_shape","source_location":"tracks[3]"},
    ]}
    report=coverage.audit(csir,plan)
    families={row["family"]:row for row in report["effect_families"]}
    assert set(families)==set(coverage.FAMILIES)
    assert report["effect_source_occurrence_count"]==7
    assert report["effect_source_occurrences_accounted"]==7
    assert all(not row["semantic_equivalence_verified"]
               for row in families.values())
    assert all(row["source_occurrence_count"]>0 for row in families.values())
    assert all(not occurrence["native_readback_verified"]
               for family in families.values()
               for occurrence in family["source_occurrences"])
    assert "LOSSY_NATIVE_ACTION_NOT_EQUIVALENT" in families["audio"]["states"]
    assert "LOSSY_NATIVE_ACTION_NOT_EQUIVALENT" in families["events"]["states"]
    assert report["rendered_audio_event_physics_fidelity_verified"] is False


def test_events_lossy_marker_never_reported_as_executed_signal():
    csir=_source()
    report=coverage.audit(csir,{"actions":[
        {"kind":"marker","source_location":"tracks[2]"}
    ]})
    events=next(r for r in report["effect_families"] if r["family"]=="events")
    assert events["source_occurrences"][0]["conversion_state"] == (
        "LOSSY_NATIVE_ACTION_NOT_EQUIVALENT"
    )
    assert "native_event_execution_and_gameplay_side_effects" in events[
        "required_independent_gates"]


def test_unregistered_effect_command_refused_and_unknown_custom_preserved():
    csir=_source()
    with pytest.raises(coverage.EffectCoverageError,match="Unregistered"):
        coverage.audit(csir,{"actions":[
            {"kind":"run_untrusted_custom_shader","source_location":"assets[0]"},
        ]})
    extra=copy.deepcopy(csir)
    extra["tracks"].append({"track_id":"unknown","ced_type":"plugin.vendor_shader_effect",
                            "name":"VendorFX"})
    report=coverage.audit(extra,{"actions":[]})
    assert report["ced_source_occurrence_count"]==len(
        csir["assets"])+len(csir["entities"])+len(extra["tracks"])
    assert report["full_cutscene_fidelity_verified"] is False
    assert report["effect_source_occurrence_count"] == 7


def test_absent_effects_remain_not_present_not_verified():
    csir={"source":{"engine":"unity"},"cutscene_id":"empty",
          "assets":[],"entities":[],"tracks":[],"relationships":[]}
    report=coverage.audit(csir)
    assert report["effect_source_occurrence_count"]==0
    assert all(family["status"]=="NOT_PRESENT_IN_SOURCE"
               for family in report["effect_families"])
