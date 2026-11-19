"""The trained CED policy can suggest mappings without creating native actions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "learning"))

import ced_pretraining


def test_trained_ced_policy_is_read_only_in_preflight(tmp_path):
    policy_path = tmp_path / "trained-ced.json"
    policy_path.write_text(json.dumps(ced_pretraining.train()), encoding="utf-8")
    csir = tmp_path / "source.json"
    csir.write_text(json.dumps({
        "cutscene_id": "unknown-type-test",
        "source": {"engine": "unity"},
        "entities": [], "assets": [],
        "tracks": [{
            "track_id": "custom", "ced_type": "timeline.track",
            "metadata": {"native_type": "GameObject"},
            "sections": [{
                "section_id": "sec", "ced_type": "timeline.clip",
                "native_payload": {"native_asset_type": "UnregisteredClip"},
                "payload": {},
            }],
        }],
    }), encoding="utf-8")
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"entities":{},"assets":{}}', encoding="utf-8")
    report_path = tmp_path / "result.json"
    result = subprocess.run([
        sys.executable, str(ROOT / "tools" / "ced_preflight.py"),
        "--csir", str(csir), "--mapping", str(mapping),
        "--trained-ced-policy", str(policy_path),
        "--out", str(report_path),
    ], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text())
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["strict_transfer_allowed"] is False
    advisories = report["trained_ced_policy"]
    assert advisories["native_conversion_authorized"] is False
    assert any(
        "entity.actor" in {x["ced"] for x in item["candidates"]}
        for item in advisories["candidate_groups"]
    )
    assert all(item["proposal_only"] is True
               and item["native_conversion_authorized"] is False
               for item in advisories["candidate_groups"])
    assert csir.is_file() and mapping.is_file()


def test_preflight_refuses_modified_trained_policy(tmp_path):
    model = ced_pretraining.train()
    model["concept_vectors"]["entity.actor"]["actor"] = 9.5
    model_path = tmp_path / "tampered.json"
    model_path.write_text(json.dumps(model))
    src = tmp_path / "unity.json"
    src.write_text('{"cutscene_id":"test","source":{"engine":"unity"},"tracks":[]}')
    target = tmp_path / "mapping.json"
    target.write_text('{"assets":{},"entities":{}}')
    proc = subprocess.run([
        sys.executable, str(ROOT / "tools" / "ced_preflight.py"),
        "--csir", str(src), "--mapping", str(target),
        "--trained-ced-policy", str(model_path),
    ], capture_output=True, text=True, check=False)
    assert proc.returncode == 2
    assert "modified" in proc.stderr
