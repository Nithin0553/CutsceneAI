# Benchmark002 — rendered Unreal video diagnosis (2026-11-02)

## Evidence

User supplied a **screen recording** of a generated Benchmark002 Level Sequence
in Unreal Editor, about 11.7 seconds long. The screenshot frames show a
camera-cut sequence, two grey humanoid characters, some character movement,
a mostly black background and a World Outliner containing 10 mapped actors.
The Editor's Sequencer is set to 24 fps. No environment actors are visible
in the recorded Outliner. **The user confirms the transferred audio is
correct**; the uploaded MP4 has no audio stream, so that claim is user
evidence, not independent waveform validation.

Do not infer that every camera or animation track is broken simply from a
single Perspective viewport recording. It must be compared against a matching
Unity source-time frame capture before establishing behavioral parity.

## Verified source code limitations

- The original Unreal auto-import explicitly set `FbxImportUI.import_materials
  = False` and `import_textures = False`; this can leave newly imported
  character meshes with default grey materials.
- A partial source scene containing only 10 cutscene actors does not capture
  Unity's skybox, ambient RenderSettings or original terrain/environment.
  A black empty-level background can therefore be a missing-environment
  transfer, not necessarily a camera failure.
- Unity `.mat` assets, URP shader graphs, renderer-feature shaders and
  postprocessing-volume equivalence are not yet implemented in the native
  converter. Copying PNG files is not the same as assigning source materials.

## Implemented diagnostic and guarded fallback

1. `integrations/unreal/studio_visual_audit.py` is a **read-only** audit
   that runs on the actual generated level: counts native material slots,
   distinguishes empty/engine-default from nondefault assignments, checks
   sky/ambient/directional environment actors, and enumerates actual camera
   cut and skeletal animation tracks where the reflected API supports it.
   It does not guess source parity, render a new scene or rewrite audio.
2. Studio **Results** now provides the command to run this audit and reads
   the immutable `visual-audit-<job>-<unique>.json` evidence file alongside
   persistence and hierarchy reports. Older generated cutscenes can be
   inspected without generating a new candidate.
3. Studio **Review** has a default-off **Try importing basic materials
   embedded in character/prop FBX files** checkbox. This changes only a
   fresh candidate's copied mapping and enables Unreal's basic FBX material
   import for SkeletalMesh/StaticMesh imports, never audio/AnimSequence.
   The option may improve assets *only if* the underlying FBX contains
   transferable material references. It does **not** reconstruct Unity
   `.mat` or shaders and must be measured by native material-slot readback.
   It may create additional target material/texture assets inside the new
   candidate's unique namespace and must be tested only on a backed-up new
   staging level.

## Next real-engine test

**Do not delete or rerun the already-generated sequence.**

- Update the feature branch and restart Studio.
- In Unreal, open the project and saved level containing the successful
  generated sequence from the video.
- Under Studio Results, copy/run **Native audit command** in the Unreal
  Python Console; it now includes `studio_visual_audit.audit_latest()`
  if the active job has no visual report. Save the generated JSON evidence.
- Click **Refresh evidence** in Studio; compare material slots, default
  material count, SkyLight/SkyAtmosphere and actual native track counts.
- Do not add an arbitrary skybox or lighting to claim parity. Compare
  Unity's actual source sky/background, light settings and material
  references first.
- If a new visual-material trial is warranted, prepare a **fresh candidate**
  with the material checkbox on, use a different backed-up empty target level,
  generate once, save/reopen and rerun visual/hierarchy/persistence audits.
  Keep audio conversion settings unchanged.

## Acceptance gate before game-ready scenes

A real transfer pass needs independently saved/reopened actors, complete
time-evaluated animation/scene motion, matching camera frame composition,
assigned material slots and expected PBR appearance, source-scoped
environment/lighting reconstruction, all required events and hierarchy,
and source-to-target audio timing measurements. None of these are implied
solely by action count, material asset presence or a passing CI run.
