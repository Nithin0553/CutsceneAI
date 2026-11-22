# Phase 10.2 — Guarded Static CineCamera World Yaw (v0.1)

**Status: software implementation and synthetic engine mocks.** No actual Unity
C# compilation, Unreal Editor mutation, editor restart, independent
post-repair CineTwin or rendered camera-facing parity has been verified.

## Scope: exactly one unanimated camera, world yaw only

The eighth narrowly scoped native repair action,
`restore_static_camera_actor_yaw`, is allowed **only** when an independently
reopened Unreal CineTwin full sample grid shows that one source-authored
CineCamera has the correct camera position, unit actor scale, roll, pitch,
physical lens and cut timing, but a **constant Unreal-world yaw** difference
between **2° and 90°**.

This is not a general camera rotation, orbit, pan, tilt, roll, aiming or
keyframe repair. Only the actor's *static base world yaw* changes. There
must be no source-authored camera animation/transform track, no transform
or property compiler action, no current native Sequencer transform/property
track, no parent or attached child object, and no independent camera
component-relative rotation/translation/scale. Missing camera component or
unavailable Unreal Python APIs **deny** the optional repair.

## Evidence source and decision authority

`packages/studio/studio_camera_yaw_evidence.py` derives a proposed
source/target yaw from:

1. The exact current native job, immutable original CSIR, candidate mapping,
   transfer plan and original Unity CineTwin capture through Element 9
   source-bound provenance; no guessed camera labels or model-authored axes.
2. Bounded Element 8 independent per-source-occurrence comparison, a
   separately reopened Element 7 native readback and sampled source/target
   original time grid. Regressed/no-progress/budget-exhausted cases cannot
   repair. The native builder must be independently complete and the
   readback from a separate reopened Unreal editor instance.
3. **Exactly one** mapped original source `entity.camera`, exact original
   source camera occurrence in Element 3's approved workflow, and precisely
   `WORLD_ROTATION_OUTSIDE_TOLERANCE` as the camera's Element 8 measured
   discrepancy. Position, scale, lens and camera cuts must already pass.
4. Matching original source/native sample times, full native mapped camera
   labels, unit quaternions/actor scale, source and native actor positions
   agreeing within **1 cm**, at most **0.1 cm** of position drift and
   **0.2°** of orientation drift across the grid, with **0.25°** maximum
   source/native roll and pitch difference. Near-gimbal pitch above
   **75°** is refused, as are mixed-axis or time-varying corrections.
5. Original source canonical quaternion converted to the target Unreal
   `Rotator(roll,pitch,yaw)` basis via the existing independently tested
   `csir_plan.canonical_quat_to_unreal_rotator` mapping. This is the
   expected yaw **not** a model/user-provided angle.
6. A `camera_yaw_repair_sha256` over exact source occurrence, native
   original rotator, source-derived corrected rotator, exact source
   project/job and Element 7/8 measurement digests.

The source-bound report marks `native_edit_authorized: false` and
`full_cutscene_fidelity_verified: false`. The LangGraph selection may
propose only the pre-registered narrow strategy after explicit current user
feedback such as **“Please fix the camera rotation”**. Requests involving
camera position, lens, cuts, moving/animated cameras, pan/tilt, multiple
objects, blending or any negated/mixed intent cannot borrow the strategy.

The AI does **not** supply a Rotator, coordinate, yaw delta, source actor
path or executable code. Native dispatch sends only the source occurrence
ID, current feedback ID and recomputed proof hash. The shared executor
checks exact project, sequence, level, active job and remaining repair
budget, then creates a **durable write-ahead claim**. Any interrupted
claim blocks native replay.

## Live native mutation and compensating rollback

`integrations/unreal/studio_camera_yaw_repair.py` freshly checks:

- current user feedback ID/kind/job and exact `camera_yaw_repair_sha256`;
- original source-staged CineCamera's **exact native UObject path and label**
  from `studio_auto_scene` staging; reused labels alone do not qualify;
- live actor class `CineCameraActor`, single matching label, no parent or
  attached child, unit scale, original world location and original
  roll/pitch/yaw still matching separately reopened source/native evidence;
- complete native master and binding Sequencer track inventory, rejecting
  transforms, property overrides, Control Rig, time-warp, nested sequences
  and unknown track types;
- `CineCameraComponent` has identity relative translation, scale and
  quaternion; live component world quaternion equals the native actor world
  orientation under the verified Unreal-to-canonical basis.

Only then one `Actor.set_actor_rotation(Rotator(expected_pitch,
source_expected_yaw, expected_roll), teleport=True)` is attempted. The
editor must confirm success and read back actor world rotation, unchanged
world location and scale, and matching CineCameraComponent world basis,
then save the existing level via the Studio native saver.

When the setter changes state and raises, returns failure, produces a
wrong yaw, translates the camera, or fails to save, the original world
rotator **and location** are restored and independently reread. If rollback
cannot be independently observed it raises an explicit error requiring
manual inspection; an interrupted disk save is **not** proof of persisted
rollback across editor restart.

Successful native receipt:
`CAMERA_STATIC_YAW_SAVED_REOPENED_CINETWIN_PENDING`, with
`cinetwin_reopened_time_grid_verified_after_repair: false`,
`rendered_camera_facing_verified: false` and
`full_cutscene_fidelity_verified: false`.
Native in-memory property readback never establishes shot composition.

## Synthetic regression coverage

A 25° native camera yaw difference with matching source placement, roll,
pitch, scale, lens and cuts; source-derived -25° correction; exact
actor/component orientation after edit; no invented AI yaw argument;
stale feedback and proof; wrong staged UObject; duplicated label; wrong
class; attachments; nonidentity relative component transform; wrong
component world basis; stale live rotation, location or scale; native
Sequencer transform/shot/time-warp; source-authored camera animation;
wrong sample times, target camera missing, source/target position or
scale mismatch, rotation drift, roll/pitch drift, near-zero/out-of-range
yaw; setter mutation then exception, refusal, incorrect native readback,
unexpected translation and save interruption; interrupted write-ahead
claim no replay.

These tests use synthetic source and target measurements and mocked Unreal
Python native objects. They do not establish compatibility of actual
Unreal Editor APIs or independent rendered fidelity.

## Remaining

Animated camera rotation curves, moving camera/pan/tilt trajectories,
complex parent rig transforms, blended and nested shots, animated lenses,
post-process effects, audio/VFX/events, moving-character retargeting and
real Unreal/Unity engine acceptance remain separate tasks.

See [Studio release acceptance](RELEASE_ACCEPTANCE.md) and
[Phase 10.2 two-shot switch](PHASE10_2_TWO_SHOT_CAMERA_SWITCH_V01.md).
