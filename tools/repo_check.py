"""Read-only repository hygiene check; no dependency on Unity or Unreal.

Check maintained Markdown links, expected project layout, immutable benchmark
freeze-manifest presence, and accidental *tracked* local generated artifacts.
Historical research documents are intentionally not rewritten by this tool.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

MAINTAINED = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("docs/INDEX.md"),
    Path("docs/REPOSITORY_GUIDE.md"),
    Path("docs/ISSUES_AND_MILESTONES.md"),
    Path("docs/BRANCH_AUDIT.md"),
)
CRITICAL = (
    Path("pyproject.toml"),
    Path(".github/workflows/ci.yml"),
    Path("packages/contracts/csir/csir-v0.1.schema.json"),
    Path("docs/benchmarks/BENCHMARK_001_TARGET_FREEZE_MANIFEST.json"),
)
BAD_COMPONENTS = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv",
    "node_modules", "Intermediate", "DerivedDataCache", "Library", "Saved",
})
BAD_NAMES = frozenset({
    "transfer-plan.json", "coverage-report.json", "evidence.json",
})
LINK = re.compile(r"\[[^\]]+\]\((<?[^)\s]+>?)\)")


def tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], check=True,
        capture_output=True,
    )
    return sorted(p.decode("utf-8") for p in completed.stdout.split(b"\0") if p)


def is_generated_artifact(path: str) -> bool:
    value = Path(path)
    name = value.name.lower()
    components = set(value.parts)
    return (
        bool(components & BAD_COMPONENTS)
        or name in BAD_NAMES
        or name.startswith("runtime-receipt") and name.endswith(".json")
        or name.endswith(".cinetwin.behavior.json")
        or name.endswith(".cinetwin.sampling-plan.json")
        or name.endswith(".csir.json")
        or (name.endswith(".json") and any(
            marker in name for marker in ("ced_preflight", "ced-preflight", "ced-discovery")
        ))
        or name == ".env"
        or name.startswith(".env.") and name != ".env.example"
    )


def broken_links(root: Path, document: Path) -> list[str]:
    """Only inspect relative Markdown file/directory links, not external URLs."""
    text = (root / document).read_text(encoding="utf-8")
    failures = []
    for match in LINK.finditer(text):
        raw = match.group(1).strip("<>")
        if raw.startswith(("https://", "http://", "mailto:", "#", "//")):
            continue
        target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
        if not target:
            continue
        # Resolve against the documented file's folder, not the working dir.
        resolved = (root / document.parent / target).resolve()
        if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
            failures.append(f"{document.as_posix()}: broken link {raw}")
    return failures


def audit(root: Path, *, tracked: list[str] | None = None) -> list[str]:
    problems = []
    root = root.resolve()
    for path in (*MAINTAINED, *CRITICAL):
        if not (root / path).is_file():
            problems.append(f"Missing maintained project file: {path.as_posix()}")
    for path in MAINTAINED:
        if (root / path).is_file():
            problems.extend(broken_links(root, path))
    if tracked is None:
        tracked = tracked_files(root)
    problems.extend(f"Local/generated artifact tracked by Git: {path}"
                    for path in tracked if is_generated_artifact(path))
    manifest_path = root / "docs/benchmarks/BENCHMARK_001_TARGET_FREEZE_MANIFEST.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "FROZEN_AUTOMATED_PASS":
                problems.append("Benchmark001 freeze manifest status changed unexpectedly")
        except (OSError, ValueError):
            problems.append("Benchmark001 freeze manifest is not valid JSON")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    problems = audit(args.root)
    if problems:
        print("[CutSceneAI] Repository hygiene FAIL:")
        for issue in problems:
            print("  -", issue)
        return 1
    print("[CutSceneAI] Repository hygiene PASS: maintained links, layout, "
          "freeze record and tracked-artifact rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
