from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / (
    "integrations/unity/com.cutsceneai.extractor/Editor/UnityTimelineSourceSnapshot.cs"
)


def test_source_snapshot_captures_timeline_offsets_without_evaluating_director() -> None:
    text = SOURCE.read_text(encoding="utf-8")

    required_fragments = [
        "Export Selected Timeline Source Snapshot",
        "track.position",
        "track.rotation",
        "track.infiniteClipOffsetPosition",
        "track.infiniteClipOffsetRotation",
        "animationPlayable.position",
        "animationPlayable.rotation",
        "animationPlayable.removeStartOffset",
        "animationPlayable.useTrackMatchFields",
        "animationPlayable.applyFootIK",
        "animationPlayable.loop.ToString()",
        "binding_global_object_id",
        ".unity-source.json",
    ]
    for fragment in required_fragments:
        assert fragment in text

    assert "director.Evaluate(" not in text
    assert "PlayableDirector.Evaluate(" not in text
