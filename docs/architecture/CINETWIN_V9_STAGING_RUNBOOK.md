# V9 staging trial — source-ground-truth character and camera correction

This is a RESEARCH TRIAL, not a proven general cutscene transfer. Keep
Benchmark001 frozen and V8 unchanged. Generate a NEW asset:
  /Game/CutSceneAI/Benchmark002/LS_Benchmark002_CED_V9

## Changes and limits

1. A verified CineTwin world-camera capture replaces native/local camera
   trajectory compilation. Camera positions and rotations are observed but
   framing, projection, and rendered image equivalence remain unverified.
2. A stationary character with skeletal animation receives an authored static
   scene world-pose track, independent of transient editor level placement.
3. Opt-in skeletal world-root lock: for source root excursion >=25cm and a
   unique matching target root with no competing transform or actor attachment,
   measure target imported skeletal-root world poses and bake actor corrections.
   This is root POSITION alignment, NOT joint retargeting, blend fidelity,
   or proof of continuous actor origins.
4. Every output remains GENERATED_UNVERIFIED until independently captured.
   Failures can leave an unsaved newly generated sequence in editor memory.
   Use a BACKED-UP staging Unreal project, and do not save the level until
   you have checked actors and attachments.

## A. Prepare V9 without touching either engine

In VS Code PowerShell in the existing working repo:

~~~powershell
cd "B:\Research\CutsceneAI\CutsceneAI"
git fetch origin
git switch feature/cinetwin-v9-world-parity-v0.1
git pull --ff-only origin feature/cinetwin-v9-world-parity-v0.1

$trial = "D:\CutSceneAI - Studio\StudioAssetTests\Benchmark002_V9_$(Get-Date -Format yyyyMMdd_HHmmss)"
python tools/studio_candidate.py --csir "D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline-e6518af4.csir.json" --mapping "B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\benchmark002_cinetwin_parity_mapping.json" --capture "D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline.cinetwin.behavior.json" --sequence "/Game/CutSceneAI/Benchmark002/LS_Benchmark002_CED_V9" --out "$trial" --skeletal-root-world-lock

Write-Host "Candidate prepared in: $trial"
~~~

This produces a fresh evidence directory and fresh mapping copy next to it,
named like Benchmark002_V9_DATE.mapping.json. Neither source CSIR, original
mapping, nor target engine assets are touched. If preparation is BLOCKED,
do not edit frozen input files to bypass the checks.

## B. Build V9 in the already open Unreal Editor

First confirm you have backed up the target Unreal project and the
Benchmark002 level is loaded. Paste the following in Unreal Python Console:

~~~python
import unreal
import sys
from pathlib import Path

sys.path.insert(0, r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal")
import build_level_sequence

parent = Path(r"D:\CutSceneAI - Studio\StudioAssetTests")
candidates = sorted((p for p in parent.glob("Benchmark002_V9_*")
                     if p.is_dir() and (p / "transfer-plan.json").is_file()),
                    key=lambda p: p.stat().st_mtime)
assert candidates, "No prepared V9 trial found"
trial = candidates[-1]
mapping_copy = trial.with_suffix(".mapping.json")

project = str(unreal.Paths.get_project_file_path())
assert "CutSceneAIStudio_CineTwin_Test" in project.replace("\\", "/")
assert project.endswith("CutSceneAIStudio.uproject")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
level_path = str(world.get_path_name()).split(".")[0]
assert level_path == "/Game/CutSceneAI/Benchmark002/L_Benchmark002", level_path
assert unreal.load_asset("/Game/CutSceneAI/Benchmark002/LS_Benchmark002_CED_V9") is None, "V9 already exists: refuse overwrite"

print("V9 source:", trial)
result = build_level_sequence.build_prepared_files(
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline-e6518af4.csir.json",
    str(mapping_copy),
    str(trial / "transfer-plan.json"),
    str(trial / "coverage-report.json"),
    str(trial / "evidence.json"),
    str(trial / "unreal-runtime-receipt.json"),
    expected_project_path=project,
    expected_level_path=level_path,
)
print("V9 GENERATED, NOT VERIFIED:", result.get_path_name())
~~~

This refuses a pre-existing V9 sequence and verifies source hashes from the
prepared handoff before modifications. Do not rerun on the same asset name.
If generation fails after creating an asset, follow the Unreal log instructions,
close WITHOUT saving and retry only with a new staging path after inspection.

## C. Independently measure V9

Use the new CineTwin diagnostic, changing only the mapping copy and target:

~~~python
import diagnose_cinetwin_parity
from pathlib import Path

parent = Path(r"D:\CutSceneAI - Studio\StudioAssetTests")
trial = sorted((p for p in parent.glob("Benchmark002_V9_*")
                if p.is_dir() and (p / "transfer-plan.json").is_file()),
               key=lambda p: p.stat().st_mtime)[-1]
report = diagnose_cinetwin_parity.run(
    csir_path=r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline-e6518af4.csir.json",
    capture_path=r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline.cinetwin.behavior.json",
    mapping_path=str(trial.with_suffix(".mapping.json")),
    sequence_path="/Game/CutSceneAI/Benchmark002/LS_Benchmark002_CED_V9",
    output_dir=str(trial),
)
~~~

Share the single new timestamped report. Frame 288 is exclusive and excluded
from active pose-error aggregates. Candidate acceptance requires independent
evidence for Character B placement, Camera B movement, improved Character A
root/Hips position and no f49->50 positional snap, and preserved prop/parented
movement. Do not count source pose reconstruction as full skeletal, audio,
event, camera, lighting, material or rendered visual fidelity.
