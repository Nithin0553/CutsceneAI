# Unreal Adapter Compatibility Ledger

This ledger is persistent engineering memory for incompatibilities discovered during
real CutSceneAI engine-transfer runs. Each incident must produce a code fix and a
regression guard so the same failure signature is not reintroduced.

## UE58-001 — Skeletal animation play rate

- **Observed:** Unreal 5.8 rejected a Python `float` assigned to
  `MovieSceneSkeletalAnimationParams.play_rate`.
- **Error signature:** `Cannot nativize 'float' as 'MovieSceneTimeWarpVariant'`.
- **Root cause:** Unreal 5.8 represents skeletal animation play rate with
  `MovieSceneTimeWarpVariant`.
- **Permanent fix:** route play-rate construction through
  `unreal_compat.make_fixed_play_rate()`, using `set_fixed_play_rate()` on 5.8.
- **Regression guard:** `tests/unreal/test_unreal_builder_ue58_contract.py`.

## UE58-002 — Sequencer section channel access

- **Observed:** `MovieScene3DTransformSection` has no `get_channels()` method.
- **Error signature:** `AttributeError: 'MovieScene3DTransformSection' object has no attribute 'get_channels'`.
- **Root cause:** Unreal 5.8 Sequencer Scripting exposes the supported channel query as
  `GetAllChannels` / Python `get_all_channels()`.
- **Permanent fix:** all channel access goes through
  `unreal_compat.get_section_channels()`, which prefers the 5.8 API and retains
  compatibility fallbacks.
- **Regression guard:** the builder contract test forbids direct `.get_channels()`
  usage in the Unreal builder.

## Failure-handling rule

The Unreal builder now deletes an incomplete generated Level Sequence when a build
exception occurs. Source CSIR remains immutable; level actor preparation is deterministic
and can be safely reapplied on the next run.

## Rule for future incidents

For every new engine/API failure:

1. Record the exact error signature here.
2. Identify the engine-version/API cause.
3. Centralize the compatibility behavior instead of scattering one-off workarounds.
4. Add a regression test that fails if the old mistake returns.
5. Keep the generated target disposable and reproducible from the frozen CSIR.
