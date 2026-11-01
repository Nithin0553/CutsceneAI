"""Opt-in visual-only adapter: Unity ActivationTrack -> Unreal VisibilityTrack.

A GameObject's active state controls scripts, physics and other behaviors,
while Unreal's visibility flag only controls rendering. This adapter is an
explicit partial fallback, NEVER semantic activation parity. It refuses
malformed/unproven ActivationClip source data before native mutation.
"""
from __future__ import annotations

from typing import Any

import csir_plan


class VisualActivationError(ValueError):
    pass


def build_action(csir: dict[str, Any], mapping: dict[str, Any],
                 track: dict[str, Any]) -> dict[str, Any]:
    if track.get("ced_type") != "event.state":
        raise VisualActivationError("Expected a Unity ActivationTrack event.state.")
    entities = {str(e.get("entity_id")): e for e in csir.get("entities", [])}
    entity = entities.get(str(track.get("binding_entity_id")))
    if entity is None:
        raise VisualActivationError("ActivationTrack source actor binding is missing.")
    name = str(entity.get("name") or "")
    target = mapping.get("entities", {}).get(name)
    if not isinstance(target, dict) or not target.get("actor_label"):
        raise VisualActivationError("No target actor mapping for ActivationTrack: " + name)
    sections = track.get("sections")
    if not isinstance(sections, list) or not sections:
        raise VisualActivationError("ActivationTrack has no authored source clips.")
    native = str((track.get("metadata") or {}).get("native_type") or "")
    if native and "ActivationTrack" not in native:
        raise VisualActivationError("Source track is not a native Unity ActivationTrack.")
    timing = csir.get("timing") or {}
    rate = timing.get("display_rate") or timing.get("source_rate") or {}
    try:
        n, d = int(rate["numerator"]), int(rate["denominator"])
        duration = float(csir_plan.rational_seconds(timing["playback_end"]))
    except (TypeError, KeyError, ValueError, ZeroDivisionError) as exc:
        raise VisualActivationError("Unity source rate/playback bounds are unavailable.") from exc
    if n <= 0 or d <= 0 or duration <= 0.0:
        raise VisualActivationError("Invalid positive source timing contract.")
    max_frame = csir_plan.seconds_to_frame(duration, n, d)
    intervals = []
    post_states = set()
    for section in sections:
        activation = (section.get("payload") or {}).get("activation") or {}
        post = str(activation.get("post_playback_state") or "")
        if activation.get("active") is not True or post not in {
            "Active", "Inactive", "Revert", "LeaveAsIs",
        }:
            raise VisualActivationError(
                "ActivationClip active/post-state data is missing or ambiguous."
            )
        post_states.add(post)
        try:
            start = csir_plan.seconds_to_frame(
                csir_plan.rational_seconds(section["start"]), n, d)
            end = csir_plan.seconds_to_frame(
                csir_plan.rational_seconds(section["end"]), n, d)
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
            raise VisualActivationError("Invalid ActivationClip timing.") from exc
        if start < 0 or end > max_frame or end <= start:
            raise VisualActivationError("Invalid or out-of-range ActivationClip frames.")
        intervals.append((start, end))
    if len(post_states) != 1:
        raise VisualActivationError("Multiple conflicting ActivationTrack post states.")
    intervals.sort()
    merged: list[list[int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    # Visually active during clips, hidden between them. The end frame may
    # be outside Sequencer's evaluated playback range and is not a proof of
    # Unity's postPlaybackState runtime game-object semantics.
    keys = [{"frame": 0, "hidden": True}]
    for start, end in merged:
        keys.append({"frame": start, "hidden": False})
        keys.append({"frame": end, "hidden": True})
    by_frame: dict[int, bool] = {}
    for row in keys:
        by_frame[int(row["frame"])] = bool(row["hidden"])
    return {
        "kind": "actor_visibility", "entity_name": name,
        "actor_label": str(target["actor_label"]),
        "track_name": str(track.get("name") or ""),
        "keys": [{"frame": frame, "hidden": by_frame[frame]}
                 for frame in sorted(by_frame)],
        "source_ced": "event.state",
        "source_post_playback_state": next(iter(post_states)),
        "source_behavior_strategy": "visual_visibility_approximation",
        "fidelity_status": "RENDER_ONLY_PARTIAL_UNVERIFIED",
        "semantic_losses": [
            "Unity GameObject activation enables/disables scripts and component behavior.",
            "Collision, physics, input and scripted callbacks are not transferred.",
            "Unity ActivationTrack post-playback state is not semantically reproduced.",
        ],
    }
