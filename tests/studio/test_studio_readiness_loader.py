"""Regression for 2026-10-31 Unreal import recursion after native staging.

Use a fresh subprocess: real UE interpreters can already contain either name
in sys.modules; a mock-only unit import is insufficient for this regression.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
CINETWIN = ROOT / "packages" / "cinetwin"
UNREAL = ROOT / "integrations" / "unreal"


def _python(source: str):
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_shadowed_tool_wrapper_and_canonical_readiness_coexist():
    result = _python(
        f"""import sys
from pathlib import Path
sys.path.insert(0, {str(TOOLS)!r})
import transfer_readiness
assert callable(transfer_readiness.audit_files)
assert not hasattr(transfer_readiness, 'audit')
sys.path.insert(0, {str(CINETWIN)!r})
from readiness_loader import load_source_readiness
semantic = load_source_readiness()
assert semantic is not transfer_readiness
assert callable(semantic.audit)
assert callable(semantic.audit_files)
assert Path(semantic.__file__).resolve() == Path({str(CINETWIN / 'transfer_readiness.py')!r}).resolve()
assert load_source_readiness() is semantic
"""
    )
    assert result.returncode == 0, result.stderr


def test_real_unreal_builder_import_uses_canonical_readiness_after_wrapper():
    result = _python(
        f"""import sys, types
from pathlib import Path
sys.path.insert(0, {str(TOOLS)!r})
import transfer_readiness
assert not hasattr(transfer_readiness, 'audit')
sys.modules['unreal'] = types.ModuleType('unreal')
sys.path.insert(0, {str(UNREAL)!r})
import build_level_sequence
assert callable(build_level_sequence.transfer_readiness.audit)
assert Path(build_level_sequence.transfer_readiness.__file__).resolve() == Path({str(CINETWIN / 'transfer_readiness.py')!r}).resolve()
"""
    )
    assert result.returncode == 0, result.stderr


def test_tools_cli_help_does_not_import_itself_recursively():
    result = subprocess.run(
        [sys.executable, str(TOOLS / "transfer_readiness.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "read-only CutSceneAI" in result.stdout.lower() or "source coverage" in result.stdout.lower()


def test_worker_preloads_generator_before_any_native_staging():
    import ast

    tree = ast.parse((UNREAL / "studio_local_editor_worker.py").read_text(encoding="utf-8"))
    run = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == "_execute")
    statements = run.body
    builder_at = next(i for i, node in enumerate(statements)
                      if isinstance(node, ast.Import)
                      and any(alias.name == "build_level_sequence" for alias in node.names))
    stage_at = next(i for i, node in enumerate(statements)
                    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "_ensure_target_level")
    assert builder_at < stage_at
