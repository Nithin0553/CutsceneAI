# CineTwin Phase 4.8 — Explicit Unreal actor level-package persistence

## Observed failure

In the copied Unreal project, a generated hierarchy was verified by 297
active-range timestamp comparisons at effectively 0 cm positional error.
The user then saved the current level, closed Unreal and reopened it.
The parent relationship **did not persist** and the child mobility reverted:

- PROP_PARENTED parent: `NONE`;
- PROP_PARENTED root mobility: `ComponentMobility.STATIC`;
- separately generated test Level Sequence: still exists.

Read-only package inspection then confirmed that both mapped prop actors
and their root components are stored directly in the same package:
`/Game/CutSceneAI/Benchmark002/L_Benchmark002`. They are **not external actors**,
so One File Per Actor is not the cause.

The exact cause is not yet proven. However, Python-driven SceneComponent
mobility and attach operations may not mark Unreal's level map package dirty.
Saving only dirty packages or using the editor's current-level save UI may
therefore fail to persist these changes even while their in-memory readback
and evaluations are correct.

Epic documentation:

- [EditorLoadingAndSavingUtils.save_packages](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorLoadingAndSavingUtils?application_version=5.7) explicitly supports `only_dirty=False`.
- [UObject::Modify](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/CoreUObject/UObject/Modify) explains marking package dirty in C++; it is not assumed to be Python-exposed.
- [Unreal 5.8 LevelEditorSubsystem](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/LevelEditorSubsystem) documents save-current-level separately.

## New general solution

`integrations/unreal/cinetwin_hierarchy_persistence.py` adds
`apply_and_save_existing(...)`. It **does not rebuild the Level Sequence**.

It requires explicit project directory and level package safety parameters,
existing generated target Level Sequence, opt-in hierarchy mapping with
`overwrite_sequence=false`, unique actor labels and both actors in the
exact expected level package.

It rebuilds only the hierarchy operation plan from frozen CSIR/mapping,
repositions only missing-attachment children to their source initial world
poses, reapplies the verified mobility preparation and parent attachment,
and immediately verifies attachment identity.

It then saves **only that map package** via
`EditorLoadingAndSavingUtils.save_packages([level_package], only_dirty=False)`.
This does not touch unrelated dirty assets, and uses the same engine-reported
package that contains the affected actors.

It rolls back in-memory actor changes on operation/save failure where
possible. Saving to disk is not fully atomic; use a backed-up staging project.
Success returns `SAVED_AWAITING_REOPEN`, not fidelity PASS.

## Staged local run

Keep only the copied Unreal test project open with `L_Benchmark002` loaded.

In Unreal Output Log → Python:

```python
import sys, importlib
sys.path.insert(0, r"B:\Research\CutSceneAI\CutsceneAI\integrations\unreal")
import cinetwin_hierarchy_persistence
importlib.reload(cinetwin_hierarchy_persistence)

result = cinetwin_hierarchy_persistence.apply_and_save_existing(
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline-e6518af4.csir.json",
    r"B:\Research\CutSceneAI\CutsceneAI\integrations\unreal\benchmark002_cinetwin_test_mapping.json",
    expected_project_directory=r"D:\Research\Unreal\UnrealProjects\CutSceneAIStudio_CineTwin_Test",
    expected_level_package="/Game/CutSceneAI/Benchmark002/L_Benchmark002",
)
print("[CineTwin] Persistence status:", result["status"])
```

Do not rerun `build_level_sequence.build()` here. The target Level Sequence
already exists and must not be overwritten.

On success, close Unreal (no extra manual level changes), reopen the copied
project and check:

- PROP_PARENTED parent actor is PROP_MOVING;
- PROP_PARENTED root mobility is MOVABLE;
- the generated test sequence still exists.

Only then is *saved-state persistence* verified. If the child persists, next
re-run tick-synchronized hierarchy readback on the reopened level and existing
test sequence. Active sampled playback hierarchy parity is a separate gate.

## Limitations

No guarantee of persistence until the actual UE5.8.3 runtime and reopened
project confirm it. The module currently requires direct target actor
attachments and explicit source world child initialization. It does not
resolve unmapped intermediate hierarchy parents, dynamic reparenting,
socket constraints, component-only proxies, physics, or complete cinematic
fidelity. The frozen Unity source and original Unreal project remain unchanged.
