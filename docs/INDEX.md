# Documentation Index

This is the maintained navigation page for CutSceneAI Studio. Documents marked **historical** describe what was known at an earlier research milestone and are not statements of present-day transfer readiness.

## Start here

- [Element 8: bounded CineTwin repair agent](studio/ELEMENT8_BOUNDED_REPAIR_AGENT_V01.md) — read-only source-bound triage, measured progress/stop budget and guarded existing repair adapters
- [Element 7: native readback + CineTwin](studio/ELEMENT7_NATIVE_READBACK_CINETWIN_V01.md) — source-bound independent native observation, per-occurrence attribution and exact Element 6 receipt
- [Element 6: guarded Unreal execution](studio/ELEMENT6_GUARDED_UNREAL_EXECUTION_V01.md) — durable one-attempt claim, no-replay checkpoints, conservative builder receipts
- [Element 5: source-bound conversion plan](studio/ELEMENT5_SOURCE_BOUND_CONVERSION_PLAN_V01.md) — complete CSIR-to-deterministic-native action reconciliation, source provenance, independent editor gate
- [Element 4: validated strategy and bounded alternative reasoning](studio/ELEMENT4_VALIDATED_STRATEGY_BOUNDED_ALTERNATIVES_V01.md) — independently revalidated decisions and a strict No → alternative → revalidate loop
- [Element 3 consolidated native execution and acceptance](studio/ELEMENT3_CONSOLIDATED_NATIVE_ACCEPTANCE_V01.md) — source-bound action authorization, real Unreal dispatch evidence and different-editor CineTwin validation
- [Element 3 Studio workflow integration](studio/ELEMENT3_STUDIO_WORKFLOW_INTEGRATION_V01.md) — candidate-bound source review, explicit acknowledgment and persistent CineTwin readback
- [Element 3.5: CineTwin per-element discrepancy attribution and bounded recovery](studio/ELEMENT3_CINETWIN_ATTRIBUTION_RECOVERY_V01.md) — fresh native observation comparisons and non-executable per-element recovery review
- [Element 3.4: Source-bound investigation and registered alternatives](studio/ELEMENT3_INVESTIGATION_AND_ALTERNATIVES_V01.md) — complete diagnostic cases, opt-in model triage, strict evidence/permissions
- [Element 3.3: Adaptive CED strategy decisions](studio/ELEMENT3_ADAPTIVE_CED_STRATEGY_V01.md) — ranked evidence, source-native routing, bounded model alternatives, and independent verification
- [Element 3.2: Dependency-aware reasoning and resumable model reviews](studio/ELEMENT3_DEPENDENCY_AWARE_REASONING_V01.md) — DAG waves, Timeline conflict blockers, validated advisory schedules, durable AI review checkpoints
- [Element 3.1: Source-complete per-element AI conversion planning](studio/ELEMENT3_PER_ELEMENT_AGENT_PLANNING_V01.md) — source occurrence contracts, opt-in model review, evidence and native permission boundaries
- [Element 2: Hybrid CED completion, signed releases and learning acceptance](studio/CED_HYBRID_COMPLETION_V02.md) — four phases, operator CLI, readback gates, security and native acceptance gaps
- [Hybrid CED knowledge service (shared baseline, local learning, reviewed promotion)](studio/CED_HYBRID_KNOWLEDGE_ARCHITECTURE_V1.md) — Element 2 contracts, contextual retrieval, privacy and validation gates
- [Agent-centric CED knowledge, LangGraph orchestration and local-model architecture](studio/AGENT_CENTRIC_ARCHITECTURE_V1.md) — active experimental refactor, explicit native safety and remaining fidelity gates
- [CED-first pre-conversion discovery](architecture/CED_FIRST_PREFLIGHT_V0_1.md)
- [CED local discovery registry](architecture/CED_DISCOVERY_REGISTRY_V0_1.md) — opt-in, redacted, deduplicated unknown-element observations
- [CED mapping rules book and offline RL feedback](studio/CED_MAPPING_RULEBOOK_AND_REINFORCEMENT_LEARNING.md) — complete semantic coverage, persistent approved user rules, candidate review and version-specific policy suggestions
- [Executed CED semantic mapping pretraining](studio/CED_POLICY_TRAINING_EXPERIMENT.md) — reproducible model fit, native-alias holdout metrics, and non-executable transfer suggestions
- [Executable CED adapter contract](architecture/CED_ADAPTER_EXECUTION.md) — source-bound handlers, native actions and verification gates
- [Native component adapter handoff](handoffs/COMPONENT_ADAPTER_DEVELOPMENT.md) — implementation branches and remaining editor evidence
- [Integrated Studio smoke-test and merge audit (#93)](studio/ISSUE_93_INTEGRATED_SMOKE_TEST.md) — unified source, CED, agent and release gates
- [Select CSIR and Source Census for each Studio transfer](studio/CSIR_CENSUS_SELECTION.md) — manual export choice, identity validation and refresh
- [Diagnose blocked Unreal generation](studio/BLOCKED_GENERATION_DIAGNOSTICS.md) — native exception, failed stage, partial import recovery and read-only job inspection
- [Studio release acceptance](studio/RELEASE_ACCEPTANCE.md) — real-engine evidence needed before declaring ready
- [Mandatory issue/PR triage before each fix](studio/ISSUE_PR_TRIAGE_POLICY.md) — inspect root cause, existing work, verified tests and clean closure
- [Agentic Studio architecture and Unity source bridge](studio/AGENTIC_STUDIO_ARCHITECTURE.md) — opt-in CSIR/census extraction, CED-guided planning, verified continual-learning boundaries


| Question | Read |
| --- | --- |
| What works today? | [Project status and transfer issues](ISSUES_AND_MILESTONES.md) |
| Where should code live? | [Repository guide](REPOSITORY_GUIDE.md) |
| How should I contribute safely? | [Development guide](../CONTRIBUTING.md) |
| How do I execute an audited transfer? | [Best-effort backend runbook](architecture/BEST_EFFORT_TRANSFER_BACKEND_V0_1.md) |
| What is the overall transfer architecture? | [Generalizable transfer architecture](architecture/GENERALIZABLE_CUTSCENE_TRANSFER.md) |
| How is cross-engine behavior evaluated? | [CineTwin overview](research/CINETWIN_PHASE_1.md), [behavior comparison](research/CINETWIN_PHASE_4_BEHAVIOR_COMPARISON.md) |
| How are training cases approved? | [Continual mapping memory](architecture/CONTINUAL_CUTSCENE_LEARNING_V0_1.md) |
| How do we register source datasets? | [Studio dataset design](architecture/STUDIO_DATASET_AND_ORCHESTRATION_V0_1.md) |
| How are backend changes reviewed? | [GitHub branch and PR audit](BRANCH_AUDIT.md) |

## Engine integrations

- [Unity extractor and CineTwin capture](../integrations/unity/com.cutsceneai.extractor/README.md)
- [Unreal adapter, mapping and readback](../integrations/unreal/README.md)
- [Engine adapter protocol](../packages/adapters/README.md)
- [Readiness and project intelligence](../packages/readiness/README.md)
- [Validation gates](../packages/validation/README.md)

## Design contracts

- [Foundation](architecture/FOUNDATION_V0_1.md)
- [Coordinate conventions](architecture/COORDINATE_CONVENTIONS_V0_1.md)
- [Timing conventions](architecture/TIMING_CONVENTIONS_V0_1.md)
- [Adaptive project intelligence](architecture/ADAPTIVE_PROJECT_INTELLIGENCE_V0_1.md)
- [Runtime compatibility](architecture/ENGINE_ADAPTER_COMPATIBILITY.md)
- [Architecture decisions](decisions/ADR-0001-source-cutscene-is-ground-truth.md)

## Benchmarks (retain as immutable evidence)

- [Benchmark 001](benchmarks/BENCHMARK_001.md) — [source freeze](benchmarks/BENCHMARK_001_SOURCE_FREEZE.md) · [target freeze](benchmarks/BENCHMARK_001_TARGET_FREEZE.md) · [validation](benchmarks/BENCHMARK_001_TARGET_VALIDATION.md).
- [Benchmark 002](benchmarks/BENCHMARK_002.md) — [source build](benchmarks/BENCHMARK_002_SOURCE_BUILD.md) · [pipeline corrections](benchmarks/BENCHMARK_002_PIPELINE_CORRECTIONS.md).

## Historical research and handoffs

The numbered [CineTwin research reports](research/) and [Benchmark 002 chat handoff](benchmarks/BENCHMARK_002_CHAT_HANDOFF.md) record earlier experiments, hypotheses and reproduced failures. Do not replace research history with current status assertions; use [Project status](ISSUES_AND_MILESTONES.md) for the live readiness overview. The obsolete original new-chat prompt was removed from the working tree because it incorrectly instructed users to restart the already-built Benchmark 002.
