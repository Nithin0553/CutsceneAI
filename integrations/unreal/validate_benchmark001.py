"""Run Benchmark001 source-to-target readback validation inside Unreal Editor."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import unreal

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
VALIDATION_DIR = REPO_ROOT / "packages" / "validation"

for path in (SCRIPT_DIR, VALIDATION_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import core as validation_core
import readback_level_sequence
import validation_expectation


def run(
    csir_path: str,
    mapping_path: str,
    output_dir: str,
) -> dict[str, Any]:
    source = json.loads(Path(csir_path).read_text(encoding="utf-8"))
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))

    expected = validation_expectation.build_expectation(source, mapping)
    actual = readback_level_sequence.readback(
        str(expected["sequence_asset_path"]),
        mapping,
    )
    report = validation_core.compare(
        expected,
        actual,
        benchmark="Benchmark001",
    )

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    expected_path = directory / "Benchmark001.expected.json"
    readback_path = directory / "Benchmark001.unreal.readback.json"
    report_path = directory / "Benchmark001.validation.json"

    expected_path.write_text(json.dumps(expected, indent=2), encoding="utf-8")
    readback_path.write_text(json.dumps(actual, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    status = str(report["status"])
    summary = report["summary"]
    unreal.log(
        "[CutSceneAI] Benchmark001 validation "
        f"{status}: pass={summary['passed']}, fail={summary['failed']}, "
        f"incomplete={summary['incomplete']}"
    )
    unreal.log(f"[CutSceneAI] Validation report: {report_path}")

    for check in report["checks"]:
        if check["status"] != "PASS":
            logger = unreal.log_error if check["status"] == "FAIL" else unreal.log_warning
            logger(
                f"[CutSceneAI] {check['status']} {check['id']}: {check['details']} "
                f"expected={check['expected']} actual={check['actual']}"
            )

    return report
