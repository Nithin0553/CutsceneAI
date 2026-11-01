# Studio — recover sequence generation without reimporting existing Unreal assets

Use this only for a *specific* CutSceneAI Studio job that imported and saved all
native source assets/actors but stopped at Python startup with:

```
cannot import name 'audit_files' from partially initialized module
'transfer_readiness' (most likely due to a circular import)
```

The failure was caused by `tools/transfer_readiness.py` and
`packages/cinetwin/transfer_readiness.py` sharing a Python module name.
The builder now imports the CineTwin implementation by exact path through
`packages/cinetwin/readiness_loader.py`, and Studio validates that import
**before** the next candidate's asset import or actor staging.

## One-time recovery of the failed job

1. **Save All and back up the existing Unreal staging project.** Do not
   reimport anything, delete the actors, or choose a new candidate yet.
2. Pull branch `feature/studio-ui-connected-v0.3` and **restart Unreal Editor**
   to discard old Python module objects. Reopen the **same** Unreal project and
   level containing the saved actors/assets from the failed job.
3. In Unreal's Python Console, explicitly opt into the one-time sequence-only
   operation:

```python
import sys
sys.path.insert(0, r"B:\Research\CutSceneAI\CutsceneAI\integrations\unreal")
import studio_generation_recovery
result = studio_generation_recovery.recover_latest()
```

Adjust the repository path if needed. The command **does not** retry the
Studio UI import. It will verify all 18 imported assets' native classes and
saved packages and all 10 unique actor labels/types against the approved,
unchanged source manifest, and check the prepared source/target fingerprints,
correct Unreal project and level, saved setup receipt and failure reason.
It refuses a target sequence that already exists.

Only after all checks pass does it write an immutable recovery-attempt record
and ask the existing Unreal generator to create the new Level Sequence.
It saves the updated Unreal level and verifies the generated sequence's class
and saved package. It updates the job pointer/receipt only after success,
preserving a copy of the original failed job file.

A failed recovery is **one-way**: the attempt and any native generation receipt
are retained; do not blindly retry. Investigate the logs first. No engine
object deletion or automatic rollback is performed.

## Acceptable result and further validation

Expected console status on success:

```
[CutSceneAI Studio] RECOVERED_GENERATED_NOT_FIDELITY_VERIFIED
[CutSceneAI Studio] No asset reimport or actor respawn was performed.
```

**Generated** does not mean structurally or behaviorally equivalent. Save All,
close and reopen Unreal, then use the documented read-only persistence and
hierarchy audits. The original 8 unresolved source-parent links (#68), materials,
animation, camera/audio accuracy and CineTwin behavior (#72) remain separate
checks.

This tool is intentionally restricted to this concrete readiness-import
failure. It will reject other setup errors, an unsaved/partial setup, changed
source evidence, mismatched editor project, missing or ambiguous assets/actors,
an existing target sequence or any previous recovery attempt.
