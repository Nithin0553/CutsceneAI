# Element 9 — Remeasure or Report Limitation (v0.1)

**Canonical architecture:** Unity source evidence + Unreal capability evidence → CED retrieval → LangGraph AI planning → validated strategy / bounded alternatives (**Element 4**) → source-bound conversion plan (**Element 5**) → guarded Unreal execution (**Element 6**) → native readback + CineTwin (**Element 7**) → bounded repair (**Element 8**) → **Element 9: Remeasure or report limitation**.

**Stack:** `feature/element9-final-remeasurement-and-limitations-v0.1`, based on draft Element 8 PR #147. We continue completing Studio software before any native Unity/Unreal editor acceptance.

## What this stage actually does

Element 9 is the *outcome reporting/stop decision*, not another executor, planner, model or native repair adapter. It independently reconstructs the **same original prepared Unity source** and the exact Element 3/4/5 source inventory. When supported native evidence exists, it also reconstructs Element 7's reopened source/target sample comparison and Element 8's **one baseline plus at most two distinct follow-up measurements**.

Every occurrence (Unity assets, entities, Timeline tracks, sections, curves and relationships) receives a redacted status and conservative next-evidence step. At no point does an unmeasured element become verified simply because the Level Sequence was generated, an AI model selected a candidate or a different domain passed.

**Before any real-engine test:** a saved job whose original source/plan is still intact produces an explicit `NATIVE_ACCEPTANCE_PENDING_ALL_SOURCE_OCCURRENCES_UNVERIFIED` outcome. No local Unreal work is started. Elements with unknown semantics or no mapped destination retain their separate source limitations rather than being silently omitted.

**After independently reproducible native CineTwin evidence:**
- If a direct measured difference remains, report it and identify either a *separately user-authorized, narrowly supported native adapter review* or a limitation. This is never a native edit permission.
- If remeasurement improves the numerical discrepancy, record measured progress but **do not claim a repair caused it**.
- If measured domains have no flagged difference, mark *measured scope only*, never entire cinematic parity.
- If the source element is unmapped, has incomplete skeletal measurements, is unknown/unmeasured, or lacks exact native action attribution, keep that limitation explicit.
- If repeated remeasurement makes no progress or regresses, stop with `STOP_REPAIR_NO_MEASURED_IMPROVEMENT_REPORT_LIMITATIONS`.
- If the maximum two follow-up observations were used, stop with `STOP_REMEASUREMENT_BUDGET_REPORT_LIMITATIONS`.
- If source files, mapping, plan, candidate/job identity, Element 3/4/5 provenance, Element 6 receipt, native observation or Element 7/8 report changed, reject the output instead of silently falling back to a clean result.

The outcome also contains a **domain coverage matrix** for measured actor transform, skeletal motion, camera lens and camera cuts, and explicitly unverified rendered-frame parity, full skeletal pose/retargeting, audio/events, physics/simulation, materials/lighting, gameplay/scripts and held-out project validation. CineTwin's own unverified domain list is preserved.

## Implementation and API

`packages/studio/studio_element9_outcome.py` provides:

- `build(workspace, job_id, evidence_folders=None)`: pure, deterministic source-complete terminal report; no background jobs, engine calls or native writes. Without an explicit ordered observation list it discovers candidate-local `native-acceptance-*` folders, rejects incomplete evidence and duplicate/excess observations, and displays filesystem-mtime ordering as **not** engine-attested causal timing.
- `verify(report, workspace, job_id, evidence_folders=None)`: rebuilds from raw source, native comparison and bounded repair records; rejects a forged result even if the attacker recomputes its own report SHA-256.
- `save_once(...)`: optional immutable candidate-local content-addressed JSON for records and research. An existing report is reverified, not overwritten. No engine state or operator permissions are changed.
- `page(report, offset=0)`: compact anonymous 50-occurrence pages with stable final-outcome fingerprint.

`tools/studio_local_bridge.py` exposes the read-only localhost `GET /api/final-outcome?offset=N`, limited to the **active Studio job** and its exact candidate. An unknown query parameter or malformed offset fails; no user-controlled filesystem path is accepted.

`apps/studio-web/app.js` adds **Element 9** in Results with a deliberate "Check final source outcome" control, source count, native observation count, limited manual remeasurement budget, conservative next step and source pagination. The UI never shows raw proprietary actor names, Unity asset paths or Unreal native actor IDs in this report. It refreshes only on user demand and invalidates cached evidence when the active job changes.

`packages/studio/studio_release_gate.py` independently reconstructs Element 9 and records `element9_final_outcome_accounting`. A *PASS* on this one check confirms **source accounting/report consistency**, **not** source-to-target cinematic fidelity. All existing requirements for rendered parity, audio/event playback, full skeletal behavior, native acceptance and held-out validation remain separate, and `release_ready` stays false whenever they are missing.

All reports include immutable source/job fingerprints, per-occurrence measurement and progress status, required domain limitations, and fixed `native_repair_authorized=false`, `automatic_native_retry_authorized=false`, `full_cutscene_fidelity_verified=false`, `release_ready=false`.

## Software regression acceptance

`tests/studio/test_element9_final_outcome.py` tests no-engine/no-observation source completeness; legacy source inventory; full measured-scope (not cinematic) result; missing mapping; remaining 7 cm error; 7→4 cm numeric progress without causal claims; repeated 7→7 cm no-progress stop; two-follow-up budget exhaustion; forged report with new hash; original Unity CSIR modification; missing Element 7 evidence in an existing native folder; missing Element 6 execution claim; immutable saving and pagination; release-readiness status; localhost API refusal of foreign/invalid requests and no filesystem side effects.

## Deferred engine and product acceptance

This implementation does **not** execute a real Unity or Unreal editor, measure an actual rendered cutscene, repair a real character, verify rollback, or prove any domain not captured by CineTwin. A generated JSON fixture or a green CI build is software evidence, **not** real editor provenance. Final engine acceptance still requires saved/reopened Unreal sequences, authenticated source and target captures, independent visual/audio/event testing, challenging skeletal/motion scenes and held-out projects.

**After Element 9:** the architecture's decision loop is represented in Studio software, but wider autonomous repair adapter coverage, native compiler completeness, PR integration into the release candidate and actual engine-based acceptance remain separate open work. Do not claim universal cutscene transfer fidelity.
