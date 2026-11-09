# Unreal Python hot reload for CutSceneAI Studio

Python-only updates should NOT require a costly Unreal Editor restart.

## One-time setup: open the correct healthy Unreal editor/project

After pulling the Python branch, open the Unreal Python Output Log and run:

```python
import sys
sys.path.insert(0, r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal")

import cutsceneai_hot_reload
cutsceneai_hot_reload.reload_project_python()
```

Expected console result: CutSceneAI Python HOT RELOAD: OK. This imports/reloads an explicit list of project modules in dependency order: source planner, sampled behavior/scene preparation, CED validation, hierarchy support, Unreal adapter shim, best-effort transfer backend and runtime builder.

For subsequent code changes in VS Code, run the same hot-reload command from Unreal's Python console (or call the imported module's reload_project_python function). No Unity/Unreal scene or asset is changed by the hot-reload command.

Use the module reference, e.g. build_level_sequence.build_prepared_files(...), not previously captured function references imported with from-import; stale references are not updated by an importlib.reload call.

## Limits and safety

- Python hot reload is a **code refresh**, not a reset of Unreal UObjects, loaded packages, native references, active Sequencer editor windows, incomplete transactions, unsaved levels or the project's filesystem.
- A prior attempt that caused Unreal to report a potentially **corrupt Level Sequence package** requires closing the Editor without saving, taking a project backup and inspecting a healthy new session. Do not use this command as recovery for a corrupt V7 package.
- Content mappings, sequence names, source hash provenance and transfer-plan files do not mutate automatically. New implementation changes that affect planned JSON require a **fresh plan directory and source-hash verification**. Never patch a signed plan/evidence file.
- Some Unreal C++ plugins, compiled native modules and editor subsystem state changes still require a restart.
- Reload the source files only when no generator call is currently running. Avoid retaining old class/function objects across reloads.
- Hot reload supports pure Python changes in the whitelisted modules. Other scripts may need to be added deliberately with dependency ordering and tests; it does not indiscriminately clear sys.modules.
- The tool refuses to reload a same-named module imported from an unrelated checkout, to prevent a hard-to-detect wrong-version transfer.

## Minimal future development loop

1. Change code in VS Code and run pytest/repo checks in an ordinary PowerShell window.
2. Pull/update the code if edited on GitHub.
3. In the running, *healthy* Unreal Editor, call cutsceneai_hot_reload.reload_project_python().
4. Prepare the next transfer plan with unique immutable output dir and new unoccupied sequence target path; verify source evidence.
5. Perform runtime generation; inspect receipts and independently validate saved playback before accepting results.

This workflow is for development convenience. Every successful runtime run still needs provenance, saved-target readback and CineTwin comparison.
