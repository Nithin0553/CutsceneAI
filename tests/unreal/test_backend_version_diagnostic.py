"""The runtime version probe must not import or change the Unreal project."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "integrations" / "unreal" / "diagnose_backend_version.py"


def _diagnostic():
    spec = importlib.util.spec_from_file_location("cutsceneai_runtime_version_probe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outdated_disk_file_is_detected_without_importing_it(tmp_path, monkeypatch):
    probe = _diagnostic()
    test_file = tmp_path / "transfer_backend.py"
    test_file.write_text("legacy verifier", encoding="utf-8")
    monkeypatch.delitem(sys.modules, "test_stale_backend", raising=False)
    result = probe.describe_module("test_stale_backend", test_file)
    assert result["file_exists"]
    assert result["on_disk_has_new_float_verifier"] is False
    assert result["loaded_in_python"] is False


def test_stale_module_cache_has_independent_status_from_upgraded_file(tmp_path, monkeypatch):
    probe = _diagnostic()
    file = tmp_path / "transfer_backend.py"
    file.write_text("differs materially from source-derived JSON at", encoding="utf-8")
    old = ModuleType("test_stale_backend")
    old.__file__ = str(file)

    def verify_prepared_artifacts():
        raise RuntimeError(" differs from source-derived JSON at ")

    old.verify_prepared_artifacts = verify_prepared_artifacts
    monkeypatch.setitem(sys.modules, "test_stale_backend", old)
    result = probe.describe_module("test_stale_backend", file)
    assert result["file_exists"]
    assert result["on_disk_has_new_float_verifier"] is True
    assert result["loaded_from_expected_file"] is True
    assert result["loaded_has_new_float_verifier"] is False
    assert result["loaded_verifier_first_line"] is not None


def test_conflicting_module_path_is_reported_without_auto_reload(tmp_path, monkeypatch):
    probe = _diagnostic()
    file = tmp_path / "transfer_backend.py"
    file.write_text("differs materially from source-derived JSON at", encoding="utf-8")
    other = ModuleType("test_stale_backend")
    other.__file__ = str(tmp_path / "another" / "transfer_backend.py")
    monkeypatch.setitem(sys.modules, "test_stale_backend", other)
    result = probe.describe_module("test_stale_backend", file)
    assert result["loaded_from_expected_file"] is False
    assert result["loaded_has_new_float_verifier"] is None
