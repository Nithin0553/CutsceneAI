"""Build a reproducible, source-only CutSceneAI Studio workstation bundle.

No binary engine, Unity/Unreal install, model weights, API keys or user projects
are packaged. Runtime Python dependencies are installed separately by the
existing opt-in Windows launcher. This is packaging readiness, not engine proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

TOP = ("tools","packages","apps/studio-web","integrations/unity",
       "integrations/unreal","config","docs/studio","tests/studio")
ROOT_FILES = ("README.md","pyproject.toml")
SUFFIXES = {
    ".py",".pyi",".js",".cjs",".css",".html",".json",".jsonl",".md",
    ".toml",".ps1",".sh",".yaml",".yml",".ini",".txt",".xml",
    ".cs",".asmdef",".meta",".svg",".png",".jpg",".jpeg",".uplugin",
    ".bat",".cfg",
}
MAX_TOTAL=96*1024*1024
MAX_FILE=8*1024*1024
MAX_COUNT=2600
TOPDIR="CutSceneAI-Studio/"
MANIFEST=TOPDIR+"studio-distribution-manifest.json"


class BundleError(ValueError):
    pass


def digest(payload:bytes)->str:
    return hashlib.sha256(payload).hexdigest()


def _files(repo:Path)->list[tuple[str,bytes]]:
    if repo.is_symlink() or not repo.is_dir():
        raise BundleError("Select a real non-symlink Studio source directory.")
    seen={}
    total=0
    for dirname in TOP:
        origin=repo/dirname
        if origin.is_symlink() or not origin.is_dir():
            raise BundleError("Required Studio source folder missing or redirected: "+dirname)
        for path in origin.rglob("*"):
            if (any(part.startswith(".") or part in {
                "__pycache__","node_modules",".venv","build","dist",
            } for part in path.relative_to(repo).parts)
                or path.is_dir()):
                continue
            if path.is_symlink():
                raise BundleError("Studio source tree includes redirected file.")
            if path.suffix.lower() not in SUFFIXES:
                continue
            relative=path.relative_to(repo).as_posix()
            if any(word in relative.lower() for word in (
                "secret","private-key","password",".env","credential",
            )):
                raise BundleError("Sensitive source artifact must be removed: "+relative)
            size=path.stat().st_size
            if size>MAX_FILE:
                raise BundleError("Studio source asset exceeds packaging size cap.")
            blob=path.read_bytes()
            total+=len(blob)
            if total>MAX_TOTAL or len(seen)>=MAX_COUNT:
                raise BundleError("Studio source distribution exceeds bounded size.")
            seen[relative]=blob
    for name in ROOT_FILES:
        path=repo/name
        if path.is_symlink() or not path.is_file():
            raise BundleError("Required root release file absent: "+name)
        seen[name]=path.read_bytes()
    if len(seen)<25:
        raise BundleError("Studio package inventory is unexpectedly incomplete.")
    for key in (
        "tools/install_studio.ps1","tools/start_studio.ps1",
        "tools/studio_local_bridge.py","tools/studio_companion_install.py",
        "packages/studio/studio_phase10_3_flow.py",
        "apps/studio-web/cinematic.js",
        "integrations/unity/com.cutsceneai.extractor/package.json",
        "integrations/unreal/studio_local_editor_worker.py",
    ):
        if key not in seen:
            raise BundleError("Required distributed workflow component absent: "+key)
    return sorted(seen.items())


def build(repo:Path,output:Path)->dict[str,Any]:
    files=_files(repo)
    if output.exists() or output.is_symlink():
        raise BundleError("Distribution output already exists; overwrite forbidden.")
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest={
        "kind":"cutsceneai.studio.source_distribution_manifest",
        "schema_version":"1",
        "distribution_kind":"SOURCE_WITH_EXPLICIT_PYTHON_DEPENDENCY_INSTALL",
        "engine_binaries_bundled":False,
        "native_companion_activation_verified":False,
        "full_cutscene_fidelity_verified":False,
        "files":{name:{"sha256":digest(data),"size_bytes":len(data)}
                 for name,data in files},
    }
    metadata=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode("utf-8")
    # Exclusive creation and fixed timestamps keep the archive byte-reproducible.
    with output.open("xb") as stream:
        try:
            with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=8) as archive:
                for name,data in [*files,("studio-distribution-manifest.json",metadata)]:
                    info=zipfile.ZipInfo(TOPDIR+name,date_time=(2026,1,1,0,0,0))
                    info.compress_type=zipfile.ZIP_DEFLATED
                    info.external_attr=(0o100644<<16)
                    archive.writestr(info,data)
        except Exception:
            output.unlink(missing_ok=True)
            raise
    return {
        "kind":"cutsceneai.studio.source_distribution_build_receipt",
        "status":"SOURCE_BUNDLE_CREATED_ENGINE_ACCEPTANCE_PENDING",
        "file_count":len(files),
        "sha256":digest(output.read_bytes()),
        "engine_binaries_bundled":False,
        "desktop_installer_independently_verified":False,
        "native_editor_fidelity_verified":False,
    }


def verify(archive_path:Path)->dict[str,Any]:
    if archive_path.is_symlink() or not archive_path.is_file():
        raise BundleError("Source distribution archive unavailable.")
    with zipfile.ZipFile(archive_path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or MANIFEST not in names:
            raise BundleError("Duplicate or missing source distribution manifest.")
        if any(not x.startswith(TOPDIR) or ".." in Path(x).parts
               for x in names):
            raise BundleError("Unsafe source bundle archive entry.")
        manifest=json.loads(archive.read(MANIFEST))
        if (manifest.get("kind")!="cutsceneai.studio.source_distribution_manifest"
                or manifest.get("engine_binaries_bundled") is not False
                or not isinstance(manifest.get("files"),dict)):
            raise BundleError("Source bundle manifest is invalid.")
        if set(names)!={MANIFEST}|{TOPDIR+name for name in manifest["files"]}:
            raise BundleError("Undocumented source artifact found in archive.")
        for relative,row in manifest["files"].items():
            payload=archive.read(TOPDIR+relative)
            if len(payload)!=row["size_bytes"] or digest(payload)!=row["sha256"]:
                raise BundleError("Source distribution asset hash mismatch: "+relative)
    return {
        "status":"SOURCE_BUNDLE_HASHES_VERIFIED_ENGINE_PENDING",
        "file_count":len(manifest["files"]),
        "sha256":digest(archive_path.read_bytes()),
        "full_cutscene_fidelity_verified":False,
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--verify",action="store_true",
                        help="Verify an existing archive, do not create one")
    args=parser.parse_args(argv)
    try:
        result=verify(args.output) if args.verify else build(args.repo,args.output)
    except (BundleError,OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    sys.exit(main())
