"""Read-only diff between Unity editor feature census and source CSIR."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
from source_surface_gap import audit_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Unity component/asset discovery against a source cutscene"
    )
    parser.add_argument("--csir", type=Path, required=True)
    parser.add_argument("--source-surface", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if args.out.exists() or args.out.is_symlink():
        parser.error("Refusing to overwrite an existing source feature audit.")
    result = audit_files(args.csir, args.source_surface)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print("[CutSceneAI] Source feature census: loaded components:",
          result["scoped_component_occurrences"])
    print("[CutSceneAI] Native components needing extraction/adapter:",
          result["unresolved_component_count"])
    print("[CutSceneAI] Cutscene parity: NOT VERIFIED")
    if args.strict and (
        result["unresolved_component_count"]
        or not result["project_identity_proven"]
        or not result["source_scope_matched"]
    ):
        print(
            "[CutSceneAI] Strict source extraction: BLOCKED"
            " (component/scope or project provenance incomplete)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
