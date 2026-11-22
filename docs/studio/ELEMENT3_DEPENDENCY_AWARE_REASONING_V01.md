# Element 3.2 — Dependency-aware reasoning and resumable model reviews

**Branch:** feature/element3-dependency-aware-scheduling-v0.1, stacked on draft Element 3.1 PR #136.
**Scope:** Source-evidence dependency graph, conservative Timeline ownership checks, read-only advisory schedule, and bounded durable LLM review pages. Native execution and measured Unity/Unreal acceptance are **not** claimed.

## Architecture

The new packages/studio/studio_element_schedule.py consumes the **existing** Element 3.1 plan and exact CSIR. It does not invent a second Unity identity map or native action registry. It emits a version-1 cutsceneai.studio.element_dependency_schedule with:

- All source occurrence IDs, stable topological waves and explicit unscheduled occurrences.
- Strongly connected component detection that reports actual dependency cycles separately from elements merely blocked downstream.
- Missing/ambiguous source dependency propagation.
- Same-source-actor transform writer and overlapping clip checks; Timeline blend/ease envelopes without an independently baked/verified native result are marked as conflicts, not silently scheduled.
- Actor-specific ownership derived **only** from already resolved, anonymous source-plan dependencies.
- Report-only, ownership-blocked, upstream-unplanned and native-preflight-required **advisory** states for every occurrence. Proposed action waves never authorize execution.

Source object names, raw Unity IDs, private asset paths and native code do not appear in schedule outputs. studio_transfer_ai.inspect builds the baseline schedule; decide rebuilds it after opt-in model choices; verify **independently reconstructs** the complete schedule from current source evidence immediately before native candidate preparation. A forged checksum cannot excuse reordered waves, hidden conflicts or omitted elements.

The existing deterministic native converter remains authoritative. The schedule is **not** wired to run the Unreal dispatcher: that would falsely turn per-element proposals into execution, bypassing native preflight and CineTwin evidence. Conflicting transform layers still require a measured bake/retargeting solution and actual native target readback.

## Durable LLM pagination

CUTSCENEAI_ELEMENT_PLANNING=model remains opt-in. The model must return exactly one advisory choice for every source occurrence, in pages of 12 anonymous elements. For scenes with more than 256 occurrences, progress now uses packages/studio/studio_element_review_checkpoint.py:

- A source-plan SHA-256, model identity and fixed batch size bind the checkpoint.
- Each page is persisted **only after** strict source membership, registered-action and graph-blocker validation.
- File replacement is atomic, writes are flushed to disk and a per-source exclusive lock avoids concurrent reviewers overwriting one another.
- On a later run with identical evidence and model, saved pages are replayed through the same strict validator. The first missing page is requested next; no completed prefix is silently skipped.
- Checkpoint content includes **only** redacted occurrence IDs, advisory choices and response digests. It never contains the original CSIR, raw source IDs, file paths or native execution instructions.
- By default, at most **32 new model pages per invocation** are requested for large scenes. CUTSCENEAI_ELEMENT_REVIEW_MAX_NEW_PAGES can set a positive 1–9999 page limit. An incomplete run exits explicitly **before any native preparation**, retaining validated pages to resume when run again.
- Checkpoints live under the Studio user's home directory at .cutsceneai-studio/element-reviews/<element-plan-sha256>.json. Files and lock files are not part of Git. A stale lock after a process crash must be inspected and manually cleared only when no review is running.

These checkpoints provide interruption recovery, not cryptographic attestation of a model provider's output. Any replayed choice is still only an unverified candidate. Changing source, CED retrieval, observed target capabilities or configured model invalidates reuse. No checkpoint can grant native execution permission.

## What is covered by software tests

- Reproducible DAG order across assets, parent entities, bindings, sections and animation curves.
- Exact cycle members vs downstream-blocked nodes; missing source dependencies and propagated blockers.
- Same actor/track multiple transform writers, overlapping section ownership, isolated actors, unproven section timing and unbaked blend envelopes.
- All-source-occurrence accounting for 300-element scenes.
- Modified schedule rejection even when its digest is recomputed.
- 257-element/22-page model review, interrupted checkpoint resumption, complete cached replay, tampered choices, stale evidence/model, exclusive lock and explicit model blocker refusal.

## Still required before declaring Element 3 fully implemented

Phase 3.3 will compare context-specific CED strategies with independently verified experience. Phase 3.4 will investigate unresolved cases and discover registered alternatives. Phase 3.5 will perform per-element CineTwin discrepancy analysis and controlled, independently remeasured recovery. None of these exists merely because a dependency schedule can order advisory actions.

**Acceptance remains pending:** compilation and real execution in connected Unity/Unreal, native source/target readback for held-out cutscenes, correct cross-engine motion, actor binding, material/camera fidelity, mixed animation blending and user-facing large-scene progress UX. No scene can claim successful conversion based on source-ordering or cached model suggestions alone.
