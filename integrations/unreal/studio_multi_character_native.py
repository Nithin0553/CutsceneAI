"""Native multi-character Sequencer binding and synchronization verification.

Used after a source-bound multi-character staging plan is constructed, and
again after reopening. A PASS proves native *structure*, not full movement,
IK contact, parent-driven animation, or rendered behavior equivalence.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


class NativeCoordinationError(ValueError):
    pass


def _class(value: Any) -> str:
    if value is None:
        return ""
    return str(value.get_class().get_name())


def _path(value: Any) -> str:
    return str(value.get_path_name()).split(".",1)[0] if value is not None else ""


def inspect(api: Any, sequence: Any, csir: dict, mapping: dict,
            plan: dict) -> dict:
    if (not isinstance(csir,dict) or not isinstance(mapping,dict)
            or not isinstance(plan,dict)
            or not isinstance(plan.get("actions"),list)
            or not isinstance(csir.get("entities"),list)):
        raise NativeCoordinationError("Prepared original character and action census required.")
    characters=[
        row for row in csir["entities"]
        if isinstance(row,dict) and row.get("ced_type")=="entity.character"
    ]
    if not 1<=len(characters)<=32:
        raise NativeCoordinationError("Expected at most 32 mapped source characters.")
    all_ids={row.get("entity_id"):row for row in csir["entities"]
             if isinstance(row,dict)}
    if len(all_ids)!=len(csir["entities"]):
        raise NativeCoordinationError("Original entity identity is ambiguous.")
    expected={}
    for actor in characters:
        name=actor.get("name")
        row=(mapping.get("entities") or {}).get(name)
        label=row.get("actor_label") if isinstance(row,dict) else None
        if not isinstance(label,str) or not label or label in expected.values():
            raise NativeCoordinationError("Native character name/label mapping is not unique.")
        expected[actor["entity_id"]]=label
    extension=getattr(api,"MovieSceneSequenceExtensions",None)
    if (extension is None or not callable(getattr(extension,"get_bindings",None))
            or not callable(getattr(extension,"locate_bound_objects",None))):
        raise NativeCoordinationError("Sequencer native binding readback unavailable.")
    world=api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    bindings=list(extension.get_bindings(sequence))
    if len(bindings)>10000:
        raise NativeCoordinationError("Unbounded native Sequencer binding count.")
    found={}
    for bind in bindings:
        objects=list(extension.locate_bound_objects(sequence,bind,world))
        if len(objects)>1:
            raise NativeCoordinationError("Ambiguous native Sequencer binding object.")
        if len(objects)!=1:
            continue
        owner=objects[0]
        label=str(owner.get_actor_label()) if callable(getattr(owner,"get_actor_label",None)) else ""
        if label not in expected.values():
            continue
        if label in found:
            raise NativeCoordinationError("A source character has multiple native bindings.")
        found[label]=(owner,bind)
    if set(found)!=set(expected.values()):
        raise NativeCoordinationError("One or more mapped characters lack native Sequencer bindings.")
    results=[]
    for character in characters:
        entity_id=character["entity_id"]
        label=expected[entity_id]
        actor,bind=found[label]
        parent_id=character.get("parent_entity_id")
        actual_parent=actor.get_attach_parent_actor()
        if parent_id:
            approved_parent=all_ids.get(parent_id)
            target=(mapping.get("entities") or {}).get(approved_parent.get("name")
                    if isinstance(approved_parent,dict) else "")
            expected_label=target.get("actor_label") if isinstance(target,dict) else None
            if not expected_label or actual_parent is None or str(
                    actual_parent.get_actor_label())!=expected_label:
                raise NativeCoordinationError("Animated source hierarchy parent not present in Unreal.")
        elif actual_parent is not None:
            raise NativeCoordinationError("Unexpected native skeletal actor attachment.")
        actions=[
            row for row in plan["actions"] if isinstance(row,dict)
            and row.get("entity_name")==character.get("name")
            and row.get("kind")=="skeletal_animation"
        ]
        expected_sections=Counter((
            int(row["start_frame"]),int(row["end_frame"]),
            str(row["unreal_asset_path"]),
        ) for row in actions)
        native_sections=[]
        transform_owner_count=0
        for track in bind.get_tracks():
            kind=_class(track)
            if kind=="MovieScene3DTransformTrack":
                transform_owner_count+=1
            if kind!="MovieSceneSkeletalAnimationTrack":
                continue
            for section in track.get_sections():
                params=section.get_editor_property("params")
                clip=params.get_editor_property("animation")
                start=int(section.get_start_frame())
                end=int(section.get_end_frame())
                native_sections.append((start,end,_path(clip)))
        if Counter(native_sections)!=expected_sections:
            raise NativeCoordinationError(
                "Native character animation sections/asset ownership differ from the source plan."
            )
        expected_world_owner=sum(
            row.get("kind")=="transform" and row.get("entity_name")==character["name"]
            for row in plan["actions"] if isinstance(row,dict)
        )
        if transform_owner_count!=expected_world_owner:
            raise NativeCoordinationError(
                "Unexpected or missing native character actor-world trajectory owner."
            )
        results.append({
            "source_entity_id":entity_id,
            "target_actor_label":label,
            "native_sections":len(native_sections),
            "source_sections":len(expected_sections.elements()) if False else sum(
                expected_sections.values()),
            "native_actor_world_track_count":transform_owner_count,
            "native_parent_binding_structurally_verified":True,
            "native_bone_pose_parity_verified":False,
        })
    return {
        "kind":"cutsceneai.studio.native_multi_character_coordination",
        "status":"NATIVE_BINDINGS_AND_SECTION_TIMING_MATCH_ORIGINAL_PLAN",
        "character_count":len(characters),
        "characters":results,
        "native_bone_pose_and_contact_verified":False,
        "reopened_independent_editor_verified":False,
        "rendered_interaction_fidelity_verified":False,
    }
