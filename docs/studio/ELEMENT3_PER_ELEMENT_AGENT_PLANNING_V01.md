# Element 3.1 — Source-complete per-element AI planning

**Branch:** `feature/element3-per-occurrence-agent-planning-v0.1` (stacked on integrated Studio release candidate, not `main`).
**Scope:** Phase 3.1 software contract and opt-in model review. This is *not* the final Element 3 dependency scheduler, adaptive native tool composer, or autonomous repair engine. Actual Unity/Unreal acceptance remains pending.

## Problem corrected

Existing LangGraph `studio_conversion_graph.select` deliberately chooses among three **global** guarded strategies (`native_source`, `source_materials`, `visual_activation_partial`). CED knowledge retrieval already accounts for source semantics, but that global choice cannot explain a distinct decision for every nested source occurrence. Treating a shared `ced_type` as one element also loses identity when multiple Timeline clips, channels or actors share the same semantic.

## Implemented contract

The portable, versioned contract is defined in `packages/contracts/agent/element-conversion-plan-v1.schema.json` and is validated at construction, model selection and pre-native verification.

`packages/studio/studio_element_plan.py` builds a source-bound `cutsceneai.studio.element_conversion_plan` v1 from the exact Unity CSIR and the complete, immutable CED knowledge snapshot. This contract:

- enumerates each asset, entity, track, section, animation curve and relationship **separately**;
- uses a stable source-structural location and anonymized `E00000`-style occurrence ID, **never source object names, file paths, raw source IDs, or unknown vendor namespaces**;
- resolves explicit parent, asset, Timeline binding, track/section and relationship references; unresolvable or duplicate dependencies make candidate actions unavailable;
- provides only existing `feature_dispatch.EXPLICIT_ACTIONS` and existing Unreal builder kinds; disables candidates whose inspected target capability is explicitly false;
- retains unknown/missing/unsupported concepts as investigation or limitation states; category-level CED routing and lexical similarity never grant native permissions;
- preserves the original CSIR, CED knowledge and observed target capability hashes; the complete plan has its own SHA-256 digest and unique occurrence accounting;
- starts every source occurrence as `selected_action=report_only` and `model_reviewed=false`, even if a potential native action exists;
- **never** substitutes the proposed action for an actual compiler action or claims native execution or fidelity.

`tools/studio_transfer_ai.inspect` produces this plan for every enabled pretransfer AI decision. `decide` attaches its hash and advisory candidates to the exact-source decision. `verify` **reconstructs the plan from fresh source/target evidence** before native preparation, rejecting changed identities, missing occurrences, invalid action selections, inconsistent model-count claims or forged source/knowledge hashes.

### Optional per-occurrence AI reasoning

To turn on **additional** per-element LLM decisions, configure the same Studio environment where the model provider runs:

```powershell
$env:CUTSCENEAI_ELEMENT_PLANNING="model"
```

Then start or safely reload the Studio backend normally. This mode reuses the existing Ollama/OpenAI provider and calls `cutsceneai_element_conversion_choices` in groups of up to **12** anonymous occurrences. It refuses missing/duplicate IDs, invented native actions, source-dependent action gaps and malformed replies **before** any native submission. A SHA-256 hash for each model response is retained. It supports up to **256** occurrences for now: larger sources receive a specific fail-closed explanation rather than silently omitting elements.

Default `CUTSCENEAI_ELEMENT_PLANNING=inventory` preserves the existing model request count and native transfer flow while still generating and verifying the complete source inventory. Injected test reasoners also remain inventory-only, not falsely marked as per-element AI-reviewed.

**This opt-in is intentional:** additional model batches can increase latency/cost. It remains experimental until the Phase 3.2 durable dependency scheduler and model-budget UX are completed. The preexisting three-strategy deterministic native conversion policy continues to govern actual engine actions regardless of AI proposals.

## Honest behavior labels

| State | Meaning |
| --- | --- |
| `NATIVE_ACTION_CANDIDATES_REQUIRE_PREFLIGHT` | Source concept and registered native action suggest a possible operation; native preflight and behavior checks still required |
| `UNKNOWN_SEMANTIC_INVESTIGATE` | No registered taxonomy concept / executable adapter may be inferred |
| `CED_KNOWLEDGE_MISSING` | Exact semantic retrieval is absent; refuse to invent a mapping |
| `TARGET_CAPABILITY_MISSING` | Required native worker capability was explicitly reported false |
| `UNRESOLVED_SOURCE_DEPENDENCY` | Parent, asset, binding or relation is missing/ambiguous; do not propose an unsafe action |
| `NO_REGISTERED_NATIVE_ACTION` | CED concept is known but no registered native builder action covers this occurrence |

A model selecting `camera_fov` or `skeletal_animation` is **not proof** that a camera lens or animation was converted. Final native action construction, version-aware preflight, source identity mapping and CineTwin measured acceptance remain independent.

## Regression coverage

- Previously unseen source scenes, duplicate semantics, nested Timeline curves, source parent/asset/binding/relationship dependencies.
- Correct canonical curve semantic lookup in CED, including raw curve records that omit `ced_type`.
- Unknown vendor types and private names omitted from model prompts and stored per-element plans.
- Missing target capabilities, ambiguous source identities and malformed Timeline sections.
- Genuine mock structured per-element model decisions, multiple bounded pages, omitted/duplicated/unknown IDs, arbitrary code/action refusals, and explicit model budget gate.
- Tampering even when the proposed plan's checksum is recomputed.
- Integrated pretransfer `decide`/`verify` with opt-in mode and untouched default native transfer workflow.
- Repository CI includes old character motion, first-run native safety contracts, CineTwin, one-click UI, Ruff, and Windows bootstrap.

## Next Element 3 phases

- **3.2 Dependency-aware reasoning:** topological execution graph, cross-element ownership/blend conflicts, dependency-gated candidate ordering and truly durable large-cutscene model pagination.
- **3.3 Adaptive decisions:** contextual CED strategy comparison with independently reviewed evidence and native capability versions.
- **3.4 Autonomous investigation:** structured missing evidence, supported alternative discovery and explicit unsupported outcomes.
- **3.5 Intelligent verification/recovery:** per-element CineTwin discrepancies, bounded authorized repair, independent remeasurement, no-progress termination.

Real Unity/Unreal native compile, adapter execution, target sequence readback and held-out end-to-end fidelity are still required before broader acceptance.
