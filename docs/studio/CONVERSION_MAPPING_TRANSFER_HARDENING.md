# Conversion, Mapping and Transfer Algorithms — Hardening Review

**Scope:** Unity CSIR → deterministic Studio planner → verified/unsupported source behavior → Unreal target mapping/preflight. This is a software-only review on `feature/studio-e2e-release-candidate-v0.1`; **no engine execution** or rendered-fidelity acceptance is claimed.

## Reason for the changes

Source identities, animation binding paths and target destinations previously relied on permissive lookup behavior. These failure modes could silently produce a valid-looking but **wrong** transfer plan: last-writer-wins on duplicate source keys; a nested bone's position misinterpreted as an actor's position; duplicate Unreal actor labels misreported as unique mapping candidates; target-side evidence used to satisfy source-side readiness; and two absolute Sequencer transform tracks competing for one actor.

Rather than guess missing input, the pipeline now rejects unsupported/ambiguous cases before native writes.

## New enforced invariants

| Boundary | Enforcement | Primary file |
| --- | --- | --- |
| Source entity and asset identity | Unique nonempty native IDs; duplicate **mapped source names** refuse because the current Studio mapping is name-keyed. Repeated **unmapped** scene names remain legal | `integrations/unreal/csir_plan.py` |
| Target actor binding | A distinct source actor cannot share one target label with another mapped source. Empty/whitespace-only actor labels refuse | `csir_plan.py` |
| Read-only discovery | Two loaded Unreal actors with the same normalized label never count as one unique target candidate; mapping remains an unapplied proposal | `packages/studio/asset_resolver.py` |
| Animation curve ownership | Only root-path Unity animation curves may drive actor/world transforms. Nested bone curves stay available in original CSIR for separate skeletal conversion, never silently overwrite actor keys | `csir_plan._curve_map`, `scene_prep._curve_map` |
| Native Unity Euler channels | Native Euler X/Y/Z share an extractor semantic placeholder but remain **independent native curves**; placeholder duplication is not treated as conflicting actor channels | `csir_plan.py` |
| Root curve conflict | Duplicate canonical root-level curves refuse (not last-writer-wins). RootT displacement is selected using the same root-only scope | `csir_plan.py` |
| Curve evaluation | Source key times strictly increase and values are finite. Unsupported weighted tangents refuse even at endpoints; trimmed source clips explicitly hold the measured/encoded endpoint through clip boundaries | `csir_plan._curve_value`, `_sample_section_transform` |
| Quaternion offsets | Track/infinite/clip rotation offsets cannot be partially specified; synthetic offset quaternions require exactly one source key per component | `csir_plan._quat_offset` |
| Output gate | Explicit target resolution must be a bounded, positive integer pair. Invalid aspect/frame output no longer silently becomes 1920×1080; that default is used only if no resolution was provided | `csir_plan._target_output_profile` |
| Source timing | Positive, finite, bounded duration/rate and frames, before allocating a sequence | `csir_plan.build_plan` |
| Mapping evidence | `source.*` requirements can only come from source project evidence; `target.*` only from destination. Equal-priority rules with different required evidence are ambiguous; different dictionary key orders do not create false conflicts | `packages/readiness/adaptive_mapping.py` |
| Transfer camera output evidence | `transfer.output_resolution` is established only by explicit validated `transfer_context.output_resolution`; neither engine profile can falsely claim transfer-gate readiness | `adaptive_mapping.resolve_dictionary` |
| Prepared Unreal destination | Duplicate prepared actor bindings, native actions targeting a different actor, actions for unknown bound source entities, and a target asset path used for incompatible asset classes refuse before native staging | `integrations/unreal/studio_destination_preflight.py` |
| Native transform ownership | At most one independently planned absolute world/local transform writer per Unreal actor. Other compositions require a verified source-bake/single-owner policy | `packages/studio/transfer_backend.py` |

## Regression coverage

- `tests/studio/test_conversion_mapping_safety.py` — duplicate source entity/asset identity, target binding collision, root vs nested bone transform ownership, malformed source keys, clip trim endpoint holds, invalid source timing, explicit camera output dimensions and incomplete quaternion offsets.
- `tests/studio/test_asset_resolver.py` plus the new duplicate loaded-label invariant.
- `tests/readiness/test_adaptive_mapping.py` — source/target evidence boundary, equal-priority rule identity, transfer output evidence.
- `tests/studio/test_studio_destination_preflight.py` — actor binding and asset-class collisions.
- `tests/studio/test_transfer_backend.py` — independent source transform ownership.
- Existing CineTwin camera, motion, hierarchy, root, readback, native preflight, immutable handoff, security and Windows bootstrap tests remain in the full CI.

## Explicit limitations and future work

- **Source capture vs curve approximation:** Authored Unity curves, retargeted skeletal animation, physics and Timeline blending can require evaluated frame evidence. Rejected or partially supported cases must remain visible as incomplete, not rewritten by a model into invented native keys.
- **Skeletal facing:** A correct Unreal actor orientation does not prove imported FBX mesh local forward axis, bind pose, per-bone orientation or IK retargeted joint equivalence. Calibrated rig basis/axis matching remains unverified.
- **Mapping schema:** Current user-visible actor/asset choices are keyed by source **name**. Unique GUID/asset-ID-keyed mapping should be designed separately before accepting duplicate-named mapped source objects; this review **refuses** them rather than silently conflating them.
- **Native acceptance:** Real Unity extraction/capture, Unreal Editor compile/generate/save/reopen, visual camera framing and held-out cutscene checks must be completed after the authorized software freeze.
- **No independent model output proof:** Mocked provider tests and CI do not demonstrate a live foundation-model decision or perfect source-to-target fidelity.

Do not merge to `main`, declare `SOFTWARE_READY_FOR_ENGINE_TEST` or claim full Unreal native fidelity based on these code-only checks.
