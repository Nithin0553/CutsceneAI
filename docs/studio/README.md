# CutSceneAI Studio — local connected UI (v0.4)

This directory documents the local browser UI and the source-driven fresh Unreal target experiments. The application is a development interface over the existing CutSceneAI source-CSIR planner and Unreal Editor adapters; it is **not** a fully automated project-to-project converter.

## Run locally

From the CutSceneAI repository root on Windows (Python and pytest installed):

```powershell
python -m pytest -q tests/studio/test_studio_local_bridge.py
powershell -ExecutionPolicy Bypass -File .\tools\start_studio.ps1
```

Open <http://127.0.0.1:8765>. The server listens on loopback only. It has no cloud backend.

## Studio workflow

1. **Connect** the exported Unity CSIR JSON, mapping JSON, target Unreal `.uproject`, and target `/Game/...` level. A matching Unity CineTwin source behavior capture is optional for preparation.
2. **Select** the cutscene exported in the CSIR. The current UI supports **one exported CSIR at a time**, not whole-project discovery.
3. **Review**: prepare a new immutable, source-verified candidate and inspect the actual planned actions, CED flags, track coverage and mapping provenance. Review warnings when the mapping's sequence namespace differs from the selected level, or when audio assets have not been verified.
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

The Stage 4 layout planner includes a precision-tolerant floating-point verification fix. Its hashes, identities, mappings and hierarchy still require exact matches. The editor scripts require an interactive, correctly loaded target Unreal project and cannot be run by ordinary Python.

Use `config/benchmark002_animation_assignments.example.json` only as a sample assignment file, not a universal transfer rule. Keep generated reports/receipts, `.uproject`, imported assets, Unity project content and source scene data **outside** this source-code repository.

## Safety and current limitations

- Source scene and Benchmark001 freeze remain unchanged; the Studio UI does not save or import assets during planning.
- Server binds to `127.0.0.1`, checks request origin and anti-CSRF token for write operations, and refuses sequence overwrites.
- Source capture validation and saved sequence verification are independent of successful editor generation. No visual or semantic equivalence is assumed.
- Not yet one-click from this interface: Unity project folder discovery and extraction, generic material/prop/audio import, end-to-end project creation, verified asset mappings, all-domain CineTwin parity, and rendered source/target image comparison.
- `REVIEW_REQUIRED` CED status and `NATIVE_UNVERIFIED` coverage are warnings, not transfer success guarantees.
- A destination preflight prevents the common first-run failure (`Expected exactly one level actor ... found 0`). It is an early guard, **not** a universal automatic-scene setup capability or a promise that Unreal generation cannot fail for other reasons.

## Tests

Local integration and Stage 1–4 planner/editor-mock tests can run without Unreal installed:

```powershell
python -m pytest -q tests/studio/test_studio_local_bridge.py tests/studio/test_studio_destination_preflight.py tests/studio/test_studio_destination_worker.py tests/studio/test_studio_fresh_target_assets.py tests/studio/test_studio_import_fresh_target.py tests/studio/test_studio_fresh_animations.py tests/test_studio_stage3_scene.py tests/test_studio_stage4_layout.py tests/test_studio_stage4_precision.py tests/test_studio_audit_stage4_layout.py
```

Actual integration with a running Unreal 5.8 Editor and Unity capture requires separate on-machine validation; the mock tests do not prove that a source cutscene is faithfully reconstructed.
