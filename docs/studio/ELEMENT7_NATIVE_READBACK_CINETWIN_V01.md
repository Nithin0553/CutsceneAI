# Element 7 — Native Readback + CineTwin (v0.1)

**Architecture:** Unity source evidence + Unreal capability evidence → CED retrieval → LangGraph AI planning → validated strategy / bounded alternative reasoning (Element 4) → source-bound conversion plan (Element 5) → guarded Unreal execution (Element 6) → **native readback + CineTwin (Element 7)** → bounded repair → remeasure/report limitation.

**Stack base:** Element 6 `feature/element6-guarded-unreal-execution-v0.1` (draft PR #145). This phase provides **software-tested preparation for real engine acceptance**. It does not assert that a local Unreal or Unity editor was run, or that full cinematic fidelity has been established.

## Prior existing native infrastructure

- `integrations/unreal/cinetwin_tick_evaluator.py` already samples Sequencer after editor tick intervals. It saves real observed actor transforms, native skeletal bones, camera lens state and Sequencer camera-cut sections at source-authored frame/boundary times. It reports unavailable rigs, missing mappings, observation quality and unsupported capture layers.
- `packages/cinetwin/behavior_compare.py` already recomputes actor trajectory errors, sampled joint positions and angular motion, physical CineCamera vertical FOV, and camera-cut timing from the raw Unity/Unreal observations. Joint absolute orientation/calibration, anatomical mesh-forward, rendering, audio, events, and physics remain separately gated.
- `integrations/unreal/studio_native_acceptance.py` already captures reopened-editor persistence evidence and callback-based native samples in a **different** editor process.
- Element 3.5 independently attributes those measured differences to the original anonymous Unity source occurrences without confusing linked Timeline contexts with causal attribution.
- Element 6 now provides a candidate-bound exclusive one-attempt native execution claim, exact compiler/authorization fingerprints, ordered irreversible checkpoints and a conservative builder receipt.

Element 7 does not replace these measured-domain tools. It binds them into **one reproducible read-only contract**.

## New Element 7 verification service

`packages/studio/studio_element7_readback.py` exposes `build(workspace, job_id, evidence_folder)` and `verify(report, workspace, job_id, evidence_folder)`. Both use the same saved evidence files; verification recomputes all fields rather than trusting a self-rehashed JSON summary.

**Source and native identity:**
- Requires the exact saved job, original immutable candidate-local session, original Unity CSIR and source capture **byte hashes**, target mapping, compiled native plan, exact output Level Sequence and candidate-owned `native-acceptance-*/` folder. Foreign candidate paths, linked files, oversized evidence, changed plan/session/mapping and mismatched source projects fail.
- Independently recreates the source sampling plan using **actual CSIR bytes** and validates the source observation grid. Both source and target snapshots must pass the existing CineTwin comparator. Per-sample mismatches, extra/missing entities, incomplete skeletal rig mapping, native optical discrepancies and altered timing cannot be replaced by a new claim of PASS.
- Independently rebuilds the **target observation request from the actual prepared mapping**. Sampled actor labels, exactly unmapped Unity entities, native skeletal-bone correspondences and mapped/source counts must match the original mapping. Even an attacker-recomputed clean CineTwin comparison cannot silently reinterpret a different target actor as the approved Unity object.
- Requires a distinct generation/observation editor PID, exact target sequence, matching `.uproject` bytes and project-path identity, source-bound target persistence audit and target editor quality metadata. The status differentiates tick-synchronized full coverage *reported by the native capture file* from missing or suspicious evidence; files alone are **not independent cryptographic proof** that an editor executed.
- Replays the original CineTwin metric computation for actor poses, skeletal joint positions/angular motion, camera optics and shot cuts, including source-bound optional rig-pose calibration and mesh-forward approvals. The reopened acceptance status must be consistent with recomputed measurements. All other unsupported or unmeasured domains remain explicit.
- Independently checks the original Element 6 exclusive claim and immutable input fingerprints, claim owner PID, completed ordered stage journal, terminal builder receipt and exact native runtime-receipt bytes. An unrecorded or interrupted legacy execution remains `INCOMPLETE`; neither creates a new claim nor authorizes replay.
- For a candidate with an active Element 3 source workflow, verifies the complete **original SHA-256-bound workflow snapshot**, Element 4 validation, Element 5 source/action reconciliation, exact compiled action inventory and separately approved native operator grant. Then independently recomputes per-occurrence attribution across all original assets, entities, tracks, sections, curves and relationships. Only anonymous `E00000` occurrence IDs, measured state codes and discrepancy codes are exposed.
- Emits a read-only SHA-256-bound `element7-readback.json` with `MEASURED_NATIVE_DIFFERENCES_DETECTED`, `NATIVE_MEASURED_SCOPE_INCOMPLETE` or `MEASURED_NATIVE_SCOPE_WITHIN_TOLERANCE`. All outcomes retain `native_repair_authorized=false`, `native_retry_authorized=false`, `full_cutscene_fidelity_verified=false` and `independent_engine_attestation_verified=false`.

## Real native capture integration

`integrations/unreal/studio_native_acceptance.py` writes the native comparison from genuine reopened target samples. After a proper `cinetwin.sampling_plan` completes, its callback invokes the independent Element 7 reconstruction and saves **one** `element7-readback.json` within the same candidate-local native acceptance directory. If calibration or mesh-forward evidence was selected, it copies the verified original JSON bytes into that acceptance directory first; later reconstruction must use the same hashes, not an unrecorded updated calibration.

A malformed source, stale native claim, bad comparison or changed calibration prevents Element 7 acceptance. The existing studio/editor worker remains the only native execution authority.

`packages/studio/studio_release_gate.py` independently re-verifies the original raw evidence and Element 7 report on every release check. It exposes two separate statuses: `element7_native_execution_chain` for the originating native builder/one-attempt proof and `element7_cinetwin_recomputation` for reopened measured-domain comparison. Missing legacy reports remain INCOMPLETE; forged or changed evidence becomes FAIL. Even a measured-domain PASS **never** marks a full release ready while rendered-frame parity, audio/events, physics, held-out validation and other required domains are missing.

`apps/studio-web/app.js` includes an explicit Element 7 section in Results, with the execution-chain status, independently recomputed CineTwin result, sampled frames and unmapped actors. It keeps the original real-engine acceptance command as an opt-in, explicit future step.

## Software-only acceptance requirements

1. Exact-source CSIR, sampling time grid, capture, source->target mapping, native sequence, editor process and project identity bound to one candidate; no substituted results.
2. The recorded reopened comparison must agree with **independently recomputed** actor/rig/camera/cut metrics and measured acceptance verdict; fabricated/self-rehashed PASS labels are rejected.
3. Source completeness and anonymous per-occurrence attribution when an Element 3 workflow exists; missing or disputed source elements remain unresolved, never silently converted.
4. Exact Element 6 claimed native attempt, immutable source/plan/approval fingerprints, stage journal and runtime receipt are required for `SOURCE_BOUND_NATIVE_BUILDER_COMPLETED`. Legacy/missing/partial attempts remain incomplete and cannot replay.
5. Missing/altered calibration and native lens evidence cannot be inferred or replaced by heuristics. Unknowns remain visible without private source names or engine filesystem paths.
6. No native writes, no new Unreal adapter permissions, no AI-generated engine code or automatic repair in Element 7.
7. A measured-scope PASS is not full cutscene fidelity or a claim that these synthetic software tests invoked a real editor.

## Pending external acceptance

Open the backed-up target in a **different** Unreal Editor process after an actual source-authenticated generation, with matching Unity CineTwin source observations, and run the existing `studio_native_acceptance.start()` script. Inspect the produced independent `element7-readback.json` through the Studio release check. Verify actual skeletal retarget calibration and native material/camera/animation behavior for real cutscenes. Conduct independent rendered-frame, audio/event, physics, and multiple real-project comparisons before any whole-cutscene fidelity claim.

**No Unity/Unreal real-engine test is performed by this PR.**
