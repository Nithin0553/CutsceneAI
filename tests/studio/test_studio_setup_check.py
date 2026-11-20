"""Offline Studio bootstrap must fail early without touching either engine."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_studio_setup


def checkout(tmp_path: Path) -> Path:
    for relative in check_studio_setup.REQUIRED_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("present", encoding="utf-8")
    return tmp_path


def test_valid_local_environment_never_claims_engine_acceptance(tmp_path):
    root = checkout(tmp_path)
    result = check_studio_setup.diagnose(
        root, python_version=(3, 11, 9), module_exists=lambda _: True,
    )
    assert result["ready_to_launch_localhost"] is True
    assert result["engine_companions_validated"] is False
    assert result["engine_fidelity_verified"] is False
    assert result["issues"] == []


def test_missing_python_and_dependencies_are_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "openai")
    root = checkout(tmp_path)
    result = check_studio_setup.diagnose(
        root, python_version=(3, 10, 14),
        module_exists=lambda name: name not in {"openai", "langgraph"},
    )
    assert not result["ready_to_launch_localhost"]
    assert "Python 3.11" in " ".join(result["issues"])
    assert result["missing_python_packages"] == ["openai", "langgraph"]
    assert ".[agents]" in " ".join(result["issues"])


def test_incomplete_checkout_is_rejected_without_engine_calls(tmp_path):
    root = checkout(tmp_path)
    (root / "integrations/unreal/studio_local_editor_worker.py").unlink()
    result = check_studio_setup.diagnose(
        root, python_version=(3, 12, 1), module_exists=lambda _: True,
    )
    assert result["missing_files"] == [
        "integrations/unreal/studio_local_editor_worker.py"
    ]
    assert not result["ready_to_launch_localhost"]


def test_windows_launcher_has_isolated_strict_preflight_and_no_engine_commands():
    install = (ROOT / "tools/install_studio.ps1").read_text(encoding="utf-8")
    launch = (ROOT / "tools/start_studio.ps1").read_text(encoding="utf-8")
    assert ".venv-studio" in install and ".venv-studio" in launch
    assert "-e" in install and "[agents]" in install
    assert "--strict" in install and "--strict" in launch
    assert "studio_local_bridge.py" in launch
    assert "UnrealEditor.exe" not in install
    assert "Unity.exe" not in install



def test_local_ollama_setup_does_not_require_openai_sdk(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = check_studio_setup.diagnose(
        checkout(tmp_path), python_version=(3, 12, 0),
        module_exists=lambda name: name != "openai",
    )
    assert result["ready_to_launch_localhost"] is True
    assert result["model_provider_configured"] == "ollama"
    assert result["model_runtime_connected"] is False
