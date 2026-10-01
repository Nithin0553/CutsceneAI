import json
from pathlib import Path

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
    known = {
        element
        for elements in ced["categories"].values()
        for element in elements
    }

    for filename in ("unity-mappings-v0.1.json", "unreal-mappings-v0.1.json"):
        mapping = _load(CONTRACTS / "dictionary" / filename)
        unknown = [entry["ced"] for entry in mapping["mappings"] if entry["ced"] not in known]
        assert unknown == [], f"{filename} references unknown CED ids: {unknown}"


def test_csir_keeps_rational_timing() -> None:
    schema = _load(CONTRACTS / "csir" / "csir-v0.1.schema.json")
    timing = schema["properties"]["timing"]["properties"]
    assert "source_rate" in timing
    assert "display_rate" in timing
    assert "tick_resolution" in timing
    assert "$defs" in schema and "rational_rate" in schema["$defs"]
