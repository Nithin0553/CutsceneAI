# Extensible source-component transfer contract v0.1

**Problem this design addresses:** A source Unity scene can contain novel static and dynamic components that are absent from Timeline. The CutSceneAI Studio importer may generate the previously mapped actors and still omit visible scenery. Its source-census strict gate also detects arbitrary components without knowing what those types require to preserve their behavior. A single hard-coded exception for Benchmark002 trees does not solve this general problem.

## General transfer contract — capability-driven, not benchmark-driven

The end-to-end system operates over an explicit **source occurrence graph**. Every component is keyed by project fingerprint, saved-scene identity, native GameObject global ID, native component global ID, hierarchy path, and any referenced asset GUIDs. Source extraction must never rely on matching names, asset appearance, or user-written hints as proof of identity.

Each distinct source occurrence progresses through these independent gates:

| Gate | Necessary evidence | What may be claimed |
| --- | --- | --- |
| D — Discovered | Native component type and source object identity | Source component exists |
| S — Source captured | Versioned typed or sanitized serialized authoring state; complete source dependency identities | Source state described; **not** Unreal behavior |
| P — Planned | Registered semantic adapter, target class/property and verified source dependency graph | Target operation intended |
| N — Native generated | Imported source-backed assets, persisted editable Unreal actors/components, and exact native readback | Native structure persisted |
| B — Behavior compared | Independent time-matched source vs target values, camera output, motion, physics, audio/events as applicable | Specific bounded-domain fidelity |
| R — Release eligible | Held-out project and version tests, secure no-overwrite staging, documented tolerance/error budgets | Feature can be advertised within its proven scope |

**No stage may imply a later stage.** Unsupported or novel types remain source-recorded, with their exact missing gate and dependency IDs, not silently mapped to a fake proxy. The source engine may contain C# scripts, shader graphs, third-party plugins and runtime dynamics without a safe portable target representation; a universal *framework* can report and route these, but cannot truthfully guarantee identical execution of arbitrary unknown semantics.

## Reusable adapter protocol

1. **Source extractor**: read-only, versioned native scanner capture; canonicalizes stable source values and asset identities. For custom plugin data, serialized-property enumeration preserves native field names, types and object-reference GUIDs without executing the plugin's code.
2. **Semantic classifier**: categorize into CED/domain semantics; unknown classes remain explicit plugin/custom occurrences. Class names are not themselves semantic proof.
3. **Dependency resolver**: separate visual mesh, collision mesh, material/shader, prefab, parent, animation, LOD, audio, event and external runtime dependencies. Missing or ambiguous references block the affected semantic adapter, not unrelated source features.
4. **Transfer planner**: use an installed, versioned plugin adapter with target actor/component class, expected import format, safe staging namespace, data conversion and readback schema. No arbitrarily generated native Python/scripts.
5. **Target builder and readback**: create/edit native Unreal data transactionally; reopen independently and audit object IDs, transform, asset paths, actor hierarchy, component settings, track keys and dependent packages.
6. **CineTwin verifier**: perform source/target comparisons on exactly the same frame timebase. Record numeric tolerances, pass/partial/unsupported per domain; never infer rendered parity from native structure.

A classifier-only registration is *not* a conversion adapter. Automatic mapping must be based on actual source metadata, not merely on an element appearing in CED's 735 concepts. Build meaningful plugins by capabilities (e.g. static mesh, LOD, collision, skinned mesh, URP material), not by scene or benchmark names.

## Initial implementation in this PR

This stacked branch builds on draft PR #113 (automatic mapping for uniquely identified, single-FBX static scene renderers). It extends Unity's read-only Feature Surface scanner and validates two **general source-native component contracts**:

**MeshCollider**
- Mesh asset path, GUID and global object ID; authored mesh name
- Convex/trigger/enabled flags and cooking-option integer
- Physics material asset path and GUID when assigned
- Missing source mesh IDs stay unresolved, not back-filled from the visible static mesh
- Source-census status is **partial source snapshot / Unreal collision adapter missing**

**LODGroup**
- LOD enabled/fade mode/animated cross-fading/size/local reference point/billboard flag
- Every authored LOD level's screen-size threshold, fade width, renderer global IDs and paths, source mesh subasset IDs/GUIDs
- Missing mesh identity, unsupported renderer classes, corrupt thresholds and duplicate renderer references are *source-incomplete*
- Source-census status is **partial source snapshot / Unreal LOD graph adapter missing**

The validator uses a source-component-type → typed-evidence-validation registry (`_TYPED_SOURCE_EVIDENCE`) as an extensible entry point. The per-component plan now records `MESH_COLLIDER_SOURCE_CAPTURED_NATIVE_ADAPTER_REQUIRED` / `LOD_GROUP_SOURCE_CAPTURED_NATIVE_ADAPTER_REQUIRED`, with a list of target properties still unsupported. The plan emits **zero synthetic collision or LOD actions**. Real UE native support requires new adapters that consume this exact evidence, stage meshes safely, construct persisted native settings and verify independent behavior.

## What remains for full component support

- Map `MeshCollider.sharedMesh` to an Unreal StaticMesh collision representation with defensible convex/complex policies, cooking and trigger semantics, and physics material/response readback. Unity/Chaos physics can differ; runtime contact/event parity needs a separate test.
- Build Unreal StaticMesh LOD chains with correct source mesh GUIDs, screen-size conversion, transition behavior and renderer/material binding. A one-FBX placeholder might reproduce the first visible LOD but cannot claim LOD parity.
- Add formats beyond FBX with source identity and importers (e.g. Blender/GLTF/Unity-generated mesh), the Unity scene's sky/ambient/render pipeline, URP shaders, hierarchical child meshes, audio/event/runtime scripts.
- Add independent multi-scene, multi-project/engine-version tests rather than testing only Benchmark002. Any advertised feature must pass S, P, N and B gates on at least one held-out source.

## Exact test procedure

1. Save Unity and Unreal projects and preserve Benchmark002's previously accepted result.
2. Check out this stacked branch, update the installed Unity CutSceneAI extractor package from this checkout and confirm zero Unity compilation errors.
3. Select the same `CUTSCENE_DIRECTOR`; re-export CSIR and new feature-surface census from the saved scene.
4. Run `python tools/studio_source_surface_gap.py --csir <source> --source-surface <census> --out <new-report> --strict`.
5. Inspect four exact component records for the rocks and trees. Valid meshes should produce partial *source* snapshots rather than `NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED`. A source lacking exact GUID/renderer identity remains a genuine unresolved source finding.
6. In Studio, prepare a *new* candidate and inspect planned actor/import counts and per-component transfer decisions before running Unreal. Expect scene props only where the source model is safely resolved per PR #113.
7. Capture saved/reopened Unreal structure and use independent CineTwin comparison before claiming collider, LOD or rendering equivalence.

GitHub Actions can run Python and JS tests, but does **not** compile Unity C# or execute native UE5.8. This branch is **not** merge-ready until local editor compilation and engine checks have been performed.

Related: [#94](../../issues/94) source assets, [#95](../../issues/95) general executable adapters, [#97](../../issues/97) rendering.
