"""Tick-synchronized CineTwin Unreal behavior probe (non-mutating).

Why this exists: ordinary Python calls run without advancing the Editor's tick.
Sequencer can move actor transforms immediately but skeletal pose evaluation may
be deferred to later Editor ticks. A single synchronous loop may record stale
bone poses for all 298 times, leading to false transfer-error diagnoses.

This probe deliberately captures after real Editor ticks. The first run should
use a handful of source-authored times before attempting a full recording.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unreal

HERE = Path(__file__).resolve().parent
for directory in (HERE, HERE.parents[1] / "packages" / "cinetwin"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import cinetwin_target_evaluator as base
import target_observation_plan
from tick_probe_quality import TickObservationError, choose_times, max_bone_motion_m

_ACTIVE: "_TickSession | None" = None


class _TickSession:
    def __init__(
        self,
        plan: dict[str, Any],
        mapping: dict[str, Any],
        sequence_path: str,
        output_path: str,
        times: list[float],
        ticks_per_sample: int,
    ) -> None:
        if ticks_per_sample < 2 or ticks_per_sample > 10:
            raise TickObservationError("Use 2 to 10 real editor ticks per timestamp.")
        self.plan = plan
        self.request = target_observation_plan.prepare_observation(plan, mapping)
        self.times = times
        self.output_path = Path(output_path)
        self.ticks_per_sample = ticks_per_sample
        self.samples: list[dict[str, Any]] = []
        self.index = 0
        self.wait_ticks = ticks_per_sample
        self.handle = None
        self.closed = False
        self.library = base._sequencer_api()
        self.sequence = unreal.load_asset(sequence_path)
        if self.sequence is None or not isinstance(self.sequence, unreal.LevelSequence):
            raise TickObservationError("Cannot load Level Sequence " + sequence_path)
        self.previous_sequence = self.library.get_current_level_sequence()
        self.previous_position = (
            self.library.get_global_position()
            if self.previous_sequence is not None
            else None
        )
        self.switched = (
            self.previous_sequence is None
            or self.previous_sequence.get_path_name() != self.sequence.get_path_name()
        )
        if self.switched:
            self.library.open_level_sequence(self.sequence)
        try:
            active = self.library.get_current_level_sequence()
            if active is None or active.get_path_name() != self.sequence.get_path_name():
                raise TickObservationError(
                    "Requested Level Sequence is not open in Unreal Sequencer."
                )
            self.actors = base._find_actors(self.request["bound"])
            self.components = {
                entry["entity_id"]: base._skeletal_component(
                    self.actors[entry["entity_id"]]
                )
                for entry in self.request["skeletal_rigs"]
            }
            self.rigs = [
                base._rig_structure(self.components[entry["entity_id"]],
                                    entry["entity_id"])
                for entry in self.request["skeletal_rigs"]
            ]
            self.rig_bones = {
                item["entity_id"]: [
                    b["bone_name"] for b in item["native_target_bones"]
                ]
                for item in self.rigs
            }
            self.initial_component_properties = {
                rig_id: {
                    "update_animation_in_editor": str(
                        component.get_editor_property("update_animation_in_editor")
                    ),
                    "pause_anims": str(component.get_editor_property("pause_anims")),
                    "no_skeleton_update": str(
                        component.get_editor_property("no_skeleton_update")
                    ),
                }
                for rig_id, component in self.components.items()
            }
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        try:
            if self.switched and self.previous_sequence is not None:
                self.library.open_level_sequence(self.previous_sequence)
            elif self.switched:
                self.library.close_level_sequence()
            if self.previous_position is not None:
                self.library.set_global_position(
                    self.previous_position, unreal.MovieSceneTimeUnit.DISPLAY_RATE
                )
                self.library.force_update()
        except Exception as error:
            unreal.log_warning("[CineTwin] Could not restore playhead: " + str(error))

    def begin(self) -> dict[str, Any]:
        # First seek is before callback registration, so the following editor
        # ticks can update animation before we read its pose.
        base._seek(self.library, self.times[0])
        self.handle = unreal.register_slate_post_tick_callback(self._tick)
        unreal.log(
            "[CineTwin] Tick-synchronized capture STARTED: "
            f"{len(self.times)} times, {len(self.rigs)} skeletal rigs. "
            "Wait for the SAVED or FAILED message before proceeding."
        )
        return {"status": "STARTED", "samples_requested": len(self.times)}

    def _sample(self, time_seconds: float) -> None:
        entities = [
            {
                "entity_id": entry["entity_id"],
                "actor_label": entry["actor_label"],
                "world_transform": base._actor_transform(
                    self.actors[entry["entity_id"]]
                ),
            }
            for entry in self.request["bound"]
        ]
        poses = [
            {
                "entity_id": rig_id,
                "bones": [
                    base._bone_state(self.components[rig_id], bone_name)
                    for bone_name in names
                ],
            }
            for rig_id, names in self.rig_bones.items()
        ]
        self.samples.append({
            "time_seconds": time_seconds,
            "entities": entities,
            "skeletal_poses": poses,
            # Diagnostic only. Editor API reports playhead as a playback-params
            # struct; its representation differs across Unreal versions.
            "editor_playhead": str(self.library.get_global_position()),
        })

    def _finish(self) -> None:
        full = (
            len(self.samples) == len(self.plan["samples"])
            and [item["time_seconds"] for item in self.samples] ==
                [item["time_seconds"] for item in self.plan["samples"]]
        )
        rig_evidence = []
        warnings = []
        for rig in self.rigs:
            rig_id = rig["entity_id"]
            movement = max_bone_motion_m(self.samples, rig_id)
            if movement < 0.0001:
                warnings.append(
                    "NO_BONE_MOTION_OBSERVED: " + rig_id
                    + " — distinguish genuine static pose from stale editor evaluation."
                )
            rig_evidence.append({
                "entity_id": rig_id,
                "maximum_target_bone_displacement_cm": round(movement * 100.0, 6),
                "editor_animation_settings": self.initial_component_properties[rig_id],
            })

        capture = {
            "schema_version": "0.1.0",
            "kind": "cinetwin.target_behavior_observation",
            "cutscene_id": self.request["cutscene_id"],
            "source": self.request["source"],
            "target": {
                "engine": "unreal",
                "engine_version": unreal.SystemLibrary.get_engine_version(),
                "sequence_asset_path": self.sequence.get_path_name(),
            },
            "coverage": {
                "sample_count": len(self.samples),
                "full_sample_count": self.request["full_sample_count"],
                "mapped_entity_count": len(self.request["bound"]),
                "source_entity_count": len(self.plan["entities"]),
                "unmapped_source_entities": self.request["missing"],
                "skeletal_rig_count": len(self.rigs),
                "full_temporal_coverage": full,
                "pose_semantic_comparison": "NOT_IMPLEMENTED_REQUIRES_BONE_MAPPING",
            },
            "native_rigs": self.rigs,
            "samples": self.samples,
            "quality": {
                "method": "slate_post_tick_between_sequencer_seeks",
                "ticks_per_sample": self.ticks_per_sample,
                "rig_evidence": rig_evidence,
                "warnings": warnings,
                "status": "SUSPECT" if warnings else "OBSERVED_NOT_YET_PROVEN",
            },
            "provenance": {
                "method": "sequencer_jump_editor_ticks_then_capture",
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "asset_mutation": False,
            },
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(capture, indent=2), encoding="utf-8")
        unreal.log(
            "[CineTwin] Tick-synchronized observations SAVED: "
            f"{self.output_path} (samples={len(self.samples)}, "
            f"mapped_actors={len(self.request['bound'])}, "
            f"skeletal_rigs={len(self.rigs)}, "
            f"quality={capture['quality']['status']})"
        )
        for item in rig_evidence:
            unreal.log(
                f"[CineTwin] {item['entity_id']}: "
                f"target_bone_motion={item['maximum_target_bone_displacement_cm']:.6f} cm"
            )
        for warning in warnings:
            unreal.log_warning("[CineTwin] " + warning)

    def _tick(self, _delta_time: float) -> None:
        global _ACTIVE
        try:
            if self.closed:
                return
            self.wait_ticks -= 1
            if self.wait_ticks > 0:
                return
            self._sample(self.times[self.index])
            self.index += 1
            if self.index == len(self.times):
                self._finish()
                self.close()
                _ACTIVE = None
                return
            base._seek(self.library, self.times[self.index])
            self.wait_ticks = self.ticks_per_sample
        except Exception as error:
            unreal.log_error("[CineTwin] Tick capture FAILED: " + repr(error))
            self.close()
            _ACTIVE = None


def start(
    plan_path: str,
    mapping_path: str,
    sequence_path: str,
    output_path: str,
    *,
    probe_times: tuple[float, ...] | None = (0.0, 0.75, 1.5, 2.25, 3.0),
    ticks_per_sample: int = 3,
) -> dict[str, Any]:
    """Start a background-in-editor sampling session. No blocking Python loop.

    This runs only while the Unreal Editor is alive and ticking, NOT as a
    scheduled external background job. Do not close the editor mid-capture.
    """
    global _ACTIVE
    if _ACTIVE is not None:
        raise TickObservationError(
            "Another CineTwin tick capture is active. Finish or stop it first."
        )
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8-sig"))
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8-sig"))
    if plan.get("kind") != "cinetwin.sampling_plan":
        raise TickObservationError("Wrong or invalid CineTwin sampling plan.")
    times = choose_times(plan, probe_times)
    session = _TickSession(
        plan, mapping, sequence_path, output_path, times, ticks_per_sample
    )
    _ACTIVE = session
    try:
        return session.begin()
    except Exception:
        session.close()
        _ACTIVE = None
        raise


def stop() -> None:
    """Manually cancel an in-editor recording and restore Sequencer state."""
    global _ACTIVE
    if _ACTIVE is not None:
        _ACTIVE.close()
        _ACTIVE = None
        unreal.log("[CineTwin] Tick-synchronized capture CANCELLED.")
