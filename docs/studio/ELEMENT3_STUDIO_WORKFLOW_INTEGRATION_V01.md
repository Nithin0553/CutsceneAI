# Element 3 — Integrated Studio Candidate Review and Persistent CineTwin Evidence

**Stacked branch:** feature/element3-studio-workflow-integration-v0.1, based on draft PR #140 (Phase 3.5), stacked through PRs #139, #138, #137 and #136.

**Software workflow milestone:** This is not real Unity or Unreal acceptance. Every output remains advisory or limited to independently measured CineTwin domains. No LLM receives new engine tool permission, new native APIs are registered, or direct engine modifications occur in Element 3 review endpoints.

## Integration into the existing Studio UI

The normal Connect → Select → Review → Transfer → Results UI remains intact. Preparing a candidate still uses the existing source-authenticated transfer backend. On success, the Review page additionally invokes a read-only Element 3 inventory action. The operator can inspect a paginated source-bound report (up to 60 rows at a time), including CED semantic category, per-element source status, dependency blockers, registered strategy alternatives, investigation gaps and next evidence to collect.

A missing or unrecognized source semantic is not treated as converted. Imported assets, scenes, tracks, curves, Timeline sections and relationships remain distinct occurrences; model review, native preflight, measured transfer and whole-cutscene fidelity are not conflated.

The UI records an explicit **acknowledgment that the operator reviewed known source limitations**. This acknowledgment is bound to the exact active candidate, source CSIR, prepared mapping, immutable transfer-plan contents, CED knowledge snapshot and target capability observations. It grants **no native execution permission**, does not approve an AI-selected alternative, and does not replace destination readiness or explicit Generate confirmation. If a user prepared the Element 3 review, the existing native queue additionally requires a matching fresh acknowledgment before accepting that candidate. The legacy/editor-autopilot path remains unchanged when an Element 3 review was never prepared.

## Localhost read-only API

New tool: tools/studio_element_workflow.py. The local companion exposes:

- GET /api/elements?offset=0 — bounded read-only summary, one page of 60 anonymous source occurrences; does not return paths or raw vendor semantics.
- POST /api/elements/prepare with {} — deterministically builds a complete read-only Element 3.1–3.4 snapshot for the *active* prepared candidate, using the source CSIR, existing hybrid CED knowledge service, currently observed Unreal capabilities (or explicitly unobserved false capabilities), and exact immutable candidate files. No extra LLM call.
- POST /api/elements/acknowledge with {"workflow_sha256":"<exact digest>","reviewed":true} — records source-review acknowledgment, not a generic native action grant.
- POST /api/elements/verify-target with {"path":"<existing native CineTwin target capture>"} — validates full source capture and independent target temporal/actor/rig/camera comparison, produces an Element 3.5 per-occurrence attribution report, and saves the report persistently under the active candidate. A second and third distinct capture trigger bounded source-remeasured comparison, not native replay.

Mutating localhost endpoints retain origin, session token, JSON length and synchronized engine-host update guards. The independent artifact viewer rejects stale/rehashed source plans, changed mapping or transfer-plan bytes, a foreign candidate, stale CED knowledge, target capability changes, invalid native target sequence identity, altered target files, duplicated target captures, and two-remeasurement budget overflow.

## Candidate-local immutable evidence

The workflow stores a source/candidate/target-capability-bound Element 3 snapshot under candidates/<candidate_id>/element-workflow-<sha256>.json and a tiny active pointer; an explicit acknowledgment has its own integrity-checked receipt. Readback reports are stored in separate content-addressed, never-overwritten JSON files with a linked index of exact observed target-file hashes. When a new snapshot is prepared, an older index is archived; old acknowledgments and target readbacks cannot silently transfer to the new evidence.

GET independently reconstructs the source knowledge/plan/schedule/strategy/investigation from the current CSIR and exact selected snapshot capabilities and re-compares the stored result. It also reconstructs the current CineTwin measurement from the original Unity and Unreal captures rather than trusting a saved/rehashed measurement. The service exposes only source-bound anonymous IDs, safe semantic labels, bounded reason/action vocabulary and numeric measured values. Candidate source names and paths remain private to local workspace files.

An absent live Unreal capability probe means candidate actions remain **unobserved/unverified**. A later editor reconnection or source/target change requires re-evaluation and re-acknowledgment.

## Results integration

The existing Results screen can still inspect a target-only CineTwin observation if no matching Unity source capture is available. When an Element 3 review exists, submitting the target observation additionally attempts independent CineTwin comparison and presents retained per-element differences and remeasurement outcomes. A target-only file or incomplete capture cannot become a false source-to-target fidelity pass. The report continues to state that skeletal skin, rendered frame, audio, physical lens compositing, event execution and other unverified domains remain unverified.

The native repair path remains the existing explicit user-feedback, single-character-offset repair; the Element 3 workflow does not invoke it or treat a diagnostic suggestion as approval.

## Validation and remaining acceptance

Tests cover a full candidate inventory, unknown/unsupported semantics, exact-source and mapping tampering, native capability freshness, explicit acknowledgment before native submission, original legacy path compatibility, persisted two-snapshot evidence, capture changes, duplicate/foreign target rejection, integrity-laundered index refusal, pagination and localhost token/origin checks.

**Not completed by this phase:** end-to-end live Unity/Unreal editor acceptance, automatically executed per-element native builder actions, autonomous extraction of missing source evidence through engine tools, autonomous multi-domain recovery, and whole-cutscene rendered/audio/event fidelity. A full successful Studio release still requires held-out native acceptance on user-selected backed-up engine projects with independently saved/reopened readbacks.
