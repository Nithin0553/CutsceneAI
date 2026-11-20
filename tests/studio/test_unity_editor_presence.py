"""Unity bridge health/status survives domain reload; no engines are started."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from studio_unity_bridge import editor_status


@pytest.fixture
def project(tmp_path):
    for child in ("Assets", "ProjectSettings"):
        (tmp_path / child).mkdir()
    return tmp_path


def _heartbeat(project, **changes):
    marker = project / "CutSceneAI/StudioBridge/unity-editor.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "kind": "cutsceneai.unity.editor_presence",
        "schema_version": "1", "project_root": str(project.resolve()),
        "heartbeat": datetime.now(UTC).isoformat(),
        "editor_pid": 12345, "source_bridge_enabled": True,
        "editor_mode": "EDIT_MODE", "bridge_version": "unity-editor-v0.3",
    }
    record.update(changes)
    marker.write_text(json.dumps(record))
    return marker


def test_enabled_unity_editor_reports_project_bound_live_bridge(project):
    _heartbeat(project)
    status = editor_status(project)
    assert status["connected"] is True
    assert status["status"] == "CONNECTED"
    assert status["editor_mode"] == "EDIT_MODE"
    assert status["editor_pid"] == 12345
    assert status["restart_required"] is False


def test_play_mode_and_returned_domain_reload_heartbeat_are_both_live(project):
    marker = _heartbeat(project, editor_mode="PLAY_MODE")
    assert editor_status(project)["editor_mode"] == "PLAY_MODE"
    marker.write_text(json.dumps({
        **json.loads(marker.read_text()),
        "editor_mode": "EDIT_MODE",
        "heartbeat": datetime.now(UTC).isoformat(),
    }))
    assert editor_status(project)["connected"] is True


@pytest.mark.parametrize("override", [
    {"source_bridge_enabled": False},
    {"editor_pid": 0},
    {"editor_pid": "1234"},
    {"bridge_version": "old-unity-worker"},
    {"editor_mode": "UNKNOWN"},
    {"kind": "fake"},
])
def test_disabled_or_invalid_unity_presence_is_not_a_connection(project, override):
    _heartbeat(project, **override)
    assert editor_status(project)["connected"] is False


def test_expired_presence_waits_for_companion_to_reconnect(project):
    _heartbeat(project, heartbeat=(
        datetime.now(UTC) - timedelta(seconds=90)
    ).isoformat())
    status = editor_status(project)
    assert status["connected"] is False
    assert status["status"] == "UNITY_COMPANION_RELOADING_OR_OFFLINE"


def test_future_presence_is_not_accepted(project):
    _heartbeat(project, heartbeat=(
        datetime.now(UTC) + timedelta(minutes=2)
    ).isoformat())
    assert editor_status(project)["connected"] is False


def test_presence_is_bound_to_exact_project_and_refuses_foreign_marker(project, tmp_path):
    _heartbeat(project, project_root=str(tmp_path / "another"))
    status = editor_status(project)
    assert status["status"] == "WRONG_UNITY_PROJECT"


def test_untrusted_presence_symlink_cannot_escape_project(project, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    marker = project / "CutSceneAI/StudioBridge/unity-editor.json"
    marker.parent.mkdir(parents=True)
    try:
        marker.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("No symlink privileges")
    assert editor_status(project)["connected"] is False


def test_unity_stale_or_absent_marker_never_creates_a_fake_export(project):
    assert editor_status(project)["connected"] is False
    assert not (project / "CutSceneAI").exists()


def test_unity_source_companion_has_opt_in_and_automatic_assembly_reload_contract():
    source = (ROOT / "integrations/unity/com.cutsceneai.extractor/Editor/"
              "CutsceneAIStudioBridge.cs").read_text()
    assert "[InitializeOnLoad]" in source
    assert "EditorApplication.update += Poll" in source
    assert "EditorPrefs.SetBool(PreferenceKey(), true)" in source
    assert "EditorPrefs.GetBool(PreferenceKey(), false)" in source
    assert "EditorPrefs.SetBool(Preference, true)" not in source
    assert "SHA256.Create()" in source
    assert "if (!WritePresence(true))" in source
    assert "Source bridge heartbeat write failed" in source
    assert "File.Replace(temporary, target, null)" in source
    assert '"unity-editor.json"' in source



def test_missing_heartbeat_explains_how_to_connect_exact_unity_project(project):
    status = editor_status(project)
    assert status["status"] == "WAITING_FOR_UNITY_EDITOR"
    assert "unity-editor.json" in status["next_action"]
    assert "Enable Source Bridge" in status["next_action"]
    assert not (project / "CutSceneAI").exists()


def test_invalid_version_is_reported_as_package_mismatch(project):
    _heartbeat(project, bridge_version="unity-editor-v0.2")
    status = editor_status(project)
    assert status["connected"] is False
    assert status["status"] == "UNSUPPORTED_UNITY_BRIDGE_VERSION"
    assert status["bridge_version"] == "unity-editor-v0.2"
    assert "Package Manager" in status["next_action"]


def test_disabled_bridge_is_not_mistaken_for_old_unity_package(project):
    _heartbeat(project, source_bridge_enabled=False)
    status = editor_status(project)
    assert status["connected"] is False
    assert status["status"] == "UNITY_SOURCE_BRIDGE_DISABLED"
    assert "project-scoped" in status["next_action"]


def test_stale_bridge_diagnostic_identifies_console_write_errors(project):
    _heartbeat(
        project,
        heartbeat=(datetime.now(UTC) - timedelta(seconds=100)).isoformat(),
    )
    status = editor_status(project)
    assert status["status"] == "UNITY_COMPANION_RELOADING_OR_OFFLINE"
    assert "Unity Console" in status["next_action"]
