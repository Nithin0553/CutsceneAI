"""Build a safe best-effort transfer plan and explicit per-track loss report.

Pure Python only. Use a separate Unreal Editor command to realize the resulting
plan; this CLI never imports Unreal or modifies game assets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "packages" / "studio", ROOT / "integrations" / "unreal",
               ROOT / "packages" / "cinetwin"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import transfer_backend


def _write_new(path: Path, value: dict) -> None:
    if path.exists():
        raise transfer_backend.TransferBackendError(
            f"Refusing to replace an existing transfer artifact: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build CutSceneAI best-effort plan with explicit source-feature losses."
    )
    parser.add_argument("--csir", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--capture", type=Path, help="Verified CineTwin source behavior capture")
    parser.add_argument("--out", type=Path, required=True, help="New empty output folder")
    args = parser.parse_args(argv)
    try:
        plan, report, evidence = transfer_backend.compose_files(
            args.csir, args.mapping, capture_path=args.capture
        )
        if args.out.exists():
            raise transfer_backend.TransferBackendError(
                "Refusing to reuse an existing transfer plan directory."
            )
        artifacts = {
            "transfer-plan.json": plan,
            "coverage-report.json": report,
            "evidence.json": evidence,
        }
        args.out.mkdir(parents=True)
        for name, document in artifacts.items():
            _write_new(args.out / name, document)
        print("[CutSceneAI] Best-effort target:", plan["sequence_asset_path"])
        print("[CutSceneAI] Planned actions:", report["actions"])
        print("[CutSceneAI] Track coverage:", report["outcomes"])
        print("[CutSceneAI] Real Unreal generation and behavior fidelity NOT YET VERIFIED.")
        print("[CutSceneAI] Prepared:", args.out)
        return 0
    except (transfer_backend.TransferBackendError, OSError, ValueError,
            KeyError, TypeError) as exc:
        print(f"[CutSceneAI] BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
