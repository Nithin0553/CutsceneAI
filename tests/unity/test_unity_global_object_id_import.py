from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUGMENTER = (
    ROOT
    / "integrations"
    / "unity"
    / "com.cutsceneai.extractor"
    / "Editor"
    / "UnityTimelineOffsetAugmenter.cs"
)


def test_global_object_id_has_unity_editor_import() -> None:
    source = AUGMENTER.read_text(encoding="utf-8")
    assert "GlobalObjectId.GetGlobalObjectIdSlow" in source
    assert "using UnityEditor;" in source
