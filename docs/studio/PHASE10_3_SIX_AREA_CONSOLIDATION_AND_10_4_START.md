# Phase 10.3 — Consolidated Six-Area Studio Software Delivery (v0.1)

**Branch base:** `bff3ed1923061c72cd5102e9593cb879d498c5fa`, already merged first Phase 10.3 source-result increment. This document covers the **six remaining work areas in one consolidated feature branch**, without implying a real Unity/Unreal run. Phase 10.4 begins concurrently through a source-only synthetic rehearsal harness.

## Six area implementation and acceptance matrix

| Area | Implemented software contract | Verification and remaining boundary |
|---|---|---|
| **1. UI consolidation** | Default and advanced interfaces use the same localhost `GET /api/flow-diagnostics` nine-stage read-only record. Standard Projects screen offers a simple companion installer preflight. UI shows only redacted statuses, no hidden native commands. | Python flow tests and Node default/advanced UI checks. Research-only controls remain intentionally advanced. Live browser/engine ergonomics remain workstation acceptance. |
| **2. AI orchestration visibility** | Backend `studio_phase10_3_flow.summarize` tracks Unity source/CineTwin, CED, AI planning, validation, source-bound plan, Unreal execution, readback, repair and final source outcome. Active job evidence must match the current run. Read-only diagnostics never grant native retry or false parity. | Source/job mismatch and native unverified tests; no unapproved agent/system privilege or real provider response inferred. |
| **3. Companion first-run wiring** | Explicit `tools/studio_companion_install.py` dry-run and `--apply` for the exact selected Unity and Unreal projects. Adds a local UPM dependency (manifest backup) and creates Unreal `Content/Python/init_unreal.py` only when PythonScriptPlugin is already explicitly enabled; refuses conflicting existing files, symlinks and project ambiguity. | Fixture tests cover clean, repeat, disabled plugin, foreign script, altered UPM and symlinks. Unity bridge opt-in still requires an explicit Editor enable; Unreal hook requires correct project scripting configuration and genuine heartbeat. No editor was launched. |
| **4. Multi-project setup and repairs** | Project-local installer never changes project contents without selected project paths and `--apply`. Standard project UI shows a literal preflight command, actionable connection state and non-replaying workflow/recovery diagnosis. Existing guarded repair consent and source-bound native gates remain authoritative. | Cross-project and stale job UI/HTTP checks; unsupported animation or arbitrary edits are not silently converted. Automatic real-project installation/repair parity remains engine-gated. |
| **5. Interrupted operation recovery** | Existing server-owned once-only autopilot stages and recovery tests are retained, now supplemented with shared source/run diagnostics, stale active-pointer HTTP refusal, delayed Element 9 response discard and a 10.4 regression driver. Never auto-requeue a queued/uncertain native import. | Full Python suite, 26 Node Studio scenarios, and Phase 10.4 interruption rehearsal; live process kill/reopen and partially committed native asset state remain separate tests. |
| **6. Workstation installation readiness** | `tools/build_studio_bundle.py` creates and verifies a byte-reproducible, SHA256-manifested, secret-rejecting, source-only Studio distribution. Includes Python scripts, web UI, companion source, schemas, docs and tests, plus existing isolated Windows Python installer. Offline `check_studio_setup.py --strict` now verifies these components. | Deterministic build, tampering, symlink, sensitive-file and overwrite tests. This is NOT a prebuilt desktop executable; a clean Windows host still needs Python/dependency installation and actual Editor plugins. Full desktop packaging/freezing remains Phase 10.5. |

### Operator workflow (project-local, opt-in)

From the Studio source folder in PowerShell or another shell with Python 3.11+:

```powershell
python tools/check_studio_setup.py --json --strict
python tools/studio_companion_install.py --unity "D:\\UnityProject" --unreal-uproject "D:\\UnrealProject\\Game.uproject"
# Inspect the dry-run output and enable Unreal PythonScriptPlugin in the Editor.
python tools/studio_companion_install.py --unity "D:\\UnityProject" --unreal-uproject "D:\\UnrealProject\\Game.uproject" --apply
```

- The installer neither runs nor restarts Unity/Unreal. It checks project ownership and plugin prerequisites before modifying either file.
- A Unity manifest backup is kept; an existing foreign Unreal startup script blocks installation. Partially interrupted wiring requires manual inspection, never blind reapplication.
- Unity project still requires explicit **Enable Source Bridge** inside the Editor. The engine auto-reconnect policy remains bound by native worker version, checkout root and source hash, and can require an Editor-mandated reload for native plugins.
- A successful installer receipt certifies only source file wiring, not active engine connection, code compilation, native save/reopen or behavior parity.

### Source-only distributable and verification

```powershell
python tools/build_studio_bundle.py --output "D:\\Releases\\CutSceneAI-Studio-source.zip"
python tools/build_studio_bundle.py --output "D:\\Releases\\CutSceneAI-Studio-source.zip" --verify
```

The build is deterministic and refuses missing required components, symlinks, oversized files, sensitive filenames or an existing ZIP. Manifest and all ZIP entries are SHA256-checked. Do not describe this source distribution as a signed self-contained desktop installer or a verified engine plugin deployment.

## Phase 10.4 — started (source-only end-to-end rehearsal)

`tools/phase10_4_rehearse.py` runs the actual existing Python and Node synthetic Studio integration suites in subprocesses. Its modules cover nine explicitly named interruption/cross-engine evidence gates: Unity source and CineTwin capture; CED/source planning; pre-native approval; Unreal disconnect/wrong level; partial import/no-replay; readback; bounded repair/outcome; UI job switching; and companion/workstation preflight.

```powershell
python tools/phase10_4_rehearse.py --output "D:\\Releases\\phase10_4-synthetic.json"
```

CI runs this command and archives the receipt at the **exact PR SHA**, separately from the ordinary Python/Node test jobs. The report records test module hashes and subprocess status without asserting editor execution. It returns **`release_candidate_ready: false`** and **`native_replay_authorized: false`** even when tests pass.

### Remaining real-world acceptance

Software CI and synthetic mocks do **not** establish Unity C# compilation in a real project, Unreal startup bootstrap, any proprietary shader/VFX fidelity, independent editor reopen, rendered/skin/audio/physics parity, or a clean-workstation installer trial. Those remain mandatory gates before Phase 10.5 freeze or any claim that a cutscene transfer is fully faithful. A source-bundle check is not proof that all third-party dependencies are available offline.

**Scope decision:** Phase 10.3's six software work areas are addressed with source-code paths and regression tests in one integration increment. The actual editor/workstation acceptance is explicitly unverified; do not silently convert these into complete native acceptance.
