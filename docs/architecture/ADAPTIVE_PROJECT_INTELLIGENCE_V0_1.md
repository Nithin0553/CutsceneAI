# Adaptive Project Intelligence and Mapping v0.1

## Goal

CutSceneAI must transfer cinematic meaning across different engines, engine versions, plugins, import settings, project conventions, and target capabilities without relying on a fixed Unity/Unreal version pair.

The system therefore resolves mappings from observed project facts, not from engine names alone.

## Dynamic behavior, stable meaning

The Cutscene Element Dictionary (CED) and authoritative source CSIR do not change meaning when the target changes. Adaptability is produced by combining:

- stable CED ontology
- source CSIR ground truth
- source Project Intelligence Profile
- target Project Intelligence Profile
- adaptive mapping rules

These produce a disposable, reproducible Resolved Mapping Dictionary for one source/target project pair.

CED defines meaning. CSIR stores source truth. Project profiles store observed engine/version/project facts. The resolved dictionary stores target-specific decisions.

## Project Intelligence Profile

Each adapter performs read-only project analysis before transfer and records the facts that can change transfer behavior: engine/build, coordinate basis, rotation representation and binding semantics, camera basis/FOV/lens rules, timing and extrapolation behavior, animation import basis/root motion/rig information, render pipeline, relevant plugins/packages, runtime APIs, project settings, and evidence/confidence.

Engine version is provenance and may be a selector, but capability and project-setting probes take precedence over hard-coded version checks.

## Adaptive CSIR context

CSIR remains canonical source ground truth. A CSIR Adaptive Context sidecar stores source-only semantic observations needed for mapping without contaminating CSIR with target decisions.

Examples include authored camera roll, source camera forward/up basis, FOV axis and provenance, root-motion availability and measured displacement, and explicit section completion/extrapolation semantics.

## Resolved Mapping Dictionary

The resolved dictionary is generated from CED + source profile + target profile + adaptive rules. Every entry records the CED id, chosen rule, transfer outcome, resolver, parameters, evidence, confidence, or explicit BLOCKED state. There is no silent fallback.

Rules can select on source/target engine, observed capabilities, project settings, and optional version prefixes. Equal-specificity conflicting rules are an error rather than a guess.

## Benchmark001 camera lesson

Benchmark001 exposed why this layer is required. The canonical camera rotation was valid, but the Unreal Python Rotator wrapper exposes positional fields as roll, pitch, yaw while native C++ documentation commonly describes the constructor as pitch, yaw, roll. Passing positional values changed intended source pitch into target roll.

The adaptive rule now requires the target rotator.semantic_fields capability, and the Unreal compatibility layer constructs rotations by named roll/pitch/yaw fields only.

## Project-analysis gate

For every CED element used by the selected cutscene, the system identifies the semantic facts required for transfer. If the source adapter cannot prove them, the transfer must capture/evaluate more information or become BLOCKED. If the target cannot prove an equivalent capability, the planner follows PRESERVE -> CONVERT -> RETARGET -> RECONSTRUCT -> UNSUPPORTED.

## Validation still closes the loop

Project analysis prevents avoidable mistakes before generation, but successful generation is not proof of fidelity. Every result is read back and compared to source semantics and evaluated values. A mismatch becomes new evidence, an adapter/rule correction, and a regression test.

## Contracts introduced

- packages/contracts/project/project-profile-v0.1.schema.json
- packages/contracts/csir/csir-adaptive-context-v0.1.schema.json
- packages/contracts/dictionary/adaptive-mapping-rules-v0.1.schema.json
- packages/contracts/dictionary/resolved-dictionary-v0.1.schema.json
- packages/contracts/dictionary/adaptive-rules-v0.1.json
- packages/readiness/adaptive_mapping.py
- integrations/unreal/project_intelligence.py

Future Unity, Unreal, and additional engine adapters should emit the same Project Intelligence Profile contract.