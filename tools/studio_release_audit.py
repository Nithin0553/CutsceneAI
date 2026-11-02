"""Inspect one finished Studio candidate's real release evidence.

Example: python tools/studio_release_audit.py
The command is READ-ONLY and exits 2 for any incomplete/failed release gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
from studio_release_gate import ReleaseEvidenceError, assess  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI evidence-based release gate")
    parser.add_argument("--workspace", type=Path,
                        default=Path.home() / ".cutsceneai-studio" / "runs")
    parser.add_argument("--job-id", default="", help="32-digit hex ID; default active job")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    try:
        if args.job_id:
            job_id = args.job_id
        else:
            active = json.loads((workspace / "active-job.json").read_text(encoding="utf-8-sig"))
            job_id = str(active["job_id"])
        result = assess(workspace, job_id)
    except (ReleaseEvidenceError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID_EVIDENCE", "release_ready": False,
                          "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["release_ready"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
