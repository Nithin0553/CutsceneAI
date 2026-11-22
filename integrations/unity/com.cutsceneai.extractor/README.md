# CutSceneAI Unity Extractor and Studio Source Bridge

Editor-only Unity package for **source intelligence**, not a conversion engine.
It extracts existing Unity Timeline cutscenes as CutsceneAI CSIR, a typed
source-component feature census, and (with explicit Play Mode consent) a
source-sampled CineTwin reference.

**Unity baseline:** 6000.0 · **Timeline dependency:** 1.8.10.

## Install from the current Git checkout

In the Unity project, choose **Window > Package Manager > Add package from
disk...** and select the **current Git checkout's**
`integrations/unity/com.cutsceneai.extractor/package.json`.

Avoid installing a second copy from a local acceptance sandbox or old exported
folder. A local disk package may need Unity to reimport/recompile scripts after
Git changes. Recompilation/domain reload is expected; routine project restarts
should not be required.

## One-click Studio source intelligence

1. Open the intended saved Unity scene. Select the GameObject with the
   `PlayableDirector` for the cutscene you want to transfer. If only one
   saved Timeline is loaded, the bridge may resolve that unique director.
2. Choose **Tools > CutsceneAI > Studio Bridge > Enable Source Bridge**.
   Consent is **scoped to this exact Unity project** (not a global EditorPrefs
   toggle shared across projects). It persists across C# domain reloads
   within this project. On upgrading from the old global preference,
   explicitly enable the new project-scoped bridge once.
3. A fresh `CutSceneAI/StudioBridge/unity-editor.json` appears in the
   **Unity project root**, reporting `bridge_version: unity-editor-v0.3`,
   the actual `project_root`, `editor_pid`, `editor_mode`, and UTC
   `heartbeat`. Studio rejects an outdated v0.2 bridge and gives a
   specific diagnostic when the heartbeat is missing, stale, or from the
   wrong project. If heartbeat writes fail, Unity logs the filesystem
   error and does **not** process source export requests.
4. In Studio, choose the *same* Unity project root and the intended Unreal
   destination. Click **New Transfer**. Studio submits a unique, non-overwriting
   source snapshot request. Unity captures the selected source Timeline
   structure plus a source feature census and writes a receipt binding
   their exact hashes and source project fingerprint.
5. When Studio requests CineTwin, **enter Play Mode manually** in Unity.
   The enabled bridge executes its already approved sampling plan and
   writes native observed source behavior. Studio validates the plan,
   capture hash, frame samples, and source identity before planning.
6. Disable Source Bridge from the Tools menu when extraction is no longer
   needed; it stops polling requests.

**Files:** `CutSceneAI/StudioBridge/requests/`,
`receipts/`, `evidence/`, and the project-local heartbeat file. Generated
source exports are written outside `Assets/`, so the bridge never modifies
the authored Timeline or saves Unity scenes/assets.

## Independent manual export

For structural export only, select the Timeline's PlayableDirector and use
**Tools > CutsceneAI > Export Selected Timeline**. The CSIR is stored under
`CutsceneAI/Exports/`. The project profile can be emitted through
**Tools > CutsceneAI > Analyze Project**.

## Source evidence coverage and limits

The extractor records supported Timeline identity/timing, recursive
tracks and bindings, animation clips and editor curves, canonical/native
transform values, cameras and FOV, lights, audio, activations, events,
static scene/hierarchy context and referenced assets. The feature census
also identifies discovered Unity component and package types. Discovery
does **not** imply that a corresponding Unreal native converter exists.

CineTwin is a separate **Play Mode** observation tool and intentionally
evaluates the selected Timeline there; the Edit Mode structural extractor
does **not** call `PlayableDirector.Evaluate`. Unsupported custom scripts,
engine-specific simulations or unmeasured scene dependencies remain
explicitly incomplete. The source bridge never invents a missing feature
or certifies the resulting Unreal Level Sequence.

## Acceptance gate (not yet completed)

Compile the updated package in a real supported Unity Editor, verify
v0.3 project-bound heartbeat and reconnect after domain reload, test
snapshot and Play Mode capture, and validate a **held-out non-benchmark**
cutscene with mixed camera, character, hierarchy, assets and an unknown
component. Then independently test Unreal readback and CineTwin
comparison. GitHub CI validates software contracts, not native Unity
compilation or cross-engine fidelity. See
`docs/studio/UNITY_SOURCE_INTELLIGENCE_AUDIT.md`.
