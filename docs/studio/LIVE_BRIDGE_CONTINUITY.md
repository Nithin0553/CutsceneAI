# CutSceneAI Studio — Live Unity/Unreal Bridge Continuity

**Software-only implementation.** No editor was launched to prove the behavior. Do
not confuse a connected editor heartbeat with an authenticated CineTwin receipt,
completed native conversion, independently reopened sequence or frame fidelity.

## Expected development behavior

Keep one already-open Unity Editor on the selected source project and one
already-open Unreal Editor on the backed-up staging target project. Once their
respective Studio companions have been explicitly enabled/started:

- Unity's source bridge is registered through `[InitializeOnLoad]` and
  `EditorApplication.update`. It resumes after Unity's ordinary C# assembly
  compilation/domain reload without requiring another menu click. The opt-in is
  preserved in `EditorPrefs`; a per-project `unity-editor.json` heartbeat
  reports the selected project root, editor PID, Edit/Play Mode, and UTC
  timestamp. A marker older than eight seconds, from a wrong project or with
  disabled status is not a live connection. The source capture and structural
  export still require separately validated immutable receipts/hashes.
- Unreal's upgraded worker keeps one stable Slate tick callback. That callback
  dispatches into the current worker module, so an **idle** changed worker
  Python file can be compiled and loaded from the trusted checkout in the
  existing Unreal Python interpreter. The original callback handle and
  workspace are preserved. No Unreal actor/asset write occurs during this
  refresh. Changes to whitelisted Studio adapter/planner Python sources also
  trigger idle-only reload/synchronization from the same checkout.
- The Studio localhost API reports `unity_editor` and `unreal_worker` in
  `/api/status`. The minimal dark UI shows subdued live bridge status. The
  browser polls; temporary source-compilation and script-refresh outages
  reconnect automatically as fresh valid heartbeats arrive.
- The Unreal worker recomputes its live worker-source digest after loading
  changed Python. The Studio host continues checking the actual hash and
  checkout root. A cached older worker version cannot advertise the new code
  without actually loading it. An invalid or deferred Python refresh is
  reported as `BLOCKED` / `DEFERRED_NATIVE_JOB`; both refuse new native
  candidate submission.

## Safety: preserve work and prevent replay

A code change never authorizes an engine operation. A transfer still needs a
newly prepared, source-bound candidate and the explicit existing one-click
approval, an available target, project/map/version checks, and native preflight.

When any native job is RUNNING, or an orphaned RUNNING job is recorded, Python
refresh defers. It never clears the old receipt, changes that job to QUEUED,
reruns an import, deletes a generated asset or overwrites a sequence. Finish
the current job or inspect the uncertain/partial artifacts first. Code
updates can make a previously prepared candidate stale; create a new
candidate in a new namespace instead of modifying its immutable files.

A bad Python update leaves Unreal open and blocks native work until the code
is corrected and the idle worker can refresh. Unity C# compilation may cause
a short heartbeat gap; it cannot replay a request with an already existing
receipt. In Play Mode, CineTwin capture still requires the user's intentional
Play Mode, not an automatic transition triggered by source changes.

## First-time setup and legacy worker upgrade

1. Link/add the extractor Unity package to the project; to propagate local
   repository C# edits, install as a local UPM package/reference to the
   checkout rather than a detached copied folder.
2. Enable `Tools > CutsceneAI > Studio Bridge > Enable Source Bridge` once
   in Unity. Unity resumes the callback after normal editor script reload.
3. In the backed-up Unreal Editor project, start the current Python companion
   once (Studio provides the exact command). Afterward, idle Python-only updates
   automatically refresh without restarting Unreal.
4. **Legacy worker only:** the old worker has no self-refresh handler. When
   no native job is RUNNING, use the Unreal Python console:
   `import importlib, studio_local_editor_worker as w; w.stop(); importlib.reload(w); w.start()`.
   Do not run this command during a native job. Subsequent compatible Python
   changes use the new automatic path.

The Python host/web server itself may need to be relaunched to pick up host
code changes. That does **not** require closing either game-engine editor;
its local file-based bridges resume when the server is available.

## Limits that cannot be promised away

Unity may recompile/reload the C# script domain when the package changes;
it cannot safely avoid engine-mandated import/assembly reload rules. Unreal
C++ plugin recompilation, compiled engine binary changes, wrong loaded
project/map, corrupt loaded packages or an editor version change can require
user action or a genuine engine restart. These exceptional cases must be
reported rather than spoofing a healthy connection.

Independent editor-process persistence acceptance for actual saved Unreal
packages remains a **separate later gate**; it is not part of routine live
Python refresh. Opening a second read-only editor process for validation is
conceptually different from repeatedly restarting the active development
editor, but neither is being executed in this software-only phase.

## Verification contracts

Code-only tests cover idle Unreal worker refresh, callback continuity,
update-induced native job deferral, broken code refusal, changed Python
adapter detection, Unity Editor heartbeat freshness/wrong-project/disable
checks, health reporting through Studio, and unchanged zero-side-effect
native queue constraints. Real Unity compilation and Unreal-editor API
acceptance remain outstanding until the user authorizes engine tests.
