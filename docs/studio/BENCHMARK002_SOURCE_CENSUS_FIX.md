# Benchmark002 Source Census: Captured native components

## Why Studio previously blocked before Unreal

The Unity scanner already emits partial authoring snapshots for:

- `UnityEngine.BoxCollider` and `UnityEngine.SphereCollider`: static shape,
  dimensions, center, rotation, trigger/enabled state and loss-of-scale policy.
- `UnityEngine.Rendering.Universal.UniversalAdditionalCameraData`: some
  URP camera settings plus serialized native values.
- `UnityEngine.Rendering.Universal.UniversalAdditionalLightData`: limited
  URP light override settings and serialized native values.
- `UnityEngine.Timeline.SignalReceiver`: registered persistent reaction
  target IDs and method names (not executable target event bindings).

`source_surface_gap.py` previously classified every one of these records
as `NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED` merely because it was
not in the short `KNOWN_SOURCE_COMPONENTS` list. That conflated two separate
questions:

1. **Did Unity record supported source authoring evidence for the component?**
2. **Did Unreal implement and independently verify equivalent behavior?**

This fix introduces the explicit
`SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED` source state.

With a matching Unity project ID and complete object/Transform scope,
correctly captured native source snapshots no longer count as *unextracted*
source components. They remain reported in
`source_snapshot_partial_findings` and are never marked native- or
behavior-verified. Existing `adaptive_components` decisions and the CED
coverage ledger retain the unconverted behavior (collider physics,
URP rendering, custom signal callbacks).

## Safety contract

No type-name-only whitelisting. The census requires exact Unity scanner
extraction signatures and actual source evidence:

- a unique source component ID;
- a matching extraction method label;
- an explicit non-truncated authoring-property scan;
- finite complete box/sphere geometry with declared scale policy;
- captured camera/light serialized or reflected settings; or
- internally consistent SignalReceiver reaction count and references.

Missing/legacy/malformed snapshots and arbitrary custom components still
block strict source coverage. The code does **not** generate new Unreal
physics bodies, URP shaders, signal/event callbacks, or guarantee parity.

## Test the fix on the real project

1. Check out `fix/benchmark002-source-census-captured-components`.
2. Update the CutSceneAI Unity extractor package in the Unity project from
   this repository, if the installed package is older.
3. In Unity, open Benchmark002 and use **Tools → CutsceneAI → Export Selected
   Timeline**, then **Tools → CutsceneAI → Discover Installed Feature Surface**.
   Both exports must be from the same project, source scene and engine build.
4. Restart Studio: `powershell -ExecutionPolicy Bypass -File
   .\tools\start_studio.ps1`. Connect the same Unity and a backed-up Unreal
   project. Leave **Allow best-effort conversion** unchecked for the baseline.
5. Click **Start Transfer** and inspect the source-census result. If the
   seven captures are valid, source-census strict readiness should be true
   with **0 unextracted source components** and **7 source-recorded partial
   components** (other source findings may remain).
6. Inspect native target readiness, transfer receipts and Unreal sequence.
   No successful end-to-end conversion or fidelity is implied by census
   readiness. Run CineTwin and the independent release audit when possible.

If the same block persists, inspect the exported
`CutSceneAI/Exports/feature-surface-unity-*.json` and confirm each affected
entry's `component_global_id`, `feature.extraction`,
`feature.native_properties_truncated` and required values. Do not upload
private scenes or source asset bytes just to diagnose this.

## Verification

Run:

```powershell
python -m pytest -q tests/studio/test_source_surface_gap.py tests/studio/test_studio_ui_feature_integration.py tests/studio/test_adaptive_components.py
python -m pytest -q
node tests/studio/test_cinematic_ui.cjs
```

Real Unity Editor re-export and a fresh Unreal transfer remain required.
