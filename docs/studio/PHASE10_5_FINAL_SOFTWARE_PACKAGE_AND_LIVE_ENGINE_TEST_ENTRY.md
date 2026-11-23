# Phase 10.5 — Software package handoff and first real Studio launch

**Decision scope:** `SOFTWARE_PACKAGE_READY_FOR_ENGINE_TEST` requires one matching commit with a green 19-gate Phase 10.4 rehearsal, valid SHA256-manifested source distribution, exact source ZIP matching the reviewed checkout, a **fresh extracted Windows installation that really starts the Studio localhost process**, and a cross-platform CI evidence correlation. It **never** means full Unity-to-Unreal cinematic fidelity is verified.

The final production freeze remains **blocked** until genuine Unity, Unreal, renderer, audio, effects, character and held-out acceptance is documented. This is an intentional release contract; engine tests begin **after** the pre-engine software package checks.

## Phase 10.5 software deliverables

| Deliverable | Evidence / contract |
|---|---|
| Full source-based Windows distribution | `tools/build_studio_bundle.py` builds deterministic ZIP with per-file SHA256 and refuses sensitive files, symlinks, tampering and overwrites |
| First-time install and start | `tools/launch_studio.ps1` creates only the isolated Python environment if missing, runs strict local setup and a real localhost smoke before handing control to the existing supervised Studio server |
| Actual packaged Studio startup | `tools/studio_startup_smoke.py` executes real `studio_local_bridge.py` from extracted ZIP, checks browser entrypoint, JavaScript, session token, default read-only stage diagnostics, foreign host blocking, absence of native jobs and fresh release status, then terminates that temporary host |
| Windows clean distribution acceptance | CI makes the ZIP, extracts it to a separate folder, installs Python dependencies there, verifies the exact ZIP matches extracted contents, starts Studio, and archives the report |
| Source-bound software freeze | `tools/phase10_5_freeze_preflight.py` verifies exact clean Git SHA, byte-identical ZIP, the 19-gate source/JS tests and immutable Phase 10.4 software evidence |
| Cross-platform handoff | `tools/phase10_5_package_acceptance.py` requires independent Ubuntu and Windows CI success **against identical LF-normalized per-file source content SHA256 fingerprints** and the same Git SHA (Windows checkout CRLF and compressed ZIP bytes can differ; both raw archives remain independently checked); returns `SOFTWARE_PACKAGE_READY_FOR_ENGINE_TEST` without production or native approval |

### CI deliverables

At the exact integration commit, the GitHub Actions run must be entirely green. Download the named artifacts from the same run:

- `studio-source-bundle-<sha>` — `CutSceneAI-Studio-source.zip`
- `phase10-4-synthetic-rehearsal-<sha>` — executed negative tests and source hashes
- `phase10-5-pre-engine-handoff-<sha>` — source-frozen software-only report
- `phase10-5-windows-packaged-studio-startup-<sha>` — actual localhost launch from fresh Windows ZIP
- `phase10-5-software-ready-for-engine-test-<sha>` — all four reconciled for one commit

If **any** artifact is absent, from a different Git SHA, or the Windows normalized source-content fingerprint disagrees with the independently verified Linux source fingerprint, the final software handoff gate fails.

## Launch Studio on your Windows testing workstation

Choose **one** reviewed version. Don't replace your existing development checkout or reset a branch with uncommitted changes.

**Option A — use the verified source ZIP.** Download the matching `studio-source-bundle-<sha>` artifact from the green GitHub Actions run, extract `CutSceneAI-Studio-source.zip` to a *new* folder, open PowerShell in its `CutSceneAI-Studio` folder, and run:

```powershell
.\tools\launch_studio.ps1
```

**Option B — use a fresh checkout of the tested integration branch.**

```powershell
git clone --branch integration/element1-9-guarded-repair-expansion-v0.1 https://github.com/Nithin0553/CutsceneAI.git CutSceneAI-Studio-Test
cd CutSceneAI-Studio-Test
.\tools\launch_studio.ps1
```

The first invocation installs the declared `.[agents]` Python requirements in `.venv-studio`, runs a temporary *actual* Studio startup smoke, closes that temporary process and starts the real local Studio supervisor. Keep the PowerShell window open. Then open **http://127.0.0.1:8765** in Microsoft Edge or another browser. This is a localhost service, not a cloud website. The default UI is simplified; append `?advanced=1` for the advanced research workspace.

If Windows blocks PowerShell scripts, review their content and use the session-scoped policy `Set-ExecutionPolicy -Scope Process Bypass` **only if permitted by your own workstation security policy**. Do not disable permanent system policy.

The one-command launcher never starts Unity, Unreal, a model invocation, asset conversion or a native job. It does not restart editor processes during normal Studio source reloads.

### Optional local-only verification

```powershell
.\.venv-studio\Scripts\python.exe .\tools\check_studio_setup.py --strict --json
.\.venv-studio\Scripts\python.exe .\tools\studio_startup_smoke.py
```

A passing smoke means only `LIVE_LOCALHOST_AND_UI_SMOKE_PASSED_ENGINE_UNVERIFIED`. It deliberately uses an isolated disposable workspace and does **not** create a live transfer.

## Begin genuine Unity/Unreal testing in this sequence

1. **Record provenance before writing anything.** Use one backed-up Unity source project with an existing saved Timeline cutscene; one *disposable* Unreal target project and new level/sequence path; the exact CI Git commit; Unity and Unreal engine/editor versions; and installed Studio companion versions. Save a snapshot/backup. Keep benchmark and previous experiment assets untouched.
2. **Install editor companions with a dry run first.** In the Studio folder run `python tools/studio_companion_install.py --unity "D:\UnityProject" --unreal-uproject "D:\TargetProject\Target.uproject"` with real selected paths. Check the proposed Unity `Packages/manifest.json` change and Unreal startup prerequisites. Only after inspection, rerun with `--apply`. A foreign Unreal `init_unreal.py`, conflicting UPM dependency, symlinked path, or disabled Unreal PythonScriptPlugin must **block** instead of overwriting. The tool never proves engine startup.
3. **Confirm both running editors and companion heartbeat.** Open the saved Unity project and Unreal .uproject/target level. In Unity choose **Tools → CutsceneAI → Studio Bridge → Enable Source Bridge** once, then confirm it reconnects after ordinary Unity compilation/domain reload. In Unreal verify the installed Python worker is running and the exact project and level match Studio. Check the UI's connection and nine-stage details before any conversion.
4. **First deterministic baseline without AI.** Connect the intended Unity cutscene and Unreal staging project in Studio. Start exactly one non-AI, explicitly consented transfer. If the source requests CineTwin data, manually enter Unity Play Mode to allow a real evaluated capture. If source hashes, asset permissions, project identity or native preflight fail, stop and preserve evidence; do not forge a capture or press Transfer again on an uncertain native job.
5. **Inspect and save native evidence.** Once the native worker reports generation, record exact source occurrence ID, candidate ID, job ID and transaction receipts. Inspect actual Level Sequence, actor/character positions and facing, camera cuts, motion curves, skeletal mapping, attachments, shader/effects/audio/event/physics limitations. Generated is **not** verified.
6. **Independent reopen test.** Save target assets. Close the generating Unreal Editor *for this acceptance test*, then open the same saved project/level/sequence in a **new Unreal OS process**. Run the native persistence/visual/behavior/CineTwin acceptance described in [Release Acceptance](RELEASE_ACCEPTANCE.md). A routine source code update does *not* need an editor restart; the distinct process is needed here only to prove persisted native data.
7. **Source-to-target comparison and safe repairs.** Use read-only native observations, compare against the original Unity CineTwin at matching times and inspect Element 9 per-source outcomes. Approve only exact guarded repairs when the evidence/consent contract allows them. If a native job may be partial, manually inspect the changed target instead of automatically requeuing.
8. **AI-enabled separate candidate and held-out scene.** Use a fresh staging target for an AI-enabled run. Verify an actual authorized model response, CED choice, compiled source-bound plan, one native job, independent readback and repair stop limits. Repeat on different, genuinely held-out cutscenes with unsupported features and record outcomes. Do not claim generalization or complete shader/skeletal/audio/physics fidelity based on partial checks.

### Read-only release report

From a new terminal in the Studio folder:

```powershell
.\.venv-studio\Scripts\python.exe .\tools\studio_release_audit.py
```

The gate returns `release_ready=false` (exit code 2) until it sees the necessary real native and source-bound evidence. It is a **correct negative result** for a new or incomplete transfer, not a reason to bypass the audit.

## Minimum first-test log

Record: Git SHA, source/destination project identifiers, editor versions and companion heartbeats; source census/CSIR SHA, CineTwin capture and expected tracks/characters/cameras; candidate/job IDs, stage/claim receipts and whether the worker is idle or uncertain; target actor/level/Sequence readback after save and independent reopen; matching-time position/facing/camera/audio/animation/effect observations; every Element 9 outcome and the native release audit's exact blockers. Store logs outside the repository and keep original evidence immutable.

**Stop conditions:** mismatched source capture, wrong project/level, missing asset permissions, stale worker, unknown strategy, modified source/approval, claimed native job with uncertain completion, failed Unreal save or missing restarted-editor evidence. None of these warrants an automatic native replay.

**Final decision:** This Phase 10.5 delivery can be **software-complete and ready to enter real-engine testing** after cross-platform CI passes; final production freeze and end-to-end fidelity remain **unverified** until the separate real-engine acceptance succeeds.
