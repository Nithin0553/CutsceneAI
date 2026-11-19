# Advanced fidelity adapters — software implementation and acceptance handoff

This document records exactly what CutSceneAI Studio can **verify in software** on the release candidate. Unity 6.3 compilation, Unreal 5.8 asset creation, native rest-pose reads, imported FBX/Unity .anim parity, frame-render parity and a held-out source cutscene have **not** been run here. Never promote the software-only CI result to a native fidelity certificate. Never merge this candidate into `main` before review.

## 1. Skeletal bind-pose and local axis calibration

The existing approved IK Retargeter remains the normal path for uniquely identified, hashed, unblended FBX takes. `integrations/unreal/studio_ik_retarget.py` compares fresh import reference poses to the reviewed source preview mesh before any retargeting. That is *eligibility*, not joint-orientation equivalence.

For post-reopen **independent** comparison, `packages/cinetwin/rig_pose_calibration.py` accepts `cutsceneai.rig_pose_calibration` JSON with:

- `kind: "cutsceneai.rig_pose_calibration"`, `schema_version: "1"`, `reference_kind: "INDEPENDENT_APPROVED_REST_POSE"`.
- `source_identity` = the sampling plan's exact `csir_sha256`, `sequence_ref`, `project_fingerprint`.
- `target_identity` = the reopened target observation's exact `engine_version`, `project_identity_sha256`, `sequence_asset_path`.
- `rigs[entity_id].bone_map` = exact source bone ID → target bone name correspondence, one-to-one and complete.
- `rigs[entity_id].reference[source_bone_id]` holds **three independently reviewed unit quaternions**: `source_world_rotation_xyzw` (canonical), `target_unreal_world_rotation_xyzw` (native UE), and `axis_alignment_xyzw` (canonical orientation-delta axis frame).

The comparator removes each rig's approved reference orientation, rotates source local delta axes through the approved frame, and evaluates matched native target orientation deltas at every source sample. It fails on missing, nonunit or stale references and flags mismatches, but cannot independently confirm that a user-supplied 'approved' reference is genuine without native measurement and review. Mesh skin deformation is separate.

In a *fresh, reopened* Unreal process, provide the approval path to `studio_native_acceptance.start(rig_calibration_path=...)`. It hashes and binds the approval to the source/target evidence and writes calibrated results into the native comparison. An omitted approval stays `INCOMPLETE`; it does not make a false PASS.

## 2. Imported character anatomical forward

`integrations/unreal/cinetwin_target_evaluator.py` and tick-synchronized `cinetwin_tick_evaluator.py` now record an actor's **actual skeletal-component world quaternion and target mesh identity** per frame. This distinguishes actor rotation from the mesh's extra relative rotation.

`packages/cinetwin/mesh_forward_basis.py` requires `cutsceneai.mesh_forward_approval` with `schema_version: "1"`, `reviewed_anatomical_axes: true`, the exact source/target identity objects described above, and:

`characters[entity_id] = { "source_forward_actor_local_canonical_xyz": [x,y,z], "target_forward_mesh_local_unreal_xyz": [x,y,z], "target_mesh_asset_path": "/Game/Characters/Mesh" }`

The two vectors must come from **separately approved anatomical directions**, not inferred from an arbitrary local +X/+Z assumption. The comparison reports maximum world-forward angular error at the source grid. A suggested Unreal yaw adjustment is informational only (`suggestion_applied: false`), never an automatic actor/rig mutation. Pass `mesh_forward_approval_path=...` to `studio_native_acceptance.start()` for the reopened acceptance run.

## 3. Complex Unity Timeline easing and overlap

`packages/studio/timeline_blend_policy.py` detects source Timeline overlaps, ease-in/out and concurrent transform tracks for the same bound entity. If the source actor/camera can be measured with a complete CineTwin Play Mode capture, `transfer_backend.compose` replaces competing Unreal transform tracks with **one frame-matched, source-evaluated actor-world trajectory** (`verified_unity_blend_evaluated_actor_world`). For blended cameras, it separately carries evaluated vertical FOV (`verified_unity_blend_evaluated_lens`). The immutable transfer report records each affected source track as `BAKED_PARTIAL`.

A character's **skeletal** pose blends cannot be accurately recreated from its actor trajectory; until the target skeletal pose-bake adapter has its own source-bound, operator-approved, real engine validation, those blends are rejected as requiring skeletal baking, never counted as converted. Unsupported blend weight algorithms and custom Unity mixers remain unverified if no evaluated source capture exists.

## 4. Formats and source-sampled skeletal `.anim`/blend pilot

`packages/studio/animation_format_policy.py` classifies FBX, native Unity `.anim`, other externally authored clips such as BVH/glTF/USD/Alembic, and unknown formats. It does not pretend an unregistered format was imported. The existing automatic IK selection stays restricted to **hashed, default single-take FBX**. Source `.anim` + skeletal clips and layered character animation are explicitly refused in standard automatic transfer until a separately approved native pose-bake is verified.

To support a controlled native adapter proof, `packages/studio/skeletal_pose_bake.py` can compile a **complete, source-authenticated Unity CineTwin local bone pose sample grid** into target-local translation/rotation/scale keys using a reviewed per-bone reference/axis map. The approval object must use:

`kind: "cutsceneai.studio.approved_skeletal_pose_bake"`, `schema_version: "1"`, `reviewed_rest_and_bone_axes: true`, `source_identity` with exact source CSIR hash/project fingerprint/sequence reference, `source_capture_sha256`, `source_entity_id`, exact `bone_map` and `reference`, plus target `skeleton_asset_path`, **new** `animation_asset_path`, and `unreal_project_identity_sha256`.

Each `reference[source_bone_id]` requires `source_local_reference` with `position_m/rotation_xyzw/scale_xyz`, `target_local_reference_unreal` with `position_cm/rotation_xyzw/scale_xyz`, `axis_alignment_canonical_xyzw`, and reviewed positive `translation_scale`. Each source bone has one native target bone. Source and target rest poses must be independently observed/reviewed, **not** taken from the first animated frame. The compiler rejects incomplete/stale samples, arbitrary animated scale/shear and invalid frame or bone budgets.

The CLI `python tools/studio_compile_skeletal_pose.py --csir SOURCE.csir.json --capture SOURCE.cinetwin.behavior.json --approval APPROVED-BONES.json --output NEW-pose-bake.json` computes **actual source/capture file-byte SHA256 hashes**, requires those hashes in the approval, validates the original CineTwin sampling plan, and refuses to overwrite an existing compiled plan.

`integrations/unreal/studio_skeletal_pose_bake.py` is a **separate operator-approved native pilot** to create one new `AnimSequence` using native Unreal 5.8 `AnimationDataController`, save it and record a durable receipt. Before creating any asset, it requires an actual matching Unreal Skeleton and uses the native reference-pose API to verify every mapped bone's rest position, rotation and scale against the compiler's approved target reference. All native writes are isolated to a fresh asset path. Use `execute(NEW-pose-bake.json, NEW-native-receipt.json, explicit_native_approval=True)` from the Unreal Python integration directory **only after project/skeleton backups, explicit approval and matching editor versions**. It refuses an occupied receipt/asset and records `PARTIAL_NATIVE_WRITE_NO_AUTORETRY` on any possible incomplete native write. It does not automatically retry after a possible native write and does **not** claim verified native readback. It is not exposed as an unrestricted AI tool or silently inserted into every existing transfer plan. Native compilation/readback, target skeleton rest-pose correspondence and held-out playback still need workstation proof before enabling normal agent-driven scheduling of the adapter. The pilot's `NATIVE_SAVED_PENDING_INDEPENDENT_READBACK` status is *not a fidelity PASS*.

## 5. Real engine acceptance matrix

Real Editor acceptance can be conducted in the previously selected Unity/Unreal workstation. Normal bridge/host code refresh should preserve open editors; the distinct-editor reopen test is **only for proving persistence of a saved candidate**, not for every code update. After the code-only software scope is reviewed:

1. Export an unchanged Unity CSIR and source CineTwin Play Mode capture, exact source hashes and Unity compiler logs.
2. In a disposable Unreal 5.8 project/map, run the existing source-bound native candidate flow; save generated sequence, clips and project. Record the actual editor PID, version and asset paths.
3. Open the **saved** level in a different Unreal process **only for the persistence acceptance case**; run `studio_native_acceptance.start(...)` with reviewed rig and mesh-forward approvals where appropriate.
4. Review six cases separately: static mesh front, moving+turning character, eased/overlapping actor/camera Timeline, approved bone orientation axes, saved/reopened native persistence, and a genuinely held-out Unity source project.
5. Put each `native-acceptance-*/comparison.json` and its full accompanying evidence in the Studio evidence workspace. Produce a SHA256-identified `cutsceneai.studio.engine_acceptance_matrix` version 1 with one `{scenario, evidence_path, evidence_sha256}` row for each required scenario. The six scenario names live in `packages/studio/engine_acceptance_matrix.py`.
6. Run `python tools/studio_engine_acceptance_matrix.py --workspace WORKSPACE --manifest MATRIX.json --output NEW-REVIEW.json`.

The matrix rejects changed/missing evidence, PID reuse, stale source project identity, missing sampled native frames and missing approved mesh/joint probes; **its output is always `EVIDENCE_COMPLETE_REQUIRES_HUMAN_ENGINE_REVIEW`, not a release certificate**. A human/QA reviewer still needs to examine actual Unity/Unreal logs, visual render/silhouette parity, material, lens, audio and physics-specific tests.

## Current claim boundary

**Implemented in the release-candidate software:** independent calibration/forward verification routines, native component basis observation, actor/camera blend capture-based planning, animation-format inventory/refusal, separately approved skeletal bone pose compiler + native writer pilot, and native evidence matrix/CLI.

**Not established by software tests:** native skeleton and AnimSequence API behavior in the real Unreal 5.8 editor, actual calibration reference authenticity, arbitrary Humanoid/multi-take/third-party format import, all skeletal Timeline blend types, final rendered/source cutscene parity or full end-to-end production-readiness. Neither `main` merge nor `SOFTWARE_READY_FOR_ENGINE_TEST` follows automatically from the current results.

## 6. Independent saved AnimSequence raw-key readback (code-only, not native accepted)

The operator-approved writer now binds its immutable write receipt to the **generating Unreal Editor PID**. After saving, use a **different** Unreal Editor 5.8 process with the exact same approved target project to call the new read-only verifier:

```python
from studio_skeletal_pose_readback import verify
result = verify(
    r"C:\\evidence\\pose-bake.json",
    r"C:\\evidence\\native-write.json",
    r"C:\\evidence\\native-readback.json",
)
print(result["status"])
```

Import from the project's `integrations/unreal` Python integration directory. This verifier **does not create or edit assets**. It refuses a partial/stale write receipt, same Editor PID, changed `.uproject`, wrong asset class/skeleton, missing native track APIs, wrong frame rate/key counts, missing/extra bones, incomplete native key channels, altered quaternions or translations, and reuse of the output file. It separately measures every saved position, rotation and scale key on every approved bone through Unreal's **raw animation track read API** and records a hash-bound result.

Only `NATIVE_SAVED_BONE_KEY_READBACK_PASS` verifies this narrow, saved native raw-key stream. `NATIVE_SAVED_BONE_KEY_READBACK_FAIL` records above-tolerance key differences. Neither status establishes evaluated animation playback, target skin deformation, approved cross-rig silhouette matching, Timeline linkage, camera projection or full cutscene fidelity. The verifier has synthetic Python API tests in `tests/studio/test_skeletal_pose_readback.py`; execution against a genuinely reopened Unreal 5.8 Editor **remains untested**. This readback is not automatically wired into AI transfer scheduling or the final release gate.
