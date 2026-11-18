# Unreal Python hot reload — continuous CutSceneAI Studio companion

Python-only updates should **not** require closing/reopening Unreal Editor.
The primary implementation is the live Studio worker in
`integrations/unreal/studio_local_editor_worker.py`. It uses one registered
Slate post-tick dispatcher, source-bounded idle module refresh and a
project/worker hash heartbeat. See
[Live bridge continuity](../studio/LIVE_BRIDGE_CONTINUITY.md).

## Automatic behavior once connected

After the worker was started **once** in the selected, backed-up Unreal
project, it keeps polling the Studio localhost file queue and reports the
actual editor project/map/PID. The source code hash is captured when the
Python worker is loaded. When the worker Python file changes on disk, the
idle callback compiles and refreshes only that trusted source file in the
same interpreter, retaining the original Slate callback handle and
workspace. After refresh, its source hash changes; a previously loaded
companion cannot simply claim the new hash from disk.

The worker also scans a bounded source set of Studio Python packages and
reloads the existing whitelisted transfer planner/adapter modules when
their code changes. It checks module origin to refuse another checkout.
Import/syntax errors or uncertain running-native-job state cause a
**fail-closed pause**, not a partial conversion or fake healthy status.
A Studio browser refresh or localhost server restart does not require
restarting either engine editor.

The Studio UI shows live connected/reloading/offline state from fresh
heartbeats. Native sequence generation still requires a *new* source-bound
immutable candidate and explicit transfer approval. A code refresh is
not a native transfer and does not write, overwrite or delete Unreal
assets.

## One-time upgrade of an older, already loaded companion

An old worker loaded before this feature has no idle self-refresh hook.
With **no native job running**, run the following in the existing Unreal
Python console; **do not close Unreal**:

```python
import importlib
import studio_local_editor_worker as w
w.stop()
importlib.reload(w)
w.start()
```

After this one-time upgrade, normal Python source updates refresh
automatically. Confirm the connected worker hash and project in Studio.
Never run the upgrade while a native job is RUNNING or while its
partial-import state is uncertain.

For non-worker tools, the explicit
`cutsceneai_hot_reload.reload_project_python()` helper remains an
optional development diagnostic. Routine Studio transfers no longer
require calling it by hand after each Python edit.

## Limits

- This is Python code refresh **in an existing healthy Unreal Editor**, not
  a reset of UObjects, open Sequencer windows, saved packages or
  transaction history.
- C++ plugins, compiled engine modules or unsafe loaded packages may
  require a genuine engine restart and/or recovery from a backup.
- The independent fresh-process persistence test remains a separate
  later engine-acceptance gate. It is **not** a prerequisite for routine
  local Python edits or Studio reconnection.
- A partially written native candidate is never requeued after refresh.
  Use its saved receipt and a new candidate, not the same sequence path.
- The code-only CI regressions do not establish Unreal 5.8 runtime
  compatibility or Unity/Unreal cutscene fidelity.

Do not use hot reload to recover an Unreal Editor session in which
packages are known to be corrupt; isolate the project and inspect a
healthy backup instead.
