# CutSceneAI Studio — Windows Local Setup (Software-Only)

**Status:** Release-candidate bootstrap, not an engine acceptance report. This
procedure does not open Unity/Unreal, invoke an external model or import assets.
It tests only the local Python/web Studio prerequisites.

## Phase 10.5 Windows first-run launcher

For a fresh checkout or extracted `CutSceneAI-Studio-source.zip`, open
PowerShell in the Studio root and run:

```powershell
.\tools\launch_studio.ps1
```

The launcher performs an isolated first-time dependency installation if
necessary, a strict setup preflight and a **real localhost Studio startup
smoke in a temporary workspace**, before starting the normal supervised UI.
Then open **http://127.0.0.1:8765**. It does not launch/restart Unity or
Unreal, invoke an LLM, or queue a transfer. Source-backed engine connections
and final fidelity remain separate. See [Phase 10.5 full engine-test entry
runbook](PHASE10_5_FINAL_SOFTWARE_PACKAGE_AND_LIVE_ENGINE_TEST_ENTRY.md).

The CI distribution job extracts the source ZIP into a clean Windows directory,
installs it independently, verifies the ZIP bytes against the extracted
workspace, starts the actual Studio server and archives a separate
source-hash-matched startup report. Only a fully green cross-platform
software-acceptance job may label the package
`SOFTWARE_PACKAGE_READY_FOR_ENGINE_TEST`.

## Isolated bootstrap

From a full checkout of the release-candidate branch in Windows PowerShell:

```powershell
.\tools\install_studio.ps1
.\tools\start_studio.ps1
```

The installer checks that Python 3.11+ is available, creates a dedicated
`.venv-studio` environment, installs the repository's declared `.[agents]`
dependency set, and runs a strict setup diagnostic. It does not edit either
engine project.

**Keep this PowerShell Studio launcher open during development.** Its
`--watch` supervisor detects changes to trusted Studio host Python modules,
checks that the files are syntax-valid and stable, waits until no queued,
running or uncertain native transfer exists, and restarts **only the Studio
localhost Python process** on the same port. The running Unity and Unreal
Editors do not close; their own file-bridge heartbeats automatically reconnect.
The browser polls the new server and obtains its new local session token.
While the backend reloads, avoid submitting another transfer. Invalid code
blocks new mutations rather than replaying an existing candidate.

For code changes made while the Editor is running, ordinary Unity C# changes
recompile in the existing Unity process and eligible Unreal Python modules
reload on an idle editor tick. You do not need to close and reopen both
editors after each git pull. The first installation/enablement of each
engine companion remains a separate, explicit one-time setup step. To use a different Python executable:

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

## Phase 10.3 — Project companion setup with explicit opt-in

The repository now includes a project-local, two-stage wiring tool. It does
**not** open either Editor or claim a connected companion. Run the first
command without `--apply` to inspect the complete proposed changes:

```powershell
python tools/studio_companion_install.py --unity "D:\\UnityProject" --unreal-uproject "D:\\UnrealProject\\Game.uproject"
python tools/studio_companion_install.py --unity "D:\\UnityProject" --unreal-uproject "D:\\UnrealProject\\Game.uproject" --apply
```

Only the second, explicitly approved command writes project-local files.
Unity receives a source-repository UPM file dependency in
`Packages/manifest.json`, preserving a before-install backup. Unreal
receives `Content/Python/init_unreal.py` only if the selected .uproject
already enables `PythonScriptPlugin` and the startup file is absent or
exactly Studio-owned. Foreign startup scripts, redirects and conflicting
Unity dependencies **block without overwriting**. Unreal's startup hook
still needs real Editor/worker heartbeat verification; Unity's source bridge
must still be enabled once in that project.

A source-only, reproducible ZIP for clean-workstation bootstrap is available:

```powershell
python tools/build_studio_bundle.py --output "D:\\Releases\\CutSceneAI-Studio-source.zip"
python tools/build_studio_bundle.py --output "D:\\Releases\\CutSceneAI-Studio-source.zip" --verify
```

CI checks the exact ZIP hashes and publishes it as an Actions artifact.
This distribution is **not** a signed standalone desktop installer; Python
dependencies and the actual Unity/Unreal installations are external.
See [Phase 10.3 six-area software contract](PHASE10_3_SIX_AREA_CONSOLIDATION_AND_10_4_START.md).

## Local Ollama inference on memory-constrained Windows workstations

The Studio software setup does not start Ollama or load model weights. For
the AI transfer workflow, first verify the configured model with
`ollama list` and a structured `/api/chat` request. A successful
`/api/tags` connection proves only that the Ollama service is listening.

The localhost Ollama provider defaults to a **120-second** bounded inference
request timeout, rather than 40 seconds, to accommodate local model loading and
JSON strategy generation. It can be configured before starting Studio:

```powershell
$env:CUTSCENEAI_MODEL_PROVIDER = "ollama"
$env:CUTSCENEAI_AGENT_MODEL = "qwen2.5:7b-instruct"
$env:CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS = "120"
.\tools\start_studio.ps1
```

Only integer timeouts from 10 through 300 seconds are accepted. The transport
distinguishes timeouts, unavailable local services, HTTP 404 missing models, and
HTTP 500 memory errors when Ollama provides memory-failure evidence. Slow
inference and out-of-memory conditions block for human investigation instead of
silently retrying; only actual pre-native connection failures receive the
existing bounded retry policy. A blocked AI attempt with no candidate/job ID
must be cancelled and restarted as a fresh transfer after the cause is fixed.
No Unity or Unreal Editor restart is needed to change the Studio host setting.

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
- **Model:** The agent now supports local Ollama (recommended for open-weight
  inference) or explicit OpenAI Responses. Set `CUTSCENEAI_MODEL_PROVIDER=ollama`
  and install/start the configured Ollama model; no OpenAI API key is needed.
  A configured `OPENAI_API_KEY` remains supported when cloud mode is selected.
  The offline setup check does not verify a real local or cloud model call.
  See [Agent-centric architecture](AGENT_CENTRIC_ARCHITECTURE_V1.md).

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

## Windows Unity source heartbeat sharing conflicts

The Unity bridge publishes a project-scoped \`unity-editor.json\` through
atomic file replacement every 0.7 seconds. A brief Windows sharing conflict
can cause \`IOException: Unable to remove the file to be replaced\`, even
when the selected Unity project itself is writable. Studio cannot use
a stale heartbeat to authorize source-export requests.

The bridge stages the heartbeat under a unique temporary filename and
retries the atomic replacement a bounded four times (150 ms total retry
sleep). It never truncates, deletes or overwrites the last successful
heartbeat as a fallback. A permanent read-only/permission failure or
persistent external lock still blocks source requests and raises a Unity
Console warning instead of pretending the Editor is connected.

Check the exact source project's heartbeat in PowerShell:

\`\`\`powershell
$bridge = "D:\Path\To\UnityProject\CutSceneAI\StudioBridge"
$presence = Get-Content "$bridge\unity-editor.json" -Raw | ConvertFrom-Json
$presence | Select-Object project_root, source_bridge_enabled, editor_mode, heartbeat
$age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($presence.heartbeat)).TotalSeconds
[math]::Round($age, 1)
\`\`\`

The emitted heartbeat must name the exact Unity project, have the source
bridge enabled and be fresh (normally under eight seconds for Studio's
connected check). If it is fresh, no native restart or manual file deletion
is needed; use the bridge to export a new paired CSIR/census. Otherwise
inspect locks/ACLs without deleting receipts, evidence, or the Unity scene.
The regression test checks source-level safety; actual Windows locking
and Unity C# compilation must still be verified on a real workstation.

## What CI verifies

`.github/workflows/ci.yml` runs the Python, JS, syntax, lint and repository
checks as well as the Windows dependency-bootstrap smoke test. The Windows CI
runner has no Unity/Unreal editor acceptance evidence. Green CI must never be
reported as a completed cutscene-transfer fidelity test.
