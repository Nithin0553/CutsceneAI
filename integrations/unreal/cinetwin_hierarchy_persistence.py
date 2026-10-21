"""Persist source-derived actor hierarchy into one explicitly scoped Unreal level.

Only use on a backed-up staging project after a generated target sequence exists.
This replays hierarchy/child setup without rebuilding or overwriting Sequencer.

Unreal Python set_mobility/attach_to_actor can change live actor state without
the level package becoming dirty. Save the exact actor package explicitly with
EditorLoadingAndSavingUtils.save_packages(..., only_dirty=False).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import unreal

HERE = Path(__file__).resolve().parent
for directory in (HERE, HERE.parents[1] / "packages" / "cinetwin"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import cinetwin_hierarchy_runtime
import csir_plan
import hierarchy_realization
import scene_prep
import unreal_compat


class HierarchyPersistenceError(RuntimeError):
    """Preflight or explicit level-package save failed."""


def _normalize_directory(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _scoped_actors(
    operations: dict[str, Any], expected_level_package: str
) -> tuple[dict[str, Any], Any]:
    labels = {
        entry[key]
        for entry in operations["attachments"]
        for key in ("actor_label", "parent_actor_label")
    }
    if not labels:
        raise HierarchyPersistenceError("No directly mapped actor attachments.")
    actors = unreal.get_editor_subsystem(
        unreal.EditorActorSubsystem
    ).get_all_level_actors()
    matches = {
        label: [actor for actor in actors if str(actor.get_actor_label()) == label]
        for label in labels
    }
    if any(len(matches[label]) != 1 for label in labels):
        raise HierarchyPersistenceError(
            "Target level actor labels must be uniquely resolved: "
            + ", ".join(sorted(
                label for label in labels if len(matches[label]) != 1
            ))
        )
    mapped = {label: matches[label][0] for label in labels}
    packages = [mapped[label].get_package() for label in sorted(labels)]
    if any(
        str(pkg.get_path_name()) != expected_level_package for pkg in packages
    ):
        raise HierarchyPersistenceError(
            "Attached actors must belong to the explicitly expected level "
            f"package: {expected_level_package}."
        )
    return mapped, packages[0]


def _restore_initializations(changes: list[dict[str, Any]]) -> None:
    for change in reversed(changes):
        change["actor"].set_actor_transform(change["original"], False, True)


def apply_and_save_existing(
    csir_path: str,
    mapping_path: str,
    *,
    expected_project_directory: str,
    expected_level_package: str,
) -> dict[str, Any]:
    """Reattach mapped actors in an isolated project and save only their level.

    Never overwrites the existing Level Sequence. Explicit project and level
    checks happen BEFORE modifications. A later reopen is still required
    before claiming disk persistence has been verified.
    """
    current_project = _normalize_directory(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    )
    expected_project = _normalize_directory(expected_project_directory)
    if current_project != expected_project:
        raise HierarchyPersistenceError(
            f"Refusing to edit another Unreal project: {current_project}"
        )
    if not expected_level_package.startswith("/Game/") or "/" not in (
        expected_level_package.removeprefix("/Game/")
    ):
        raise HierarchyPersistenceError("Expected an explicit /Game/... level package.")

    csir = csir_plan.load_json(csir_path)
    mapping = csir_plan.load_json(mapping_path)
    if not mapping.get("enable_cinetwin_hierarchy"):
        raise HierarchyPersistenceError(
            "The target mapping has not opted in to hierarchy reconstruction."
        )
    if mapping.get("overwrite_sequence"):
        raise HierarchyPersistenceError("Refusing an overwriting target mapping.")
    asset_path = str(mapping.get("sequence_asset_path", ""))
    if not asset_path or not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        raise HierarchyPersistenceError(
            "The previously generated test Level Sequence must exist. "
            "No sequence will be created or overwritten."
        )
    if not callable(getattr(unreal.EditorLoadingAndSavingUtils, "save_packages", None)):
        raise HierarchyPersistenceError(
            "This Unreal version does not expose explicit package saving."
        )

    # No asset loading or modification before the source->target plan is valid.
    actions = csir_plan.build_plan(csir, mapping)["actions"]
    operations = hierarchy_realization.build_attachment_operations(
        csir, mapping, actions
    )
    actors, level_package = _scoped_actors(operations, expected_level_package)

    # The builder originally prepares mapped child actors from their source
    # world transforms before establishing KEEP_WORLD. Reapply *only* the
    # affected unattached children; unrelated actors and the saved sequence
    # remain untouched.
    scene_ops = {
        op["actor_label"]: op for op in scene_prep.build_scene_prep(csir, mapping)
    }
    pending = [
        edge for edge in operations["attachments"]
        if actors[edge["actor_label"]].get_attach_parent_actor()
        != actors[edge["parent_actor_label"]]
    ]
    child_poses: list[tuple[Any, dict[str, Any]]] = []
    for edge in pending:
        label = edge["actor_label"]
        if label not in scene_ops:
            raise HierarchyPersistenceError(
                "Source child has no verified world initialization: " + label
            )
        child_poses.append((actors[label], scene_ops[label]))
    unreal.log(
        "[CineTwin] Explicit level save PRECHECK: "
        f"package={expected_level_package}, existing_sequence={asset_path}, "
        f"attachments={len(operations['attachments'])}, "
        f"missing_attachments={len(pending)}"
    )

    initialized: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    try:
        for child, op in child_poses:
            initialized.append({
                "actor": child, "original": child.get_actor_transform()
            })
            x, y, z = op["location_cm"]
            pitch, yaw, roll = op["rotation_pitch_yaw_roll_degrees"]
            sx, sy, sz = op["scale_xyz"]
            child.set_actor_location(unreal.Vector(x, y, z), False, True)
            child.set_actor_rotation(
                unreal_compat.make_rotator_semantic(
                    roll=roll, pitch=pitch, yaw=yaw
                ), True
            )
            child.set_actor_scale3d(unreal.Vector(sx, sy, sz))
        applied = cinetwin_hierarchy_runtime.apply_hierarchy(operations)

        for edge in operations["attachments"]:
            child = actors[edge["actor_label"]]
            parent = actors[edge["parent_actor_label"]]
            if child.get_attach_parent_actor() != parent:
                raise HierarchyPersistenceError(
                    "Attachment changed before save: " + edge["actor_label"]
                )

        # IMPORTANT: force the map package to disk even if the Python actor
        # operations have not set UPackage.bDirty. Never save all unrelated
        # dirty assets or rely on whatever level happens to be selected.
        saved = unreal.EditorLoadingAndSavingUtils.save_packages(
            [level_package], only_dirty=False
        )
        if saved is not True:
            raise HierarchyPersistenceError(
                "Unreal did not confirm saving the exact level package."
            )
        if any(
            actors[edge["actor_label"]].get_attach_parent_actor()
            != actors[edge["parent_actor_label"]]
            for edge in operations["attachments"]
        ):
            raise HierarchyPersistenceError(
                "Level saved, but attachment readback unexpectedly changed."
            )
        unreal.log(
            "[CineTwin] LEVEL PACKAGE EXPLICITLY SAVED: "
            + expected_level_package
            + " (only_dirty=False). Reopen to verify persistence."
        )
        return {
            "status": "SAVED_AWAITING_REOPEN",
            "level_package": expected_level_package,
            "sequence_asset_path": asset_path,
            "attachment_count": len(operations["attachments"]),
            "new_attachment_count": len(pending),
            "unresolved_source_parent_count": len(
                operations["unresolved_source_parents"]
            ),
        }
    except Exception:
        # Roll back uncommitted editor state. A false/partial disk save might
        # still require a restored backup: the save API has no atomic undo.
        if applied:
            cinetwin_hierarchy_runtime.rollback_hierarchy(applied)
        _restore_initializations(initialized)
        raise
