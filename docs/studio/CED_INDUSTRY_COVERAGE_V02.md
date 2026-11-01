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
