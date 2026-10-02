# Engine Adapter Compatibility Architecture

CutSceneAI adapters are capability-driven, not hard-wired to one engine version.

## Principle

Engine version strings are recorded for provenance and diagnostics, but adapter behavior
should be selected primarily by runtime feature detection. Minor releases, plugins,
custom engine builds, and backported APIs can differ even when version labels look
similar, so exact version checks are a last resort rather than the primary mechanism.

## Runtime flow

```text
Read engine/version provenance
        ↓
Probe runtime capabilities
        ↓
Build capability profile
        ↓
Preflight required transfer actions
        ↓
Select native API / compatibility shim / semantic conversion
        ↓
Realize target cutscene
        ↓
Read back and validate
```

## Capability states

Each adapter feature should resolve to one of these states:

- `NATIVE` — the engine exposes the required API directly.
- `SHIM` — a version/API compatibility path preserves the same semantics.
- `CONVERTED` — the source and target expose different representations, but a
  deterministic semantic conversion is available.
- `RETARGETED` — the source data requires target-specific retargeting.
- `UNSUPPORTED` — the required semantics cannot be preserved safely.

The adapter must never silently guess when a required capability is `UNSUPPORTED`.

## Unreal implementation

`integrations/unreal/unreal_compat.py` is the boundary for Unreal runtime variation.
The Level Sequence builder should not call version-fragile APIs directly when a
compatibility operation exists.

Current capability probes include:

- engine version provenance through `SystemLibrary.get_engine_version()`
- Sequencer section channel discovery
- skeletal-animation play-rate representation
- CameraActor / CineCameraActor component resolution
- component-aware camera-lens realization
- required Sequencer class availability

The builder performs preflight before it moves target actors or creates the generated
Level Sequence.

## Camera semantic adaptation

Source and target engines may use different camera representations. For example, Unity
`Camera.fieldOfView` is a vertical FOV while Unreal `CameraComponent.FieldOfView` is
horizontal. CutSceneAI therefore carries the source FOV axis in the reconstruction plan.

For an Unreal CineCameraComponent, a source vertical FOV is converted deterministically
to `CurrentFocalLength` using the target filmback sensor height. For a generic
CameraComponent, vertical FOV is converted to horizontal FOV using that component's
aspect ratio.

This is semantic conversion, not regeneration.

## Animation semantic adaptation

Animation identity and skeletal compatibility do not guarantee equivalent world motion
after import. CutSceneAI therefore separates pose transfer from root-motion alignment.
When source root curves are available, the adapter computes the source world
displacement, samples the imported target animation root displacement, and aligns the
target section through a non-destructive Sequencer root-motion offset.

Section completion behavior is also explicit. A target engine must not silently restore
a reference pose when the source cutscene expects the evaluated end state to persist.

## Camera output gate

Camera FOV is a lens semantic, while aspect ratio may be a property of the active render
surface rather than of the camera asset itself. Validation therefore uses an explicit
output-resolution gate. Source-observed aspect values can be retained as provenance, but
target filmback/aspect should be derived from the declared validation output unless the
source provides an explicitly authored aspect constraint.

## Regression rule

Every engine integration failure found in a real transfer must produce:

1. an exact error signature in the adapter compatibility ledger,
2. a root-cause statement,
3. a centralized compatibility or semantic-conversion fix,
4. a regression test,
5. a preflight check where the capability can be detected before target mutation.

This creates persistent engineering memory in the repository and prevents known failures
from being reintroduced.

## Cross-engine policy

The same architecture applies to Unity, Unreal, and future adapters. Each adapter owns
its native API probing and conversion shims; CSIR and CED remain engine-neutral. The
transfer core asks adapters for capabilities rather than embedding engine-version
conditionals in the core.
