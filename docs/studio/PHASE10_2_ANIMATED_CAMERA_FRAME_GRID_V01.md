# Phase 10.2 — Animated CineCamera Source-Frame Conversion Contract (v0.1)

**Status:** Software-only native planning, preflight and synthetic regression
coverage. No actual Unity Editor capture, Unreal Editor Sequencer writing,
post-save reopen, independently evaluated CineTwin target motion or rendered
camera continuity has been verified in this increment.

## Why this is not a ninth autonomous repair

The Studio **already** compiles Unity `camera.transform` into Unreal
`MovieScene3DTransformTrack` and can substitute exact Unity **evaluated
CineTwin camera world transforms** when an original capture exists. The
previous weaknesses were in source authority and motion semantics, **before**
Element 8 or any native repair agent should make corrections:

- Sparse camera position/rotation keys were previously passed to Unreal
  without guaranteed source interpolation between the keys. The target
  could use different tangents/interpolation without a source-level proof.
- Unrelated or nested curves could be ignored, a nonempty camera transform
  clip could reuse an invented zero-origin camera for unauthored axes, and
  multiple camera transform tracks or separated clips could compete.
- Authored clips with adjacent frame boundaries could overwrite the same
  native frame or bridge unknown Timeline gaps, even if the source has
  explicit blend/ease/parent-motion semantics.
- The native writer did not require the entire **nine-channel**
  Location/Rotation/Scale contract or initialize camera scale channels.
- Most importantly, demanding a locally valid camera transform before
  using separately captured **evaluated Unity world poses** would improperly
  reject the actual authoritative source when local parent/clip baselines
  were incomplete.

Instead of adding an unrestricted animated-camera "repair", this phase
hardens native source reconstruction and keeps autonomous post-edit camera
animation changes **report-only** pending a separately proven inverse
writer and independently reopened target grid.

## Source authority, in order

### A. Original, verified Unity CineTwin capture (preferred)

For a mapped `camera.transform` track **with original authenticated capture**,
the independent source evaluator supplies `_world_keys` on **every display
frame**, through the original exclusive playback-end boundary. The existing
`verified_cinetwin_camera_world_pose` transfer action remains authoritative
even when native/local authored curves have no safe world origin or parent
calibration. It is emitted **without first requiring** speculative local
camera conversion. Observed source FOV values are independently baked into
a separate camera-lens action at each available frame (including camera
tracks with zero or unknown directly exported FOV curves).

The target action remains `BAKED_PARTIAL` in the source-track ledger.
Evaluated Unity source motion is strong **source evidence**, not proof of
target Unreal motion or rendered shot equivalence.

### B. Only original local curves, no validated source capture

`csir_plan._sample_section_transform(..., camera_frame_bake=True)` now
samples exactly one native transform key **per source display frame** within
every frame-aligned clip, including its terminal frame. Original legacy
linear curves and supported unweighted Unity Hermite curves are **evaluated
at those actual timestamps**, including source-offset/time-scale clipping.
Off-grid source keys remain evaluator inputs; they are **not separately
rounded** into colliding native frames. Each source key becomes a linear
Unreal channel key, not an auto-tangent guess. Quaternions are canonicalized
into Unreal roll/pitch/yaw using existing tested Unity-to-Unreal basis math,
then equivalent Euler representations are made continuous across clip seams.

Safe local authoring is deliberately limited:

- One active camera-transform track per source camera, frame-aligned
  boundaries, no section overlap, no temporal gaps or discontinuous shared
  clip poses, and no unknown camera source-owner curves.
- Original `track_offset`, `clip_offset` and `infinite_offset` values
  must each be static. Nested camera/rig curves, duplicate Euler axes,
  conflicting quaternion/Euler owners, incomplete quaternion axes and
  weighted tangents are rejected rather than silently discarded.
- Unity Timeline clip easing/blending and any animated ancestor/parent
  source-track owner require a **verified evaluated CineTwin capture**.
- If a camera animates only rotation, the unauthored position axes come
  from the original static source world transform. If it animates only
  position, its original static source orientation is preserved. No
  missing world baseline is replaced with an invented origin.
- Parented cameras with unauthored local channels cannot borrow a
  **world-space** metadata pose as though it were a local transform.
- A source camera with no verified world baseline and only partial
  position/rotation curves is reported `SKIPPED`/incomplete by the Studio
  transfer ledger rather than converted into an incorrectly positioned
  native camera.

This scope supports only **sampled source display-frame behavior**; values
between frames, per-pixel framing, depth of field, motion blur, and
multi-rig camera interpolation still require native editor verification.

## Native preflight and execution

New `integrations/unreal/studio_camera_motion_contract.py` validates
both the exact source-local strategy
`source_frame_baked_camera_transform_v1` and the existing
`verified_cinetwin_camera_world_pose` source-capture strategy.

Validation checks the original action's source identity, bounded
finite world positions/rotations, consecutive unique frame indices,
frame count, clip bounds and full grid; camera turns faster than
150° per display frame are blocked rather than hiding temporal aliasing.
For captured world motion, the target grid must cover frame zero through
the native playback-end frame. For locally baked source clips, the
original clip's exact frame bounds and one sample per intervening frame
are verified. Mixed/duplicate action owners are rejected before
native mutation.

`build_level_sequence._preflight` now calls this validator **before
moving actors or creating assets**, and checks required native
absolute-transform and linear-key capabilities. During camera
realization, `_add_transform` requires **exactly nine native editable
channels**: XYZ Location, Roll/Pitch/Yaw Rotation, XYZ Scale. It
activates the source-controlled section, selects absolute blending,
initializes all three scale channels to **1.0**, and emits source
frame samples as linear keys.

The existing source-bound plan preparation, identity hashes, target
asset no-overwrite protections and native sequence ownership remain
in effect; no model-authored coordinate or arbitrary source path is
introduced.

## Software acceptance and limitations

Tests cover source-linear sparse keys, sub-display-frame source key
times, 601-frame animation, source offset/speed, adjacent clips with
identical seam pose, rejects for discontinuous seams, gaps, overlaps,
duplicate camera tracks/curve axes, weighted/native unknown channels,
missing camera world baselines, nonfinite or subframe clip timing,
source camera parenting and Timeline easing, stale/malformed native
key grids, drop/reorder/duplicate frames, nonfinite position/rotation,
high angular movement, and preservation of independently captured
evaluated camera world motion/FOV with native nine-channel preflight.

**Still not supported for autonomous mutation:** repairing arbitrary
existing animated Unreal Sequencer transform curves, multiple
time-varying camera track owners, weighted quaternion tangents,
nested shots/track mixing, arbitrary camera rig parenting, multi-shot
continuity beyond previously approved two-shot boundary correction,
camera blend envelopes, unknown Unity property animators and rendered
fidelity. These require their own independent native edit/rollback,
component ownership, renderer observation and post-repair CineTwin
readback contracts. They are not inferred from the existence of
source-frame plans.

See [Studio release acceptance](RELEASE_ACCEPTANCE.md) and
[Phase 10.2 static camera yaw](PHASE10_2_STATIC_CAMERA_YAW_V01.md).
