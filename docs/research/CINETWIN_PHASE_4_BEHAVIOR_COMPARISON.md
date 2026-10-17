# CineTwin Phase 4 — Automatic source-vs-target behavior comparison

## Verified starting point

Benchmark002 Unity behavior was captured at 298 planned timestamps, including the
evaluated poses of two skeletal rigs. The Phase 2 capture verifier reported zero
structural failures (overall INCOMPLETE because other domains were not captured).

An Unreal 5.8.3 smoke capture succeeded for five timestamps. The subsequent
full observation reported 298 source-aligned sample times, 8 mapped actors,
21 unmapped source entities, and 2 native Unreal skeletal rigs.

**These are measurements, not a claim of complete transfer fidelity.**

## Why an independent comparator

Extracted Timeline/Sequencer tracks and animation assets are not necessarily
equivalent to what the engine evaluates. Unity's PlayableDirector.Evaluate()
evaluates a graph at a requested time; Unreal exposes Sequencer global playhead
positioning and immediate evaluation. This experiment compares actual recorded
source/target observations at exactly those times.

References:

- https://docs.unity3d.com/ScriptReference/Playables.PlayableDirector.Evaluate.html
- https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/LevelSequenceEditor/ULevelSequenceEditorBlueprintLib-/SetGlobalPositio-
- https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI/LevelSequenceEditor/ForceUpdate

## Implemented

The pure Python comparison uses the existing:
- \`Benchmark002.cinetwin.sampling-plan.json\`
- \`Benchmark002_Timeline.cinetwin.behavior.json\`
- \`Benchmark002_Unreal_CineTwin_Full.json\`

It requires source identity equality, a verified complete source capture, full
target timestamp coverage, one-to-one mapped actor identities, finite numeric
measurements, and stable skeletal bone lists. Partial smoke-test captures are
rejected instead of interpolated without evidence.

For each **mapped native actor** it reports:

- mean/max/end world-position differences, in centimeters;
- time of worst position difference;
- maximum **relative trajectory** difference after subtracting each engine's
  starting position (helps separate scene placement from movement mismatch);
- the source/target maximum movement distance from their own start points;
- worst world-rotation difference, in degrees (quaternion sign invariant);
- diagnostic flags for position, rotation, and source-motion-vs-static-target;
- source identity, target actor label, and sample count.

For skeletal rigs it reports an **unpaired motion-presence diagnostic**:
maximum sampled world displacement of *each rig's own native bone set* relative
to its own starting pose. If the source bones move but the target bones are
completely static, the observer raises a diagnostic flag. These are **not**
pose correspondence or bone retargeting error metrics.

It explicitly reports the 21 source entities that were not mapped to independent
Unreal actors. Some may be valid target components or timeline-only objects;
their semantics remain unverified rather than automatically declared lost.

An unflagged result is **NOT proof of entire cutscene fidelity**. Neither
camera optics, light appearance, cross-rig bone pose accuracy, audio, events,
rendered pixels nor physics have yet passed comparable evaluation.

## Local experiment (no Unreal or Unity scene edits)

After merging and pulling \`main\`, run this from VS Code PowerShell:

\`\`\`powershell
cd B:\Research\CutsceneAI\CutsceneAI

python tools\cinetwin.py compare \`
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002.cinetwin.sampling-plan.json" \`
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline.cinetwin.behavior.json" \`
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Unreal_CineTwin_Full.json" \`
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_CineTwin_Comparison.json"
\`\`\`

This only reads JSON and writes a **new report file**. It does not launch
the game engines, regenerate the saved target, or mutate the frozen Unity
source. The console ranks actors by maximum world-position discrepancy and
prints a motion-presence summary for both rigs.

Default diagnostic tolerances: 1 cm world position and 2 degrees world
rotation. These are *investigation thresholds*, not a declaration of
visually imperceptible errors or universal cinematic quality criteria.

## Next research milestone

After examining measured differences, add a semantic entity coverage analyzer
and an explicit source-to-target skeletal correspondence/retargeting model.
Then develop independent target playback validation and a bounded correction
loop. A comparator cannot repair what it has not established semantically.
