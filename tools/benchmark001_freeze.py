"""Create an auditable Benchmark001 target-freeze manifest after automated PASS."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


EXPECTED_SOURCE_SHA256 = "5da9ede712854e77bb51e914ccf99d6e5b7432e6b9d24acbbb971c2d539b5ef4"


class FreezeError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"Unable to read JSON {path}: {exc}") from exc


def _git_head(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def create_manifest(
    *,
    repo_root: Path,
    source_csir: Path,
    mapping: Path,
    target_uasset: Path,
    validation_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    files = {
        "source_csir": source_csir,
        "mapping": mapping,
        "target_level_sequence": target_uasset,
        "expected": validation_dir / "Benchmark001.expected.json",
        "readback": validation_dir / "Benchmark001.unreal.readback.json",
        "validation": validation_dir / "Benchmark001.validation.json",
    }
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise FreezeError("Missing required freeze artifacts: " + ", ".join(missing))

    source_hash = sha256_file(source_csir)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise FreezeError(
            "Source CSIR hash does not match frozen Benchmark001 ground truth: "
            f"{source_hash}"
        )

    report = _load_json(files["validation"])
    summary = report.get("summary", {})
    if (
        report.get("status") != "PASS"
        or int(summary.get("failed", -1)) != 0
        or int(summary.get("incomplete", -1)) != 0
    ):
        raise FreezeError(
            "Target freeze requires validation PASS with failed=0 and incomplete=0."
        )

    readback = _load_json(files["readback"])
    expected = _load_json(files["expected"])

    manifest = {
        "schema_version": "0.1.0",
        "benchmark": "Benchmark001",
        "status": "FROZEN_AUTOMATED_PASS",
        "source": {
            "engine": "Unity",
            "artifact": str(source_csir),
            "sha256": source_hash,
        },
        "target": {
            "engine": readback.get("engine", {}),
            "sequence_asset_path": readback.get("sequence_asset_path", ""),
            "artifact": str(target_uasset),
            "sha256": sha256_file(target_uasset),
        },
        "validation": {
            "status": report["status"],
            "summary": summary,
            "expected_sha256": sha256_file(files["expected"]),
            "readback_sha256": sha256_file(files["readback"]),
            "report_sha256": sha256_file(files["validation"]),
            "display_rate": readback.get("display_rate"),
            "playback": readback.get("playback"),
        },
        "mapping": {
            "artifact": str(mapping),
            "sha256": sha256_file(mapping),
        },
        "software": {
            "repository": "Nithin0553/CutsceneAI",
            "git_head": _git_head(repo_root),
        },
        "artifacts": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for name, path in files.items()
        },
        "expectation_sequence_asset_path": expected.get("sequence_asset_path", ""),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--source-csir", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--target-uasset", required=True, type=Path)
    parser.add_argument("--validation-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    manifest = create_manifest(
        repo_root=args.repo_root,
        source_csir=args.source_csir,
        mapping=args.mapping,
        target_uasset=args.target_uasset,
        validation_dir=args.validation_dir,
        output_path=args.output,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
