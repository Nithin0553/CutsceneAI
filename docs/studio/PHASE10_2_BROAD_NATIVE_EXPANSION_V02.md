# Phase 10.2 — Broad Native Expansion and Acceptance Boundary (v0.2)

**Baseline:** consolidated software merge `4cdb6ac5cab3c7d148208f94826494e52a050dc0`, Phase 10.2 seven-area integration PR #149.

**Purpose:** implement substantial native Unreal execution and CineTwin verification surfaces in **one** follow-on PR. No real engine was launched by this repository/CI effort. "Implemented source-bound path" is not the same as "tested in a user Unity and Unreal installation." This branch must not replace unverified semantics with invented animation.

## Actual code changes by original seven work areas

| Area | New implementation | Explicit remaining limitation |
| --- | --- | --- |
| 1. Animated camera | `studio_camera_rotation_curve.py` source-verified key-grid compiler handles approved bounded existing roll/pitch/yaw camera keys, and `realize_from_original` rechecks the exact staged CineCamera UObject/Sequencer owner before any edit; checks independently captured quaternions against prepared source, validates all nine exact native channels/interpolation, saves edited sequence and compensates rollback on failure. Existing one/two/multi-key yaw and position adapters unchanged. | Only exclusive, absolute, measured one-camera key ownership. Imported rigs, wrapped/singular rotations, arbitrary tangents, spline interpolation, new/deleted keys and rendered in-between parity remain unavailable. The new direct adapter does not join the autonomous AI allowlist. |
| 2. Timeline | `studio_native_shot_tracks.py` authors approved, exact consecutive source-identified nested cinematic-shot references in a native parent Level Sequence. Refuses missing child sequences, competing master tracks, timewarp, weighted mixer, gaps or overlaps; reads back native sequence bindings and section frames; requires confirmed save or rollback. | Does not synthesize arbitrary Unity mixer/Playables, multi-layer nested timewarp, shot crossfades, variable-speed curves or rendered camera transitions. |
| 3. Moving-character | `root_motion_calibration_6dof.py` solves per-frame 3D world actor location and quaternion facing from independently measured Unity world root and native actor-local root, requires approved skeleton rest/bone axes and exclusive animation ownership. Native builder supports its absolute nine-channel actor transform track. | Must be connected through an explicitly approved source/native immutable plan; actual native clip root isolation, IK/skin, reopened motion/facing must be observed in an editor. No arbitrary automatic motion repair. |
| 4. Skeletal retarget | `studio_ik_retarget.py` now uses UE 5.8 typed `IKRetargetBatchOperationInputs` / `run_batch_retarget` when available, with compatible legacy fallback, exact output asset/skeleton readback and save confirmation. Retains required approved authored rigs and independent reference pose. | Does not auto-design source/target IK rig chains, convert arbitrary vendor rigs, or claim skinned-vertex deformation equivalence. |
| 5. Multi-character | `studio_multi_character_native.py` checks exact mapped native Sequencer actor binding, per-character animation clip/range, actor transform ownership and actor parent attachment. Reopened Unreal acceptance now collects `native-multi-character-coordination.json` and binds its SHA in comparison. | Native structural checks cannot establish animated attachment world-offset fidelity, two-character contacts, root-motion/IK interactions or rendered choreography. |
| 6. Lighting / shader / audio / VFX / event / physics | `phase10_2_effect_comparison.py` compares independently provided source/native frame-aligned property/audio-sample statistics, particle and collision state, discrete events, and material/lighting properties per exact source ID. Missing, foreign or mismatched domains fail. Existing native constant PBR/light/audio/collider actions retained. | No automatic proprietary shader graph/HLSL rewriting, custom Niagara/Unity GPU-VFX translation, middleware audio synthesis, script execution conversion or deterministic physics solver replacement. Typed numeric comparison is **not** final render/audio/physical equivalence. |
| 7. Production acceptance | `phase10_2_engine_acceptance_suite.py` checks complete seven-domain native evidence roster, SHA256 paths and existing independent six-case engine acceptance matrix (distinct Unreal Editor PID/held-out project). `tools/phase10_2_engine_acceptance.py` writes a one-time, review-only report. | Actual Unity/Unreal execution, independent process reopening, source/target rendered frame/audio recordings, skinned-mesh/physics comparisons and human review must run on an engine-equipped workstation before any full acceptance. |

## Execution and separate evidence gates

- All direct native writes require existing source identity, user-approved asset
  names and no competing owners. They cannot be invoked by LLM-generated commands
  or arbitrary untrusted project metadata.
- A direct adapter may report **native save and immediate key/section readback**,
  not native project persistence after restart. An interrupted or partially
  saved native operation must not replay blindly.
- The master builder's Level Sequence save must explicitly return `True`.
- The real reopened Editor's native acceptance callback attempts independent
  multi-character binding/attachment inspection; failures remain explicit
  incomplete receipts rather than silently successful transfer.
- The seven-domain acceptance suite composes the pre-existing six native
  scenarios with all seven area-specific evidence files. Because a JSON file
  can be created synthetically, the suite deliberately returns
  `acceptance_complete: false` pending independent editor/reviewer confirmation.

## Required workstation acceptance

1. Compile/install the Unity bridge, extract a cutscene with mixed cameras,
   Timeline, multi-character animation, effects and project metadata.
2. Run the approved Unreal native operation in a clean staged target project.
   Inspect actor, rig, child-sequence, material, audio and VFX assets in the
   **actual Unreal Editor**, not a Python mock.
3. Save and close that Unreal Editor; reopen the generated level in a **different
   process**, record fully matched CineTwin frames, native binding/property
   evidence and source-equivalent audio/event/physics traces.
4. Compare held-out source projects, camera shots (including transitions),
   actor/world skeletal roots and skinned vertices, interactions, source-specific
   material/light/VFX visuals and sound output.
5. Assemble all seven area-specific evidence files plus the existing baseline
   engine acceptance matrix; run:

```sh
python tools/phase10_2_engine_acceptance.py --workspace /studio/runs \
  --manifest /studio/runs/phase10_2-acceptance.json \
  --output /studio/runs/phase10_2-engine-review.json
```

6. Independently inspect Unity and Unreal logs, artifacts, renderer output and
   held-out scene provenance. Do not record workstreams as complete until every
   required native and behavioral acceptance criterion passes.

## What this PR does NOT establish

**Phase 10.2 is not fully accepted or universally complete.** A software
implementation cannot demonstrate arbitrary custom shader/VFX script/physics
equivalence without the original project assets, approved mapping code and
independent target engine behavior. CI and synthetic mocks verify source
contracts and code failure behavior only. The seven-area native performance
and fidelity proof is expressly deferred until engine-equipped verification;
this is a genuine limitation rather than a silently skipped feature.

This work does not modify the release candidate or `main` directly.
