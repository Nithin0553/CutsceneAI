"""Phase 10.3 source-only workstation distribution: deterministic, no secrets."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))

import build_studio_bundle as bundle


def _repo(tmp_path):
    root=tmp_path/"CutSceneAI"
    for name in bundle.TOP:
        (root/name).mkdir(parents=True)
    for name in bundle.ROOT_FILES:
        (root/name).write_text("source root "+name,encoding="utf-8")
    for name in (
        "tools/install_studio.ps1","tools/start_studio.ps1",
        "tools/launch_studio.ps1","tools/studio_startup_smoke.py",
        "tools/phase10_5_package_acceptance.py",
        "tools/phase10_5_freeze_preflight.py",
        "tools/studio_local_bridge.py","tools/studio_companion_install.py",
        "packages/studio/studio_phase10_3_flow.py",
        "apps/studio-web/cinematic.js",
        "integrations/unity/com.cutsceneai.extractor/package.json",
        "integrations/unreal/studio_local_editor_worker.py",
    ):
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("source "+name,encoding="utf-8")
    for i in range(25):
        path=root/"packages/studio"/("module_"+str(i)+".py")
        path.write_text("value = "+str(i)+"\n",encoding="utf-8")
    return root


def test_distribution_build_reproducible_and_verify_each_file(tmp_path):
    repo=_repo(tmp_path)
    first=tmp_path/"first.zip"
    second=tmp_path/"second.zip"
    report=bundle.build(repo,first)
    assert report["status"]=="SOURCE_BUNDLE_CREATED_ENGINE_ACCEPTANCE_PENDING"
    assert report["engine_binaries_bundled"] is False
    assert report["desktop_installer_independently_verified"] is False
    receipt=bundle.verify(first)
    assert receipt["file_count"]==report["file_count"]
    bundle.build(repo,second)
    assert first.read_bytes()==second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        manifest=json.loads(archive.read(bundle.MANIFEST))
        assert "tools/studio_companion_install.py" in manifest["files"]
        assert "packages/studio/studio_phase10_3_flow.py" in manifest["files"]
        assert manifest["full_cutscene_fidelity_verified"] is False
        assert not any(".env" in x for x in archive.namelist())


def test_distribution_fails_when_missing_bootstrap_and_never_overwrites(tmp_path):
    repo=_repo(tmp_path)
    (repo/"tools/start_studio.ps1").unlink()
    archive=tmp_path/"bundle.zip"
    with pytest.raises(bundle.BundleError,match="Required distributed"):
        bundle.build(repo,archive)
    assert not archive.exists()
    (repo/"tools/start_studio.ps1").write_text("start",encoding="utf-8")
    bundle.build(repo,archive)
    before=archive.read_bytes()
    with pytest.raises(bundle.BundleError,match="overwrite"):
        bundle.build(repo,archive)
    assert archive.read_bytes()==before


def test_distribution_rejects_symlink_and_sensitive_source(tmp_path):
    repo=_repo(tmp_path)
    destination=tmp_path/"external.py"
    destination.write_text("SECRET = 'external'",encoding="utf-8")
    redirect=repo/"tools/outside.py"
    try:
        redirect.symlink_to(destination)
    except (NotImplementedError,OSError):
        pytest.skip("Host platform does not permit symlinks.")
    with pytest.raises(bundle.BundleError,match="redirected"):
        bundle.build(repo,tmp_path/"bundle.zip")
    redirect.unlink()
    (repo/"tools/secret_token.py").write_text("api='should-not-ship'",encoding="utf-8")
    with pytest.raises(bundle.BundleError,match="Sensitive"):
        bundle.build(repo,tmp_path/"bundle.zip")


def test_distribution_rejects_extra_or_missing_manifest_entries(tmp_path):
    repo=_repo(tmp_path)
    archive=tmp_path/"bundle.zip"
    bundle.build(repo,archive)
    with zipfile.ZipFile(archive,mode="a") as zipfile_writer:
        zipfile_writer.writestr("CutSceneAI-Studio/unlisted.py","malicious")
    with pytest.raises(bundle.BundleError,match="Undocumented"):
        bundle.verify(archive)


def test_distribution_archive_must_match_exact_checkout_for_freeze(tmp_path):
    repo=_repo(tmp_path)
    archive=tmp_path/"release.zip"
    bundle.build(repo,archive)
    ok=bundle.verify_exact_checkout(repo,archive)
    assert ok["exact_checked_out_source_verified"] is True
    (repo/"packages/studio/module_0.py").write_text(
        "value = 'different source revision'\n",encoding="utf-8",
    )
    # ZIP remains internally valid but no longer represents this checkout.
    assert bundle.verify(archive)["status"]==(
        "SOURCE_BUNDLE_HASHES_VERIFIED_ENGINE_PENDING"
    )
    with pytest.raises(bundle.BundleError,match="exact checked-out"):
        bundle.verify_exact_checkout(repo,archive)


def test_portable_source_fingerprint_ignores_only_text_crlf_variants(tmp_path):
    repo=_repo(tmp_path)
    source=repo/"packages/studio/module_0.py"
    source.write_bytes(b"value = 0\n# source\n")
    first=tmp_path/"linux.zip"
    bundle.build(repo,first)
    original=bundle.verify(first)
    source.write_bytes(b"value = 0\r\n# source\r\n")
    second=tmp_path/"windows.zip"
    bundle.build(repo,second)
    converted=bundle.verify(second)
    assert original["source_manifest_sha256"]!=converted["source_manifest_sha256"]
    assert original["portable_source_manifest_sha256"]==converted[
        "portable_source_manifest_sha256"
    ]
    source.write_bytes(b"value = 1\r\n# source\r\n")
    third=tmp_path/"altered.zip"
    bundle.build(repo,third)
    changed=bundle.verify(third)
    assert original["portable_source_manifest_sha256"]!=changed[
        "portable_source_manifest_sha256"
    ]


def test_portable_source_fingerprint_never_normalizes_binary_asset_bytes(tmp_path):
    repo=_repo(tmp_path)
    image=repo/"apps/studio-web"/"test.png"
    image.write_bytes(b"fake-png\r\nbyte-stream")
    first=tmp_path/"binary-a.zip"
    bundle.build(repo,first)
    before=bundle.verify(first)
    image.write_bytes(b"fake-png\nbyte-stream")
    second=tmp_path/"binary-b.zip"
    bundle.build(repo,second)
    after=bundle.verify(second)
    assert before["portable_source_manifest_sha256"]!=after[
        "portable_source_manifest_sha256"
    ]
