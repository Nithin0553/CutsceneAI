# CutSceneAI Studio: CED v0.2 and expandable cross-engine conversion

## Versioned feature catalog

CED v0.2 contains **39 feature families, 63 semantic domains, and 735 canonical IDs**. The v0.1 baseline remains unchanged. New Unity and Unreal engine/plugin types are open-ended and must be discovered from the installed editor. Catalogued does not mean converted.

Native builder support currently comprises nine action kinds. Each requires source identity, target saved readback and independent motion/appearance/behavior testing. Unknown actions are now rejected at source-side preflight, before engine mutation.

## Transfer algorithm

1. **Discover source/target types.** Unity reflection scans loaded assemblies, installed component/Playable/Timeline subclasses, source GameObjects, missing scripts and project asset types. Unreal reflection reports Python-exposed engine/plugin classes and loaded actor types.
2. **Extract and account.** CSIR holds authored cutscene semantics. Compare the Unity feature census against CSIR to reveal components and scripts that extraction omitted. The feature dispatcher inventories every CSIR asset, entity, track, section, animation curve and relationship.
3. **Choose the evidence-backed route.** Every CED concept has a candidate path: native timeline construction, native asset import, scene reconstruction, evaluated cache/baking, plugin runtime adapter or source preservation. This route is not a native handler.
4. **Resolve dependencies and validate.** Native actor/asset mappings, fingerprints and builder action types are checked before spawning or importing anything. An unimplemented action cannot silently continue.
5. **Generate and verify.** Save and reopen source-backed target objects and sequences, then compare timing, positions, cameras, skeletal animation, rendering, audio, events, constraints, physics and any other relevant behaviors against the same source samples.
6. **Promote verified adapters.** Only a separately demonstrated conversion enters the verified project mapping/learning registry. Custom handlers require an explicit version and native/behavior evidence gates.

## Source engine discovery

In the already-connected Unity Editor, choose **Tools → CutsceneAI → Discover Installed Feature Surface**. It writes a unique JSON to the project-root CutSceneAI/Exports folder, outside Assets. This is read-only and does not save the scene or import assets.

In the Unreal Python console (adjust repository path):

```python
import sys
sys.path.insert(0, r"B:\Research\CutSceneAI\CutsceneAI\integrations\unreal")
import studio_feature_surface
report_file = studio_feature_surface.save_latest()
```

The Unreal census is written under ~/.cutsceneai-studio/runs/feature-surfaces. It discovers Python-exposed installed engine classes without editing assets or levels. Discovery does not imply conversion.

## Read-only CLI reports

From the repository root, each output must use a new path:

```powershell
python tools/ced_capability_report.py --out ced-capability-v02.json
python tools/studio_source_surface_gap.py --csir SOURCE.csir.json --source-surface UNITY_SURFACE.json --out source-gap.json --strict
python tools/studio_feature_audit.py --csir SOURCE.csir.json --plan transfer-plan.json --out source-feature-inventory.json
```

The source gap tool reports missing native components/custom scripts separately from other project assets, and exits 2 in strict mode if components in the cutscene scope are not extracted or covered. Source identities and fingerprints remain preserved.

## Implementation records

| Path | Responsibility |
| --- | --- |
| packages/contracts/dictionary/cutscene-elements-v0.1.json | Frozen legacy taxonomy |
| packages/contracts/dictionary/cutscene-elements-v0.2.json | Active feature catalog |
| packages/studio/feature_dispatch.py | Category routes, source occurrence ledger, extensible adapter registration, builder action gate |
| packages/studio/ced_preflight.py | Canonical-first classification |
| packages/studio/transfer_backend.py | Runtime-preparation coverage including feature_dispatch |
| packages/studio/source_surface_gap.py | Component and missing-script source comparison |
| integrations/unity/com.cutsceneai.extractor/Editor/CutSceneAIFeatureSurfaceScanner.cs | Installed Unity native-feature scanner |
| integrations/unreal/studio_feature_surface.py | Unreal reflected API/actor scanner |
| tools/ced_capability_report.py | Complete CED capability matrix |
| tools/studio_source_surface_gap.py | Strict source extraction gap report |

## Acceptance and research integrity

The CED and dynamic class scanner can enumerate concepts not previously known to this repository. They do not automatically implement new C# scripts, proprietary shaders, custom Unreal Blueprint nodes or middleware. Those require handlers plus saved readback and source/target parity tests. World-space motion baking may preserve visible behavior without reconstructing the editable original group hierarchy.

The current real Unreal test proved 18/18 mapped assets, 10/10 actors and 2/2 direct parent links. Eight other missing source-parent actor relationships are still under issues #68 and #85. The 39-family implementation epic is #86: https://github.com/Nithin0553/CutsceneAI/issues/86 . Keep the existing Unreal level and frozen Benchmark001 unchanged; new catalog hashes apply to **new** trials only.

## Official API references

- Unity TypeCache: https://docs.unity3d.com/ScriptReference/TypeCache.GetTypesDerivedFrom.html
- Unreal Editor Python: https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python
- Unreal 5.8 Python class index: https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=5.8

## Native adapter candidate: Unity ActivationTrack visual-only mapping

For a fresh source-to-Unreal candidate only, a mapping may opt in to the partial fallback:

```json
{"enable_actor_visibility_fallback": true}
```

An authored Unity Timeline ActivationTrack classified as event.state, bound to a mapped actor, can produce actor_visibility keys on an Unreal MovieSceneVisibilityTrack (bHidden). Clip timing, target binding and source post-playback metadata must pass source-side checks.

**This is render-only approximation.** Unity GameObject activation can affect scripts, collision, physics and gameplay, while actor visibility only affects rendering. Unity postPlaybackState is not equivalent to an Unreal hidden flag. The source-side action therefore retains `semantic_losses` and `RENDER_ONLY_PARTIAL_UNVERIFIED`.

CED preflight labels event.state `KNOWN_PARTIAL` only when the mapping has opted in, and `KNOWN_UNSUPPORTED` otherwise. Source planning tests and Unreal builder contract tests do not substitute for real UE 5.8 save/reopen and visibility playback evidence.

Use a backed-up new staging target for tests. Do not edit or overwrite the existing verified Benchmark002 level.

## Data-driven native scalar property animation

The mapping can explicitly bind a Unity source curve semantic and native component class to an Unreal numeric actor/component property. One working example of the required mapping contract is:

```json
{
  "scalar_property_mappings": [
    {
      "source_semantic": "custom.light_temperature",
      "source_component_type": "MyGame.CustomLight",
      "source_entity_name": "MOVING_PROP",
      "target_scope": "component",
      "target_class": "PointLightComponent",
      "target_property_name": "Temperature",
      "target_property_path": "Temperature",
      "value_scale": 1.0,
      "value_offset": 0.0
    }
  ]
}
```

The source-adapter validates component identity, curve slope/tangents, absence of weighted keys, Timeline clip offset/time scaling, native frame-aligned timestamps, finite units, unique target writers, and exact actor mapping. It does not guess an Unreal property from the Unity name. Unreal's builder checks the destination class, component count, and numeric editor property **before modifying the scene**, then creates an editable MovieSceneFloatTrack with source-aligned linear keys.

Nonlinear/stepped keys, subframe timings, multiple source clips, nested target paths, and unsupported unit conversions remain explicit implementation work rather than silently retimed tracks. Native save/reopen and playback comparisons are still required before fidelity acceptance.

## Make the Unity source census part of automatic preparation

After exporting a matching Unity feature surface, add the following to the **copied new candidate mapping** (use an absolute Windows path when the Unity project is elsewhere):

```json
{
  "source_feature_surface_path": "B:/Research/Unity/Project/CutSceneAI/Exports/feature-surface-unity-EXAMPLE.json",
  "require_complete_source_features": true
}
```

The preparer checks Unity source project fingerprint, editor version, component/scene scope, missing MonoBehaviours and unimplemented native components. If strict, it blocks unsafe source coverage **before native generation**. Both report and original feature-census file hash are included in immutable preparation evidence and independently rechecked by the Unreal builder. A missing old census leaves the source feature-surface state NOT_COLLECTED, not full coverage verified. For an explicit best-effort diagnostic report, set require_complete_source_features to false; missing components stay reported and must not be called converted.
