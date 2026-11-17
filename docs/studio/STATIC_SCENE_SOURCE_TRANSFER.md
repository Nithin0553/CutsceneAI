# Source-backed static scenery included without Timeline tracks

## Observed problem (Benchmark002, November 9, 2026)

After the user added `ENV_TREE_LEFT`, `ENV_TREE_RIGHT`, `ENV_ROCK_LEFT` and
`ENV_ROCK_RIGHT` to a Unity scene, re-exported CSIR and source census, Studio
generated the existing 10 target actors and 11 imports, but no new scenery.
The Results UI reported 30 source entities lacking independent target bindings.
Other incomplete domains (URP shader, audio, skylight and missing CineTwin)
do **not** explain why new actors were absent from the generation plan.

**Root cause:** `UnityTimelineOffsetAugmenter.AugmentStaticSceneContext` already
records all renderable scene objects and their source mesh references. However,
`tools/studio_project_discovery._source_mapping` selected only actors with active
Timeline tracks and a limited attached-child special case. The fresh source
census is an inventory, not an automatic reconstruction instruction. A static
background object without a Timeline track therefore had no mapping/actor.

## First adapter scope (this PR)

- Add `scene_renderable_root` and `source_lod_group_root` flags to
  Unity source entity metadata. Direct renderer objects, LODGroup objects and
  actual prefab instance roots are recognized; their exact source
  `source_model_assets` records are retained.
- Source-scoped auto mapping now admits only static `entity.prop` roots
  belonging to the **same saved scene** as the selected PlayableDirector,
  marked as renderable and carrying **exactly one uniquely identified
  `Assets/.../*.fbx` source model path**. Actors maintain unique source names.
- Nested LOD0/LOD1 renderers are not independently spawned when their
  LODGroup parent is mapped or unresolved. Multi-FBX LODGroup content is
  deliberately left unresolved, not assigned an arbitrary mesh.
- Built-in Unity primitives, `.obj`/`.asset` meshes, shaders stored under
  `Packages/`, unavailable model bytes and duplicate source object names
  are **NOT** silently converted. Missing visible renderer roots now receive
  an explicit incomplete warning separate from auxiliary transform counts.
- No source Unity scene, frozen benchmark, existing Unreal asset or target
  namespace is modified by planning. Native importing still requires a fresh
  candidate, project/level validation and import permissions.

This is a reusable scene-renderer discovery contract, NOT an assertion of
all Unity/Unreal scene environment, LOD, material/URP shader or lighting parity.
Unsupported formats require new adapters.

## Local validation: fresh Unity export plus Unreal staging

1. Preserve the successful original Benchmark002 artifacts and back up the
   user Unreal project. Use a **new** Unreal target level and staging folder.
2. Install/update the Unity editor extractor from this exact checkout:
   `integrations/unity/com.cutsceneai.extractor/package.json`. In Unity,
   verify **Console compilation has no C# errors**; automated GitHub Actions
   do not compile the Unity editor package.
3. Open the saved Benchmark002 scene. Confirm scene props
   `ENV_TREE_LEFT`, `ENV_TREE_RIGHT`, `ENV_ROCK_LEFT`, `ENV_ROCK_RIGHT`
   are prefab roots with source model file paths in
   `Assets/...` and that any LOD meshes use the same source FBX. Otherwise
   expect a specific unresolved-object warning, not a fabricated conversion.
4. Select `CUTSCENE_DIRECTOR` and execute
   **Tools > CutsceneAI > Export Selected Timeline** and
   **Tools > CutsceneAI > Discover Installed Feature Surface**. Inspect CSIR
   metadata on the new scenery entities: `scene_renderable_root`,
   `source_lod_group_root`, `source_model_assets[].asset_path` and
   `parent_entity_id`.
5. Restart Studio and Unreal Editor on this checkout, reconnect the Unity/
   Unreal project roots and choose the **new** CSIR plus matching source census.
   Approve source copying into a unique candidate.
6. Before execution, compare planned actors/imports with the old 10/11
   baseline. Additional FBX-backed scenery roots should be listed as props
   and source FBX as StaticMesh imports. Unresolved primitives and multi-FBX
   LODs must be explicitly counted, not silently considered successful.
7. Execute the native staging and sequence generation. Independently inspect
   rendered static meshes, their source-derived world poses, materials,
   camera composition, and saved/reopened sequence. CineTwin/source render
   parity remains unverified until actual matching-time captures are attached.
8. Preserve CSIR, census, manifest, native receipts, visual audit and any
   exact unresolved source asset paths. If a source tree/rock still does not
   appear, distinguish **not mapped**, **unsupported source mesh format**,
   **import failed**, and **imported but material/LOD wrong**.

## Automated regression evidence

Coverage:
- Source-scene FBX roots appear in generated actor mappings with no Timeline
  track, while LOD children remain excluded.
- Missing/ambiguous multi-FBX LOD source roots, native Unity primitives, OBJ,
  duplicate names and unrelated scenes remain excluded.
- Source-backed new prop reaches the automatic StaticMesh import plan.
- A skipped renderable source root emits an explicit incomplete warning.
- C# source contract verifies exporter metadata is emitted.

The unit tests mock the input CSIR and source files; **real Unity and Unreal
acceptance is still required**. Use Issue #94 for source mesh mapping/format
coverage, #95 for adapter contracts, and #97 for native material/render parity.
