# Adaptive CED v0.3 — actual element conversion, not taxonomy-only

## Why the old Benchmark002 output did not change

CED v0.2 catalogued 735 semantics and displayed 39 families, but the original 25-action transfer plan was constructed from CSIR Timeline tracks **before** the Unity source census was consulted. The census did not contain component values. Increasing the CED count alone cannot change a Level Sequence.

This update adds a source-to-target execution path in actual `transfer_backend.compose_files()`. It does not change or overwrite existing Benchmark001 / Benchmark002 assets.

## New adaptive data flow

```text
Unity Editor source components (real project + scene IDs)
         |
         v
Typed feature census: URP camera, Unity Light, Box/Sphere geometry,
SignalReceiver reactions, and bounded native serialized scalar values
         |
         v
Verify Unity project fingerprint, scene scope and source CSIR
         |
         v
Match EXACT source scene path + hierarchy path + mapped actor
         |
         v
CED v0.2 semantic classification + registered native builder handler
         |
         v
Choose source-grounded native property action / explicit partial
         |
         v
Append new actions into immutable Studio transfer plan
         |
         v
Unreal native class/property preflight before editor mutation
         |
         v
Native editable Level Sequence BoolTrack / FloatTrack
         |
         v
Save/reopen + independent property and rendered-behavior verification
```

## Currently executable automatic rules

| Unity component property | Unreal target | Strategy | Evidence |
|---|---|---|---|
| UniversalAdditionalCameraData.renderPostProcessing | CineCameraComponent.post_process_blend_weight | Native editable FloatTrack at frame 0, 0 or 1 | Renderer-only partial candidate; URP effects/volumes/AA still differ |
| UnityEngine.Light.shadows | LightComponent.cast_shadows | Native editable BoolTrack at frame 0 | Shadow-enable candidate; shadow algorithms and filtering remain unverified |
| Explicit mapped C# serialized float/bool | Explicit target actor or component numeric/bool property | Validated native FloatTrack/BoolTrack | Requires exact native class/property readback, independent source-target evaluation |

Recognized but **not yet natively realized**: Unity BoxCollider and SphereCollider geometry/physics, SignalReceiver reaction dispatch, UniversalAdditionalLightData renderer overrides, URP camera stacking/renderer features and proprietary custom script logic. Source scanner now captures collider size/center/world orientation, SignalReceiver persistent target/method IDs, and common URP fields to support follow-on adapters. They remain visible gaps until native implementation and readback.

## Benchmark002 repeat test: IMPORTANT source rescan

**Old source census JSONs cannot create these new property actions.** They only contain type names. Open the same Unity Benchmark002 project and run **Tools → CutsceneAI → Discover Installed Feature Surface** again after updating the branch. Verify it writes a unique new `feature-surface-unity-*.json` under the Unity project-root `CutSceneAI/Exports` folder.

Restart Studio, connect the Benchmark002 CSIR to a backed-up **fresh empty Unreal level**, then in Review:

1. Click **Refresh Unity census** and choose the **newest** file (not the old one).
2. Check **Source identity confirmed**. Strict mode may still report seven component-level coverage gaps because the new adapters are partial, and collision/SignalReceiver runtime conversion is not yet complete.
3. For an explicitly best-effort baseline with real component actions, uncheck strict source-completeness; keep the new census **selected**. Leave ActivationTrack visual-only fallback unchecked.
4. Prepare once; look for **New adaptive Unreal actions** in Candidate feature accounting and expand **component-by-component conversion decisions**.
5. Only generate to the fresh Unreal target if the added actions match real source values. Native Unreal class/property reflection is checked before generation. Save All, restart Unreal, reopen the exact target and collect persistence/hierarchy reports.

**The number of added actions is source-dependent, not hardcoded.** For Benchmark002 we expect up to three URP camera post-process properties and one light shadow-casting property if the source census and exact actor paths match; do not invent 4/4 until the prepared report confirms it. A lack of new actions is actionable diagnostic evidence.

## Custom/game-ready component conversion: typed mapping

For plugin-defined properties, specify a trusted mapping in the source mapping JSON (Studio makes an immutable candidate copy):

```json
{
  "component_property_mappings": [
    {
      "source_component_type": "MyCompany.CinematicGlow",
      "source_entity_name": "CAM_A_Wide",
      "source_property_path": "m_Intensity",
      "source_semantic": "metadata.property_descriptor",
      "value_type": "float",
      "target_scope": "component",
      "target_class": "CineCameraComponent",
      "target_property_name": "post_process_blend_weight",
      "value_scale": 1.0,
      "value_offset": 0.0
    }
  ]
}
```

This contract requires the exact source serialized member, mapped entity, native Unreal class/property, expected type and explicit units. It does **not** infer function equivalence from names, execute custom source code, or claim plugin behavior parity. Unsafe, ambiguous or unrepresentable mappings are rejected or remain in the evidence ledger.

## Source and native verification

- `packages/studio/adaptive_components.py`: typed adaptation and per-source decision records.
- `packages/studio/feature_dispatch.py`: canonical CED semantic → native builder action constraints.
- `integrations/unity/com.cutsceneai.extractor/Editor/CutSceneAIFeatureSurfaceScanner.cs`: safe source property extraction, reference IDs and bounded native scalar property scanning.
- `integrations/unreal/build_level_sequence.py`: native validated FloatTrack and BoolTrack construction.
- `tools/studio_local_bridge.py` and `apps/studio-web/app.js`: expose concrete action counts and component decisions.
- `tests/studio/test_adaptive_components.py`: proves fresh source census adds real planned Unreal actions instead of only adding dictionary entries.

CI validates source parsing, native action planning, type safety and code syntax. It cannot establish Unity Editor C# compilation or Unreal 5.8 runtime behavior. These require the local engine run before marking conversion pass. Frozen previous evidence is not retrospectively relabeled.

## Official references

- [Unreal Sequencer Python](https://dev.epicgames.com/documentation/unreal-engine/python-scripting-in-sequencer-in-unreal-engine?lang=en-US)
- [Unity URP camera additional data](https://docs.unity3d.com/kr/Packages/com.unity.render-pipelines.universal%4014.0/api/UnityEngine.Rendering.Universal.UniversalAdditionalCameraData.html)
- [Unreal CineCameraComponent native properties](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/CineCameraComponent)
- [Unreal LightComponent shadow properties](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/LightComponent)
