# Phase 10.2 — Exactly Two Animated CineCamera Position Keys (v0.1)

**Scope:** Guarded source-bound correction of exactly **two** nonadjacent, interior,
already-existing Sequencer XYZ **position** keys on the **same axis** of one
source-mapped, newly staged CineCamera. This is the **tenth narrowly bounded
autonomous native repair family**. It is not general camera-curve repair.

**Engine acceptance: NOT VERIFIED.** Software-only Python fixtures do not
establish that the Unreal Editor API behaves identically on real native objects,
that packages survive editor restart, or that rendered motion matches Unity.

## Entry conditions

1. Explicit current feedback asks to **fix/repair two or both animated camera
   position keyframes**. Single-key feedback must never authorize two edits.
   Requests for every/all/multiple/unbounded keys, rotation, rig, lens, cut,
   shot, scale or blend edits are rejected.
2. Recompute the immutable original job and candidate chain, Unity CSIR,
   original **evaluated world** CineTwin camera samples, compiled exact
   source display-frame key grid, Element 3/4/5 source occurrence, Element 6
   builder receipt, and independently reopened Element 7/8 baseline.
3. Require exactly one mapped, unparented source camera, one active camera
   transform track, original `verified_cinetwin_camera_world_pose` action,
   and a genuinely moving source camera. No prior remeasurement attempts.
4. Every frame must contain its unique source and target camera world
   position, quaternion orientation and unit-scale sample. The original
   compiled XYZ grid must match the source evaluated world trajectory
   within 0.1 cm; source/native orientation must match within 0.2°.
5. Allow **exactly two** independently measured 3–30 cm native XYZ
   position-axis discrepancies, on the **same axis**, at least two
   display frames apart and neither at the sequence boundary. Every
   other position axis/frame must match within 0.15 cm. Any competing
   rotation/scale/lens/cut discrepancy, missing or duplicate sample,
   ambiguous camera binding, or unsupported source owner refuses repair.
6. Authorization contains only feedback ID, occurrence ID and a digest
   of recomputed measured evidence. The model supplies no native keys,
   numeric values, source paths or edit commands.

## Guarded Unreal native execution

- Recheck current feedback and independently rebuild source evidence.
- Locate the exact original staged camera UObject, source-generated
  actor binding, one absolute transform section, no parent/child rig,
  no competing camera-component transform or time owner.
- Inspect **all nine native Sequencer transform channels** and every
  original display-frame key. Position and rotation key times/modes must
  match original linear source grid; scale channels have unit defaults
  and no explicit keys. Refuse any other altered key, frame, tangent
  mode, extra section or non-unit scale.
- Change only the two measured, **already-existing** position key values.
  Re-read the complete nine-channel grid before saving the **generated
  Level Sequence only**. If either setter, readback or save fails,
  attempt to restore **both original values** (including after a
  mutate-then-throw setter). A failed/partial native save is not
  guaranteed transactionally recovered and must be reported, never
  counted as accepted engine fidelity.
- The receipt is
  `TWO_ANIMATED_CAMERA_POSITION_KEYS_SAVED_REOPENED_CINETWIN_PENDING`,
  never a claim of matching rendered frames, successful new-process
  persistence or post-repair CineTwin parity.

## Deliberately unsupported

- Animated camera rotation keys (Euler wrap and quaternion interpolation),
  more than two position keys, adjacent edits, different-axis edits,
  velocity/tangent/extrapolation repair, insertion/deletion/retiming,
  master/subsequence/timewarp, rig/parent ownership, lens/zoom, physics,
  target native persistence after a new Editor process, and complete
  cutscene fidelity. These remain report-only until separately
  source-owned and natively proven.

## Regression checks

Synthetic software coverage verifies two measured source sample outliers,
separate consent routing, stale/invalid hashes, axis/adjacency/boundary
refusals, other transform-key and scale refusal, complete nine-channel
post-edit native readback, save refusal and both-key rollback after the
second setter mutates and throws. End-to-end live editor/capture acceptance
must be performed later in Phase 10.4 or real-engine evaluation.
