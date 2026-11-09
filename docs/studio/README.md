# CutSceneAI Studio — local connected UI (v0.8)

This directory documents the local browser UI and the source-driven fresh Unreal target experiments. The application is a development interface over the existing CutSceneAI source-CSIR planner and Unreal Editor adapters; it is **not** a fully automated project-to-project converter.

## Run locally

From the CutSceneAI repository root on Windows (Python and pytest installed):

```powershell
python -m pytest -q tests/studio/test_studio_local_bridge.py
powershell -ExecutionPolicy Bypass -File .\tools\start_studio.ps1
```

Open <http://127.0.0.1:8765>. The server listens on loopback only. It has no cloud backend.

## Two-folder discovery (v0.7)

Users can select the Unity **project root or `Assets/`** and the Unreal **project root or `Content/`** using native folder dialogs. Studio recognizes a parent folder holding several projects and asks the user which one to open; if several valid CSIR exports, `.uproject` files, or maps exist, it presents choices rather than guessing. The backend scans for actual schema-matched Unity CSIR JSON files within the project (even with different filenames or nested export paths). It never treats a native `.unity` / `.playable` file as a verified CSIR without an exporter; when no export exists, it explains the required Unity export step.

When the Unreal project contains no saved `.umap` and there is no valid loaded map, Studio may **plan** `/Game/CutSceneAI/AutoTransfer/L_Studio_Fresh`. This is only an intent: the folder scan and connection do not write to Unreal. During an explicitly approved automatic generation run, the Unreal worker checks the immutable source/plan, current `.uproject`, map-name collision, and dirty state of the open map before creating the new map with the Unreal Level Editor Subsystem. If the editor cannot verify that the current map is saved, creation is blocked. The map and Level Sequence are never overwritten. The new-level integration has local mock/API tests; real Unreal Editor validation is still required.

## Studio workflow

1. **Connect** the exported Unity CSIR JSON, mapping JSON, target Unreal `.uproject`, and target `/Game/...` level. To enable automatic staging, also provide the local Unity project directory, a cutscene-specific `Assets/...` subtree, and source-copy permission. A CineTwin capture is optional.
2. **Select** the cutscene exported in the CSIR. The current UI supports **one exported CSIR at a time**, not whole-project discovery.
3. **Review**: prepare a new immutable, source-verified candidate and (when Unity files are configured) a manifest identifying matched models, clips, audio, textures, and target actor labels. Inspect planned actions, CED flags, track coverage, and provenance. Review warnings when the mapping's sequence namespace differs from the selected level, or when audio assets have not been verified.
4. **Transfer**: back up the target project, open the intended level in Unreal Editor, and start the on-screen editor companion from the Unreal Python Console. **Destination readiness** checks the real level for uniquely named mapped actors with suitable component types, required AnimSequence/SoundWave assets and a free output sequence path. Generation is disabled until it passes. A fresh project/level heartbeat and explicit approval are also required. Existing sequences are not overwritten.
5. **Results**: inspect runtime receipts, errors and optionally attach an existing Unreal CineTwin target observation JSON without rerunning the generator.

Missing prerequisites are shown on the Transfer page as `SCENE_SETUP_REQUIRED` or `ASSETS_REQUIRED`, without submitting a job. The server checks the editor-signed freshness of the exact candidate, source mapping and loaded project/level, and the worker rechecks immediately before building. After updating from v0.3, **restart Unreal Editor** to reload `studio_local_editor_worker.py`; the old worker is rejected by the UI. The readiness check does **not** automatically import missing assets or actors; those remain a prerequisite of the current beta.

A generated sequence has status `GENERATED_UNVERIFIED`; saved readback and independently observed source/target behavior are separate validation gates.

## Engine adapter scripts and verified research checkpoints

Fresh-target experimental scripts (kept separately from the generic UI/API):

| Stage | Pure Python planner / tooling | Unreal Editor script |
|---|---|---|
| 1: assets | `tools/studio_fresh_target_assets.py` | `integrations/unreal/studio_import_fresh_target.py` |
| 2: animation assets | `tools/studio_fresh_animation_plan.py` | `integrations/unreal/studio_import_fresh_animations.py` |
| 3: actors | `tools/studio_stage3_scene_plan.py` | `integrations/unreal/studio_stage3_scene.py` |
| 3: saved audit | — | `integrations/unreal/studio_audit_stage3_scene.py` |
| 4: layout + attachment | `tools/studio_stage4_layout.py` | `integrations/unreal/studio_stage4_apply.py` |
| 4: saved audit | — | `integrations/unreal/studio_audit_stage4_layout.py` |

The standalone Stage 4 layout planner includes a precision-tolerant floating-point verification fix. Its hashes, identities, mappings and hierarchy still require exact matches. The editor scripts require an interactive, correctly loaded target Unreal project and cannot be run by ordinary Python. The v0.5 automatic setup path is separate and currently implements source-backed, unverified imports and actor staging, not the same persistence audit and hierarchy guarantees as those experimental scripts.

Use `config/benchmark002_animation_assignments.example.json` only as a sample assignment file, not a universal transfer rule. Keep generated reports/receipts, `.uproject`, imported assets, Unity project content and source scene data **outside** this source-code repository.

## Safety and current limitations

- Source scene and Benchmark001 freeze remain unchanged; the Studio UI does not save or import assets during planning.
- Server binds to `127.0.0.1`, checks request origin and anti-CSRF token for writes, validates exact file hashes and provenance, verifies the selected project/level, requires source-copy permission and refuses sequence/asset overwrite. An importer that partially mutates Unreal produces `PARTIAL_SETUP_MUST_INSPECT` and must not be replayed blindly.
- Source capture validation and saved sequence verification are independent of successful editor generation. No visual or semantic equivalence is assumed.
- Not yet one-click: Unity Editor timeline extraction (CSIR must already exist), automatic materials/shaders/texture assignment, prop mesh fidelity, FBX rig compatibility and retargeting, dynamic plugins, full signal semantics, creating a new `.uproject`, complete CineTwin parity, and frame comparison. The matched FBX clip name is a source-identity hypothesis, not proof of a compatible animation. A source asset that is only a Unity `.anim` file or is ambiguous must be exported or mapped explicitly; Studio does not fabricate it.
- `REVIEW_REQUIRED` CED status and `NATIVE_UNVERIFIED` coverage are warnings, not transfer success guarantees.
- A destination preflight prevents the common first-run failure (`Expected exactly one level actor ... found 0`). It is an early guard, **not** a universal automatic-scene setup capability or a promise that Unreal generation cannot fail for other reasons.

## Tests

Local API, automatic import, and Stage 1–4 planner/editor-mock tests can run without Unreal installed:

```powershell
python -m pytest -q tests/studio/test_studio_local_bridge.py tests/studio/test_studio_destination_preflight.py tests/studio/test_studio_destination_worker.py tests/studio/test_studio_fresh_target_assets.py tests/studio/test_studio_import_fresh_target.py tests/studio/test_studio_fresh_animations.py tests/test_studio_stage3_scene.py tests/test_studio_stage4_layout.py tests/test_studio_stage4_precision.py tests/test_studio_audit_stage4_layout.py
```

Actual v0.5 end-to-end import and Level Sequence generation in Unreal 5.8.3 still requires testing in the user's fresh staging project; local fake-Editor tests do not establish successful rendering, skeleton compatibility, or fidelity. A successful editor generation remains `GENERATED_UNVERIFIED`.

## Two-folder project connection (v0.6)

The **Projects** screen now provides native **Browse folder** controls. On a Windows
workstation, the localhost companion opens a native folder-selection dialog;
the browser itself does not have permission to reveal full local paths.

1. Select the Unity project directory (containing `Assets/` and `ProjectSettings/`).
2. Select the Unreal project directory (containing exactly one `.uproject`).
3. Studio finds *previously exported* Unity CSIR files in `CutsceneAI/Exports`,
   `CutSceneAI/Exports`, or `Exports`; inspects saved Unreal `.umap` levels; and
   identifies the editor's active map when available. With multiple matches,
   choose from a dropdown (no path entry).
4. On **Connect projects**, Studio creates a non-overwriting mapping proposal
   inside `~/.cutsceneai-studio/runs/discovered-mappings/`, matches a Unity
   CineTwin capture only when the exact CSIR digest agrees, and binds the
   selected source/target files into the existing validated Studio connection.
5. **Prepare transfer** creates new immutable transfer artifacts. Automatic
   asset scanning begins at the selected Unity project's `Assets/` root; the
   importer accepts this scope and reports missing/ambiguous assets before
   generating. Explicit permission to copy source assets remains required.

**Important limits:** This is *project discovery and mapping setup*, not
in-editor Unity Timeline extraction. A Unity CSIR must have been exported at
least once with the CutSceneAI Unity extractor; when no export exists, the UI
shows the precise Unity menu action, never invents a source cutscene. An
Unreal map must already exist or be loaded/saved; the user may need to select
one from the detected dropdown. Unreal Editor and the Studio companion must
still be running to modify the destination. Source-derived mappings are
proposals and cannot establish asset correctness or cinematic parity.
Do not commit generated local mappings, cutscenes, or Unity/Unreal project
content to the code repository.

The native picker is supported on Windows only in this release. Existing
legacy JSON-path `/api/connect` calls remain supported for diagnostic and
integration-test compatibility; the normal GUI no longer exposes them.

## Texture and readiness diagnostics (v0.8)

The current Unity exporter records the rendered mesh's actual AssetDatabase
path/GUID and the renderer's material and base-color texture references. After
updating the Unity extractor package, run **Tools → CutsceneAI → Export Selected
Timeline** again to create a CSIR with these identities. For a strict source
census, also rerun **Discover Installed Feature Surface**. Older CSIR files
without these fields retain the conservative name-resolution fallback and do
not establish material provenance.

The current census records serialized enum values and referenced Unity
object/asset identities alongside scalar component properties. Strict source
scope requires a matching Transform for every CSIR scene object; a census
that sees only some cutscene objects is blocked and identifies each missing
path. These extra source values are evidence for future adapters, not proof
that URP render behavior, colliders, or signal callbacks transfer to Unreal.

Automatic staging can follow an exact renderer FBX, `.mat`, or PNG reference
elsewhere inside the selected Unity project's `Assets/`, even when the chosen
search subtree is narrower. It checks the exported GUID against the Unity
`.meta` file when a GUID is present and blocks conflicting character identity.
An exported character with no rendered model asset is not replaced by an FBX
whose filename happens to match its name. Native `.anim`, non-FBX meshes and
other unsupported source formats still need an explicit adapter or a truthful
blocked/partial outcome.

Only source-referenced PNGs are planned for import. Unrelated tutorial/editor
PNG files are ignored; a referenced invalid PNG is reported and skipped, with
material appearance still unverified. Source-backed `.mat` + texture GUID and
the actual imported FBX slot name are required for automatic albedo recovery;
arbitrary URP shader/sky behavior is not reconstructed. An empty required
asset or invalid required WAV still blocks preparation.

The Transfer screen no longer shows an indefinite `Checking...` when the editor probe is missing, stale or failing: it reports `INSPECTION_UNAVAILABLE`, `INSPECTION_FAILED` or `UPGRADE_COMPANION` and explains the next action. The Unreal worker emits a diagnostic readiness report on inspection errors; generation remains disabled until verified. The new companion version is `studio-editor-v0.4`; **restart Unreal Editor after pulling changes** to unload the previous Python module before running the companion command.
