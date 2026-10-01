# CutsceneAI Unity Extractor

Editor-only package for structural extraction of existing Unity Timeline cutscenes into CutsceneAI CSIR v0.1.

## Baseline

- Unity 6000.0
- Timeline 1.8.10

## Install for development

In a Unity benchmark project, open Package Manager and choose **Add package from disk...**. Select this package's `package.json`.

When the CutsceneAI repository and Unity project are on different drives/locations, use the absolute local path to this folder.

## Export

1. Open the scene containing the source cutscene.
2. Select the GameObject containing its `PlayableDirector`.
3. Choose **Tools > CutsceneAI > Export Selected Timeline**.
4. The JSON artifact is written under the Unity project root at `CutsceneAI/Exports/`.

## Read-only structural mode

This package does not call `PlayableDirector.Evaluate`, modify bindings, create/delete Timeline tracks, or save Unity scenes/assets. It only reads authored state and writes a separate export artifact.

## Current coverage

- Timeline identity/timing
- recursive tracks
- track bindings
- animation clips and editor curves
- raw + canonical transform curve keys
- audio clips
- activation tracks
- camera metadata
- signal markers
- generic clip/marker fallback

## Next gate

Install this package in Benchmark 001 and verify:

1. the package compiles in Unity;
2. selection validation works;
3. export completes;
4. exported JSON validates against `packages/contracts/csir/csir-v0.1.schema.json`;
5. expected benchmark counts/times/assets are present.
