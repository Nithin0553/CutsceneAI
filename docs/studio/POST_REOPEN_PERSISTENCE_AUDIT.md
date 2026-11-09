# Studio — safe post-reopen persistence check

After a successful **Import Unity assets & generate sequence** run, save the staging Unreal project, close Unreal Editor, and **reopen the same .uproject and generated level**. Do **not** rerun the transfer. The following optional check is read-only in Unreal.

## In Unreal's Python Console

Copy the path to `integrations/unreal` from your checkout and run:

```python
import sys
sys.path.insert(0, r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal")
import studio_persistence_audit as audit
result = audit.audit_latest()
print(result["status"], result["asset_count"], result["actor_count"])
```

Replace the example local path with your own repository location. The command uses `~/.cutsceneai-studio/runs/active-job.json` and the immutable prepared Studio candidate. This command does **not** spawn, delete, import or modify an Unreal object or an existing sequence.

## Outputs and evidence meanings

`post-reopen-audit-<job-id>.json` is created **once** next to the candidate's original receipts. Its contents are derived from the current editor's loaded asset registry/objects, actor labels/classes and sequence, plus saved .uasset/.umap package existence; input hashes connect the result to the source-backed import and generation receipts.

- `STRUCTURAL_READBACK_PASS_RESTART_UNVERIFIED`: all expected native assets/classes and actors were found, their package files exist, the level package exists and the LevelSequence's bindings/tracks could be enumerated. A restart is only **operator-reported**, not cryptographically proven.
- `STRUCTURAL_READBACK_FAIL`: at least one required package, class or actor is missing or conflicting. Investigate before another trial.
- `STRUCTURAL_READBACK_INCOMPLETE`: native sequences/assets/actors are present but the sequence's track/binding enumeration was unavailable; do not claim a PASS.

The script also refuses a different target Unreal project or level, a missing/failed setup/generation receipt, or an output-file overwrite. Do not upload raw assets, private file paths or proprietary source data with issue comments: a redacted result/status and relevant counts are sufficient for triage.

**Not validated:** actual actor restarts, source/target behavior or trajectory parity, material accuracy, complete skeletal pose, audio waveform, cinematographic framing, event execution or hierarchy correctness. Use CineTwin and independent source/target observations for those research claims. #54 #55 #62 #72 remain open until authentic engine evidence satisfies their acceptance criteria.


## Audit compatibility with older successful setup receipts

The first implementation required the saved setup receipt to contain both
`target_sequence` and `target_namespace`. Earlier Studio runs may predate
these metadata fields even when the native import was completed.

The updated read-only auditor compares all **present** identities; a
contradictory field or non-success status blocks the audit with a precise
field name. When an optional historic identity field is **missing**, it still
checks the live Unreal assets, actor classes and saved packages, but records
`provenance_status: INCOMPLETE_LEGACY_RECEIPT` and
`status: STRUCTURAL_READBACK_INCOMPLETE`. It never silently promotes a
missing identity to verified evidence or changes the original receipts.

If a mismatch persists, the error reports the exact field that differs. Do
not edit the receipts to make them match or rerun the transfer over an existing
Level Sequence.


## Inspect native pass/fail counts from a previously generated audit

The original `asset_count` and `actor_count` fields count records **examined**;
they do not demonstrate that the corresponding packages and actors passed.

From Unreal's Python Console after updating the repository:

```python
import sys, importlib
sys.path.insert(0, r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal")
import studio_persistence_audit as audit
importlib.reload(audit)
summary = audit.summarize_latest()
```

This reads the **existing** `post-reopen-audit-*.json`, including audits created
by the previous script, and prints verified-versus-planned counts for assets
and actors, on-disk sequence/level status, bindings/tracks counts, and actual
failures. It makes **no Unreal API calls** and creates **no files**.

`native_structure_status` distinguishes structural checks from the
`provenance_status` of historical receipts. For example, real structure may
be PASS while historical identity fields keep overall status INCOMPLETE.
Neither status claims source-to-target animation/visual/audio fidelity.
