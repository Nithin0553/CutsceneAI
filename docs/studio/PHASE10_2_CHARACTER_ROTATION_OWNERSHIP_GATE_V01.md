# Phase 10.2 — Native Character Rotation Ownership Gate (v0.1)

**Integration target:** `integration/element1-9-guarded-repair-expansion-v0.1`.  
**Verification method:** software-only native API doubles and integrity fixtures; **no real Unity/Unreal Editor acceptance performed**.  
**Decision:** **READ-ONLY NATIVE INSPECTION BUILT; CHARACTER ROTATION MUTATION NOT AUTHORIZED.**

## Problem addressed

A character may have a correct Unreal actor quaternion while its rendered
mesh faces another way. Conversely, the actor quaternion may differ while
SkeletalMeshComponent anatomy remains aligned. The source-to-target mesh
forward comparator introduced in Phase 10.2 measures these separately, but
neither the comparator nor an LLM can tell which native layer owns a rotation
without inspecting the reopened Unreal editor. Rotating the wrong layer can
break root motion, retargeting, attached props and animation.

This change makes **independently reopened native ownership evidence** a
first-class, source-hash-bound, fail-closed diagnostic input to Studio. It does
**not** install a speculative sixth repair strategy.

## New live-editor read-only preflight

`integrations/unreal/studio_character_facing_ownership.py::inspect()`:

1. Requires exactly one actor with the expected source-bound label, a
   `SkeletalMeshActor` and one `SkeletalMeshComponent` using the explicitly
   approved `/Game/...` skeletal mesh asset.
2. Observes actor roll/pitch/yaw and scale, hierarchy parent/children,
   component-relative translation/quaternion/scale, animation mode and native
   physics status. Refuses nonfinite data, non-upright pose, non-unit/negative
   scale, dynamic hierarchy or an unapproved imported mesh.
3. Enumerates *all* native master and binding Sequencer tracks, capped by a
   bounded inventory. Only camera cut, audio and visibility tracks are
   classified as unrelated to a static actor base yaw. Skeletal animation,
   actor transforms, Control Rig, property, attachment, shot, subsequence,
   constraint and unknown plugin tracks **block** static owner isolation.
4. On any unavailable Unreal Python API, changed actor, ambiguous binding,
   non-identity mesh component basis, physics or animation-owner uncertainty,
   returns explicit **BLOCKED_UNVERIFIED_OWNER** evidence instead of inferring
   that the actor base rotation owns the problem.
5. Even with no observed conflict, returns only
   `STATIC_NATIVE_OWNER_CANDIDATE_REQUIRES_SOURCE_PROOF`.
   `native_edit_authorized`, `actor_yaw_repair_authorized` and
   `full_cutscene_fidelity_verified` are always **false**. No position,
   rotation, mesh, skeleton, Sequencer or asset mutation occurs.

The animation mode is an **observed label**, not proof that an Animation
Blueprint, native clip or skeletal root will remain static at playback time.
Source authored tracks, imported reference axes and full body animation still
need independent validation.

## Provenance and acceptance wiring

`integrations/unreal/studio_native_acceptance.py` now writes, from the real
separately reopened Unreal process,
`native-character-facing-ownership.json` under that job's immutable
`native-acceptance-*` folder. The file is scoped to the exact job,
candidate, original Unity CineTwin capture SHA-256, target observation SHA-256,
Level Sequence path and reopened editor PID. Its read-only hash is recorded in
`comparison.json`.

`packages/studio/studio_element7_readback.py` independently checks that the
optional receipt matches the exact source/target/job/PID/sequence and contains
**no native edit or full-fidelity authority**. A present but unreferenced,
symlinked, missing, modified, foreign or falsely authorized report is rejected.
Legacy native observations without this optional receipt remain valid only
for their earlier measured scope; they are **not** native character-owner proof.

`packages/studio/studio_character_facing_review.py` then reads only
verified reopened Element 7 evidence and produces a **redacted** summary:
how many characters have a possible static base owner, how many are blocked,
how many independent actor/mesh facing mismatches were measured and how many
lack approved anatomical basis. Raw project names, actor names, native paths
and reference-pose bytes are **not passed to the LLM**.

A user comment about character facing can reach this review through
`studio_agent_graph.py` and `agent_intent_router.py`. When native evidence
is available, the agent receives the registered disposition
`NATIVE_CHARACTER_ROTATION_OWNERSHIP_REVIEW_ONLY`. The **only** strategy
remains `report_only`, with no tool to set actor yaw, mesh component rotation
or retargeted skeletal root transforms. A mixed-domain user request or
expired repair budget remains report-only.

## Synthetic test gates

- Realistic Unreal Python API doubles: exact actor/mesh/hierarchy/class,
  native component rotation/scale, observed animation mode and physics.
- Refusals: 3D Transform, SkeletalAnimation, ControlRig, SubTrack, Shot,
  property, attachment, plugin tracks, including root and binding tracks.
- Refusals: missing/changed actor or mesh, duplicate actor label, attached
  children, changed actor roll/pitch, negative scale, non-identity component
  rotation, physical simulation and unreadable API responses.
- Native acceptance writes job-bound **read-only** observations without
  failing unrelated visual/structural acceptance on a missing mesh approval.
- Element 7 revalidates the exact native receipt/hash and rejects foreign,
  stale, forged, unreferenced or claimed-authoritative records.
- LangGraph accepts only a redacted report-only native-owner assessment;
  missing evidence, mixed user intent and altered owner evidence cannot
  authorize an engine write.

## What is still needed before a native facing adapter is safe

1. A genuinely source-bound, full-frame **static and upright** character
   orientation discrepancy, including approved native mesh anatomical axis
   and full joint/rest-pose/root-motion ownership validation.
2. A native owner contract that rules out Animation Blueprint, latent native
   animation, imported model forward-axis and root-motion conflicts, not merely
   a track inventory with no authored Sequencer keys.
3. Exact current user feedback authorizing a **single newly staged**
   character and a separately registered bounded repair name. All numeric
   rotation parameters must be independently recomputed inside Unreal,
   never accepted from model output.
4. Native readback before/after, safe editor transaction + rollback on
   failed setter/save, one write-ahead attempt and no automatic replay.
   Reopen the saved target in **another** Unreal process for a fresh CineTwin
   comparison; even that does not establish rendered/skin/audio fidelity.
5. Synthetic negative and interrupted-write tests for every new native
   mutation hook and a real Unreal Editor validation campaign after Studio
   software freeze.

The five previously registered bounded native repair adapters are unchanged.
Moving characters, retarget root/axis blending, cameras under animation rigs,
nested cuts and custom events remain unsupported or diagnostic-only until
registered source-grounded semantics and independent native outcomes exist.

See [Phase 10.1 software gap audit](PHASE10_1_SOFTWARE_GAP_AUDIT_V01.md)
and [Phase 10.2 character facing calibration](PHASE10_2_CHARACTER_FACING_CALIBRATION_V01.md).
