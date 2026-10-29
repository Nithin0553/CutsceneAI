"""Read-only CED-first discovery: inspect a source CSIR before conversion.

Examples:
    python tools/ced_preflight.py --csir source.csir.json --mapping mapping.json
    python tools/ced_preflight.py --csir source.csir.json --mapping mapping.json --out discovery.json
    python tools/ced_preflight.py --csir source.csir.json --mapping mapping.json --strict
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "packages" / "studio"
if str(STUDIO) not in sys.path:
    sys.path.insert(0, str(STUDIO))

import ced_preflight
import ced_discovery_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csir", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="New report file; existing files are never overwritten")
    parser.add_argument(
        "--discovery-registry", type=Path,
        help="Opt-in local JSONL registry; writes only novel unknown observations",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 2 if any active feature needs review, lacks a rule or is only partial",
    )
    args = parser.parse_args(argv)
    try:
        source_bytes = args.csir.read_bytes()
        csir = json.loads(source_bytes.decode("utf-8-sig"))
        mapping = json.loads(args.mapping.read_text(encoding="utf-8-sig"))
        report = ced_preflight.audit(csir, mapping)
        report["source_csir_sha256"] = hashlib.sha256(source_bytes).hexdigest()
        if args.out:
            if args.out.exists():
                raise ced_preflight.CEDPreflightError(
                    "Refusing to overwrite an existing CED discovery report."
                )
            if not args.out.parent.is_dir():
                raise ced_preflight.CEDPreflightError("Report parent directory does not exist.")
            args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
        print("[CutSceneAI] CED-FIRST PREFLIGHT:", report["status"])
        print("[CutSceneAI] CED version:", report["ced_version"])
        print("[CutSceneAI] Feature states:", report["counts"])
        print("[CutSceneAI] Active alerts:", report["active_alert_count"])
        print("[CutSceneAI] Unique discovery signatures:", report["unique_discovery_count"])
        print("[CutSceneAI] Review groups:", report["review_group_count"])
        for group in report["review_groups"]:
            examples = ", ".join(group["example_native_types"])
            print(
                f"  [{group['state']}] "
                f"CED={group['ced'] or '<missing>'} "
                f"occurrences={group['occurrences']} "
                f"native_samples={examples or '<unknown>'}"
            )
        if report["active_alert_count"]:
            print("[CutSceneAI] Full indexed findings are in the JSON report.")
        if args.discovery_registry:
            result = ced_discovery_registry.record(report, args.discovery_registry)
            print("[CutSceneAI] Discovery registry: "
                  f"{result['new_feature_signatures']} new signatures, "
                  f"{result['new_observations']} new observations.")
            print("[CutSceneAI] No automatic CED updates or remote notifications.")
        if args.strict and not report["strict_transfer_allowed"]:
            print("[CutSceneAI] STRICT CED PREFLIGHT: BLOCKED", file=sys.stderr)
            return 2
        print("[CutSceneAI] Read-only; no CED definitions or engine assets changed.")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"[CutSceneAI] PREFLIGHT FAILED: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
