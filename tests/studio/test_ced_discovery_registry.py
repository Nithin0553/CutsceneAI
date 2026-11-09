"""The CED discovery queue stores only new semantics and never mutates source."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import ced_discovery_registry as registry
import ced_preflight


def _source(native: str = "Studio.CustomEffect"):
    return {
        "cutscene_id": "scene-sensitive",
        "source": {"engine": "unity", "private_file": "D:/PRIVATE/SCENE"},
        "entities": [
            {"entity_id": "actor", "name": "SecretActor",
             "ced_type": "entity.prop"},
        ],
        "assets": [],
        "tracks": [{
            "track_id": "track-private-1", "ced_type": "timeline.track",
            "metadata": {"native_type": native},
            "sections": [{
                "section_id": "section-private-1", "ced_type": "timeline.clip",
                "native_payload": {"native_asset_type": "Studio.CustomClip"},
                "payload": {},
            }],
        }],
    }


def _report(native: str = "Studio.CustomEffect"):
    return ced_preflight.audit(_source(native), {
        "entities": {"SecretActor": {"actor_label": "SecretUE"}},
        "assets": {},
    })


def test_single_run_groups_unknowns_and_does_not_store_private_source_data(tmp_path):
    data = _report()
    assert data["unique_discovery_count"] == 2
    before = copy.deepcopy(data)
    file = tmp_path / "local-events.jsonl"
    result = registry.record(data, file)
    assert result["new_feature_signatures"] == 2
    assert result["new_observations"] == 2
    assert data == before
    lines = registry.read_events(file)
    assert len(lines) == 2
    text = file.read_text(encoding="utf-8")
    for secret in ("SecretActor", "SCENE", "track-private", "section-private",
                   "Studio.CustomEffect", "Studio.CustomClip", "scene-sensitive"):
        assert secret not in text
    assert all(len(x["source_digest"]) == 64 for x in lines)
    assert all(x["classification"] == "UNKNOWN_NATIVE" for x in lines)
    assert all(x["kind"] == "ced.discovery" for x in lines)


def test_second_run_is_idempotent_but_new_source_snapshot_is_observed(tmp_path):
    first = _report()
    path = tmp_path / "registry.jsonl"
    registry.record(first, path)
    original_bytes = path.read_bytes()
    again = registry.record(first, path)
    assert again["new_feature_signatures"] == 0
    assert again["new_observations"] == 0
    assert again["already_recorded"] == 2
    assert path.read_bytes() == original_bytes

    new_source = copy.deepcopy(first)
    new_source["source_csir_sha256"] = "a" * 64
    incoming = registry.record(new_source, path)
    assert incoming["new_feature_signatures"] == 0
    assert incoming["new_observations"] == 2
    assert len(registry.read_events(path)) == 4


def test_known_partial_or_unmapped_do_not_create_new_semantic_tasks(tmp_path):
    partial = _report()
    for f in partial["findings"]:
        f["state"] = "KNOWN_PARTIAL"
    partial["source_csir_sha256"] = "b" * 64
    file = tmp_path / "empty.jsonl"
    result = registry.record(partial, file)
    assert result["novel_observation_groups"] == 0
    assert not file.exists()
    for f in partial["findings"]:
        f["state"] = "MISSING_TARGET_MAPPING"
    second = registry.record(partial, file)
    assert second["new_observations"] == 0
    assert not file.exists()


def test_invalid_registry_fails_before_append_and_preserves_existing_bytes(tmp_path):
    file = tmp_path / "corrupt.jsonl"
    file.write_text("{invalid JSON}\n", encoding="utf-8")
    before = file.read_bytes()
    with pytest.raises(registry.DiscoveryRegistryError, match="Malformed registry"):
        registry.record(_report(), file)
    assert file.read_bytes() == before


def test_invalid_source_hash_and_mixed_fingerprint_are_refused(tmp_path):
    report = _report()
    report["source_csir_sha256"] = "not-a-sha"
    with pytest.raises(registry.DiscoveryRegistryError, match="SHA-256"):
        registry.record(report, tmp_path / "bad.jsonl")
    assert not (tmp_path / "bad.jsonl").exists()
    report = _report()
    unknown = [f for f in report["findings"] if f["state"] == "UNKNOWN_NATIVE"]
    unknown[1]["feature_fingerprint"] = unknown[0]["feature_fingerprint"]
    with pytest.raises(registry.DiscoveryRegistryError, match="conflicting"):
        registry.discoveries(report)


def test_dry_run_previews_without_writing_a_registry(tmp_path):
    file = tmp_path / "local.jsonl"
    dry = registry.record(_report(), file, dry_run=True)
    assert dry["new_feature_signatures"] == 2
    assert dry["new_observations"] == 2
    assert dry["dry_run"] is True
    assert not file.exists()


def test_cli_ingests_existing_report_with_no_unknowns(tmp_path):
    report = _report()
    report["source_csir_sha256"] = "1" * 64
    for finding in report["findings"]:
        if finding["state"] in registry.NOVEL_STATES:
            finding["state"] = "KNOWN_PARTIAL"
    source = tmp_path / "preflight-v2.json"
    source.write_text(json.dumps(report), encoding="utf-8")
    folder = tmp_path / "no-entries.jsonl"
    cmd = [
        sys.executable, str(ROOT / "tools" / "ced_discovery_registry.py"),
        "--report", str(source), "--registry", str(folder),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "New semantic signatures: 0" in result.stdout
    assert not folder.exists()


def test_preflight_cli_opt_in_records_unknowns_locally(tmp_path):
    src = tmp_path / "source.json"
    target = tmp_path / "mapping.json"
    reg = tmp_path / "local-discoveries.jsonl"
    src.write_text(json.dumps(_source()), encoding="utf-8")
    target.write_text(json.dumps({"assets": {}, "entities": {}}), encoding="utf-8")
    cmd = [
        sys.executable, str(ROOT / "tools" / "ced_preflight.py"),
        "--csir", str(src), "--mapping", str(target),
        "--discovery-registry", str(reg),
    ]
    first = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert "2 new signatures" in first.stdout
    again = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert again.returncode == 0, again.stderr
    assert "0 new signatures" in again.stdout
    assert len(registry.read_events(reg)) == 2
