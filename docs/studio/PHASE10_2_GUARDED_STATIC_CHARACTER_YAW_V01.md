# Phase 10.2 — Guarded Static Character Actor Yaw Repair (v0.1)

**Integration branch:** `integration/element1-9-guarded-repair-expansion-v0.1`  
**Status:** software adapter, source/native proof and synthetic editor regression suite. **Real Unreal Editor execution, save/reopen and rendered parity have NOT been verified.**

## Specific supported case

Exactly **one** newly staged, unparented and upright `SkeletalMeshActor`
with one reviewed skeletal-mesh component, no competing authored character
track and a constant, independently sampled source/native world-space yaw.
Both source and target character positions, actor yaw, scale and every
observed skeletal bone must stay constant for the complete source sampling
grid. Original source character anatomy and target mesh-local forward are
explicitly approved for the exact source project, target project/sequence
and mesh asset. A separately approved **full rig/rest-pose calibration** must
also pass the existing joint-reference and joint-motion measurements.

The only native mutation is an Unreal **actor base rotation**, NEVER an FBX
axis, SkeletalMeshComponent relative rotation, animation key, skeletal root
pose, Control Rig or animation asset edit. This policy is intentionally
narrow: e.g. an animated walking/turning character is **not eligible**.

## Evidence, authority and native writer

`studio_static_character_yaw_evidence.build(workspace, job)` checks:

1. Exact prepared source CSIR hash, source CineTwin capture hash, target
   mapping, compiled transfer plan, active source occurrence workflow,
   original native builder completion and separately reopened Editor PID.
2. Independently reconstructed Element 7 full target time grid and bounded
   Element 8 recovery status (no no-progress/regression/exhausted budget).
3. Current reopened `native-character-facing-ownership.json` associated
   with the very same source capture, native target SHA, Level Sequence, job
   and generated character. Any blocked, unapproved or ambiguous native
   actor/mesh owner prevents eligibility.
4. Approved `mesh-forward-approval.json` source/target anatomy, reviewed
   native skeletal-mesh asset path, and matching source/target/mesh component
   world quaternions at **every** sample. Candidate yaw is allowed only when
   circular variation is at most **0.5°**, the non-yaw residual is at most
   **2°**, and correction is **5–180°**. This is a diagnostic-to-native
   *candidate*, not independent permission to execute.
5. Approved `rig-calibration.json`, passed joint reference orientation,
   passed joint angular-motion profile, passed joint positions, and no
   other measured actor/rig mismatch. Source/target actor position must
   match within 1 cm; static drift at most 0.1 cm; orientation drift at most
   0.25°; only unit actor scale and upright pure-yaw quaternions.
6. No authored source Timeline transform/animation track, no competing
   compiled character property, animation or track action.
7. Exactly one source character and an exact prepared label; a
   cryptographically hashed `character_yaw_repair_sha256` pins the proof,
   the original native observed yaw, correction and final target yaw.

A real user request such as “Please fix the character facing direction”
is additionally required. “Fix animated character facing”, requests
involving cameras, positions, root motion, materials, walking or multiple
characters, and negated requests are explicitly refused.

The model receives only verified eligibility and domain status; the
native request contains **no model-authored yaw, axis or transform numbers**.
`studio_agent_graph` and the intent router may choose only the exact
allowlisted `restore_static_character_actor_yaw` strategy. As with every
native adapter, the pending request is committed before executing, and
`studio_agent_executor.service_one` creates a durable
`agent-claim-*.json` **before any mutation**. Interrupted claims are never
replayed automatically and at most two native repair receipts are accepted
for a job.

Inside `studio_static_character_yaw_repair.attempt` the current Unreal
editor must independently recheck:

- exact current feedback identity and one-character source proof hash;
- current source-created actor in the setup receipt and unique live label;
- **full** native master/binding Sequencer track inventory, attachment,
  component-relative basis, mesh path, scale, physics, roll/pitch;
- **inactive skeletal animation**, including no active AnimInstance,
  AnimBlueprint class, postprocess instance, single-node animation asset
  or mesh-authored postprocess AnimBP; missing/changed Python APIs fail closed;
- live actor yaw matches independent reopened original, and live
  SkeletalMeshComponent world quaternion actually follows actor base yaw.

Only then one `Actor.set_actor_rotation(Rotator(0, final_yaw, 0), True)`
may execute. The actor AND mesh world bases are immediately reread.
The actor location cannot change. Native setter failure, readback mismatch,
unexpected translation or level-save failure triggers best-effort rollback
of original actor rotation **and position**; interrupted disk saves may
still require manual inspection rather than false rollback claims.

A successful receipt has status
`STATIC_CHARACTER_YAW_SAVED_REOPENED_CINETWIN_PENDING` and explicitly
sets independent reopened full-grid CineTwin, skeletal-root post-edit
sampling, editor-restart persistence, rendered facing and overall cinematic
fidelity to **false/pending**. Live in-memory property readback is not a
CineTwin pass.

## Synthetic acceptance and attack scenarios

- Stable 90° source/target approved anatomical discrepancy, complete static
  actor+joint samples, proof hash, current feedback and one native actor write.
- Refused: stale source/job/approval, missing rig calibration, misaligned
  target mesh/component, inconsistent pose or sample time, non-unit scale,
  actor translation, animated source/native character, skeletal-root or
  Control Rig track, shot/subsequence, attachments, physics, active AnimBP,
  postprocess/single-node animation, stale editor yaw, wrong mesh.
- Refused: mixed or negated user feedback, forged model strategy, obsolete
  proof digest or feedback ID, foreign editor/project/level.
- Recovery: setter returns failure, mutates then throws, wrong native
  post-edit readback, unexpected actor translation, failed save;
  verify best-effort rollback. No automatic replay after an interrupted
  native write-ahead claim.
- LangGraph queues only source ID and proof hash, never yaw numbers;
  the executor checks exact native project/sequence/level before dispatch.

All tests use synthetic readbacks, module-level source-contract doubles or
Unreal Python API doubles. They do **not** establish real Unity C# compiler
compatibility, actual Unreal editing or clean rendered parity.

## What remains

1. Live Unreal Python API compatibility for static animation-data/postprocess
   inspection and actor rotation/readback, plus real engine save/reopen
   acceptance — deliberately deferred by the user until the Studio software
   phase is completed.
2. **Animated/root-motion character facing** is still unsupported. Actor
   track/yaw ownership, IK retarget reference axes, per-frame moving
   trajectories, animation Blueprint/Control Rig and Timeline blend
   semantics require different independently safe adapters.
3. Broader camera animation, multiple camera cuts, spatial parent rigs, audio,
   VFX, custom shader/event/physics fidelity and complete rendered parity
   are still separate unsupported or diagnostic-only domains.

**No “perfect conversion” or entire cinematic equivalence claim is made.**

See [Phase 10.2 Native Character Rotation Ownership Gate](PHASE10_2_CHARACTER_ROTATION_OWNERSHIP_GATE_V01.md)
and [Element 1–9 integration / release acceptance](RELEASE_ACCEPTANCE.md).
