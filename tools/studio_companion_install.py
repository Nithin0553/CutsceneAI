"""Opt-in, non-overwriting Unity/Unreal Studio companion project wiring.

Never starts editors, runs native Python or changes source scenes. A plan
contains no authorization. --apply requires explicit operator approval.
Actual Package Manager reload and Unreal PythonScriptPlugin behavior require
running Editors and separate native acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

PACKAGE = "com.cutsceneai.extractor"
WORKER = "integrations/unreal/studio_local_editor_worker.py"
PROJECT_GUIDANCE = (
    "Enable the selected Unity project's Source Bridge in Unity Editor once. "
    "Enable Unreal PythonScriptPlugin, load the selected map and verify its "
    "Studio worker heartbeat. Existing editor sessions may require one-time "
    "in-editor Python console import, not a forced restart."
)


class CompanionInstallError(ValueError):
    pass


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _secure_file(path: Path, *, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise CompanionInstallError("Missing, oversized or redirected project configuration.")
    return path.read_bytes()


def _no_link_parent(path: Path, root: Path) -> None:
    for parent in (path, *path.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise CompanionInstallError("Symlinked companion directory or target forbidden.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise CompanionInstallError("Companion target escaped selected project.")


def inspect(repo: Path, unity_project: Path, unreal_uproject: Path) -> dict:
    """Validate all changes BEFORE a file may be modified."""
    for target in (repo, unity_project, unreal_uproject):
        if target.is_symlink():
            raise CompanionInstallError("Symlinked selected repository/project forbidden.")
    root = repo.resolve(strict=True)
    unity = unity_project.resolve(strict=True)
    unreal_file = unreal_uproject.resolve(strict=True)
    if (not unity.is_dir() or not unreal_file.is_file()
            or unreal_file.suffix.lower() != ".uproject"
            or not unreal_file.parent.is_dir()
            or not (unity/"Assets").is_dir()
            or not (unity/"ProjectSettings").is_dir()):
        raise CompanionInstallError("Select one real Unity project and one Unreal .uproject.")
    if any((unity/part).is_symlink() for part in ("Assets","ProjectSettings","Packages")):
        raise CompanionInstallError("Selected Unity project redirects a required directory.")
    if not (root/WORKER).is_file() or not (root/"tools/studio_local_bridge.py").is_file():
        raise CompanionInstallError("Studio repository lacks native worker or local host.")
    package_dir = root/"integrations/unity"/PACKAGE
    pkg = json.loads(_secure_file(package_dir/"package.json",limit=64*1024))
    if pkg.get("name") != PACKAGE or not isinstance(pkg.get("version"),str):
        raise CompanionInstallError("Source Unity package identity is incorrect.")
    manifest = unity/"Packages"/"manifest.json"
    _no_link_parent(manifest,unity)
    before = _secure_file(manifest,limit=512*1024)
    try:
        parsed=json.loads(before.decode("utf-8-sig"))
    except (ValueError,UnicodeDecodeError) as exc:
        raise CompanionInstallError("Unity Packages/manifest.json is invalid.") from exc
    deps=parsed.get("dependencies")
    if not isinstance(parsed,dict) or not isinstance(deps,dict):
        raise CompanionInstallError("Unity manifest must contain dependency mapping.")
    source = "file:" + package_dir.as_posix()
    existing = deps.get(PACKAGE)
    if existing not in (None,source):
        raise CompanionInstallError(
            "Different Unity extractor already installed; review its version manually."
        )
    next_manifest=before
    if existing != source:
        updated=dict(parsed)
        updated["dependencies"]={**deps,PACKAGE:source}
        next_manifest=(json.dumps(updated,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
    _no_link_parent(unreal_file,unreal_file.parent)
    up = json.loads(_secure_file(unreal_file,limit=1024*1024))
    if not isinstance(up,dict):
        raise CompanionInstallError("Unreal project manifest is invalid.")
    plugin=up.get("Plugins",[])
    if not isinstance(plugin,list) or not any(
            isinstance(p,dict) and p.get("Name")=="PythonScriptPlugin"
            and p.get("Enabled") is True for p in plugin):
        raise CompanionInstallError(
            "Enable PythonScriptPlugin explicitly in Unreal Editor before installing startup wiring."
        )
    target=unreal_file.parent/"Content/Python/init_unreal.py"
    _no_link_parent(target,unreal_file.parent)
    if any((unreal_file.parent/p).is_symlink() for p in ("Content","Content/Python")):
        raise CompanionInstallError("Unreal Python startup directory is redirected.")
    if any(ord(v)<32 or v in "\r\n" for v in str(root)):
        raise CompanionInstallError("Studio repository path contains control characters.")
    startup=(
        "# CutSceneAI Studio opt-in project-local Unreal Python bootstrap\n"
        "# Only runs inside the editor when PythonScriptPlugin is enabled.\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"_csai_path = {str(root/'integrations/unreal')!r}\n"
        "if _csai_path not in sys.path:\n"
        "    sys.path.insert(0, _csai_path)\n"
        "import studio_local_editor_worker as _csai_worker\n"
        "if _csai_worker.HANDLE is None:\n"
        "    _csai_worker.start()\n"
    ).encode("utf-8")
    if target.exists():
        if _secure_file(target,limit=64*1024) != startup:
            raise CompanionInstallError(
                "Existing Unreal init_unreal.py is not Studio-owned; do not overwrite it."
            )
    steps=[]
    if next_manifest!=before:
        steps.append("WRITE_UNITY_LOCAL_UPM_DEPENDENCY_WITH_BACKUP")
    if not target.is_file():
        steps.append("CREATE_UNREAL_PROJECT_PYTHON_STARTUP_EXCLUSIVELY")
    return {
        "kind":"cutsceneai.studio.opt_in_companion_project_wiring",
        "schema_version":"1",
        "repository":str(root),
        "unity_project":str(unity),
        "unreal_uproject":str(unreal_file),
        "unity_manifest":str(manifest),
        "unity_manifest_sha256_before":_hash(before),
        "unity_manifest_sha256_after":_hash(next_manifest),
        "unity_manifest_bytes_after":next_manifest,
        "unreal_startup":str(target),
        "unreal_startup_sha256":_hash(startup),
        "unreal_startup_bytes":startup,
        "steps":steps,
        "native_editor_connected":False,
        "real_companion_activation_verified":False,
        "instructions":PROJECT_GUIDANCE,
    }


def install(repo: Path, unity_project: Path, unreal_uproject: Path, *,
            consent: bool) -> dict:
    if consent is not True:
        raise CompanionInstallError("Explicit --apply consent is required.")
    plan=inspect(repo,unity_project,unreal_uproject)
    manifest=Path(plan["unity_manifest"])
    startup=Path(plan["unreal_startup"])
    # Preserve originals; never silently replace backup from another attempt.
    backup=manifest.with_name("manifest.json.cutsceneai-before-install.bak")
    if "WRITE_UNITY_LOCAL_UPM_DEPENDENCY_WITH_BACKUP" in plan["steps"] and backup.exists():
        raise CompanionInstallError("Unity manifest backup already exists; inspect it before retrying.")
    did_write_unity=False
    try:
        if "CREATE_UNREAL_PROJECT_PYTHON_STARTUP_EXCLUSIVELY" in plan["steps"]:
            startup.parent.mkdir(parents=True,exist_ok=True)
            _no_link_parent(startup,Path(plan["unreal_uproject"]).parent)
            with startup.open("xb") as stream:
                stream.write(plan["unreal_startup_bytes"])
        if "WRITE_UNITY_LOCAL_UPM_DEPENDENCY_WITH_BACKUP" in plan["steps"]:
            original=_secure_file(manifest,limit=512*1024)
            if _hash(original)!=plan["unity_manifest_sha256_before"]:
                raise CompanionInstallError("Unity manifest changed during installation.")
            with backup.open("xb") as stream:
                stream.write(original)
            tmp=manifest.with_name("manifest.json."+uuid.uuid4().hex+".tmp")
            try:
                tmp.write_bytes(plan["unity_manifest_bytes_after"])
                os.replace(tmp,manifest)
                did_write_unity=True
            finally:
                if tmp.exists():
                    tmp.unlink()
    except (OSError,ValueError) as exc:
        # Do not remove an Unreal startup script that may have been loaded by
        # an editor between writes. Preserve anything partially created and
        # require explicit inspection instead of automatic replay.
        raise CompanionInstallError(
            "Companion installation incomplete; inspect the project-local "
            "startup file and the Unity manifest backup before retrying."
        ) from exc
    return {
        "kind":"cutsceneai.studio.companion_wiring_receipt",
        "status":"PROJECT_WIRING_WRITTEN_EDITOR_ACTIVATION_UNVERIFIED",
        "steps":plan["steps"],
        "unity_manifest_sha256_after":_hash(_secure_file(manifest,limit=512*1024)),
        "unreal_startup_sha256":_hash(_secure_file(startup,limit=64*1024)),
        "unity_backup_created":did_write_unity,
        "native_editor_connected":False,
        "real_companion_activation_verified":False,
        "next_action":PROJECT_GUIDANCE,
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--unity",type=Path,required=True)
    parser.add_argument("--unreal-uproject",type=Path,required=True)
    parser.add_argument("--apply",action="store_true",
                        help="Explicitly modify only the selected project wiring")
    args=parser.parse_args(argv)
    try:
        result=(install(args.repo,args.unity,args.unreal_uproject,consent=True)
                if args.apply else inspect(args.repo,args.unity,args.unreal_uproject))
    except (CompanionInstallError,OSError,ValueError,KeyError,TypeError) as exc:
        parser.error(str(exc))
    for key in ("unity_manifest_bytes_after","unreal_startup_bytes"):
        result.pop(key,None)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    sys.exit(main())
