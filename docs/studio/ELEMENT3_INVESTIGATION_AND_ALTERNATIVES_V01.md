# Element 3.4 — Source-bound investigation and registered alternative discovery

**Stacked branch:** feature/element3-autonomous-investigation-v0.1, based on draft PR #138 (Element 3.3), which depends on PRs #137 and #136.

**Scope:** Complete, evidence-bound investigation and opt-in model-guided diagnostic recommendations. This does **not** run native Unreal code, automatically change source/target projects, claim that unsupported elements were converted, or prove cinematic fidelity.

## Purpose

Earlier phases inventory every Unity CSIR occurrence, construct dependency waves and conflicts, and rank registered native action candidates using CED experience. Phase 3.4 answers a different question: when an occurrence is unknown, blocked, limited by native capabilities, missing source or CED evidence, or still unverified, **what exact evidence is missing and which safe next investigation should be considered?**

The new packages/studio/studio_element_investigation.py builds one record for **every** asset, entity, Timeline track, section, curve and relationship. The record contains only anonymous occurrence IDs, known CED concepts or unknown.unclassified, fixed reason codes, bounded evidence requirements, eligible registered alternatives from Phase 3.3 and fixed-vocabulary next-step options.

Investigation sources are the **same exact** source-bound Element 3.1 plan, Element 3.2 dependency schedule, Element 3.3 strategy comparison and complete CED knowledge snapshot. It never obtains native permissions from an LLM, unreviewed local data, lexical similarity or source object names.

## Investigations and findings

Cases explicitly distinguish:

- Unknown/unregistered CED concepts or unavailable CED mappings.
- Missing or ambiguous source parent, asset, track binding and relationship references.
- Actual dependency cycles, blocked dependents, muted tracks, multiple transform writers and unproven blend ownership.
- Missing/unobserved target native capabilities and source-specific native routing mismatches.
- Missing action-specific CED rule evidence, uninspected source capabilities and failed/conflicting independent project-group experience.
- Registered alternatives not selected by the AI and native preflight/readback/fidelity still unverified.

Allowed diagnostic choices include reviewing source references, target capability observations, CED knowledge, Timeline ownership, and registered alternatives, as well as requesting native preflight/readback and CineTwin comparison. **These are next-step suggestions only.** A recommended readback does not mean readback happened.

The source knowledge/strategy registry remains authoritative. The existing packages/studio/ced_discovery_registry.py remains the dedicated local-only append-only registry for genuinely novel CED preflight observations; this phase does not duplicate or silently write to that registry, promote unreviewed rules or send discoveries to an external service.

## API and safety

- inspect builds an inventory-only cutsceneai.studio.element_investigation report.
- decide attaches the exact-source report to the global AI decision. Every finding starts at selected_step=report_only, model_reviewed=false.
- verify independently reconstructs **all** findings and compares the stored report against the current CSIR, CED snapshot, target capability probe, source plan, dependency graph and adaptive strategies. Recomputing the report SHA-256 cannot hide unsupported actions, changed issue classifications or missing occurrences.
- Native execution remains governed by the original deterministic converter and preflight policy; the new report has native_execution_authorized=false and source_and_target_fidelity_verified=false.
- Source cutscene names, raw object IDs, private asset paths, arbitrary unknown vendor namespaces and native code are absent from model requests and saved investigation checkpoints.

## Model-guided diagnostic selection (opt-in)

The default is CUTSCENEAI_ELEMENT_INVESTIGATION=inventory: generate/verify the complete investigation report without any additional model requests. CUTSCENEAI_ELEMENT_INVESTIGATION=model enables read-only model-assisted selection of an allowed next step for every case that has a diagnostic option. A model may always choose report_only.

The configured existing Studio Ollama or OpenAI JSON provider receives at most **12 anonymous cases per request**. Every response must cover exactly the requested occurrence IDs, with one known and allowed diagnostic step (or report_only) and a bounded provider response hash. Omitted/duplicate/foreign IDs, extra code fields or arbitrary tool calls are rejected. No model output can grant Unreal/Unity native permissions.

For more than 256 investigative cases, pages use the existing per-model, source-bound atomic ReviewCheckpoint implementation in the user's .cutsceneai-studio/element-investigations directory. A changed source, knowledge, graph, strategy, model or capability record yields a different checkpoint identity. Review saves pages only after strict validation and revalidates cached pages on replay. By default at most 32 **new** pages are reviewed per invocation, controlled by CUTSCENEAI_ELEMENT_INVESTIGATION_MAX_NEW_PAGES (positive 1–9999). If incomplete, the process reports that no native job was authorized; a later same-evidence run can resume.

An investigation checkpoint stores **only** the source-bound report checksum, anonymous occurrence IDs, allowed diagnostic choice and model response hashes. It does not store source CSIR or execute any suggested diagnostic.

## Regression and limitations

Tests cover full source accounting, privacy, unknown CED refusal, character/prop registered-route constraints, missing target capability evidence, cycles, Timeline conflicts, action/ID tampering, wrong model steps, checksum laundering, exact-paged opt-in model review, interrupted/resumed 270-case reviews and integrated pre-native verification.

Phase 3.4 is a **bounded investigation and recommendation mechanism**, not a real unattended engine investigator. It cannot gather missing evidence from Unity/Unreal by itself or implement unsupported native adapters. Those capabilities require separately authorized read-only engine tool interfaces, registered alternative/native preflight work, and real engine-side acceptance.

Next: Phase 3.5, per-element CineTwin discrepancy attribution and bounded, independently remeasured recovery. Real Unity/Unreal acceptance and held-out cinematic fidelity remain pending.
