# Guarded AI character-translation repair (experimental)

Branch: `integration/agent-native-adapters-v0.1`. **Not a real-engine acceptance PASS.**

## Purpose

An LLM can propose `restore_constant_actor_offset` only after a user
explicitly asks to correct the **position of one named character**. The
model never writes engine commands or supplies displacement numbers.

The graph reads the original job-bound, source-hashed CineTwin diagnostic and
validates the source CSIR, Unity Play Mode capture, mapping, destination project
and saved Level Sequence. It exposes this strategy only when the pure evidence
gate finds a constant source-minus-target actor-world offset over **every active
playback frame**. Root-bone world offset must independently agree with the
same displacement within **2 cm**. Corrective magnitude must exceed 2 cm and
remain below 5 m. The character must have one unambiguous mapping, one
unparented skeletal component and a unique Sequencer binding, with no
`MovieScene3DTransformTrack` or unsupported competing track.

This is intentionally **not** an answer for a changing trajectory, wrong
facing, rotation, skeletal retargeting, an attached actor, or a root-motion
disagreement. The screenshot's Ch31 actor/root errors (about 295.5 cm versus
379.7 cm) are not proof of a shared constant offset; the native evidence gate
must inspect the full frame samples before allowing an edit.

## Native execution

The existing write-ahead request and one-shot claim queue prevent unattended
replays. The editor worker checks exact job, Unreal project, map, sequence,
active candidate, user feedback ID, original report SHA and setup receipt for
the newly created character. It independently reruns the full CineTwin
comparison. It rechecks the same actor/root eligibility and rejects stale or
ambiguous evidence.

Only then can the worker translate the isolated actor once (no camera,
animation, skeleton, source asset or non-target actor edits). It immediately
remeasures full actor and skeletal-root world positions against source samples,
and saves the level **only if both maximum absolute errors are at most 2 cm**.
If verification fails, it restores the original location without saving and
returns a failure receipt. Source diagnostic reports remain immutable; new
readback reports are retained separately.

A successful receipt means only *native in-editor actor and root positions*
met the specified tolerance. It **does not** establish saved-asset persistence
after a clean Unreal restart, visual/render/audio parity, exact root rotations,
or general cinematic fidelity. Reopen the target map and run separate readback
before any broader claim.

## User test (no new transfer needed)

1. Pull this integration branch into the local **acceptance checkout**; do not
   merge PR #124 into main.
2. Close and restart Unreal Editor so the Python worker and adapters load the
   new revision. Open the exact expected Unreal project and saved level,
   then start `studio_local_editor_worker.start()` as for previous testing.
3. Restart the local Studio server using the Python environment that has the
   API key, keeping the existing generated transfer and receipts.
4. In **Review Cutscene**, request a read-only diagnosis first:
   `Analyze the character Ch31_nonPBR actor and skeletal-root offsets. Do not modify the scene.`
   This must remain `report_only`.
5. For a live repair test, only after keeping a separate backup of the Unreal
   staging project, use a **single-character position-only request** such as:
   `Please correct the position of Ch31_nonPBR.`
   If the full evidence gate rejects it (e.g. root offset not matching actor
   offset, existing transform track, missing frames), expect a report explaining
   why, **not** a modified cutscene.
6. Inspect `/api/agents`, `/api/agent-conversation`, the latest
   `agent-state-<job-id>.json` and candidate-scoped `agent-receipt-*.json`.
   Never bypass a refusal by editing receipt or gate files.

## Development safeguards and limitations

- LLM-selected strategies are always allowlisted and checked again on the
  Unreal editor thread.
- No execution for ambiguous, mixed animation/position/facing requests or
  analysis-only feedback.
- No partial replay after crash: pending claim with no receipt demands manual
  inspection.
- At most two guarded repair receipts per job.
- The pure evidence checker and mocked native rollback have automated tests,
  but must be validated inside **Unreal Engine 5.8** before use on a real
  cutscene. The first accepted outcome remains a candidate, not a fidelity pass.
