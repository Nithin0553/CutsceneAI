# Conversion Issues and Acceptance Milestones

**Snapshot:** 2026-10-27 · **Target:** Unity Timeline → Unreal Engine Level Sequence · **Status:** engineering/research, not a universal production converter.

The items below are **not all implementation bugs**. They distinguish an implemented but unverified capability from a missing subsystem or source/target limitation. Nothing is marked complete merely because a unit test passes. Source `coverage-report.json`, Unreal runtime receipts, saved target readback and independent target behavior observation must be correlated per experiment.

| # | Area | Current evidence / limitation | Objective acceptance check |
| --- | --- | --- | --- |
| 1 | Unreal sequence generation | A prepared plan is not proof that a Level Sequence was created and persisted. | Run in backed-up Unreal, inspect `GENERATED_UNVERIFIED`, save approved target, reopen and read back real sequence. |
| 2 | Asset mapping | Compatible target meshes/animations/audio and manually curated mappings still required. | Inventory imported assets, verify type and identity; demonstrate automatic resolution with ambiguous cases blocking safely. |
| 3 | Character positioning | Placement and displayed character position can diverge. | Measure source/target actor and root-bone world positions at matched timestamps. |
| 4 | Root motion | Source and target skeletal motion carriers may differ. | Report source/target trajectory errors by actor, component and root bone across full playback. |
| 5 | Skeletal retargeting | No general bone/rig retargeter exists. | Transfer a source clip across independently rigged characters; verify normalized poses/bone correspondences. |
| 6 | Animation blending | Sequencer eases implemented for some clips; in-engine equivalence unknown. | Compare bone trajectories and blend transitions at overlap boundaries. |
| 7 | Animation curves | Weighted Unity tangents and overlapping transform blending incomplete. | Validate keyed Hermite/weighted curves and overlapping clip interpolation against independent source samples. |
| 8 | Parent–child relationships | Parent-local CineTwin conversion added in Python; no accepted Unreal validation. | Verify attached parent identity and sampled child world trajectory at multiple times. |
| 9 | Hierarchy persistence | Previous persistence tests exist, new V5 hierarchy needs reconfirmation. | Save/reopen test level and verify attachment, mobility, and source-relative motion. |
| 10 | Camera positioning | Initial/moving camera parity not fully measured. | Capture matched world poses and verify actor/component camera motion. |
| 11 | Camera optics | Vertical FOV conversion exists, but composition may differ. | Compare output resolution/aspect, filmback or projection and image-space reference landmarks. |
| 12 | Lighting | Intensity-transfer prototype; shadows/appearance not measured. | Compare supported source photometric parameters and rendered results under controlled exposure. |
| 13 | Audio | Sequencer audio/fade representation exists; playback not waveform-verified. | Capture target waveform/timing, assess fades and mixing against source. |
| 14 | Events and signals | Unity signal identities are preserved as markers, not executable payloads. | Provide explicit event mapping then independently demonstrate target callbacks/payload effects. |
| 15 | Scene hierarchy mapping | Earlier CineTwin inspection reported 21 unmapped source entities. | Re-inventory source nodes and resolve or explicitly report every required mapping with no silent omission. |
| 16 | Playback timing | Unreal exclusive end at exactly 12 s remains an acceptance boundary. | Verify all in-range frames and classify exact end as distinct endpoint behavior, not false parity. |
| 17 | Materials/rendering | Different shaders, lighting, sky and exposure can change images. | Verify imported/material mapping and compare controlled rendered frames; log unsupported effects. |
| 18 | Physics/constraints | Dynamic constraints, sockets and reparenting not generally transferable. | Establish capabilities by feature and independently validate supported simulated trajectories. |
| 19 | Transfer validation | Full pose/camera/audio/event/pixel parity not established. | Produce complete, reproducible, independent per-feature readback with PASS/FAIL/INCOMPLETE. |
| 20 | Generalization | No multi-project unseen-cutscene proof. | Evaluate multiple independent projects, with held-out whole-project test cases and no benchmark hardcoding. |

## Milestone gates

| Milestone | Prerequisite | Output |
| --- | --- | --- |
| M1 — Reliable generation | Issues 1, 2, 8, 9 | New generated and saved Unreal sequence, source/target binding report, recorded losses |
| M2 — Spatial and time parity | Issues 3, 4, 6, 7, 10, 16 | Sampled motion/timing error report across the full timeline |
| M3 — Rich semantics | Issues 5, 11–15, 17, 18 | Explicit supported/partial/blocked behavior with per-feature validation |
| M4 — Research evaluation | Issues 19, 20 | Reproducible benchmark suite and statistically honest unseen-project results |

## Acceptance vocabulary

- **PLANNED**: source was analyzed and target actions were calculated; **no engine generation**.
- **GENERATED_UNVERIFIED**: the engine builder produced a sequence; persistence/fidelity still unproven.
- **SAVED_READBACK**: loaded the saved target and extracted independent native information.
- **PASS / FAIL / INCOMPLETE**: result of an evidence-backed validation gate, not a GUI appearance or planning test.
- **NATIVE_UNVERIFIED / BAKED_PARTIAL / SKIPPED**: per-source-track transfer coverage labels, **not final acceptance**.

## Working policy

Implement reusable CED/CSIR/adapter behavior rather than benchmark-specific patches. Do not relabel unknown shader/script/audio behavior as transferred. Keep freezes in `docs/benchmarks/` intact and store measurements per experiment with source and target fingerprints.
