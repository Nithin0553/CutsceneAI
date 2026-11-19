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
    parser.add_argument(
        "--trained-ced-policy", type=Path,
        help="Optional immutable CED pretrained model for read-only mapping suggestions",
    )
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
        if args.trained_ced_policy is not None:
            learning = str(ROOT / "packages" / "learning")
            if learning not in sys.path:
                sys.path.insert(0, learning)
            import ced_pretraining
            model_path = args.trained_ced_policy
            if (model_path.is_symlink() or not model_path.is_file()
                    or model_path.stat().st_size > 16 * 1024 * 1024):
                raise ced_preflight.CEDPreflightError("Unsafe or missing trained CED model.")
            model = ced_pretraining.validate(
                json.loads(model_path.read_text(encoding="utf-8-sig"))
            )
            suggestions = []
            seen = set()
            for finding in report["findings"]:
                if not (finding.get("active") is True
                        and finding.get("state")
                        in {"UNKNOWN_CED", "UNKNOWN_NATIVE", "NEEDS_EVIDENCE"}):
                    continue
                fingerprint = finding["feature_fingerprint"]
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                source_term = str(finding.get("native_type") or finding.get("ced") or "")
                if not source_term:
                    continue
                # Retrieved semantics are proposals only: no target mapping,
                # resolver, conversion or native asset is modified.
                candidates = ced_pretraining.suggest(
                    model, source_term, engine="unity", limit=3)
                suggestions.append({
                    "feature_fingerprint": fingerprint,
                    "candidates": candidates,
                    "proposal_only": True,
                    "native_conversion_authorized": False,
                })
            report["trained_ced_policy"] = {
                "payload_sha256": model["payload_sha256"],
                "training_kind": model["training_type"],
                "native_conversion_authorized": False,
                "candidate_groups": suggestions,
            }
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
