"""One-click Studio regression: source-backed feedback never invents perfection."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
sys.path.insert(0, str(ROOT / "tools"))
import closed_loop_evaluation as review
import studio_local_bridge as bridge


def test_cinetwin_motion_mismatch_is_reported_with_real_measurement():
    diagnostic = {
        "kind": "cutsceneai.cinetwin.unreal_world_pose_diagnostic",
        "source": {"missing_source_frames": []},
        "entities": {
            "CharacterA": {
                "status": "READY",
                "actor_world": {"max_offset_removed_motion_error_cm": 280.7},
                "skeletal_root_world": {"max_offset_removed_motion_error_cm": 3.0},
            },
        },
        "errors": [],
    }
    visual = {
        "kind": "cutsceneai.studio.visual_readback_audit",
        "visual_issues": ["NO_DIRECTIONAL_LIGHT_FOUND", "RENDER_MATERIALS_MISSING_OR_ENGINE_DEFAULT"],
    }
    outcome = review.evaluate(diagnostic, visual, max_motion_error_cm=2.0)
    assert outcome["status"] == "REVIEW_REQUIRED"
    assert outcome["issue_count"] == 4
    assert outcome["fidelity_verified"] is False
    assert outcome["automatic_repair_executed"] is False
    assert any(i.get("error_cm") == 280.7 for i in outcome["issues"])


def test_no_cinetwin_does_not_infer_perfect_transfer():
    outcome = review.evaluate(None, {
        "kind": "cutsceneai.studio.visual_readback_audit", "visual_issues": []
    })
    assert outcome["status"] == "REVIEW_REQUIRED"
    assert "CINETWIN_EVIDENCE_MISSING" in [i["category"] for i in outcome["issues"]]
    assert not outcome["fidelity_verified"]


def test_no_detected_gaps_still_does_not_prove_visual_parity():
    outcome = review.evaluate({
        "kind": "cutsceneai.cinetwin.unreal_world_pose_diagnostic",
        "source": {"missing_source_frames": []},
        "entities": {"A": {
            "status": "READY",
            "actor_world": {"max_offset_removed_motion_error_cm": 0.2},
        }},
        "errors": [],
    }, {"kind": "cutsceneai.studio.visual_readback_audit", "visual_issues": []})
    assert outcome["issue_count"] == 0
    assert "UNVERIFIED" in outcome["status"]
    assert outcome["fidelity_verified"] is False


def test_unsafe_evidence_and_tolerance_rejected():
    with pytest.raises(review.EvidenceError):
        review.evaluate({"kind": "fake", "entities": {}}, None)
    with pytest.raises(review.EvidenceError):
        review.evaluate(None, None, max_motion_error_cm=float("nan"))


def test_report_never_overwrites_existing_evidence(tmp_path):
    path = tmp_path / "closed-loop.json"
    report = review.evaluate(None, None)
    review.write_new(path, report)
    assert json.loads(path.read_text()) == report
    with pytest.raises(FileExistsError):
        review.write_new(path, report)


def test_one_click_approval_requires_exact_candidate_and_source_permission(tmp_path):
    folder = tmp_path / "runs"
    folder.mkdir()
    (folder / "active-candidate.json").write_text(json.dumps({
        "candidate_id": "20261101T111111Z_abcdef12",
        "automatic_setup": {"ready": True},
    }))
    config = {"csir": "source.json", "target_project": "Destination.uproject",
              "level_path": "/Game/Maps/L_Stage", "source_rights_confirmed": True}
    (folder / "connection.json").write_text(json.dumps(config))
    approved = bridge.approve_one_click("20261101T111111Z_abcdef12", folder)
    assert approved["approved"]
    assert json.loads((folder / "one-click-approval.json").read_text())["target_level"] == "/Game/Maps/L_Stage"
    with pytest.raises(ValueError, match="stale or invalid"):
        bridge.approve_one_click("other", folder)
    config["source_rights_confirmed"] = False
    (folder / "connection.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="rights"):
        bridge.approve_one_click("20261101T111111Z_abcdef12", folder)


def test_cinematic_ui_calls_live_backend_and_uses_indeterminate_progress():
    ui = (ROOT / "apps" / "studio-web" / "cinematic.js").read_text()
    page = (ROOT / "apps" / "studio-web" / "index.html").read_text()
    css = (ROOT / "apps" / "studio-web" / "cinematic.css").read_text()
    for route in ("pick-folder", "discover", "connect-projects", "source-surfaces",
                  "prepare", "approve-one-click", "execute", "jobs/", "verification", "closed-loop"):
        assert route in ui
    assert "setInterval" in ui and "indeterminate" in ui
    assert "100%" not in ui and "72%" not in ui
    assert "cinematic.js" in page and "app.js" in page
    assert "#39d900" in css.lower()
    assert "prefers-reduced-motion" in css
