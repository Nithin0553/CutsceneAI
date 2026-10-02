import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_contract_json_files_parse() -> None:
    files = list(CONTRACTS.rglob("*.json"))
    assert files, "No contract JSON files found"
    for path in files:
        _load(path)


def test_transfer_outcomes_are_complete() -> None:
    data = _load(CONTRACTS / "common" / "transfer-outcome-v0.1.schema.json")
    assert data["enum"] == [
        "EXACT",
        "CONVERTED",
        "RETARGETED",
        "BAKED",
        "RECONSTRUCTED",
        "TARGET_MAPPED",
        "BLOCKED",
    ]


def test_engine_mappings_reference_known_ced_ids() -> None:
    ced = _load(CONTRACTS / "dictionary" / "cutscene-elements-v0.1.json")
    known = {element for elements in ced["categories"].values() for element in elements}

    for filename in ("unity-mappings-v0.1.json", "unreal-mappings-v0.1.json"):
        mapping = _load(CONTRACTS / "dictionary" / filename)
        unknown = [entry["ced"] for entry in mapping["mappings"] if entry["ced"] not in known]
        assert unknown == [], f"{filename} references unknown CED ids: {unknown}"


def test_ced_covers_foundation_domains() -> None:
    ced = _load(CONTRACTS / "dictionary" / "cutscene-elements-v0.1.json")
    required_categories = {
        "sequence",
        "timeline",
        "time",
        "curve",
        "entity",
        "binding",
        "transform",
        "character",
        "animation",
        "camera",
        "audio",
        "dialogue",
        "event",
        "light",
        "vfx",
        "render",
        "scene",
        "material",
        "constraint",
        "relationship",
        "asset",
        "media",
        "subtitle",
        "physics",
        "simulation",
        "provenance",
    }
    assert required_categories <= set(ced["categories"])


def test_canonical_coordinate_contract_is_stable() -> None:
    schema = _load(CONTRACTS / "common" / "coordinate-system-v0.1.schema.json")
    properties = schema["properties"]
    assert properties["handedness"]["const"] == "RIGHT_HANDED"
    assert properties["up_axis"]["const"] == "+Y"
    assert properties["forward_axis"]["const"] == "-Z"
    assert properties["right_axis"]["const"] == "+X"
    assert properties["linear_unit"]["const"] == "METER"
    assert properties["rotation_representation"]["const"] == "QUATERNION_XYZW"


def test_rational_time_contract_preserves_non_integer_rates() -> None:
    schema = _load(CONTRACTS / "common" / "rational-time-v0.1.schema.json")
    rate = schema["$defs"]["rate"]
    assert rate["properties"]["numerator"]["minimum"] == 1
    assert rate["properties"]["denominator"]["minimum"] == 1


def test_csir_requires_canonical_space_and_exact_timing_bounds() -> None:
    schema = _load(CONTRACTS / "csir" / "csir-v0.1.schema.json")
    required = set(schema["required"])
    assert {"coordinate_system", "timing", "assets", "entities", "tracks", "relationships"} <= required

    timing = schema["$defs"]["sequence_timing"]
    assert {"source_rate", "playback_start", "playback_end", "duration_seconds"} <= set(
        timing["required"]
    )
    assert "rational_rate" in schema["$defs"]
    assert "rational_time" in schema["$defs"]


def test_csir_preserves_source_native_payload_escape_hatch() -> None:
    schema = _load(CONTRACTS / "csir" / "csir-v0.1.schema.json")
    section = schema["$defs"]["section"]
    assert "native_payload" in section["properties"]


def test_first_benchmark_is_documented() -> None:
    benchmark = ROOT / "docs" / "benchmarks" / "BENCHMARK_001.md"
    text = benchmark.read_text(encoding="utf-8")
    assert "Unity Timeline" in text
    assert "Unreal Level Sequence" in text
    assert "readback" in text.lower()


def test_adaptive_mapping_rules_validate_and_reference_known_ced_ids() -> None:
    ced = _load(CONTRACTS / "dictionary" / "cutscene-elements-v0.1.json")
    known = {element for elements in ced["categories"].values() for element in elements}
    schema = _load(CONTRACTS / "dictionary" / "adaptive-mapping-rules-v0.1.schema.json")
    rules = _load(CONTRACTS / "dictionary" / "adaptive-rules-v0.1.json")

    Draft202012Validator(schema).validate(rules)
    unknown = [rule["ced"] for rule in rules["rules"] if rule["ced"] not in known]
    assert unknown == []


def test_project_intelligence_and_resolved_dictionary_contracts_are_valid_schemas() -> None:
    for path in (
        CONTRACTS / "project" / "project-profile-v0.1.schema.json",
        CONTRACTS / "dictionary" / "resolved-dictionary-v0.1.schema.json",
        CONTRACTS / "csir" / "csir-adaptive-context-v0.1.schema.json",
    ):
        Draft202012Validator.check_schema(_load(path))


def test_validation_contracts_are_valid_schemas() -> None:
    for path in (
        CONTRACTS / "validation" / "target-readback-v0.1.schema.json",
        CONTRACTS / "validation" / "report-v0.1.schema.json",
    ):
        Draft202012Validator.check_schema(_load(path))
