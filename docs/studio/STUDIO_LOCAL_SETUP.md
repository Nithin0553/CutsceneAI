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
  In Editor select `Tools > CutsceneAI > Studio Bridge > Enable Source Bridge`.
  A genuine CineTwin capture requires already-entered Play Mode; Studio cannot
  silently execute project scripts or change the editor to Play Mode.
- **Unreal:** Open the selected backed-up target `.uproject`, load the intended
  level and run the Studio-compatible editor worker using the command supplied
  in the Studio interface. The worker reports project/level and version identity;
  outdated or mismatched workers cannot be treated as connected to the target.
- **Model:** The real pre-transfer model requires a valid `OPENAI_API_KEY`
  within the local server process. The offline setup diagnostic verifies only
  the Python SDK is installed, never the key or an actual model invocation.

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
