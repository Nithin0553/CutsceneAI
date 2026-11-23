# CutSceneAI Studio — evidence-based release acceptance

**Status: NOT RELEASE-CERTIFIED.** A successful GitHub Action is a code
regression result, not a Unity/Unreal fidelity test. This checklist follows
[P0 master Issue #80](https://github.com/Nithin0553/CutsceneAI/issues/80);
it is the existing release standard, not a new benchmark or product version.

## Release gate integrated into Studio

The Studio Results page reads \`GET /api/release-readiness\`; the release
quality gate is implemented independently in
\`packages/studio/studio_release_gate.py\`. Unlike the editable-sequence
generation indicator, the gate only credits existing, source-bound native
evidence. It reports \`PASS\`, \`FAIL\` or \`INCOMPLETE\` for each domain and
never labels an unverified generated sequence "release-ready".

From the project root:

\`\`\`powershell
python tools/studio_release_audit.py
\`\`\`

For an exact historical job (read-only, no editor modifications):

\`\`\`powershell
python tools/studio_release_audit.py --job-id <32-character-job-id>
\`\`\`

The command prints JSON and exits with code **2** if evidence is incomplete,
failed or missing. A file inside the active candidate directory is not
accepted as evidence for another job, and a modified Unity CSIR/transfer plan
fails its saved-session hash comparison.

## Required real-engine acceptance sequence

1. Record the exact Git commit, Unity project and cutscene CSIR identity,
   exported source feature census, source CineTwin capture (if supported),
   target Unreal project and engine versions. Choose a **new, backed-up saved
   destination level**. Do not overwrite Benchmark001's frozen evidence or
   the Benchmark002 baseline sequences.
2. Connect projects using the Studio UI. With **Enable AI agents unchecked**,
   run the deterministic transfer and collect the automatic native import and
   Sequencer-generation receipts. If source completeness is incomplete, do
   not call this strict conversion a pass. Use a distinctly labelled
   best-effort experiment only after explicit opt-in.
3. Save packages; run CineTwin on the matching source capture. Check actor
   trajectories, root motion, orientation, camera cuts, animation poses,
   attachment relationships and audio/event timing. Never treat a measured
   material-slot count as an image or skeletal-pose fidelity result.
4. Close Unreal Editor, **reopen the target map and generated Level Sequence
   in a new Unreal process**, start the current companion and run Studio's
   native persistence, hierarchy and visual audits from Results/Advanced.
   The audit compares the real editor process IDs and saved native packages.
   Old transfers that lack generation process IDs remain restart-unverified.
   Inspect bindings, materials, attachments and generated audio.
5. Repeat with **Enable AI agents** only on a fresh candidate/staging level.
   Verify the graph's exact strategy, source provenance, persisted request,
   one-time Unreal execution, native receipt, changed material slots and
   stop conditions. Never retry into a partially mutated candidate.
6. Re-run the read-only release audit and compare per-domain differences
   against the baseline. Perform the same experiment on multiple independent
   source projects, including a held-out one. Verify that **approved** case
   memory changes a later CED strategy and improves an independently measured
   outcome before making adaptive-learning or generalization claims.

## Current release blockers that code-only CI cannot clear

- Full source-census coverage and non-ambiguous source asset dependencies
  across more than the prepared samples.
- Benchmark002 actor/root-motion and character facing discrepancy; prior
  evidence identified about 280 cm positional and 90° orientation errors.
  End-to-end real-editor retargeting and orientation fixes are not certified.
- Matching-time source and target image/camera projection validation,
  complete skeletal joint pose, shaders/sky/environment lighting,
  audio waveform synchronization and event side effects.
- Native persistence needs an actual second Unreal process. New jobs record
  the generating Unreal OS process ID; the native audit recognizes distinct
  process ID plus independently loaded, saved package and sequence readback.
  Existing jobs without that evidence remain INCOMPLETE. This proves a
  different-process readback, not that the original process was forcibly closed.
- Actual verified learning: case approval, safe CED policy update, retrieval,
  strategy change and improved outcome on a different source project.
- Held-out source-project validation and a published compatibility/capability
  matrix with independently measured supported/unsupported feature outcomes.

The integrated Elements 1–9 / Phase 10.2 software stack now registers
**eight narrowly bounded source-bound repair families**: material albedo
fallback, one-character constant actor offset, static physical CineCamera lens,
single camera-cut section boundary, static CineCamera world placement,
**one static-character actor-base yaw**, an exact **two-camera, two-shot
shared-switch frame correction** (no inserts, deletes, reorder, retargeting,
time-warps, subsequences or general multi-cut scheduling), and **one
static-CineCamera actor world-yaw-only correction** (no animated camera
transform, rig, pitch/roll, lens, cut or moving-camera rewrites). Static character yaw
requires reviewed anatomical mesh
forward, exact native reopened owner, calibrated motionless rig and no active
native animation/Sequencer transform controller. The native owner,
source/CineTwin evidence, user consent, preflight, direct readback and rollback
guards differ by family. They have **synthetic/software tests only**; no real
Unreal editor mutation, repaired sequence reopening or rendered fidelity is
certified. Moving/animated character facing, general IK retarget calibration,
camera animation, audio, events, lighting/shader parity and unknown plugins
remain diagnostic-only or unsupported. See [Elements 1–9 audit](ELEMENT1_TO_9_INTEGRATED_AUDIT_AND_REPAIR_EXPANSION_V01.md),
[Phase 10.1 gap audit](PHASE10_1_SOFTWARE_GAP_AUDIT_V01.md), and
[Phase 10.2 static character yaw scope](PHASE10_2_GUARDED_STATIC_CHARACTER_YAW_V01.md)
and [Phase 10.2 two-shot camera switch scope](PHASE10_2_TWO_SHOT_CAMERA_SWITCH_V01.md), and
[Phase 10.2 static camera yaw scope](PHASE10_2_STATIC_CAMERA_YAW_V01.md).
Animated camera world-trajectory reconstruction now has a distinct
[source-frame and native nine-channel motion contract](PHASE10_2_ANIMATED_CAMERA_FRAME_GRID_V01.md):
the independent evaluated Unity CineTwin capture is authoritative when
available, otherwise a complete, nonblended source-local camera curve is
baked on every exact display frame. The native writer preflights contiguous
source frames, absolute transform channels, and scale defaults **before
editor mutation**. Unknown camera curves, missing world baselines,
overlapping/gapped/eased clips, moving camera parents and ambiguous local
curve ownership fail closed unless original evaluated source capture is
available. **This is conversion-layer hardening, not a ninth autonomous
native post-generation repair.** True Unreal reopens and rendered parity
remain unverified.
Phase 10.2 now also includes a **ninth narrow guarded repair family**:
a source-evaluated CineTwin-backed, independently reopened **one animated
CineCamera XYZ position-key** restoration, with exact original Sequencer
nine-channel key-grid comparison, one existing native key mutation,
save/readback and rollback. The prior statement of **eight families** above
describes the earlier static adapter generation, not this new ninth member.
See [Phase 10.2 single animated camera key](PHASE10_2_ONE_ANIMATED_CAMERA_KEY_V01.md).
This is **not** general animated-camera curve/rig/blend repair and does not
establish actual Unreal editor execution, independent post-repair CineTwin,
rendered motion or a release-ready cutscene.
A **tenth** bounded family now permits exactly two nonadjacent, interior
source-measured animated CineCamera XYZ **position** keys on one native axis,
with separate two-key user consent, a recomputed original CineTwin/CSIR
evidence hash, nine-channel native preflight and all-key readback, and
compensating two-key rollback attempts after write/readback/save failure.
See [Phase 10.2 exactly two animated camera keys](PHASE10_2_TWO_ANIMATED_CAMERA_KEYS_V01.md).
This does **not** imply generic camera curve or rotation repair, nor does it
establish real-editor save/reopen, post-repair CineTwin or rendered fidelity.
The earlier family counts are historical descriptions of previous increments.
An **eleventh** guarded software adapter now supports exactly one
**source-measured, interior animated CineCamera yaw keyframe** (3–30°) with
physical source/native quaternion-versus-Euler proof, no unwrap/gimbal
ambiguity, strict full-grid position/pitch/roll/scale checks, original
native Sequencer nine-channel ownership, exact current user feedback,
one existing key edit, full channel readback and rollback attempts.
It does **not** permit arbitrary rotation curves, multi-yaw/pitch/roll
edits, moving camera rigs, shot blending, or claim post-repair distinct
Unreal Editor reopen, CineTwin or rendered parity.
See [single animated camera yaw key contract](PHASE10_2_ONE_ANIMATED_CAMERA_YAW_KEY_V01.md).
Earlier counts on this page describe historical earlier increments.
The Phase 10.2 consolidated seven-workstream software branch also adds
a **twelfth** guarded repair family: counted **2–8** nonadjacent,
independently source-measured animated CineCamera yaw-only key restorations,
with source quaternion-to-Unreal-Euler proof, current exact-count feedback,
full native nine-channel preflight, save/readback and multi-key compensating
rollback. It does NOT support generic key tangents, pitch/roll,
quaternion-spline interpolation, moving rig/parent blends, or rendered
continuity without separately measured editor acceptance.

The seven original Phase 10.2 work areas are inventoried with exact
source features, installed action candidates and explicit remaining gates
in [the consolidated seven-workstream contract](PHASE10_2_SEVEN_WORKSTREAM_CONSOLIDATED_V01.md).
The `phase10_2_consolidated_audit` can be exclusively persisted and later
recomputed through `tools/phase10_2_audit.py`; the release gate may mark
that source/action **accounting** PASS while all engine, renderer, native
post-reopen and held-out acceptance remain independently INCOMPLETE.
No seventh workstream may be silently marked complete from CI alone.
No arbitrary Unity script, proprietary shader, animation rig or camera
control may be reconstructed simply because an LLM identifies a mismatch.

## Release decision rules

- **Native generation success:** an editable Level Sequence exists and the
  generator finished safely, but still has unverified fidelity.
- **Supported-scope verified transfer:** every claimed supported feature has
  independent source/target parity evidence; unsupported features are
  clearly excluded or blocked.
- **Studio release-ready:** complete source intake, supported asset staging,
  native generation, safe failure recovery, post-restart persistence,
  feature-level verification, reproducible held-out cases and approved
  learning, with no unresolved P0 acceptance blockers.
- **Universal perfect transfer:** not a scientifically defensible guarantee
  for arbitrary Unity/Unreal custom scripts, plugins, shaders, middleware or
  source-asset rights. The Studio must fail visibly where semantics cannot
  be reconstructed.

This document is a release decision procedure, **not** a claim that any
local Unity/Unreal run was executed by GitHub Actions.
