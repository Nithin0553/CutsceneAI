# Phase 10.2 — Single Source-Proven Animated CineCamera Yaw Key (v0.1)

**Software adapter:** one explicit user-approved, source-measured **interior
Unreal Sequencer yaw key**, not general pitch/roll, quaternion-curve or whole-
trajectory repair. This is the **eleventh** narrow native repair family after
the single and two-position-key adapters. Real engine acceptance is **not verified**.

## Source and reopened-target evidence

- Recompute original immutable Unity CSIR, mapping, original evaluated CineTwin
  world-source capture, source frame grid and compiled camera action, source
  occurrence and Element 3/4/5 plans, once-only Element 6 builder evidence,
  distinct-editor reopened Element 7 readback and Element 8 per-occurrence
  diagnosis. Exactly one source-mapped, unparented active CineCamera transform
  owner and original `verified_cinetwin_camera_world_pose` action are required.
- The source camera must **change yaw** across the complete display-frame grid.
  At every original sample, native/source positions must match within 0.15 cm,
  original compiled source rotations must agree with independently evaluated
  Unity quaternions and the original native source Euler channel, and scale
  must remain unit.
- For every sample, source/native pitch and roll must agree within 0.2°.
  All source/target Euler components must stay within absolute 120° and pitch
  below 65° to avoid aliasing/gimbal ambiguity; source yaw steps may not
  exceed 60°. The target quaternion physical difference must be consistent
  with the measured Unreal yaw-only difference. Other camera lens/cut domains
  must independently pass.
- Exactly **one** independently reopened camera sample may contain a 3–30°
  yaw-only difference, at an **interior** frame. No other source/native
  position, orientation, scale, cut or lens error is accepted.
- Element 8 must report exactly
  `WORLD_ROTATION_OUTSIDE_TOLERANCE` for the source camera entity occurrence.
  The original readback/repair source hashes bind the proof. No prior repaired
  capture is reused.

## Current consent and native write contract

1. User feedback must explicitly request repair of an **animated camera yaw
   keyframe**. Broad rotation, two/multiple keys, pitch/roll, lens, rig, shot,
   whole curves, deletion/insertion and negation are rejected.
2. LangGraph may select only `restore_single_animated_camera_yaw_key` or
   `report_only` after verifying a hash-bound source proof. The model provides
   no angles, numeric commands, file paths or new keyframes.
3. Native Unreal dispatch re-verifies current feedback, original job/sequence,
   original compiled action and source occurrence, exact staged CineCamera
   UObject and binding, single absolute source section, attachments, master
   timeline and camera-component owners.
4. Full **nine-channel** Sequencer key inventory, exactly original frames,
   required linear interpolation, native source-unwrapped rotation values
   and unit-scale defaults must match the immutable source except this one
   independently measured existing yaw channel key (native channel index 5).
   No other Euler alias or frame/time/key edit is permitted.
5. Set exactly one existing yaw key from the original compiled source action,
   re-read **all nine channels and all original frames**, directly check the
   corrected value, save only the generated Level Sequence. If a native
   setter mutates then throws, readback fails, or save fails, attempt to
   restore the original key and independently recheck its original state.
   A compensating rollback is **not** a guaranteed persisted transaction.

Receipt:
`ONE_ANIMATED_CAMERA_YAW_KEY_SAVED_REOPENED_CINETWIN_PENDING`.

This receipt does **not** establish post-repair independent CineTwin capture,
new-process asset persistence, between-key rendered motion, visual parity or
a successful live Unreal Editor run.

## Remaining unsupported Phase 10.2 work

- Multiple yaw keys, pitch/roll and quaternion-native rotation repair,
  interpolated curves and tangents, keys across angle wraps/pitch poles,
  camera rigs/parents/timewarps, animated optical tracks, nested shots and
  blending, and independent postrepair rendered visual motion.
- Phase 10.2 workstreams 2–7 continue separately. This adapter is not
  sufficient to close the animated-camera workstream or Studio release.

## Regression contract

Synthetic tests check original quaternion vs native Euler source agreements,
exact one-frame yaw selection, cross-domain/pitch/roll/second-key refusal,
Euleralias bound, native nine-channel preflight, save and full readback,
rollback after save failure and mutate-then-throw setter. No engine was launched.
