# Phase 10.1 — Studio Software Gap Audit (Elements 1–9)

**Audit date:** 2026-11-22  
**Baseline audited:** `7e6ccd90530b184ff2ee9b378ae304ad59cd55fc` on `integration/element1-9-guarded-repair-expansion-v0.1` ([integration draft PR #149](https://github.com/Nithin0553/CutsceneAI/pull/149)).  
**Corrections:** `audit/phase10-1-studio-flow-gaps-v0.1` ([draft PR #151](https://github.com/Nithin0553/CutsceneAI/pull/151)), stacked on integration, not directly on the release candidate or `main`.  
**Decision:** **CODE AUDITED; PRE-ENGINE SOFTWARE FREEZE NOT YET AUTHORIZED.** No real Unity or Unreal editor was run as part of this audit.

## Method and confidence

Reviewed the 507-blob integrated repository tree, the canonical Elements 1–9 audit, source/evidence/approval/plan/execution/readback/repair/outcome modules, both separately loaded browser implementations, localhost GET/POST routes, one-click autopilot, existing release and setup contracts, and regression coverage. The earlier integrated head passed 1,538 Python tests (7 skipped) plus Studio JavaScript, lint, CED and Windows bootstrap checks. That is **software regression evidence**, not real native verification.

The homepage loads `apps/studio-web/cinematic.js` in the default one-click mode; `?manual=1` exposes research steps in that script; `?advanced=1` loads the separate `apps/studio-web/app.js`. These are intentional supported entrypoints, **not unused duplicates**. Any change to a production-facing job state must account for both implementations.

Classification used below:
- **CONNECTED / SOFTWARE-TESTED:** source module and the relevant route or caller exist and automated fixtures cover the behavior.
- **PARTIAL / DEFERRED:** supported subsets exist; named additional semantics need registered adapters, independent observations or packaging work.
- **ENGINE-UNVERIFIED:** requires actual Unity compilation, Unreal native operation, editor save/reopen or independently measured rendered behavior.

## Element-by-element wiring and remaining scope

| Element | Source and integration path reviewed | Software conclusion | Remaining boundary |
| --- | --- | --- | --- |
| **1 — Unity and Unreal evidence** | Unity `CutsceneAIStudioBridge.cs`, source CSIR/census and CineTwin, `studio_unity_bridge.py`, `studio_local_editor_worker.py`, `/api/unity-source`, `/api/status` | CONNECTED: explicit source request, heartbeat/project fingerprint and worker capability gates; editor-refresh logic exists | Actual C# compile/domain reload and editor-target probe remain ENGINE-UNVERIFIED; wider semantic component census PARTIAL |
| **2 — CED knowledge** | `packages/studio/ced_agent_knowledge.py`, `packages/ced/ced_agent_knowledge.py`, local CED records and feature/mapping registries | CONNECTED: contextual source/capability retrieval and approved registration separated from engine write authority | Unknown engine/component combinations must be investigated and refused, not inferred into native capability |
| **3 — LangGraph planning** | `studio_conversion_graph.py`, `studio_element_plan.py`, schedule, strategy, investigation, `tools/studio_element_workflow.py` | CONNECTED: per-source occurrence inventory, bounded options, dependency scheduling and model data boundaries | Live model/provider behavior not established by mocked CI; source/rig/track combinations beyond supported contracts PARTIAL |
| **4 — Strategy validation** | `studio_element4_validation.py` and workflow/alternative check | CONNECTED: independent validation, bounded alternatives and report-only fallback | Native compatibility cannot be presumed from a registered choice |
| **5 — Conversion plan** | `studio_element5_plan.py`, `transfer_backend.py`, `integrations/unreal/csir_plan.py` | CONNECTED: native action reconciliation and exact source/approval hashes | Some older compiled actions remain separately reviewed as unattributed; general cinematic semantics not proven |
| **6 — Guarded Unreal execution** | `studio_element6_execution.py`, `studio_element_native_gate.py`, `studio_local_editor_worker.py`, `/api/execute` | CONNECTED: once-only job claim, exact target and action checks, staged receipts and no automatic replay | Editor mutation, disk persistence and error recovery remain ENGINE-UNVERIFIED |
| **7 — Native CineTwin readback** | `studio_element7_readback.py`, `studio_native_acceptance.py`, behavior comparator, `/api/verification` | CONNECTED: independent, source-sampled measured actor/root, camera optics and cut timing comparisons with provenance; rejects incomplete native evidence | Renderer/projection, calibrated full joint pose, signals/audio, simulation and true distinct-editor reopen ENGINE-UNVERIFIED |
| **8 — Bounded repair** | `studio_element8_repair.py`, `studio_agent_graph.py`, `studio_agent_executor.py` and registered Unreal repair files | CONNECTED for **five narrow families**: material albedo, one constant character offset, static physical camera lens, one camera-cut boundary, and static camera world position | Character facing/forward-axis, retarget/blend ownership, camera tracking, animation, audio, VFX, full lighting and custom event repairs are **not** general autonomous capabilities |
| **9 — Terminal outcome** | `studio_element9_outcome.py`, `studio_release_gate.py`, `/api/final-outcome`, advanced Results | CONNECTED: source-complete outcome ledger, unverified domains and bounded repair stop reasons remain explicit | Normal one-click Results do **not yet** expose the full per-occurrence Element 9 outcome; native measured parity still pending |

## Confirmed software defects corrected in this audit

| ID | Severity | Confirmed code path and problem | Correction / regression |
| --- | --- | --- | --- |
| **GAP-10.1-01** | High | `cinematic.js` previously ignored the autopilot/native job ID mismatch after a new run became **BLOCKED** or **CANCELLED**. A previous completed native job could therefore reappear as a new run's result | Require the current autopilot run's exact `job_id` for **every** active run status, not only nonterminal statuses; Node regression tests old generated job followed by blocked/cancelled run |
| **GAP-10.1-02** | High | `cinematic.js` and `app.js` retained results, diagnostics, release state and AI/CineTwin evidence when the active native job changed or disappeared outside the current browser tab | Invalidate job-scoped UI data at the identity boundary; Node integration tests exercise advanced job replacement and job removal |
| **GAP-10.1-03** | Medium | Local `GET /api/verification` and `GET /api/closed-loop` accessed a job filename derived from an unverified active pointer; damaged/orphaned active files could produce server exceptions or reference a foreign job | Validate lowercase hex job ID, reject job-file symlink, check embedded job identity, return explicit JSON 409 on invalid/missing evidence; Python HTTP boundary tests |
| **GAP-10.1-04** | Medium | CI branch filters did not include the current Elements 1–9 integration target or audit branches, so stacked review pushes could lack automatic checks | Expand push and PR CI filters to `integration/**` and `audit/**`; retain full existing Python, Node, CED and Windows jobs |
| **GAP-10.1-05** | Documentation | The release checklist still described autonomous repair as material-only, contradicting the integrated five-family allowlist; older Studio setup notes predate continuous editor bridge refresh | Update current-scope note and link this report instead of rewriting historical experiment logs |

## Prioritized remaining work after 10.1

| Priority | Finding | Recommended owner phase | Gate |
| --- | --- | --- | --- |
| **P1** | Default one-click Results lacks a user-friendly **Element 9 source-occurrence limitation report** even though `GET /api/final-outcome` exists and advanced mode has it | **10.3 — Orchestration/UI** | Display job-bound report and honest statuses without exposing raw private names; handle pagination and incomplete capture |
| **P1** | Wider character facing, calibrated retargeting, animated root ownership, camera tracking/zoom/cuts, material shader semantics and source events are not generally transferrable/repairable | **10.2 — Algorithm/adapter support** | Either implement a measured, guarded, native-registered subset with positive/refusal tests, or mark it unsupported in the versioned capability matrix |
| **P1** | Native companion first-run installer and self-contained desktop packaging are not proven; checkout-based Windows bootstrap is not a full distribution | **10.3/10.5 — Setup/freeze** | Verified installer/preflight contract and actionable setup errors before the workstation campaign |
| **P1** | Native readback currently covers measured subsets, not rendered frames, full skeletal orientation, audio waveform, effects or custom signal side effects | **10.2 and later engine campaign** | Preserve fail-closed release gate; do not promote absence of discrepancy in measured fields to cinematic parity |
| **P1** | End-to-end negative test matrix should include direct job switches during UI polling, partial native imports, source hash changes, wrong project/editor, and interruption at every native stage | **10.4 — Full synthetic rehearsal** | CI green with unique job/candidate receipt boundaries and no native replay |
| **Later / engine-only** | Real Unity C# compilation; actual provider call; live Unreal Python/native mutations; save/reopen in a distinct Unreal process; rendered and held-out cross-project fidelity | **First real-engine acceptance campaign** | Collect authentic independently observed evidence at one frozen source SHA; until then `ENGINE-UNVERIFIED` |

Do not treat the P1 items as all resolved by the high-level architecture or by the number of passing synthetic tests. A repair family is supported only when its own explicit native gate, source-matched test fixtures, rollback policy, and independent remeasurement contracts exist.

## 10.1 exit criteria

1. Trace all nine element contracts and the default/advanced browser paths to concrete source files and direct callers: **reviewed**.
2. Fix verified lifecycle/cross-job state defects with negative regression coverage: **implemented on the audit branch; CI result is a separate required check**.
3. Account for unsupported cinematic behaviors, untested native claims, and packaging limitations rather than labeling them done: **documented**.
4. Merge only reviewed, green audit changes into the current integration branch, avoiding all historical stacked PR re-merges: **pending PR review**.
5. **Do not declare a Studio software freeze** until Phases 10.2–10.5 address supported-scope decisions, UI completion, full synthetic E2E, and install/handoff criteria.

### Reproducible software-only checks

From the repository root:

```bash
python -m compileall -q packages tools integrations/unreal
python -m pytest -q
node --check apps/studio-web/app.js
node --check apps/studio-web/cinematic.js
node tests/studio/test_cinematic_ui.cjs
python -m ruff check tests
python tools/repo_check.py
```

The Windows dependency bootstrap and CED model integrity workflow run separately in `.github/workflows/ci.yml`. None invokes a real Unity/Unreal editor. See [Elements 1–9 integrated audit](ELEMENT1_TO_9_INTEGRATED_AUDIT_AND_REPAIR_EXPANSION_V01.md), [end-to-end software contract](END_TO_END_STUDIO_SOFTWARE_COMPLETION.md), and [release acceptance](RELEASE_ACCEPTANCE.md).
