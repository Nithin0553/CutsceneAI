# Element 4 — Validated Strategy? / Bounded Alternative Reasoning (v0.1)

**Architecture:** Unity source evidence + Unreal capability evidence → CED knowledge retrieval → LangGraph AI planning (**Element 3**) → **Element 4: Validated strategy?**. **Yes** proceeds to the source-bound conversion-plan stage; **No** enters bounded alternative reasoning, returns through validation, and ultimately reports a limitation when no eligible strategy exists.

**Stack:** This implementation branches from the clean, software-tested consolidated Element 3 native-acceptance integration PR #142 and remains a separate draft PR. It does **not** merge into main, execute Unity/Unreal, or certify fidelity.

## Source of truth and boundaries

- `packages/studio/studio_conversion_graph.py` already implements a genuine LangGraph global-strategy loop with two maximum pretransfer model attempts. It remains responsible for global strategy grammar/validity.
- Element 3 already provides source-complete per-occurrence inventories, dependency scheduling, CED-ranked eligible native alternatives, bounded model review, optional read-only investigation, and native operation guards.
- Element 4 adds the previously missing **final independent source-bound recomputation of the combined selected source-graph strategy**. Being a registered action and being individually recommended by CED are **not** enough: a selected action whose upstream source element is unplanned, cyclic, blocked, or has conflicting Timeline ownership is rejected. An eligible proposal is still only a preflight candidate.
- Nothing in Element 4 can grant native execution, create a new Unreal action, retry a partially mutated transfer or claim rendered-frame/audio/event fidelity.

## New module

`packages/studio/studio_element4_validation.py`:

`build(plan, schedule, adaptive, investigation, knowledge, csir, target_capabilities, global_strategy, allowed_strategies)` independently revalidates the existing source-bound plan, dependency graph, CED strategy, complete investigation record, global allowlist and current capability observations. It produces one anonymous decision for **every** source occurrence, three distinct terminal statuses, bounded rejection reason codes, report-only limitations and a SHA-256 of the complete validation record.

- `VALIDATED_FOR_SOURCE_BOUND_PLANNING`: all proposed native actions are source/graph-eligible, still unexecuted and subject to downstream builder/native preflight.
- `VALIDATED_WITH_REPORTED_LIMITATIONS`: all proposed actions are valid but some occurrences remain report-only / unresolved. This is an accepted best-effort **planning** result, **never** fidelity completion.
- `REJECTED_BOUNDED_ALTERNATIVE_REQUIRED`: at least one selected action conflicts with source dependencies, registered CED context, current target capability or native ownership. The native plan is blocked until the strategy is corrected or explicitly reported as a limitation.

`reason_bounded(..., max_rounds=2)` implements the **No** path. It considers only the rejected anonymous occurrences, in batches of at most 12, sends a fixed allowlist of registered alternatives and/or `report_only` to the configured structured model provider, and requires exact ID coverage, no extra fields, a content fingerprint, no duplicated/foreign choices, and actual model-selection progress. It rebuilds the dependency graph, adaptive strategy and investigation after each round; the repaired candidate is valid only if the entire source graph passes again. A missing model, invalid response, fabricated action, absent source or exhausted budget stops without native writes.

## Studio integration

`tools/studio_transfer_ai.decide` runs Element 4 **after** the optional Element 3 per-occurrence model proposal. The gate runs in default inventory mode too, requiring no extra model call. When a model-reviewed combination is rejected and genuine structured model support exists, Element 4 allows up to two source-bound correction rounds before investigation/plan assembly. It records bounded, redacted round/page provenance and finally binds the validation to the exact compiled decision. The existing per-element review checkpoint retains its original independently verified pages; alternate-round records are separate and cannot impersonate native approval.

`tools/studio_transfer_ai.verify` independently rebuilds Element 4 from the fresh Unity source CSIR, current CED knowledge/capabilities, exact scheduled dependencies and selected model choices immediately before the native transfer is prepared. Tampered or rehashed strategy/gate records, stale source evidence, incomplete model progress and unsupported alternatives fail closed.

The **Studio Review** screen also displays the active Element 4 decision and counts of advisory candidates, reported limitations and rejected combinations. It explicitly distinguishes `NO_MODEL_STRATEGY_DECISION` (inventory only), a source-recomputed model decision, and `MODEL_STRATEGY_EVIDENCE_STALE_OR_UNVERIFIABLE`. A source inventory alone never becomes a validated model decision. The UI does not grant native execution permission.

## Acceptance requirements

1. Zero omitted source occurrences, duplicate identities, or fabricated strategy claims.
2. Native actions selected only from registered, source-context-eligible alternatives, with no unplanned dependency or ownership conflict.
3. No more than two bounded alternative reasoning rounds and exactly one structured choice per rejected occurrence.
4. Unknown/unmapped source concepts and absent target capability evidence remain report-only and visibly unverified.
5. Model payloads/report records contain no raw source object IDs, paths, proprietary vendor names, Unity scripts, credentials or arbitrary Unreal code.
6. No new native action permissions, no native retries, no engine restart and no inferred fidelity pass.
7. Existing deterministic compiler, user approval, native preflight and later CineTwin verification remain the only native execution/acceptance authorities.

## Validation

`tests/studio/test_element4_strategy_validation.py` tests complete inventories, accepted source proposals, upstream graph rejection, bounded correction, failure/no-progress, malformed/unsafe alternatives, privacy and altered/rehashed gates. GitHub CI additionally runs the existing Studio/agent/engine-stub regression suites, Python syntax/Ruff, JavaScript checks and Windows bootstrap.

**Still outstanding:** engine-side validation in actual Unity/Unreal projects and complete cinematic source/target fidelity acceptance. These are deferred by design, not counted as passed.
