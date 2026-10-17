"""Create or verify CineTwin artifacts without modifying a source project."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from sampling_plan import plan_file, validate_capture
from behavior_compare import BehavioralComparisonError, compare_files
from hierarchy_plan import plan_actor_hierarchy


def main() -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI CineTwin capture preparation")
    sub = parser.add_subparsers(dest="command", required=True)

    make = sub.add_parser("plan", help="Create a source-derived behavior sampling plan")
    make.add_argument("csir", type=Path)
    make.add_argument("output", type=Path)

    check = sub.add_parser("verify", help="Check completeness of a Unity behavior capture")
    check.add_argument("plan", type=Path)
    check.add_argument("capture", type=Path)

    comparison = sub.add_parser(
        "compare", help="Compare independently observed Unity/Unreal behavior"
    )
    comparison.add_argument("plan", type=Path)
    comparison.add_argument("source", type=Path)
    comparison.add_argument("target", type=Path)
    comparison.add_argument("output", type=Path)

    hierarchy = sub.add_parser(
        "hierarchy", help="Read-only source-to-target attachment planning"
    )
    hierarchy.add_argument("csir", type=Path)
    hierarchy.add_argument("mapping", type=Path)
    hierarchy.add_argument("output", type=Path)

    args = parser.parse_args()
    if args.command == "plan":
        plan = plan_file(args.csir, args.output)
        print(
            f"[CineTwin] Plan: {len(plan['samples'])} sample times, "
            f"{len(plan['entities'])} entities, {args.output}"
        )
        print(
            "[CineTwin] Not implemented yet: "
            + ", ".join(
                entry["layer"] for entry in plan["capabilities"]
                if entry["status"] == "NOT_IMPLEMENTED"
            )
        )
        return 0

    if args.command == "hierarchy":
        csir = json.loads(args.csir.read_text(encoding="utf-8-sig"))
        mapping = json.loads(args.mapping.read_text(encoding="utf-8-sig"))
        result = plan_actor_hierarchy(csir, mapping)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(
            "[CineTwin] Hierarchy dry-run: "
            f"{len(result['planned_actor_attachments'])} mapped attachments, "
            f"{len(result['unresolved_source_parents'])} unresolved source parents."
        )
        for edge in result["planned_actor_attachments"]:
            print(
                f"  ATTACH {edge['actor_label']} -> {edge['parent_actor_label']} "
                f"(rule={edge['attachment_rule']})"
            )
        print("[CineTwin] No Unreal assets or source files modified.")
        return 0

    if args.command == "compare":
        try:
            report = compare_files(
                args.plan, args.source, args.target, args.output
            )
        except BehavioralComparisonError as exc:
            print("[CineTwin] Comparison blocked:", exc, file=sys.stderr)
            return 1
        summary = report["evaluation"]
        print(
            f"[CineTwin] {summary['status']}: "
            f"{summary['sampling_times']} times, "
            f"{summary['mapped_actor_count']} mapped actors, "
            f"{summary['unmapped_entity_count']} unmapped entities."
        )
        for item in report["entities"]:
            print(
                f"  {item['source_name']}: "
                f"max_position_error={item['max_world_position_error_cm']:.3f} cm, "
                f"max_rotation_error={item['max_world_rotation_error_degrees']:.3f} deg, "
                f"source_motion={item['source_max_motion_from_start_cm']:.3f} cm, "
                f"target_motion={item['target_max_motion_from_start_cm']:.3f} cm, "
                f"initial_offset={item['initial_world_position_error_cm']:.3f} cm, "
                f"relative_trajectory_error={item['max_relative_trajectory_error_cm']:.3f} cm, "
                f"diagnosis={item['motion_diagnostic']}"
            )
        for rig in report["rig_motion_diagnostics"]:
            print(
                f"  RIG {rig['source_name']}: "
                f"source_bone_motion="
                f"{rig['source']['maximum_bone_displacement_from_start_cm']:.3f} cm, "
                f"target_bone_motion="
                f"{rig['target']['maximum_bone_displacement_from_start_cm']:.3f} cm"
            )
        print(
            "[CineTwin] Cutscene fidelity NOT established: other semantic "
            f"domains remain unverified. Report: {args.output}"
        )
        return 0

    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    capture = json.loads(args.capture.read_text(encoding="utf-8-sig"))
    report = validate_capture(plan, capture)
    print(json.dumps(report, indent=2))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
