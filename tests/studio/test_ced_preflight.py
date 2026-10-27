"""CED preflight audits semantics without modifying source, target or dictionary."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
import ced_preflight


def _source():
    return {
        "schema_version": "0.1.0",
        "cutscene_id": "ced-scene",
        "source": {"engine": "unity"},
        "entities": [
            {"entity_id": "hero", "ced_type": "entity.character", "name": "Hero"},
            {"entity_id": "cam", "ced_type": "entity.camera", "name": "Cam"},
        ],
        "assets": [{"asset_id": "clip", "name": "Walk", "ced_type": "animation.clip"}],
        "tracks": [{
            "track_id": "t1", "ced_type": "animation.track",
            "binding_entity_id": "hero",
            "metadata": {"native_type": "UnityEngine.Timeline.AnimationTrack"},
            "sections": [{
                "section_id": "s1", "ced_type": "animation.section",
                "payload": {"asset_id": "clip", "animation": {"curves": [{
                    "canonical_semantic": "transform.position.x",
                    "property_name": "m_LocalPosition.x",
                }]}},
            }],
        }],
        "relationships": [],
    }


def _mapping():
    return {
        "entities": {
            "Hero": {"actor_label": "HeroUnreal"},
            "Cam": {"actor_label": "CameraUnreal"},
        },
        "assets": {"Walk": "/Game/Clips/Walk"},
    }


def test_known_track_and_canonical_axis_are_supported_but_not_verified():
    s, m = _source(), _mapping()
    saved = copy.deepcopy(s), copy.deepcopy(m)
    out = ced_preflight.audit(s, m)
    assert (s, m) == saved
    assert out["status"] == "READY_FOR_ENGINE_PREFLIGHT"
    assert out["strict_transfer_allowed"] is True
    assert out["ced_version"] == "0.1.0"
    assert len(out["ced_sha256"]) == 64
    assert out["active_alert_count"] == 0
    curves = [x for x in out["findings"] if x["kind"] == "curve"]
    assert len(curves) == 1
    assert curves[0]["ced"] == "transform.position"
    assert curves[0]["state"] == "SUPPORTED_UNVERIFIED"


def test_custom_unity_track_is_not_mistaken_for_generic_supported_timeline_track():
    src = _source()
    original = copy.deepcopy(src)
    for index in range(2):
        src["tracks"].append({
            "track_id": f"custom-{index}", "ced_type": "timeline.track",
            "metadata": {"native_type": "com.studio.ImpulseCameraTrack"},
            "sections": [{
                "section_id": f"sec-{index}", "ced_type": "timeline.clip",
                "native_payload": {"native_asset_type": "com.studio.ImpulseClip"},
                "payload": {},
            }],
        })
    report = ced_preflight.audit(src, _mapping())
    alerts = [f for f in report["findings"] if f["state"] == "UNKNOWN_NATIVE"]
    assert len(alerts) == 4  # two tracks and two sections
    assert report["unique_discovery_count"] == 2
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["strict_transfer_allowed"] is False
    assert src["tracks"][:-2] == original["tracks"]


def test_known_ced_does_not_mean_unreal_conversion_is_supported():
    source = _source()
    source["tracks"][0]["ced_type"] = "event.state"
    report = ced_preflight.audit(source, _mapping())
    event = next(x for x in report["findings"] if x["kind"] == "track")
    assert event["state"] == "KNOWN_UNSUPPORTED"
    assert report["strict_transfer_allowed"] is False


def test_unknown_semantic_and_missing_asset_are_distinct():
    s = _source()
    s["tracks"][0]["sections"][0]["payload"]["animation"]["curves"].append({
        "canonical_semantic": "render.custom_laser_intensity",
        "property_name": "LaserIntensity",
    })
    mapping = _mapping()
    mapping["assets"] = {}
    out = ced_preflight.audit(s, mapping)
    assert {"UNKNOWN_CED", "MISSING_TARGET_MAPPING"} <= set(out["counts"])
    findings = [f for f in out["findings"] if f["state"] == "UNKNOWN_CED"]
    assert findings[0]["source_location"].endswith("curves[1]")
    assert out["strict_transfer_allowed"] is False


def test_native_property_without_canonical_semantic_requires_evidence():
    s = _source()
    s["tracks"][0]["sections"][0]["payload"]["animation"]["curves"] = [{
        "property_name": "m_MysteryValue",
    }]
    out = ced_preflight.audit(s, _mapping())
    curve = next(f for f in out["findings"] if f["kind"] == "curve")
    assert curve["state"] == "NEEDS_EVIDENCE"
    assert out["status"] == "REVIEW_REQUIRED"


def test_generic_native_group_is_known_but_explicitly_unsupported():
    s = _source()
    s["tracks"].append({
        "track_id": "group", "ced_type": "timeline.track",
        "metadata": {"native_type": "UnityEngine.Timeline.GroupTrack"},
        "sections": [{"section_id": "g", "ced_type": "timeline.clip",
                      "native_payload": {}, "payload": {}}],
    })
    out = ced_preflight.audit(s, _mapping())
    track = next(x for x in out["findings"] if x["source_id"] == "group")
    assert track["ced"] == "timeline.group"
    assert track["state"] == "KNOWN_UNSUPPORTED"


def test_muted_unknown_track_is_still_observed_but_not_active_alert():
    src = _source()
    src["tracks"].append({
        "track_id": "muted", "ced_type": "custom.unrecognized",
        "muted": True, "sections": [{"section_id": "s2", "ced_type": "custom.section",
                                    "payload": {}}],
    })
    out = ced_preflight.audit(src, _mapping())
    active = [x for x in out["findings"] if x["state"] == "UNKNOWN_CED"]
    assert active
    assert all(x["active"] is False for x in active)
    assert out["status"] == "READY_FOR_ENGINE_PREFLIGHT"


def test_feature_fingerprint_remains_stable_across_different_track_ids_and_paths():
    s1 = _source()
    s2 = _source()
    s1["tracks"][0].update({
        "ced_type": "timeline.track",
        "metadata": {"native_type": "game.CustomCameraTrack"},
        "track_id": "studio-a",
    })
    s2["tracks"][0].update({
        "ced_type": "timeline.track",
        "metadata": {"native_type": "game.CustomCameraTrack"},
        "track_id": "studio-b",
    })
    s2["source"]["path"] = "D:/very-private-project"
    a, b = ced_preflight.audit(s1, _mapping()), ced_preflight.audit(s2, _mapping())
    fa = next(x for x in a["findings"] if x["kind"] == "track")
    fb = next(x for x in b["findings"] if x["kind"] == "track")
    assert fa["feature_fingerprint"] == fb["feature_fingerprint"]
    assert "very-private" not in json.dumps(b)


def test_cli_reports_unknown_and_strict_blocks_without_engine_mutation(tmp_path: Path):
    source = _source()
    source["tracks"][0]["ced_type"] = "timeline.track"
    source["tracks"][0]["metadata"]["native_type"] = "company.Custom"
    src = tmp_path / "source.json"
    mapping = tmp_path / "map.json"
    output = tmp_path / "report.json"
    src.write_text(json.dumps(source), encoding="utf-8")
    mapping.write_text(json.dumps(_mapping()), encoding="utf-8")
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    cmd = [sys.executable, str(ROOT / "tools" / "ced_preflight.py"),
           "--csir", str(src), "--mapping", str(mapping), "--out", str(output)]
    done = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert done.returncode == 0, done.stderr
    assert "[UNKNOWN_NATIVE]" in done.stdout
    assert output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    blocked = subprocess.run(cmd[: -2] + ["--strict"], text=True,
                             capture_output=True, check=False)
    assert blocked.returncode == 2
    assert "STRICT CED PREFLIGHT: BLOCKED" in blocked.stderr
    unchanged = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert unchanged.returncode == 2
    assert "Refusing to overwrite" in unchanged.stderr
