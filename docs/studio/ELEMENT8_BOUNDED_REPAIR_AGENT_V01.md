# Element 8 — Bounded Repair Agent (v0.1)

**Architecture:** Unity source evidence + Unreal capability evidence → CED retrieval → LangGraph AI planning → validated strategy (Element 4) → source-bound conversion plan (Element 5) → guarded Unreal execution (Element 6) → independently recomputed native readback + CineTwin (Element 7) → **bounded repair agent (Element 8)** → remeasure or report limitation.

**Branch:** `feature/element8-bounded-cinetwin-repair-agent-v0.1`, stacked on Element 7 draft PR #146. **All changes are software-only; Unity and Unreal editor acceptance is still deferred.**

## Design and the existing trusted adapters

CutSceneAI already provides a narrowly scoped, opt-in LangGraph repair path (`packages/studio/studio_agent_graph.py` and `integrations/unreal/studio_agent_executor.py`) and two separately guarded native policies:
- `studio_transform_repair.attempt` corrects **one** newly staged unparented character's constant placement offset only after independent source-bound actor/root evidence, a fresh Unreal readback, an exact natural-language user correction, original diagnostic file validation and post-edit remeasurement. It rolls back when native actor/root errors fail to improve and does not save a failed placement.
- `studio_visual_repair.attempt` restores only source-GUID-provenanced albedo on newly staged Unreal fallback material slots, after original import manifest and changed slot checks. It cannot infer shader, pipeline, render or full cutscene parity.

Element 8 **does not add arbitrary Unreal actions**, allow a model to output native Python, bypass explicit user feedback, or authorize any native retry. It extends the existing agent and its editor executor with stronger original-source CineTwin evidence gating.

## Exact-source recovery triage

`packages/studio/studio_element8_repair.py` exposes `build(workspace, job_id, evidence_folders)`, `verify(...)`, `save_once(...)` and `select_advisory(...)`.

Each input must be an Element 7 independently reproducible readback belonging to the **same native job, same original Unity source/capture, same mapping, same compiled plan, same candidate, same output sequence, and same finished Element 6 single native attempt**. Forged, foreign, symlinked, oversized, rehashed or partial results fail closed. The full raw CineTwin source-target samples and all required Element 3/4/5 approvals are re-verified. No synthetic outcome or saved PASS label can replace the original frames.

The repair agent accepts **one baseline and at most two distinct native follow-up measurements**. It reuses CineTwin's numeric error and exact source-occurrence comparison. An identical capture is not a second independent measurement; a newly hashed report with unchanged motion cannot count as improvement. Regression or no measured improvement stops the repair suggestion, and a used budget cannot reset by changing a model prompt or submitting another response.

Every source occurrence is classified using anonymous `E00000` IDs and a fixed, non-executable advice vocabulary. Different measured actor transforms, unsupported skeletal rig and bone orientation, global lens/cut timing discrepancies, unmapped target actors, and unmeasured assets/tracks/sections/curves/relationships remain distinct. A camera-cut timing mismatch is global, not automatically attributed as causally defective Timeline section.

The only positive *character-repair review* hint is the pre-existing `INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY`, and only for an independently observed single-character world-position discrepancy with no additional flagged error or failing joint proof. It **does not** approve a native modification. The existing offset adapter still independently checks exact actor identity, source/target frames, explicit single-target user feedback, real editor project/sequence/level, setup receipt, actor ancestry, fresh native readback, rollback and saved-state audit.

No automatic skeletal, camera, audio, material animation, event, or physics repair is introduced. Material restoration remains separately subject to its original source-provenanced visual-adapter policy; Element 8 does not pretend that CineTwin actor positions prove material correctness.

## Studio agent, worker, and release gating

`studio_agent_graph` now inspects verified Element 7 native evidence when available, includes a redacted Element 8 summary in the LangGraph reasoner's context, and refuses to select a constant actor offset if Element 8 reports no corresponding safe review candidate, regression, or exhausted observation budget.

`studio_agent_executor` independently recomputes Element 8 from the original exact evidence before running its existing native actor-offset adapter. This is a **separate engine-side guard** from what the model recommended. The existing write-ahead native agent-claim and two-repair-receipt budget remain in effect. No model response can override an unsupported candidate.

The older `studio_generation_recovery.recover_latest` helper now refuses to regenerate an Element 6-claimed job, closing an otherwise possible bypass of the new exclusive no-replay guarantee.

`studio_release_gate` independently evaluates Element 8's read-only recovery classification and returns a dedicated `element8_bounded_repair_triage` check. A triage PASS means only that source-bound recovery **decision safety** was checked, never that a repair executed or cinematic fidelity was proven. The Results UI displays the triage, remaining observation budget and explicit lack of automatic native retry. Open-editor module refresh loads the canonical Element 8 code without requiring repeated Unreal restarts.

## Status and strict boundaries

- A source occurrence with no native measurement or verified mapping remains **report-only/investigate**, not automatically repaired.
- A native pass within tolerance is **measured scope only**. Final persisted skeletal retargeting, full rendered video, lights, audio, events, gameplay physics and held-out projects still need independent tests.
- The new triage records include original source/target evidence fingerprints, measured deltas, progress/regression classifications and anonymized source-occurrence IDs, but not private actor names, local project file paths or model-generated coordinates.
- `native_repair_authorized=false`, `automatic_native_retry_authorized=false` and `full_cutscene_fidelity_verified=false` in every Element 8 report.
- The existing user-approved actor/material adapters can perform their narrow allowed edits later in a real, explicitly connected Unreal editor, subject to all original native preflight. No engine ran in this PR.

## Software acceptance

New `tests/studio/test_element8_bounded_repair.py` exercises the complete Element 7 raw sample fixture; exact-source provenance; eligible/rejected actor-offset advice; unknown target mapping; optional camera lens/cut domain findings; model override rejection; 7 cm → 4 cm genuine measured progress; no progress; reused capture rejection; exhausted two-remeasurement budget; stale/tampered report; legacy/interrupted native attempt; Studio release gate; LangGraph redacted input and Unreal executor independently blocking unsupported offset; hot reload and legacy generator replay rejection.

The test suite's fake native captures are **not evidence that Unity or Unreal ran**. Real reopened-editor CineTwin capture, opt-in native corrections, rollback/save behavior and full cinematic acceptance must still be tested in the later engine phase.
