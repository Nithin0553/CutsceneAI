"""Read-only local setup diagnostics for the CutSceneAI Studio launch path.

Checks checkout structure and Python dependencies without opening an Editor,
running a model, starting a server, or altering either engine project.
This can confirm only the localhost Python side; real companion initialization
and engine acceptance remain separate explicit tests.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "pyproject.toml",
    "tools/studio_local_bridge.py",
    "tools/studio_autopilot.py",
    "apps/studio-web/index.html",
    "apps/studio-web/cinematic.js",
    "integrations/unity/com.cutsceneai.extractor/package.json",
    "integrations/unreal/studio_local_editor_worker.py",
    "packages/studio/studio_release_gate.py",
)
REQUIRED_MODULES = (
    ("pydantic", "pydantic"),
    ("yaml", "pyyaml"),
    ("jsonschema", "jsonschema"),
    ("langgraph", "langgraph"),
)


def diagnose(
    repo: Path = ROOT,
    *,
    python_version: tuple[int, ...] | None = None,
    module_exists: Callable[[str], bool] | None = None,
) -> dict:
    """Return deterministic machine-readable startup blockers, never engine parity."""
    if python_version is None:
        python_version = tuple(sys.version_info[:3])
    if module_exists is None:
        module_exists = lambda name: importlib.util.find_spec(name) is not None
    root = Path(repo).resolve()
    missing_files = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    # Local Ollama uses the Python standard library HTTP transport and never
    # requires an OpenAI SDK or an API key. The OpenAI path still does.
    provider = os.environ.get("CUTSCENEAI_MODEL_PROVIDER", "").strip().lower()
    if not provider:
        provider = "openai" if os.environ.get("OPENAI_API_KEY") else "ollama"
    required = (
        (("openai", "openai"),) if provider == "openai" else ()
    ) + REQUIRED_MODULES
    missing_modules = [
        package for module, package in required
        if not module_exists(module)
    ]
    python_ok = tuple(python_version[:2]) >= (3, 11)
    issues = []
    if provider not in {"ollama", "openai"}:
        issues.append("CUTSCENEAI_MODEL_PROVIDER must be ollama or openai.")
    if not python_ok:
        issues.append("Studio requires Python 3.11 or newer.")
    if missing_files:
        issues.append("The checkout is incomplete: " + ", ".join(missing_files))
    if missing_modules:
        issues.append(
            "Missing Python packages: " + ", ".join(missing_modules)
            + ". Install with: python -m pip install -e '.[agents]'"
        )
    return {
        "kind": "cutsceneai.studio.setup_diagnostic",
        "schema_version": "1",
        "python_version": ".".join(map(str, python_version[:3])),
        "python_supported": python_ok,
        "missing_files": missing_files,
        "missing_python_packages": missing_modules,
        "ready_to_launch_localhost": not issues,
        "model_provider_configured": provider,
        "model_runtime_connected": False,
        "engine_companions_validated": False,
        "engine_fidelity_verified": False,
        "issues": issues,
        "next_step": (
            "Start the localhost Studio server. Unity and Unreal companions still "
            "require separate installation, enabled bridge, version and native checks."
            if not issues else
            "Correct setup errors and rerun the diagnostic before launching Studio."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI Studio offline launch preflight")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Print the complete structured diagnostic")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero for missing requirements")
    options = parser.parse_args(argv)
    result = diagnose(options.repo)
    if options.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("CutSceneAI Studio local setup: " +
              ("READY TO LAUNCH" if result["ready_to_launch_localhost"] else "BLOCKED"))
        for issue in result["issues"]:
            print(" - " + issue)
        print(result["next_step"])
        print("Unity and Unreal native installation and runtime are NOT verified by this command.")
    return int(options.strict and not result["ready_to_launch_localhost"])


if __name__ == "__main__":
    raise SystemExit(main())
