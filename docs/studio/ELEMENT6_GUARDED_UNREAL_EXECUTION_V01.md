# Element 6 — Guarded Unreal Execution (v0.1)

**Canonical architecture:** Unity evidence + Unreal capabilities → CED → LangGraph AI planning → validated strategy / bounded alternatives (**Element 4**) → source-bound conversion plan (**Element 5**) → **guarded Unreal execution (Element 6)** → independent native readback + CineTwin → bounded repair → remeasure/report limitations.

**Branch:** `feature/element6-guarded-unreal-execution-v0.1`, stacked on Element 5 draft PR #144. No engine-side acceptance has been conducted.

## Existing protections retained

The existing Studio worker already enforces target project/level identity, fresh sequence-only generation, prepared artifact verification, registered builder actions, exact-action operator consent for reviewed Element 3/5 candidates, source manifest and automatic setup preflight, fresh native readiness, builder runtime receipt and measured-domain diagnostics. The worker runs on the Unreal editor tick, not through an arbitrary AI-supplied command. Those protections remain unchanged.

## New durable one-attempt guard

`packages/studio/studio_element6_execution.py` is a stdlib-only, bounded, read-only/reviewable execution policy. It **does not** implement or authorize native Unreal mutations. Its `claim()` method runs in the Unreal worker **before** changing a job to RUNNING and before any asset, map, actor or Sequencer modification.

The guard:
- Requires the exact queued job, active-job pointer, active candidate, immutable handoff session, source CSIR, mapping, compiled plan and fresh non-overwrite target path.
- Records a write-ahead **exclusive** JSON claim containing a SHA-256 of the original queued payload, immutable job identity, source/target/plan/session byte hashes, and any applicable Element 3 operator grant, active element review pointer and opt-in AI decision digest.
- Uses an exclusive-create file and fsync so two editor processes cannot both acquire the same native attempt.
- Reopens and independently verifies the original claim before the first engine operation and at each checkpoint. Changes to original source, mapping, plan, grant or candidate ownership cause a hard stop. A stopped/partially executed attempt is never automatically retried.
- Records strictly ordered, once-only phase checkpoints: source/auth preflight, editor preflight, start of target mutation, destination setup, start/return of deterministic sequence builder, post-generation audits and terminal evidence.
- Writes a one-time terminal **builder completion vs failure** receipt tied to the original claim and to the real builder's already-existing native runtime receipt. A builder completion is explicitly `READBACK_AND_FIDELITY_UNVERIFIED`; individual action equivalence, persistence, audio, rendered frames and cinematic fidelity cannot be inferred.
- Supports read-only `inspect()` for Studio results. An unfinalized RUNNING job without a connected observed worker is `NATIVE_ATTEMPT_UNOBSERVABLE_INSPECT_BEFORE_RECOVERY`, never a clean success.

## Native worker and Studio integration

`integrations/unreal/studio_local_editor_worker.py` makes the exclusive claim before RUNNING, reopens the claim after prior source/native authorization checks and before any mutation, and appends checkpoints before and after irreversible operations. Any failure creates a terminal failure/no-replay record when possible, without rewriting, deleting or rerunning a partially generated sequence.

`integrations/unreal/studio_planner_sync.py` refreshes the canonical Element 6 guard alongside the native adapter stack in the already-running Unreal interpreter when idle. There is no repeated editor restart or worker reinitialization for ordinary code refreshes.

`tools/studio_local_bridge.py` exposes only the redacted claim/phase/receipt status of the active job; `apps/studio-web/app.js` displays it in Transfer and Results. The new status is **observational**, not a new permission to execute. Source identifiers, actor names, local project paths and tracebacks are omitted from the new ledger.

## Acceptance conditions

1. **At most one native attempt:** single exclusive claim, never overwritten or replayed across editor processes or worker restarts.
2. **Operator + source binding:** unchanged source CSIR, mapping, plan, prepared session, active job/candidate identity, explicit Element 3/5 grant and approved optional AI decision, where applicable.
3. **No native action until preflight:** existing immutable prepared-transfer verifier and independently rechecked Element 3/5 native authorization still run before level/actor/asset mutation.
4. **Checkpointed irreversible lifecycle:** no omitted or out-of-order phase records; mutations are preceded by durable `DESTINATION_MUTATION_STARTED` evidence.
5. **Failures and interruptions stay visible:** no automatic retry on stale editor, interrupted claim, failed asset import, partial sequence, malformed native runtime receipt or unverified action.
6. **No new native handlers or arbitrary Python execution:** the existing deterministic builder is unchanged, and the AI's choices remain advisory.
7. **No fidelity overclaim:** successful builder completion only proves receipt presence, not actual restored cutscene behavior. Unreal test remains explicitly deferred.

## Validation

`tests/studio/test_element6_guarded_execution.py` tests exclusive creation, parallel editor race, source/candidate drift, immutable approval and plan hashes, exact ordering, forged stage hashes, success/failure classification, host orphan visibility and static assurance of the worker's pre-mutation gates. The existing full software regression suite runs in GitHub Actions.

**Limits:** The static/software fake-editor tests do not prove the execution claims are durably persisted by a real Unreal editor or that native assets, skeletal animation, audio, events or rendered visuals match Unity. Independent real-engine execution and reopen-based CineTwin acceptance remain deferred.
