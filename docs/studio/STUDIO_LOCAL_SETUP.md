# CutSceneAI Studio — Windows Local Setup (Software-Only)

**Status:** Release-candidate bootstrap, not an engine acceptance report. This
procedure does not open Unity/Unreal, invoke an external model or import assets.
It tests only the local Python/web Studio prerequisites.

## Isolated bootstrap

From a full checkout of the release-candidate branch in Windows PowerShell:

```powershell
.\tools\install_studio.ps1
.\tools\start_studio.ps1
```

The installer checks that Python 3.11+ is available, creates a dedicated
`.venv-studio` environment, installs the repository's declared `.[agents]`
dependency set, and runs a strict setup diagnostic. It does not edit either
engine project. To use a different Python executable:

```powershell
.\tools\install_studio.ps1 -Python "C:\Path\To\python.exe"
```

A developer can inspect prerequisites without launching Studio:

```powershell
.\.venv-studio\Scripts\python.exe .\tools\check_studio_setup.py --json --strict
```

`ready_to_launch_localhost=true` confirms only the Python runtime and checkout
layout. It does **not** confirm a running engine, an installed/enabled editor
companion, valid source capture, an actual OpenAI response, generated native
assets or cross-engine fidelity.

## Companion setup remains explicit and bounded

- **Unity:** Add or confirm the extractor package
  `integrations/unity/com.cutsceneai.extractor` in the *selected* Unity project.
  For live local-repo changes, ensure the Unity project references the local
  package folder, rather than a stale copied package. In Editor select
  `Tools > CutsceneAI > Studio Bridge > Enable Source Bridge` **once**.
  The `[InitializeOnLoad]` callback automatically resumes after Unity C#
  script compilation/domain reload. Unity writes a scoped, read-only
  `CutSceneAI/StudioBridge/unity-editor.json` heartbeat; Studio detects
  reconnects without a second enable click or reopening the Unity Editor.
  A genuine CineTwin capture still requires **manually entered Play Mode**;
  Studio never silently starts scripts or replays an export receipt.
- **Unreal:** Open the selected backed-up target `.uproject`, load the intended
  level and start the editor worker with the command supplied in Studio
  **once**. The upgraded worker uses a stable callback that dynamically
  dispatches to the current Python module, refreshes its own changed Python
  source and trusted planning/adapter modules when the native worker is idle,
  and resumes its heartbeat **without closing Unreal Editor**. Changes during
  an active/uncertain native job wait for inspection; a broken update blocks
  native transfer and never authorizes replay. Studio shows the source and
  target editor heartbeats and can reconnect automatically after source updates.
  A worker loaded before this feature was added may need a **one-time in-editor
  Python console reload** with no native job running:
  `import importlib, studio_local_editor_worker as w; w.stop(); importlib.reload(w); w.start()`.
  Outdated or mismatched worker/adapter code never counts as transfer-ready.
  See [Live bridge continuity](LIVE_BRIDGE_CONTINUITY.md).
- **Model:** The real pre-transfer model requires a valid `OPENAI_API_KEY`
  within the local server process. The offline setup diagnostic verifies only
  the Python SDK is installed, never the key or an actual model invocation.

**Limits:** Python-only Unreal edits can refresh without an editor restart.
Unity can recompile/reload its C# domain in the same editor, but changes to
native C++ plugins, engine binaries, project/UPM package wiring or damaged
loaded packages may still require an engine-mandated restart. Independent
fresh-process persistence acceptance remains a separate later gate; it is not
required after every routine code edit. No engine was launched to validate this
automatic reconnection behavior in the current CI run.

Do not start native transfer tests until the release-candidate software
contract records `SOFTWARE_READY_FOR_ENGINE_TEST` with an exact reviewed SHA
and green CI run. Treat restart recovery as **non-replaying**: an existing native
job is recovered by verified job/candidate identity, never resubmitted.
An expired read-only character inspection must end with an explicit error.
If interrupted after creating a candidate but before finalizing state, Studio
blocks and preserves the partial candidate instead of silently preparing it
twice.

## What CI verifies

`.github/workflows/ci.yml` runs the Python, JS, syntax, lint and repository
checks as well as the Windows dependency-bootstrap smoke test. The Windows CI
runner has no Unity/Unreal editor acceptance evidence. Green CI must never be
reported as a completed cutscene-transfer fidelity test.
