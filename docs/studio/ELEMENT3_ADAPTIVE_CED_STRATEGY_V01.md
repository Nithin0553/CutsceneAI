# Element 3.3 — Adaptive CED strategy decisions

**Stack:** Phase 3.3 is based on draft PR #137 (Element 3.2), which itself is stacked on draft PR #136 (Element 3.1). This is a **read-only software planning** milestone, not evidence of a successful native Unreal transfer or Unity/Unreal cinematic fidelity.

## What Phase 3.3 actually implements

New module: packages/studio/studio_element_strategy.py.

Every source occurrence receives a deterministic, evidence-bound comparison of its **already registered** candidate actions. The comparison uses only:

- The exact-source per-occurrence Element 3.1 inventory, identity hashes, registered explicit action set and current target capability probe.
- The Element 3.2 dependency schedule, including unresolved reference, cyclic ownership, overlapping Timeline, muted track and incomplete source timing blockers.
- The **existing** hybrid CED knowledge service's source/target-version-ranked rules and recipe action lists.
- CED's independently reviewed and held-out project-group signals (not model-asserted success). Failed and conflicting project observations remain visible as risk signals rather than being overwritten by successful reruns from the same project.
- Installed Unreal source routing from integrations/unreal/csir_plan.py: a resolved character-bound animation.track is an advisory skeletal-animation branch; a resolved non-character animation.track uses the transform branch. Sections inherit that parent routing. **This is a candidate constraint, not proof that source skeletal assets, retargeting, blending or target readback are ready.**

The output tracks every occurrence's available and excluded alternatives, CED evidence score, verified project-group count, known negative evidence, missing target capability observations, source route compatibility and the safe report_only option. Ambiguous equally ranked actions remain report_only, rather than receiving an invented confidence score. Numerical scores are heuristic advisory comparisons, **not calibrated probabilities of transfer fidelity**.

The strategy record is source/plan/schedule/CED/target-capability bound with SHA-256 checksums and explicit native_execution_authorized=false and full_cutscene_fidelity_verified=false. For every proposed action, native_preflight_required=true and current_cutscene_fidelity_verified=false.

## Agent integration and rollout

Studio inspect creates the baseline comparison alongside the complete inventory and schedule. In CUTSCENEAI_ELEMENT_PLANNING=model, every page of the existing bounded model review receives **redacted eligible actions and ranked context**, never raw Unity object names, proprietary unknown vendor IDs, paths, source model assets, or unregistered Unreal commands. The model can choose a permitted alternative or report_only. Excluded routes, missing observed capabilities, graph blockers, invented actions, and invalid cached choices fail closed.

For large scenes (>256 occurrences), the existing durable checkpoint binds the selected model to the **comparison digest** as well as the exact source plan, preventing an earlier answer from being trusted when strategy options change. Each saved page is replayed through current model-review validation before completion. Partial review cannot become a native job.

Studio decide attaches the final exact-plan comparison after model choices. Studio verify recomputes the plan, dependency schedule and complete adaptive strategy comparison from freshly read CSIR, CED and target capabilities, rejects modified/rehashed results and refuses selected alternatives excluded by source routing. Native execution remains governed by the original deterministic conversion and preflight policies. There is **no automatic per-element native dispatcher** in this phase.

Inventory-only remains the default mode and requires no additional LLM requests. No new model, engine restart, or Unity/Unreal native plugin installation is required solely for this software milestone.

## Validation

Regression tests cover character vs prop Timeline routing, parent section constraints, source-unknown privacy, unobserved target capability refusal, ambiguous strategies, mixed-writer conflict blockers, malicious proposed actions, model prompt privacy, exact occurrence accounting, checksum tampering and independently recomputed pretransfer verification. Existing Element 3.1 and 3.2 tests and all Studio/native safety suites run in CI.

## Boundaries and the next phases

- A high CED ranking means only that a **registered candidate** looks preferable given the currently available evidence; it cannot assert the model converted an animation or that the target footage matches the source.
- Missing source asset mappings, plugin-version compatibility, mixed animation baking, skeletal retargeting, material fidelity, and native readback still require real-engine acceptance.
- Phase 3.4 adds bounded investigation and registered alternative discovery for missing evidence/unsupported source semantics.
- Phase 3.5 adds per-element CineTwin discrepancy attribution, authorized bounded recovery and independent target remeasurement.

Run held-out real Unity/Unreal evaluation before promoting any strategy to a proven cross-engine conversion policy.
