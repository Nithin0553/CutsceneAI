"""Phase 10.2 — lossless cinematic effects / events capability accounting.

Audio playback, event markers, light intensity, collision geometry and
materials have native building candidates, not evidence of semantic equality.
Unknown shader, VFX, runtime event and physics effects are preserved as explicit
blockers; neither an LLM nor a native receipt can silently turn them into PASS.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

import feature_dispatch


class EffectCoverageError(ValueError):
    """Source family or native action provenance is inconsistent."""


FAMILIES = {
    "lighting": ("light.", "entity.light", "lighting.", "shadow."),
    "shaders_materials": ("shader.", "material.", "texture.", "postprocess."),
    "audio": ("audio.", "sound.", "dialogue.", "music."),
    "vfx": ("vfx.", "particle.", "fluid.", "procedural.", "simulation."),
    "events": ("event.", "signal.", "gameplay.", "interaction."),
    "physics": ("physics.", "collider.", "cloth.", "constraint.", "destruction."),
}
READBACK_GATES = {
    "lighting": ("native_light_binding_and_properties",
                 "time_matched_photometric_and_rendered_comparison"),
    "shaders_materials": ("native_material_graph_and_surface_parameters",
                          "rendered_color_space_and_shading_parity"),
    "audio": ("native_soundwave_binding_and_timing",
              "decoded_waveform_spatial_and_loudness_comparison"),
    "vfx": ("native_effect_identity_and_ownership",
            "time_matched_particle_or_rendered_state"),
    "events": ("explicit_event_schema_and_handler_mapping",
               "native_event_execution_and_gameplay_side_effects"),
    "physics": ("native_collision_shape_and_motion_ownership",
                "time_matched_physical_state_and_contact"),
}
SOURCE_ONLY = "SOURCE_RECORDED_TARGET_BEHAVIOR_UNVERIFIED"
SOURCE_MISSING = "SOURCE_RECORDED_ADAPTER_MISSING"
PLANNED = "NATIVE_ACTION_PLANNED_BEHAVIOR_UNVERIFIED"
LOSSY = "LOSSY_NATIVE_ACTION_NOT_EQUIVALENT"


def _family(semantic: str) -> str | None:
    for category, prefixes in FAMILIES.items():
        if semantic.startswith(prefixes):
            return category
    return None


def audit(csir: Mapping[str,Any], plan: Mapping[str,Any] | None = None) -> dict[str,Any]:
    """Aggregate the repository's actual per-source-occurrence action ledger.

    Never equate an Unreal marker with executed Unity signal reactions, a
    SoundWave with audible parity, or physical collider shape with simulation.
    """
    try:
        ledger = feature_dispatch.audit(csir,plan)
    except (feature_dispatch.FeatureDispatchError,
            ValueError, TypeError, KeyError) as exc:
        raise EffectCoverageError(
            "Cannot reconcile exact CED source features against native actions."
        ) from exc
    if ledger.get("unknown_action_kinds"):
        raise EffectCoverageError("Unregistered native action cannot establish cinematic support.")
    grouped = {domain:[] for domain in FAMILIES}
    for row in ledger["source_occurrences"]:
        semantic = row["ced"]
        family = _family(semantic)
        if family is None:
            continue
        state = row["state"]
        if state in (
                "LOSSY_ACTION_PLANNED_UNVERIFIED",
        ):
            status=LOSSY
        elif state in ("NATIVE_ACTION_PLANNED_UNVERIFIED",
                       "CUSTOM_HANDLER_REGISTERED_UNVERIFIED"):
            status=PLANNED
        elif state in ("SOURCE_RECORDED_ADAPTER_MISSING",
                       "NATIVE_ACTION_HANDLER_MISSING",
                       "REGISTERED_ADAPTER_NOT_EXECUTED"):
            status=SOURCE_MISSING
        else:
            status=SOURCE_ONLY
        grouped[family].append({
            "source_location":row["source_location"],
            "source_semantic":semantic,
            "source_name":row.get("source_name"),
            "source_state":state,
            "conversion_state":status,
            "potential_builder_actions":row["potential_builder_actions"],
            "matching_plan_action_kinds":row["matching_plan_action_kinds"],
            "native_readback_verified":False,
            "source_target_behavior_verified":False,
        })
    reports = []
    for family, rows in grouped.items():
        counts=Counter(x["conversion_state"] for x in rows)
        reports.append({
            "family":family,
            "source_occurrence_count":len(rows),
            "source_occurrences":rows,
            "states":dict(sorted(counts.items())),
            "required_independent_gates":list(READBACK_GATES[family]),
            "status":(
                "NOT_PRESENT_IN_SOURCE" if not rows
                else "REQUIRES_SOURCE_NATIVE_AND_BEHAVIOR_EVIDENCE"
            ),
            "verified_native_effect_count":0,
            "semantic_equivalence_verified":False,
        })
    all_rows=[r for family in reports for r in family["source_occurrences"]]
    return {
        "kind":"cutsceneai.studio.phase10_2.effects_capability_audit",
        "schema_version":"1",
        "ced_source_occurrence_count":ledger["source_occurrence_count"],
        "effect_source_occurrence_count":len(all_rows),
        "effect_source_occurrences_accounted":len({
            row["source_location"] for row in all_rows
        }),
        "effect_families":reports,
        "native_effects_generation_verified":False,
        "rendered_audio_event_physics_fidelity_verified":False,
        "lossy_action_never_implies_equivalence":True,
        "full_cutscene_fidelity_verified":False,
    }
