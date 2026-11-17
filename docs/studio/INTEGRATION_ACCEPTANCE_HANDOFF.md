# Integration acceptance handoff — AI Studio and native adapters

**Branch:** integration/agent-native-adapters-v0.1 (draft PR #124)  
**Current status:** Automated integration tests pass. Real Unity and Unreal native acceptance **not completed**.  
**Primary runbook:** [NATIVE_ADAPTER_ACCEPTANCE.md](NATIVE_ADAPTER_ACCEPTANCE.md).

## First source candidate: abandoned hallway guard

A guard walks through an abandoned hallway, hears a noise, stops, turns toward a door, and quietly asks who is there.

Not every behavior in this scene is supported. Audio/dialogue, cinematic camera framing, arbitrary animation and rendered fidelity must remain unresolved unless independently measured. A generated editable Level Sequence is not automatically the same cutscene.

## Workstation procedure

1. Use a backed-up Unity project, a disposable Unreal 5.8 staging project/level and the **exact same integration commit** in both companion packages. Record real Unity and Unreal versions and full SHA. Install the Unity extractor package, then **compile it in the actual Unity Editor**. Save its Console/Editor.log output.
2. Configure approved Unreal IK Rigs and IK Retargeter assets for any retargeted character clips; this is not an automatic solution for unknown skeletons.
3. Start Studio and both Editor companions. In the saved Unity scene, enable **Tools → CutsceneAI → Studio Bridge → Enable Source Bridge**. Select the PlayableDirector if multiple Timelines are loaded.
4. Connect Unity and Unreal project folders in Studio, confirm asset rights and press **Transfer** once. The Unity Editor exports an Edit Mode CSIR and census, and Studio queues a hash-bound CineTwin sampling plan automatically.
5. Studio will show **WAITING_FOR_UNITY_CAPTURE**. Enter **Unity Play Mode** in the selected scene; the enabled companion will capture the planned Timeline samples automatically without a file picker. Studio deliberately does not enter Play Mode itself because that runs project scripts. An absent or mismatched source capture must block rather than be invented.
6. The Unreal worker prepares and executes the verified source transfer into unoccupied staging assets. Save the resulting Level Sequence and map, and record candidate and job IDs.
7. Close the generating Unreal Editor. Open the exact saved project/level/sequence in a **new Unreal process**. In Unreal Python console, run:

    import sys
    sys.path.insert(0, r"D:/CutsceneAI/integrations/unreal")  # adjust checkout path
    import studio_native_acceptance
    print(studio_native_acceptance.start())

8. The Editor command starts native CineTwin sampling over real editor ticks. Keep the Editor open until complete. Review the evidence-folder files **persistence.json**, **target-behavior.json**, and **comparison.json**, including source and report hashes, generation/observation process IDs and measured differences.

## Test matrix

| Case | Native evidence | Acceptance scope |
| --- | --- | --- |
| Guard placement and facing | Matched-time actor poses and root trajectory | Measured positions and orientations only |
| Walk, stop and turn | Approved IK retargeted clip refs and per-joint matching-time positions | Joints, peaks, time and root motion; no unmeasured skin/face claims |
| Static primitive colliders | Reopened geometry and real query hit/miss/distance | Supported Default-layer blockers only, not dynamic physics |
| Constant PBR | Reopened material slots, parameter defaults and blend | Native property match; rendered frames separately |
| Camera, lighting, dialogue and audio | Source-target independent behavior/image/audio evidence | Unsupported/incomplete until genuinely measured |
| Held-out project and deliberate unsupported feature | Real different source, mismatched rig or unsupported shader | Block or report; never claim false parity |

## Decision

- **GENERATED_UNVERIFIED** means editable sequence creation, not cutscene parity.
- **STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE** means native structure and the *measured* motion scope only.
- Any missing native samples, modified source identity, wrong project, or failed reopening keeps acceptance incomplete or failed.
- Do not merge into main or authorize new AI correction strategies solely because automated CI passes.

Automated reproducibility: python -m pytest -q; node tests/studio/test_cinematic_ui.cjs; python -m ruff check tests; python tools/repo_check.py.
