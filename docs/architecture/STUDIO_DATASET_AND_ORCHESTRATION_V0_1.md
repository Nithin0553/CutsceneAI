# CutSceneAI Studio v0.1 — dataset collection and conversion sessions

## What is implemented

- Immutable, SHA-256-checked **source dataset registration** from an existing
  Unity CutSceneAI CSIR, CineTwin sampling plan, and independently observed
  Play Mode behavior capture. Registry verifies requested frames/rigs and
  fails on missing or altered samples.
- Optional source Project Intelligence Profile snapshots.
- Dataset status that checks every stored source record and whether enough
  independent project fingerprints exist for project-level evaluation.
- A single source-only Studio prepare command that stores the transfer plan,
  feature coverage ledger and optional previously verified mapping suggestions
  in a versioned conversion session. It never launches Unity or Unreal.
- Existing Unreal adapter continues to provide in-engine capability diagnostics,
  staged generation, readback and fidelity comparison as separate operations.

**Not implemented:** generic import of arbitrary 3D assets, universal character
retargeting/pose-baked fallback, shader or game-logic conversion, automated
functional event translation, photometric/audio/render parity, or a complete
production Studio GUI. A passing source dataset or Python test does not
establish universal cutscene portability.

## Suggested initial dataset design

Collect four independently authored scenes from each of five DIFFERENT Unity
projects, starting with simple supported behavior and increasing complexity.
Use different assets, settings and rigs across source projects:

P01: camera static/move/cuts/lens animation
P02: character walk/turn/overlap/two-character motion
P03: moving props/parenting/rotation/combined transforms
P04: lights/audio/events/mixed cinematic tracks
P05: heterogeneous projects with new assets, rigs and frame rates

This is a *collection target*, not enough to guarantee good fine-tuning.
First validate retrieval-based adaptive mapping; reserve at least one **whole
Unity project** for an unseen-project test. Never randomly split scenes
within the same source project across training/evaluation.

## For each source scene

1. Create or duplicate a working Unity project/scene; do not touch frozen
   Benchmarks 001 and 002.
2. In Unity: Tools > CutsceneAI > Analyze Project; preserve profile and engine
   version. Select the GameObject with PlayableDirector and choose
   Tools > CutsceneAI > Export Selected Timeline.
3. Under Unity project root CutsceneAI/Exports locate exported **actual**
   CSIR file. Its name may have a source hash suffix.
4. From repository root run:
     python tools/cinetwin.py plan "D:/Unity/P01/CutsceneAI/Exports/TIMELINE.csir.json" "D:/Unity/P01/CutsceneAI/Exports/TIMELINE.cinetwin.sampling-plan.json"
5. Enter Unity **Play Mode** and select the PlayableDirector; choose
   Tools > CutsceneAI > CineTwin > Capture Selected Timeline Behavior
   (Play Mode), selecting the new sampling plan. Capture is written as
   TIMELINE.cinetwin.behavior.json under CutsceneAI/Exports.
   Beware custom scripts with external side effects; capture in disposable
   scene/project copies.
6. Verify the capture:
     python tools/cinetwin.py verify "<sampling plan>" "<source behavior capture>"
   Status may correctly be INCOMPLETE if audio output, event execution,
   rendered pixels or physics states are not captured. No source capture
   errors are allowed.
7. Register authentic artifacts (example command, adapt paths):
     python tools/studio_dataset.py register --root "B:/Research/CutsceneAI/Datasets" --project-id P01 --scene-id DS001 --csir "<CSIR>" --plan "<sampling plan>" --capture "<behavior capture>" --profile "<project profile>"
   Omit --profile if unavailable. Registry copies sources to a content-checked
   folder and refuses to rewrite a source record with different bytes.
8. Run:
     python tools/studio_dataset.py status --root "B:/Research/CutsceneAI/Datasets"
   Confirm sample count and fingerprints before creating the next scene.

## Preparing a transfer session for a mapped cutscene

    python tools/studio.py prepare --csir "<CSIR>" --mapping "<mapping>" --out "<new empty session directory>" --target-project "<Unreal .uproject>" --case-store "<verified mapping case store>"

Case store and target project are optional. The command writes:

- session.json: frozen input SHA-256, target asset reference, stage status,
  source/target identity, and explicit unverified gates;
- readiness.json: all supported/unsupported source track coverage;
- transfer-plan.json: deterministic source-driven reconstruction actions
  (only when the source coverage is not BLOCKED);
- suggestions.json: closest verified mapping **proposals only**.

This does **not** prove the exact Unreal project/runtime/API is compatible.
Run integrations/unreal/diagnose_transfer.py inside the target Unreal Editor
before generation. Only then stage a new Level Sequence, independently read
back its native data and compare measured source/target behavior.

Never set overwrite_sequence=true in a new Studio session. Existing scene actors
can be affected by an editor build; back up target level packages and preserve
the main/original scene/sequence prior to attempting generation.

## After successful conversion

Create a Resolved Mapping Dictionary with the existing deterministic
adaptive resolver. Collect independent target readback and validation.
Use tools/cutscene_learning.py to create a review template tied to the exact
CSIR/mapping/resolved-dictionary/validation hashes. Explicitly approve mapping
labels only when they are correct; don't treat partial pose/audio/event/render
coverage as a full cutscene success.

The continual-learning case store is a separate data product from raw dataset
registration. A new raw source capture is not itself a supervised label.
Models are retrained only after sufficient reviewed independent examples
and held-out project tests. New model predictions must remain proposals until
deterministic validation approves them.

## Long-term architecture

UnityExtractor/UnrealExtractor + CSIR/CED → project intelligence →
feature-coverage + asset mapping → deterministic plan (+ learned suggestions) →
safe Unreal staging adapter → native readback + evaluated comparison →
human review + versioned verified dataset → optional periodic training.

Adapters should remain modular so another engine can implement the same
contracts without copying Unity or Unreal assumptions into core code.
