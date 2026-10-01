# Unity Read-Only Extractor v0.1

## Goal

Extract an already-existing Unity Timeline into a CutsceneAI CSIR document without modifying source assets or scene serialization.

## Supported baseline

- Unity 6.0 / 6000.0
- Timeline 1.8.x
- `PlayableDirector` + `TimelineAsset`
- Animation tracks/clips
- Audio tracks/clips
- Activation tracks
- Signal markers
- Generic track/clip preservation
- Scene bindings
- Camera component metadata
- AnimationClip curve extraction

The initial controlled benchmark does not require Cinemachine. Camera cuts are represented with camera-bound ActivationTracks, while camera/prop motion can be carried by AnimationTracks.

## Read-only rule

The extractor may read Unity assets and scene bindings and may write an export artifact under `CutsceneAI/Exports/`. It must not:

- call Timeline asset creation/deletion APIs;
- change track bindings;
- modify scene objects;
- save scenes/assets;
- evaluate runtime behavior as part of structural extraction.

Runtime/evaluated capture, if later required, will be a separate isolated mode.

## User flow

1. Open the Unity source project.
2. Select a GameObject containing a `PlayableDirector`.
3. Choose `Tools > CutsceneAI > Export Selected Timeline`.
4. The package validates the selection and Timeline.
5. A CSIR JSON file is written under `CutsceneAI/Exports/`.
6. CutsceneAI backend ingests and validates the artifact.

## Extraction policy

### Timeline

Preserve Timeline identity/duration, editor frame rate, track hierarchy, track type/name/mute state, bindings, clips and markers.

### Clips

Preserve start, end, duration, clip-in, time scale, blend/ease durations, asset identity and native type.

### Animation

For `AnimationPlayableAsset`, preserve AnimationClip identity and editor curve bindings/keyframes. Known transform channels are additionally tagged with canonical conversion semantics. Raw Unity curve information is retained in native payload so no source information is lost.

### Audio

For `AudioPlayableAsset`, preserve AudioClip identity, duration, frequency, channels, samples and looping state.

### Camera

When a binding resolves to a GameObject/Component containing `Camera`, preserve field of view, physical-camera flag, focal length, sensor size, lens shift, clipping planes and aspect.

### Signals

Preserve SignalEmitter time, SignalAsset identity, emit-once and retroactive flags.

## Coordinate conversion

Unity source coordinates are left-handed, +Y up, +Z forward, meters.

CutsceneAI canonical coordinates are right-handed, +Y up, -Z forward, +X right, meters.

For vector positions: `(x, y, z)_unity -> (x, y, -z)_csir`.

For quaternion rotations under the Z-axis basis reflection: `(x, y, z, w)_unity -> (-x, -y, z, w)_csir`.

Raw native values remain preserved alongside canonical values where conversion is applied.

## Explicit non-goals for v0.1

- runtime procedural evaluation;
- Cinemachine-specific semantic reconstruction;
- custom Playable behavior execution;
- automatic target generation;
- animation retargeting;
- visual validation.
