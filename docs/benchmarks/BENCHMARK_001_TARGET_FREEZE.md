# Benchmark 001 — Unreal Target Freeze

Status: **PENDING LOCAL ARTIFACT HASH MANIFEST**

Benchmark001 has already reached:

- visual acceptance
- automated readback validation `PASS`
- 54 passed checks
- 0 failed checks
- 0 incomplete checks

The remaining freeze operation is intentionally local because the authoritative Unreal
`.uasset` and generated validation JSON artifacts live in the controlled Unreal project
workspace rather than in this repository.

## Required artifacts

The freeze manifest hashes:

- frozen Unity source CSIR
- local Benchmark001 mapping JSON
- generated Unreal `LS_Benchmark001.uasset`
- source-derived expectation JSON
- Unreal readback JSON
- validation report JSON
- current CutSceneAI repository commit

## Freeze command

From PowerShell:

```powershell
cd B:\Research\CutsceneAI\CutsceneAI

python tools\benchmark001_freeze.py `
  --repo-root "B:\Research\CutsceneAI\CutsceneAI" `
  --source-csir "D:\Unreal\CutsceneAI_Benchmark001_Unreal\Benchmark001.csir.json" `
  --mapping "B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\benchmark001_mapping.json" `
  --target-uasset "D:\Unreal\CutsceneAI_Benchmark001_Unreal\CutSceneAI_Bench001\Content\CutSceneAI\Benchmark001\LS_Benchmark001.uasset" `
  --validation-dir "D:\Unreal\CutsceneAI_Benchmark001_Unreal\validation" `
  --output "D:\Unreal\CutsceneAI_Benchmark001_Unreal\validation\Benchmark001.target-freeze.json"
```

The script aborts if:

- the source SHA-256 is not the frozen Benchmark001 source hash;
- a required artifact is missing;
- the validation report is not `PASS`;
- failed or incomplete checks are non-zero.

Once the manifest is created, its hashes can be copied into this record and the status can
be changed to **FROZEN AUTOMATED PASS**.
