import sys
from pathlib import Path

VALIDATION_DIR = Path(__file__).resolve().parents[2] / "packages" / "validation"
sys.path.insert(0, str(VALIDATION_DIR))

import benchmark_spec


def _rt(seconds: float) -> dict:
    return {
        "value": round(seconds * 1_000_000),
        "rate": {"numerator": 1_000_000, "denominator": 1},
    }


def _spec() -> dict:
    return {
        "benchmark": "Benchmark002",
        "timing": {
            "display_rate": {"numerator": 24, "denominator": 1},
            "duration_seconds": 12.0,
            "duration_tolerance_seconds": 1e-6,
        },
        "requirements": [
            {"id": "characters", "ced": "entity.character", "minimum_count": 2},
            {"id": "blend", "ced": "animation.blend", "minimum_count": 1},
            {"id": "root", "ced": "animation.root_motion", "minimum_count": 1},
            {"id": "parent", "ced": "transform.parent", "minimum_count": 1},
        ],
    }


def _csir() -> dict:
    return {
        "timing": {
            "source_rate": {"numerator": 24, "denominator": 1},
            "duration_seconds": 12.0,
        },
        "entities": [
            {
                "entity_id": "a",
                "ced_type": "entity.character",
                "parent_entity_id": None,
            },
            {
                "entity_id": "b",
                "ced_type": "entity.character",
                "parent_entity_id": None,
            },
            {
                "entity_id": "prop",
                "ced_type": "entity.prop",
                "parent_entity_id": "b",
            },
        ],
        "tracks": [
            {
                "track_id": "anim-a",
                "ced_type": "animation.track",
                "sections": [
                    {
                        "section_id": "walk",
                        "ced_type": "animation.section",
                        "start": _rt(0.0),
                        "end": _rt(4.0),
                        "payload": {
                            "animation": {
                                "curves": [
                                    {"property_name": "RootT.x"},
                                    {"property_name": "RootT.y"},
                                    {"property_name": "RootT.z"},
                                ]
                            }
                        },
                    },
                    {
                        "section_id": "turn",
                        "ced_type": "animation.section",
                        "start": _rt(3.5),
                        "end": _rt(6.0),
                        "payload": {},
                    },
                ],
            }
        ],
        "relationships": [],
    }


def test_inventory_infers_parent_root_motion_and_animation_overlap() -> None:
    counts = benchmark_spec.inventory(_csir())

    assert counts["entity.character"] == 2
    assert counts["transform.parent"] == 1
    assert counts["animation.root_motion"] == 1
    assert counts["animation.blend"] == 1


def test_source_readiness_is_ready_when_requirements_are_observed() -> None:
    report = benchmark_spec.evaluate_source(_spec(), _csir())

    assert report["status"] == "READY"
    assert report["summary"]["failed"] == 0
    assert report["summary"]["needs_evidence"] == 0


def test_missing_feature_becomes_needs_evidence_not_silent_pass() -> None:
    csir = _csir()
    csir["entities"][2]["parent_entity_id"] = None

    report = benchmark_spec.evaluate_source(_spec(), csir)

    assert report["status"] == "NEEDS_EVIDENCE"
    parent = next(check for check in report["checks"] if check["id"] == "parent")
    assert parent["status"] == "NEEDS_EVIDENCE"


def test_wrong_timebase_is_hard_failure() -> None:
    csir = _csir()
    csir["timing"]["source_rate"] = {"numerator": 60, "denominator": 1}

    report = benchmark_spec.evaluate_source(_spec(), csir)

    assert report["status"] == "FAIL"
    timing = next(check for check in report["checks"] if check["id"] == "timing.display_rate")
    assert timing["status"] == "FAIL"
