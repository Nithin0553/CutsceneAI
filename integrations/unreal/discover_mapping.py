"""Read-only Unreal project inventory and source mapping suggestions.

Run from the *target* Unreal Editor; never import assets or spawn actors.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import unreal

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "packages" / "studio") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages" / "studio"))

import asset_resolver


def propose_from_editor(csir_path: str, report_path: str) -> dict[str, Any]:
    csir = json.loads(Path(csir_path).read_text(encoding="utf-8-sig"))
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor_labels = [str(a.get_actor_label()) for a in subsystem.get_all_level_actors()]
    assets = [
        str(asset) for asset in unreal.EditorAssetLibrary.list_assets(
            "/Game", recursive=True, include_folder=False
        )
    ]
    report = asset_resolver.propose(
        csir,
        target_actor_labels=actor_labels,
        target_asset_paths=assets,
    )
    report["unreal_project"] = str(unreal.Paths.get_project_file_path())
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    report["loaded_level"] = str(world.get_path_name()).split(".")[0]
    output = Path(report_path)
    if output.exists():
        raise ValueError(f"Refusing to overwrite inventory report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    unreal.log(
        f"[CutSceneAI] Read-only candidate mapping saved: {output}. "
        "No asset import or actor creation. Verify before applying."
    )
    return report
