"""Read-only native Unreal Level Sequence camera-cut binding and timing audit."""
from __future__ import annotations

from typing import Any

MAX_NATIVE_CUTS = 10000


def inspect(sequence: Any, api: Any) -> dict[str, Any]:
    """Inspect actual saved Sequencer tracks; never infer success from a plan.

    Incompatible Unreal Python capabilities yield explicit UNAVAILABLE instead
    of guessing which camera is active. No world/asset mutation or saves.
    """
    extensions = getattr(api, "MovieSceneSequenceExtensions", None)
    section_extensions = getattr(api, "MovieSceneSectionExtensions", None)
    track_type = getattr(api, "MovieSceneCameraCutTrack", None)
    editor_type = getattr(api, "UnrealEditorSubsystem", None)
    required = (
        (extensions, "get_master_tracks"),
        (extensions, "get_bindings"),
        (extensions, "get_binding_id"),
        (extensions, "locate_bound_objects"),
        (section_extensions, "get_start_frame"),
        (section_extensions, "get_end_frame"),
    )
    if (track_type is None or editor_type is None
            or any(not callable(getattr(container, name, None))
                   for container, name in required)):
        return {"status": "UNAVAILABLE", "reason": "NATIVE_SEQUENCER_CUT_API_UNVERIFIED"}
    try:
        tracks = [track for track in extensions.get_master_tracks(sequence)
                  if isinstance(track, track_type)]
        if len(tracks) > 1:
            return {"status": "UNAVAILABLE", "reason": "MULTIPLE_NATIVE_CAMERA_CUT_TRACKS"}
        if not tracks:
            return {"status": "OBSERVED", "binding_provenance": "NATIVE_SEQUENCE_CAMERA_BINDING_ID",
                    "sections": []}
        sections = list(tracks[0].get_sections())
        if len(sections) > MAX_NATIVE_CUTS:
            return {"status": "UNAVAILABLE", "reason": "EXCESSIVE_NATIVE_CAMERA_CUT_SECTIONS"}
        world = api.get_editor_subsystem(editor_type).get_editor_world()
        native_bindings = []
        for binding in extensions.get_bindings(sequence):
            owners = list(extensions.locate_bound_objects(sequence, binding, world))
            if len(owners) != 1:
                continue
            label = getattr(owners[0], "get_actor_label", None)
            if not callable(label):
                continue
            native_bindings.append((extensions.get_binding_id(sequence, binding), str(label())))
        result = []
        for section in sections:
            get_camera = getattr(section, "get_camera_binding_id", None)
            if not callable(get_camera):
                return {"status": "UNAVAILABLE", "reason": "CAMERA_CUT_BINDING_READBACK_MISSING"}
            section_id = get_camera()
            matches = [label for native_id, label in native_bindings if native_id == section_id]
            if len(matches) != 1 or not matches[0]:
                return {"status": "UNAVAILABLE", "reason": "CAMERA_CUT_NATIVE_BINDING_UNRESOLVED"}
            start_native = section_extensions.get_start_frame(section)
            end_native = section_extensions.get_end_frame(section)
            if (isinstance(start_native, (bool, float))
                    or isinstance(end_native, (bool, float))):
                return {"status": "UNAVAILABLE", "reason": "CAMERA_CUT_NATIVE_RANGE_UNVERIFIED"}
            # UE Python exposes FFrameNumber as a native value type, not
            # necessarily Python int. Use its integer frame value explicitly.
            first = int(getattr(start_native, "value", start_native))
            last = int(getattr(end_native, "value", end_native))
            if first < 0 or last <= first:
                return {"status": "UNAVAILABLE", "reason": "CAMERA_CUT_NATIVE_RANGE_UNVERIFIED"}
            result.append({
                "actor_label": matches[0],
                "start_frame": first,
                "end_frame": last,
            })
        return {
            "status": "OBSERVED",
            "binding_provenance": "NATIVE_SEQUENCE_CAMERA_BINDING_ID",
            "sections": sorted(result, key=lambda item: (
                item["start_frame"], item["end_frame"], item["actor_label"]
            )),
        }
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return {"status": "UNAVAILABLE", "reason": "NATIVE_CAMERA_CUT_INSPECTION_FAILED"}
