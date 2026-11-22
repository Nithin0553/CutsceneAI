# Phase 10.2 — Character facing and calibrated orientation hardening (v0.1)

**Implementation:** `feature/phase10-2-calibrated-facing-guard-v0.1`, stacked on Elements 1–9 and completed Phase 10.1 integration.  
**Testing boundary:** software/synthetic contract regression only; no actual Unity or Unreal Editor has been launched and no general character-facing repair is authorized.

## Why this change was necessary

The earlier anatomical mesh-forward comparator was correctly source/target anatomy-approved and native-observation-based, but its `suggested_target_actor_yaw_correction_degrees` was derived from the *single frame with the largest angular error*. In an animated cutscene that could produce a plausible-looking rotation number even when:

- the mesh orientation error varies over time;
- the problem is an imported mesh or rig pitch/roll mismatch rather than an actor yaw;
- the measured anatomical forward approaches the vertical axis, making horizontal yaw poorly defined;
- only one frame was supplied, so consistency was never demonstrated; or
- source and target timestamps are repeated or out of order.

A standalone suggestion based on any of those conditions risks confusing model diagnosis with a safe native edit. Source and target **world** direction can be measured without knowing which native transform layer owns the mismatch.

## Revised independent policy

`packages/cinetwin/mesh_forward_basis.py::compare_mesh_forward` now:

1. Retains the explicit reviewed source actor-local and target native mesh-local anatomical axes, source/target identity binding, native skeletal component world quaternion, and exact target mesh-asset path requirements.
2. Requires strictly increasing, finite, matching source/target sample times; one uniquely measured source character and one observed native mesh component per sample.
3. Measures three-dimensional anatomical-world-forward error across **every supplied sample**, with quaternion-sign equivalence.
4. Computes a *diagnostic* Unreal yaw candidate only if at least two sampled frames each have a well-defined horizontal projection, the circular yaw differences agree within **0.5°**, and one constant yaw reduces **full three-dimensional direction residual** to the supplied comparator tolerance (normally **2°**).
5. Otherwise emits **no numeric yaw** (`null`) and an explanatory diagnostic status. Source capture's original complete time grid still must be separately verified at the source/target acceptance layer.
6. Always emits `native_actor_yaw_repair_authorized: false`, `suggestion_applied: false`, and `requires_original_full_grid_validation: true`. A constant sampled yaw is **not sufficient** to rotate a native actor: attachment, mesh component basis, authored Sequencer transform tracks, skeletal root ownership, bind pose, operator approval, rollback and a fresh native CineTwin remeasurement remain independent prerequisites.

### Diagnostic statuses

| Status | Meaning | Native permission |
| --- | --- | --- |
| `ALREADY_WITHIN_TOLERANCE` | Approved sampled world-forward comparison passes | No corrective edit |
| `STABLE_SAMPLED_YAW_DIAGNOSTIC_ONLY` | Independently approved axes and a consistent sampled yaw explain the discrepancy | **None**; report the candidate only |
| `INSUFFICIENT_FRAMES_FOR_CONSTANT_YAW` | A single sample cannot establish a constant yaw | None |
| `UNSAFE_NONPLANAR_OR_VERTICAL_FORWARD` | A sampled direction cannot define reliable horizontal yaw | None |
| `UNSAFE_TIME_VARYING_OR_NON_YAW_ORIENTATION` | Frame-to-frame yaw varies or pitch/roll residual cannot be fixed by constant yaw | None |

Element 8's `_recommend` now distinguishes a sole `CHARACTER_MESH_ANATOMICAL_FORWARD_MISMATCH` into the *advisory-only* registered `INSPECT_APPROVED_MESH_ANATOMICAL_FORWARD_BASIS` strategy; mixed calibrated-bone and skeletal-motion errors continue to demand broader retargeting investigation. An LLM may select that exact diagnostic label only through the existing bounded source-occurrence review. It cannot create arbitrary native actor transformations.

## Cross-layer facing ownership diagnosis

`packages/cinetwin/behavior_compare.py` now reports
`facing_ownership_diagnostic` for every independently sampled rig. It
separates measured **actor world quaternion error** from the approved mesh
anatomical-forward error, instead of assuming that a character's actor,
SkeletalMeshComponent, imported FBX axis and skeletal root share one rotation
owner. Its conservative states include:

- `ACTOR_ONLY_ANATOMICAL_MESH_UNMEASURED`: no approved native mesh-forward
  basis; matching actor transforms cannot establish visual facing.
- `ACTOR_ALIGNED_MESH_OR_COMPONENT_BASIS_DIFFERS`: actor world rotation is
  measured within tolerance, but approved anatomical forward differs.
- `ACTOR_ROTATION_DIFFERS_BUT_MESH_FORWARD_MATCHES`: the mesh-forward
  direction matches despite a separate actor world-rotation error; it is
  unsafe to adjust the actor without inspecting ownership.
- `ACTOR_AND_ANATOMICAL_MESH_ORIENTATION_BOTH_DIFFER`: multiple measured
  orientation layers disagree and one global yaw is insufficient evidence.
- `MEASURED_ACTOR_AND_MESH_FORWARD_WITHIN_TOLERANCE`: only the **measured**
  actor and anatomical forward domains match; not full skeletal/rendered parity.

All cases set `native_rotation_owner_isolated: false` and
`native_character_rotation_repair_authorized: false`. The new targeted
Element 8 review is an investigation policy, **not** a new native edit
permission.

## Calibrated joint orientation improvement

`packages/cinetwin/rig_pose_calibration.py::compare_reference_calibrated` additionally requires each sampled source/target pair to be strictly increasing in time, finite, and matched. Repeated frames cannot be counted as a valid independent animation sequence, even when all bone references and quaternions are syntactically well formed. The separate original full-grid and approved bind-reference evidence requirements remain in force.

## Regression and acceptance scope

Synthetic regression tests verify:
- A consistent 90° approved anatomical mesh offset across four turning-character frames is diagnosed as yaw, but never executed.
- Different target yaw offsets on different frames produce no actor yaw candidate.
- Nonplanar (pitch/roll) mismatches cannot be numerically disguised as a yaw fix.
- Vertical directions, insufficient frame count, duplicate/reversed/nonfinite times, missing/foreign/duplicate native mesh evidence fail closed.
- Exact source/target profile identity and anatomical-axis approval, plus quaternion sign equivalence.
- Calibrated skeletal bone orientation grids must be matched and strictly increasing.
- Element 8 permits only the registered, source-bound non-executable anatomy review strategy.

## Remaining Phase 10.2 work

- **Character-facing native repair:** add independently checked actor-vs-mesh-vs-skeletal-root ownership and a registered reversible native operation *only if* isolated behavior is observable across the original complete sequence; no guessed 90/180-degree FBX correction.
- **Multi-character and layered animation:** support only validated, documented combinations and refuse unsupported root-motion/Timeline blends.
- **Animated camera behavior:** investigate source-authored tracking/follow/zoom or multi-cut semantics, then separate native capability coverage from independent CineTwin acceptance.
- **Custom shaders, audio, events and physics:** retain explicit unsupported/incomplete status until both semantic extraction and guarded destination adapters exist.

**Release decision:** This improvement strengthens the evidence/diagnostic algorithm and is **not** proof of calibrated whole-body pose, rendered anatomical facing, or real-editor transfer fidelity. The broader Phase 10.2 objective is still in progress.
