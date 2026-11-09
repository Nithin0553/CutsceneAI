"""Regression tests for the independent repository-hygiene gate."""
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "repo_check.py"
spec = util.spec_from_file_location("repo_check", SCRIPT)
assert spec is not None and spec.loader is not None
repo_check = util.module_from_spec(spec)
spec.loader.exec_module(repo_check)


def test_refuse_generated_artifacts_without_blocking_versioned_specs() -> None:
    assert repo_check.is_generated_artifact("TransferPlans/V5/transfer-plan.json")
    assert repo_check.is_generated_artifact("tests/__pycache__/cached.pyc")
    assert repo_check.is_generated_artifact("results.cinetwin.behavior.json")
    assert repo_check.is_generated_artifact("Benchmark002.csir.json")
    assert repo_check.is_generated_artifact("runtime-receipt-v5.json")
    assert repo_check.is_generated_artifact(".env.local")
    assert not repo_check.is_generated_artifact(
        "docs/benchmarks/BENCHMARK_002_SPEC.json"
    )
    assert not repo_check.is_generated_artifact(
        "docs/benchmarks/BENCHMARK_001_TARGET_FREEZE_MANIFEST.json"
    )
    assert not repo_check.is_generated_artifact(".env.example")
    assert repo_check.is_generated_artifact("my-local-ced-preflight-report.json")
    assert repo_check.is_generated_artifact("Benchmark002_CED_Preflight_V1.json")
    assert not repo_check.is_generated_artifact("packages/studio/ced_preflight.py")
    assert not repo_check.is_generated_artifact("tests/studio/test_ced_preflight.py")


def test_check_markdown_links_against_original_document_directory(tmp_path: Path) -> None:
    folder = tmp_path / "docs"
    folder.mkdir()
    (tmp_path / "README.md").write_text("Root document", encoding="utf-8")
    (folder / "notes.md").write_text(
        "[root](../README.md) [folder](../) [web](https://example.com)",
        encoding="utf-8",
    )
    assert repo_check.broken_links(tmp_path, Path("docs/notes.md")) == []
    (folder / "notes.md").write_text(
        "[missing](../does-not-exist.md) [escape](../../secret.txt)",
        encoding="utf-8",
    )
    errors = repo_check.broken_links(tmp_path, Path("docs/notes.md"))
    assert len(errors) == 2
    assert "does-not-exist.md" in errors[0]


def test_repository_maintained_links_and_git_index_pass_in_checkout() -> None:
    # This is independent of Unreal Editor and does not need asset files.
    assert repo_check.audit(ROOT) == []
