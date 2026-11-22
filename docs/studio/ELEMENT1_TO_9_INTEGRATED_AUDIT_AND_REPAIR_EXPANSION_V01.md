# CutSceneAI Studio — Elements 1–9 Integrated Audit and Guarded Repair Expansion (v0.1)

**Integration branch:** `integration/element1-9-guarded-repair-expansion-v0.1` (draft PR #149); **base:** `feature/studio-e2e-release-candidate-v0.1`. All Element 3 subbranches and Elements 4–9 appear once through their linear commit ancestry. Older individual draft PRs must **not** be merged again on top of this integrated branch. Neither this document nor GitHub CI establishes a real Unity or Unreal engine acceptance.

**The word "implemented" below means present in repository software and subjected to automated tests; it does not mean proven in a running editor.** Source/target native execution and full cinematic fidelity remain explicitly unverified until the separate engine acceptance campaign.

## Architecture and exact boundaries

```text
[1] Unity source evidence ---------+
                                  +--> [2] CED source/target knowledge retrieval
[1] Unreal capability evidence ---+           |
                                              v
                                      [3] LangGraph source planning
                                              |
                                   [4] Validated strategy?
                                       | no               | yes
                                  bounded options -------+ 
                                              |
                                   [5] Source-bound compiled plan
                                              |
                                   [6] Guarded Unreal execution
                                              |
                                   [7] Native readback + CineTwin
                                              |
                                   [8] Bounded repair agent
                                              |
                                   [9] Remeasure or report limitation
```

**Cross-cutting invariants:** original Unity source/capture and native mapping byte identity; unique source occurrence inventory; CED candidates never equal native execution permission; model decisions are advisory and bounded; immutable action/approval plan; exact native target project/map/sequence; one claimed transfer attempt with no automatic replay; independent source/target measured comparison; at most two independent follow-up observations per bounded repair plan; no implicit fidelity, learning, or unsupported-domain completion.

## Source-code audit: all nine elements

| Element | Actual repository implementation | Software contract verified | Engine acceptance / remaining gap |
| --- | --- | --- | --- |
| **1 — Unity source and Unreal capability evidence** | `integrations/unity/com.cutsceneai.extractor/Editor/CutsceneAIStudioBridge.cs`; `tools/studio_unity_bridge.py`; `tools/studio_local_bridge.py`; `integrations/unreal/studio_local_editor_worker.py`; source census, captured CSIR, worker heartbeat and project fingerprint evidence | Source request identity, versioned native export receipt, Unity source hashing, exact target .uproject/level heartbeat, localhost/session/origin gates, no restart for already-connected editor; see `tests/studio/test_studio_unity_bridge.py`, `test_unity_editor_presence.py`, `test_studio_local_bridge.py` | Must compile and run source package in Unity Editor, connect an actual Unreal Editor 5.x instance and record real capability readback |
| **2 — CED knowledge retrieval and constrained rule promotion** | `packages/ced/ced_agent_knowledge.py`; CED dictionary, approved mapping/version compatibility, local discovery/case learning pipelines; `docs/studio/CED_HYBRID_COMPLETION_V02.md` | Per-source semantic coverage, target capability-conditioned registered options, privacy projection, approved-only promotion and no direct model tool rights; see `tests/studio/test_ced_hybrid_knowledge.py`, `test_ced_pretraining_integration.py`, `test_ced_auto_learning.py` | CED inference is not semantic execution; custom plugins, scripts, arbitrary shaders/assets and unknown source versions require new evidence/registration and native validation |
| **3 — LangGraph per-source AI planning** | `packages/studio/studio_conversion_graph.py`; `studio_element_plan.py`, `studio_element_schedule.py`, `studio_element_strategy.py`, `studio_element_investigation.py`; `tools/studio_element_workflow.py` | Every CSIR asset/entity/Timeline track/section/curve/relationship receives an anonymous stable source occurrence; dependent strategy scheduling/conflicts, bounded model response validation, candidate capability and CED provenance remain advisory. Tested through source-plan/agent/schedule suites | Actual model invocation requires the user-configured model/provider; synthetic test prompts are not proof a live model made correct decisions |
| **4 — Validated strategy and bounded alternatives** | `packages/studio/studio_element4_validation.py`; LangGraph bounded registered-option policy | Independent source/target/knowledge/dependency validation, permitted `report_only` fallback and at most two rejected-strategy reasoning rounds; no unregistered tools. `tests/studio/test_element4_* ` and integrated test directly rebuild the validation | True native compatibility and alternative effectiveness require a real target project and readback |
| **5 — Source-bound conversion plan** | `packages/studio/transfer_backend.py`, `integrations/unreal/csir_plan.py`, `packages/studio/studio_element5_plan.py` | Every actual compiled native action is accounted for, fingerprinted, structurally attributed to source location only where explicit evidence exists, and kept in original builder order. Unattributed legacy actions require separate approval; no fabricated equivalence | Registered action plans do not prove that animation/audio/events/materials execute equivalently |
| **6 — Guarded Unreal execution** | `packages/studio/studio_element6_execution.py`; `integrations/unreal/studio_element_native_gate.py`; `studio_local_editor_worker.py`; separate native operator approval | Exact candidate/source/plan/approval revalidation before scene writes; one durable native job claim, ordered stage receipts, multi-editor exclusion, no replay, no existing-sequence overwrite; synthetic worker tests cover stages and interruption | No actual engine-side execution, save and process-reopen verification on this integration branch |
| **7 — Native readback + CineTwin** | `integrations/unreal/studio_native_acceptance.py`, `cinetwin_tick_evaluator.py`, `packages/studio/studio_element7_readback.py`, `packages/cinetwin/behavior_compare.py` | Independent source-sampled comparison of actor transforms, skeletal joint positions/angular motion, physical CineCamera vertical FOV and camera-cut section timing; exact target actor/mapping/PID/plan/checksum and persisted acceptance rechecked. Supported observations remain **measured scope only** | Real reopening with separate editor process and authentic source/target captures; full joint orientation/skin, VFX, rendered projection, audio/event/simulation still separate |
| **8 — Bounded repair** | `packages/studio/studio_element8_repair.py`; `studio_agent_graph.py`, `agent_intent_router.py`; guarded `studio_agent_executor.py`, `studio_transform_repair.py`, `studio_visual_repair.py`, and newly added camera adapters (below) | Each suggestion grounded in exact current Element 7 readback and original source, user feedback and registered handler; full numeric remeasurement; one baseline + at most two distinct observations; stops on no progress/regression/exhaustion; original no-auto-replay remains intact | Native repair execution and rollback not yet proven in actual editor; numerical improvement is not a causal or fidelity certification |
| **9 — Remeasure or report limitation** | `packages/studio/studio_element9_outcome.py`, `studio_release_gate.py`, Studio Results and localhost `/api/final-outcome` | Every source occurrence accounted for even **before** engine acceptance; measured, unmapped, unsupported and unverified domains distinguished; stop-reason/budget preserved; immutable candidate-local final report; no release fidelity promotion | Final genuine end-to-end comparison is outstanding; report correctness does not imply generated cutscene correctness |

**Verification matrix scope:** This integration executes the repository's full Python/JavaScript/Ruff/hygiene/Windows-bootstrap CI, and adds an explicit cross-element test that independently verifies Element 2 CED retrieval, Element 3 plan/scheduling/strategy, Element 4 validation, Element 5 action/source reconciliation, Element 6 immutable claim, Element 7 native-readback comparator, Element 8 bounded triage, and Element 9 source-complete terminal outcome, using clearly labeled synthetic engine fixtures. The actual Unity/Unreal runtime has **not** been called.

## Existing + newly expanded native repair matrix

| Correction family | Current operation | Guarded eligibility | What is NOT proven |
| --- | --- | --- | --- |
| Character world translation | **Existing** `restore_constant_actor_offset`: one newly staged unparented character, full sampled constant offset; native actor + root motion separately read | Exact user-named character, source capture and target binding, no animated transform track, independent CineTwin/native diagnostics, post-edit max 2 cm actor and root, rollback | General moving character retargeting, yaw/orientation, articulated animation, full skin or footage |
| Source-provenanced base material | **Existing** `restore_source_albedo`: source-GUID validated imported material on newly staged fallback slots only | Exact import material GUID/hash and target slot, no overwrite of unrelated/nondefault slot, independent native material count | Shader/URP/PBR graph parity, textures under custom shader semantics, rendered-image parity |
| Constant physical CineCamera FOV | **New software-implemented** `restore_static_camera_lens` | One source camera, constant source vertical FOV, one native CineCamera, constant observed filmback/focal across original CineTwin grid, ≤35° disparity, no native FOV/property animation owner, explicit user lens request, live independent source/baseline, native constrained property setter/rollback, post-edit native physical optics readback | Animated zoom, camera shake, rendered projection equivalence, verified reopened behavior |
| Single camera-cut boundary | **New software-implemented** `restore_single_camera_cut_timing` | One source-authored frame-aligned camera cut, one native observed cut track/section and exact camera binding, mismatch ≤8 frames, no nested/multi-shot/subsequence rewrite, explicit user cut-timing request, same source, rollback and native readback | Multiple cameras/overlapping cuts, camera blending, shot track rewrite, actual rendered camera switching, verified reopened behavior |
| Character yaw/mesh forward axis | **Diagnostic-only** | Can identify actor rotation vs mesh/rig/Sequencer root causes but lacks a single safe, independently validated writable adapter | Arbitrary rotation edits could corrupt animation, root motion, attachments |
| Skeletal retarget calibration/root motion blending | **Diagnostic-only** for generalized repairs | Existing conversion-time IK profile validation/readback continues, but not a universal independently rollback-safe repair | Unknown rigs/skeletons/moving-root behavior, dynamic blends/constraints |
| Lighting intensity/exposure/shadows | **Compiler/native-action support may exist; no general autonomous repair** | CED may plan light intensity or registered component metadata; missing independent target-domain parity and safe post-generation repair contract | Lighting/render and source postprocess equivalence |
| General audio/dialogue and custom events | **Compiler candidates/report-only; not verified autonomous repair** | Source timing and original plan may be recorded; Unity callbacks/side effects are not equivalent to Sequencer markers | Waveform alignment, signal side effects, lip sync and audio render |
| VFX, physics, cloth, complex materials, scripts and custom plugins | **Report-only** | Version/source-semantic evidence and approved independent native adapters required first | Universal runtime transfer or full fidelity |

New camera repair decisions pass **redacted** source occurrence IDs and source-evidence hashes through LangGraph; actual camera/section names and numeric parameters are reconstructed independently in the guarded native editor from source and CineTwin evidence. No AI-generated code or native actions are accepted. Both are opt-in, user-scoped, bounded by two cumulative repair receipts, and recheck exact project/map/sequence before native mutation. A successful native property/section save is **not a CineTwin post-reopen or rendered-cut PASS**.

## Consolidation boundaries and reviewer checklist

1. **Single ancestry:** PR #149 includes every upstream draft Element 3–9 change, not just latest file snapshots. Older draft PRs remain useful as historical code review records; do not merge them on top of PR #149.
2. **Deterministic compiler is the final source of Unreal actions:** CED and model reasoning may discover/suggest, but cannot register arbitrary engine commands. Elements 4/5/6 all independently enforce action/capability/consent boundaries.
3. **Model is not engine authority:** A native repair request contains only known strategy identity, exact user feedback ID and source-bound source/measurement digest. It does not contain executable Python, numeric camera FOV, cut frame boundaries, arbitrary Unreal asset paths, or new tool registration.
4. **Native rollback and no retry:** Static lens and one-section cut adapters restore original editor values if their initial readback or save fails. Interrupted repairs have durable write-ahead claims and cannot be replayed. Real editor save-after-failure and rollback behavior remain unverified.
5. **False-positive prevention:** No solver is allowed to claim full cinematic fidelity from actor positions, material fallback count, native camera property, a recorded builder receipt, an approved CED suggestion, a green CI run or a stale/copyable JSON.
6. **Model/content risks:** Raw source identifiers, user paths and engine-authored numerical repair parameters stay out of model-visible summaries. Unknown source CED categories, unregistered plugins and unsupported target capabilities remain reported limitations.
7. **Re-open before release:** Save/reopen in a second Unreal process and capture actual CineTwin time grid; compare matched-frame actor/skeletal/camera/cut behavior, actual level/sequence/save persistence, color/rendered frames, audio/events, physics, light and held-out projects.
8. **No automatic learning from weak labels:** Synthetic, interrupted, user-unconfirmed and merely improved (but not independently validated) examples cannot be treated as successful training data for generalization.

## Deferred engine acceptance protocol

Later, on a disposable backed-up Unity/Unreal pair using **the exact same commit**:
- Compile and connect the Unity C# bridge; export a real PlayableDirector Timeline with source CSIR, census and Play Mode CineTwin.
- Connect a real Unreal companion in the *already-open* target editor and validate runtime capabilities and native operation preflight. Prepare and approve a unique action-bound candidate once.
- Generate exactly one staging sequence; save level, sequence and all imported referenced assets. Reopen the target in a distinct editor process.
- Run `studio_native_acceptance.start()`; collect raw target observations, persistence evidence and recomputed Element 7 results. Review Element 8 bounded diagnostics and Element 9 terminal source outcomes.
- Use explicit user feedback to authorize a single camera-lens or single cut timing repair only when the source and native baseline satisfy all current guards; record rollback/receipt/save and collect **another** independent reopened CineTwin observation before calling it improved.
- Independently compare rendering, shading, calibrated full skeleton, audio/event behavior and scene behavior on multiple real/held-out projects. Remain **INCOMPLETE** or **BLOCKED** where such evidence is missing.

**Current status:** integrated source, data and safety contracts are software-tested, not engine-proven. More general autonomous repair adapters and full cinematic fidelity remain open engineering work.