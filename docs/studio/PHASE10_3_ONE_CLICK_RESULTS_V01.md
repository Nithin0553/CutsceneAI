# Phase 10.3 — One-click Results and live connection orchestration (v0.1)

**Target:** Studio default browser workflow (`apps/studio-web/cinematic.js`) and
the localhost-only API (`tools/studio_local_bridge.py`). This increment builds
on merged Phase 10.2 integration commit
`af5d91edb6fc4af8f6c10775dd470a7481412b6f`. Real Unity/Unreal engine
testing remains deferred and is **not** implied by CI.

## Gap addressed

The Phase 10.1 gap audit identified that default one-click Results did not
expose Element 9's source-complete outcome, even though the advanced workspace
could request `/api/final-outcome`. Users would see "generated" and AI
conversation without an accessible account of unsupported or unmeasured
source elements. That can be misleading even if the underlying native contract
remains fail-closed.

## Implemented

1. **Compact Results reporting.** Default Results now show source occurrence
   counts, native observation count, available manual measurement budget,
   final status, next evidence action and outcome grouping. Full 50-entry
   pages are contained in a collapsed scrollable list with Previous/Next
   navigation. The view is dark, keyboard accessible and responsive.
2. **Explicit job binding.** The endpoint supports
   `GET /api/final-outcome?job_id=<32-lowercase-hex>&offset=<number>`.
   It compares the requested job with the active native job before rebuilding
   and returning source evidence, rejecting stale IDs, malformed/duplicate
   query values, foreign jobs and symlinked active pointers with HTTP 409.
   Existing advanced requests containing only `offset` remain supported.
3. **No cross-job report bleed.** The default UI clears Element 9 output on
   job removal, switch, fresh autopilot start or project reconnection. It
   refuses a late response if the job or active run changed while the
   request was pending. Each result page uses an exact native job ID.
4. **Incomplete evidence stays incomplete.** An unavailable report yields a
   visible, nonblocking message and a manual Refresh button. It is not
   automatically retried on every two-second status poll. Source report
   availability does not grant native retry, fresh engine execution, full
   fidelity or release readiness.
5. **Connection guidance.** The simple Projects view distinguishes a
   disconnected/mismatched Unreal project and a wrong target level, using
   existing destination-readiness instructions. No editor restart or
   automatic bridge mutation is triggered.

## Source and security contract

- The Element 9 builder and page renderer still recompute the immutable
  original source/re-measurement evidence; the frontend does not fabricate
  completion from a job's generated status.
- The UI renders only per-occurrence source IDs, source types, native action
  counts and outcome codes from the bounded, redacted page. It escapes all
  externally supplied strings.
- An earlier transfer, blocked/cancelled autopilot run, stale active job
  pointer or wrong `job_id` can never be used to populate the current
  Results source report.
- The browser never controls native writes or arbitrary callbacks.

## Software-only regression

- Python HTTP tests cover valid job-bound pages, mismatched or malformed
  `job_id`, empty/multiple offsets and unsupported query parameters.
- Node Studio UI fixtures cover automatic loading, 50-entry pagination,
  previous/next controls, unavailable native evidence without poll storms,
  manual recovery, blocked-run isolation and actionable offline Unreal status.
- CI additionally runs original Python source/engine adapters, Studio UI,
  syntax/lint, CED integrity and Windows bootstrap. It does not run either
  editor.

## Remaining Phase 10.3 scope

This is **Phase 10.3's first increment**, not the entire phase. The
remaining work includes broader default/advanced UI convergence, entire
per-stage orchestration diagnostics, companion first-run installation,
multi-project setup and repair UX, complete UI interruption simulations
and workstation packaging readiness. Phases 10.4/10.5 and Phase 10.2's
real-engine acceptance are separate.
