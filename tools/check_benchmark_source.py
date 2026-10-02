"""Check an extracted source CSIR against a CutSceneAI benchmark specification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "packages" / "validation"
if str(VALIDATION) not in sys.path:
    sys.path.insert(0, str(VALIDATION))

import benchmark_spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--csir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    csir = json.loads(args.csir.read_text(encoding="utf-8"))
    report = benchmark_spec.evaluate_source(spec, csir)

    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    if report["status"] == "FAIL":
        raise SystemExit(2)
    if report["status"] == "NEEDS_EVIDENCE":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
