# Benchmark002: Multi-mesh FBX StaticMesh import recovery

This diagnostic is from a **real Unreal 5.8 workstation run** (2026-11-17). Source CineTwin capture succeeded. Importing the planned prop `CSAI_ENV_TREE_LEFT` from `Assets/SimpleNaturePack/Models/Tree_02.fbx` generated native `Tree_02_LOD0` and `Tree_02_LOD1` StaticMesh assets instead of the expected single planned name. The editor recorded `PARTIAL_SETUP_MUST_INSPECT` under target namespace `/Game/CutSceneAI/AutoTransfer/T_3644CA36`. No Level Sequence was produced.

The observed failure was specifically `Import did not create StaticMesh at /Game/CutSceneAI/AutoTransfer/T_3644CA36/Props/CSAI_ENV_TREE_LEFT`. Both native LOD assets were physically present, and earlier character and rock imports had succeeded. This is an importer naming mismatch, **not** a completed or fidelity-verified transfer.

## Code fix in draft integration PR #124

- For each planned static prop, import source FBX in an isolated per-target staging folder. Repeated FBXs used by several props (e.g., left/right trees) cannot collide on their shared source mesh-node names.
- When Unreal produces the planned exact StaticMesh in that folder, copy it to the prepared canonical target. Otherwise inspect only that task's `imported_object_paths`, require a unique source-bound `_LOD0` StaticMesh and reject unexpected/ambiguous imported meshes. Copy selected LOD0 into the exact **new** asset target using `EditorAssetLibrary.duplicate_asset`; never overwrite an existing asset.
- Preserve the separately created `_LOD1` and other source LOD meshes as provenance; do **not** claim they were configured as Unreal LOD levels. Receipt `static_mesh_imports` records selected source path, canonical target, unverified other LOD nodes and `lod_chain_verified=false`.
- If no unambiguous LOD0 exists or native copy fails, stop with a precise partial-mutation receipt; do not synthesize a mesh or silently combine source LODs.

## Workstation retry: do not replay the partial candidate

1. Retain the failed candidate receipt and existing `T_3644CA36` assets. Work only in the backed-up/disposable `Test_Project`, never the original research frozen scene.
2. Pull the latest `integration/agent-native-adapters-v0.1` into the separate `CutsceneAI-Acceptance` checkout. Stop the Studio server and **fully restart Unreal Editor** to unload the previously imported native Python modules.
3. Open the same intended `D:\CutSceneAI - Studio\Unreal\Test_Project\Test_Project.uproject` and saved level `/Game/AI_Test01`. Re-enable its Unreal worker from the current checkout and verify the actual project/level and the active worker.
4. Start the Studio server again. Return from the blocked view to Projects, select the existing Unity Benchmark002 and target Unreal test project, and begin **one new** transfer. This must create a fresh candidate/asset namespace; do not edit or reuse the old immutable manifest.
5. The Unity companion will need fresh Edit Mode extraction and Play Mode CineTwin source capture; enter Play Mode when prompted. Preserve exact logs and report any new native failure.
6. After native generation, require an editable Level Sequence, saved asset readback and a **new Unreal process** for independent CineTwin persistence and playback acceptance.

The code fix is verified by Python fake-Editor tests, including two props sharing a multi-LOD source FBX. It still requires an actual Unreal 5.8 retest; native LOD switching, rendered fidelity, skeleton motion, events and sound remain unverified.

Reference: Epic Games' official Unreal FBX import guide explains why a source FBX containing multiple meshes can create multiple StaticMesh assets rather than a single destination-named asset.
