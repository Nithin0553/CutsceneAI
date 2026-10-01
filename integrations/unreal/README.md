# CutSceneAI Unreal Integration — Benchmark 001

This integration realizes the first controlled Unity → Unreal transfer proof.

The Unity Timeline remains the authoritative source. Unreal generation consumes:

1. CSIR v0.1 (`*.csir.json`)
2. Unity Timeline source-offset snapshot (`*.unity-source.json`)
3. explicit Benchmark 001 mapping (`benchmark001.mapping.json`)

The source-offset snapshot is required because Unity Timeline stores Animation Track / clip offsets separately from animation curves. Those offsets must be preserved rather than inferred from an evaluated Scene snapshot.

## Safety model

Generation creates a **new staging Level Sequence** and refuses to overwrite an existing asset with the same path. Benchmark actors are created as Sequencer spawnables. The adapter does not rewrite the source Unity project or unrelated Unreal level actors.

## Unreal prerequisites

Test target: Unreal Engine 5.8.

Enable these editor plugins:

- Python Editor Script Plugin
- Sequencer Scripting

Prepare/import equivalent Benchmark 001 target assets before generation:

- `Ch31_nonPBR` skeletal mesh
- the matching Catwalk / 180-turn animation on that skeleton
- the Benchmark audio asset
- the controlled hallway environment / target map

Benchmark 001 deliberately uses manual asset mappings. Automatic asset matching and cross-skeleton retargeting are out of scope for this first deterministic proof.

## 1. Pull the repository

```powershell
cd B:\Research\CutSceneAI\CutsceneAI
git pull origin main
```

## 2. Export the Unity source-offset snapshot

In Unity, **turn Timeline Preview off first** so Scene transforms are not left in an evaluated preview state.

Select `CUTSCENE_DIRECTOR`, then run:

```text
Tools → CutsceneAI → Export Selected Timeline Source Snapshot
```

This writes a file such as:

```text
<CutSceneAI Unity project>\CutsceneAI\Exports\Benchmark001_Timeline-5c57872a.unity-source.json
```

The existing CSIR export is still required. This sidecar is source-engine provenance, not a replacement for CSIR.

## 3. Create the mapping

Copy:

```text
integrations/unreal/benchmark001.mapping.example.json
```

to:

```text
integrations/unreal/benchmark001.mapping.json
```

Update every `/Game/...` target asset path to match the assets actually imported into your Unreal project. Keep `sequence_name` as a staging name.

## 4. Run from Unreal Editor Python

Open Unreal Editor 5.8 and the target project. Open **Output Log → Python** (or the Python console) and run:

```python
import sys
sys.path.insert(0, r"B:\Research\CutSceneAI\CutsceneAI\integrations\unreal")

from cutsceneai_unreal.editor_adapter import generate_from_files

result = generate_from_files(
    csir_path=r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutsceneAI\Exports\Benchmark001_Timeline-5c57872a.csir.json",
    unity_source_path=r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutsceneAI\Exports\Benchmark001_Timeline-5c57872a.unity-source.json",
    mapping_path=r"B:\Research\CutSceneAI\CutsceneAI\integrations\unreal\benchmark001.mapping.json",
    plan_output_path=r"B:\Research\CutSceneAI\CutsceneAI\research\artifacts\benchmark001.transfer-plan.json",
)
print(result)
```

The adapter creates a new Level Sequence under the mapping's `sequence_path`, saves it, and opens it in Sequencer.

## Planned Benchmark 001 reconstruction

The generated staging sequence includes deterministic operations for:

- character skeletal animation
- moving-prop transform keys
- two camera bindings and the 5-second cut
- Camera B transform animation
- Camera B FOV animation
- audio section with the exact source start time
- `Benchmark_Event_01` as a marked frame at 6.5 seconds

The sequence uses the source display rate and a high-resolution source tick rate so source timestamps are not silently rounded to display frames.

## Failure behavior

The adapter fails instead of guessing when required data or asset mappings are missing. In particular it rejects unsupported transform composition cases rather than silently producing a visually plausible but numerically incorrect transfer.

After staging succeeds, the next milestone is Unreal readback → CSIR → validation against the Unity ground truth. The staging sequence is not considered a Benchmark 001 pass until readback and validation succeed.
