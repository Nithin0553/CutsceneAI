"""Backward-compatible Benchmark001 wrapper around the generic validator."""

from __future__ import annotations

from typing import Any

import validate_transfer


def run(
    csir_path: str,
    mapping_path: str,
    output_dir: str,
) -> dict[str, Any]:
    return validate_transfer.run(
        "Benchmark001",
        csir_path,
        mapping_path,
        output_dir,
    )
