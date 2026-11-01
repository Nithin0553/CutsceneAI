"""Regression: show pending automatic import as an actionable step, not a failed transfer.

These are static UI contract checks. Engine import success requires the separate
Unreal Editor worker and runtime receipts.
"""
from pathlib import Path

APP = (Path(__file__).resolve().parents[2] / "apps" / "studio-web" / "app.js").read_text(
    encoding="utf-8"
)


def test_auto_import_eligibility_is_shared_by_render_and_execute():
    assert "const automaticSetupState = (candidate, destination)" in APP
    assert "const setup=automaticSetupState(p,d);" in APP
    assert "const autoReady=automaticSetupState(state.candidate,d).safe;" in APP
    assert "destination.candidate_id===candidate?.candidate_id" in APP
    assert "destination?.wrong_asset_types" in APP
    assert "destination?.duplicate_actors" in APP


def test_preimport_assets_are_explained_and_button_is_visible_above_lists():
    assert "READY TO IMPORT AUTOMATICALLY" in APP
    assert "Mapped actors planned for creation" in APP
    assert "Mapped assets planned for import" in APP
    assert "Import and playback have NOT happened yet." in APP
    assert APP.index("Ready for the next step: import") < APP.index("Mapped actors planned for creation")


def test_unapproved_or_stale_setup_is_not_reported_as_ready():
    assert "const prepared = Boolean(auto.available && auto.ready)" in APP
    assert "eligibleStatuses.includes(destination?.status)" in APP
    assert "matchingCandidate && !conflictCount" in APP
    assert "if(!workerTarget || (!d?.ready&&!autoReady)" in APP


def test_new_auto_level_is_supported_only_with_connected_project():
    assert "c?.auto_create_level && d.status==='NEW_LEVEL_REQUIRED'" in APP
    assert "w.connected&&normPath(w.project)===normPath(c?.target_project)" in APP
