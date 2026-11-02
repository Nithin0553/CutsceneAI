"""Regression: Unreal's long-lived Python VM must not use a cached 25-action
planner to verify a newly prepared 29-action adaptive CED candidate."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "integrations" / "unreal" / "studio_planner_sync.py"
BUILDER = ROOT / "integrations" / "unreal" / "build_level_sequence.py"
WORKER = ROOT / "integrations" / "unreal" / "studio_local_editor_worker.py"


def test_stale_embedded_python_planner_is_reloaded_from_canonical_checkout():
    script = f"""
import sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'integrations' / 'unreal'))
for sub in ('packages/studio', 'packages/cinetwin', 'packages/learning'):
    sys.path.insert(0, str(root / sub))
import transfer_backend
import prepared_transfer
import studio_planner_sync
old_compose = transfer_backend.compose_files
transfer_backend.compose_files = lambda *a, **k: (
    {{'actions':[{{'kind':'legacy'}}] * 25}}, {{}}, {{}}
)
prepared_transfer.verify = lambda _: 'STALE'
assert transfer_backend.compose_files(None, None)[0]['actions'][0]['kind'] == 'legacy'
loaded = studio_planner_sync.synchronize()
assert len(loaded) == len(studio_planner_sync.MODULES)
assert transfer_backend.compose_files is not old_compose
assert transfer_backend.compose_files.__module__ == 'transfer_backend'
assert prepared_transfer.verify.__module__ == 'prepared_transfer'
 print('PLANNER_RELOADED')
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PLANNER_RELOADED" in result.stdout


def test_verification_runs_sync_before_mutating_unreal_or_using_cached_modules():
    worker = WORKER.read_text(encoding="utf-8")
    builder = BUILDER.read_text(encoding="utf-8")
    assert "studio_planner_sync.synchronize()" in worker
    assert "studio_planner_sync.synchronize()" in builder
    assert worker.index("studio_planner_sync.synchronize()") < worker.index(
        "prepared_transfer.verify(candidate_dir)")
    assert worker.index("prepared_transfer.verify(candidate_dir)") < worker.index(
        "\n    _ensure_target_level(job)")
    assert builder.index("studio_planner_sync.synchronize()") < builder.index(
        "transfer_backend.compose_files(")
    assert "transfer_backend.verify_prepared_artifacts(" in builder


def test_source_hash_artifacts_are_not_modified_by_planner_sync():
    source = SYNC.read_text(encoding="utf-8")
    assert "ROOT = Path(__file__).resolve().parents[2]" in source
    assert "importlib.reload(existing)" in source
    assert "Path(actual_raw).resolve() != expected" in source
    for prohibited in (
        "unlink(", "write_text(", "write_bytes(", "open('w'", 'open("w"',
        "exec(", "eval(", "subprocess.", "unreal.",
    ):
        assert prohibited not in source
