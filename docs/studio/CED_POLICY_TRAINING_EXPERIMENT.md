# CED-grounded policy training — executed software experiment

This document describes a **real offline fit**, not a claim of real Unity-to-Unreal
engine correctness or reinforcement-learning improvement.

## Training corpus and supervision

The source contracts are all pinned by SHA256 in each trained checkpoint:

- `cutscene-elements-v0.2.json`: all **735 CED concepts**, spanning **63
  semantic categories**.
- `adaptive-rules-v0.1.json`: **five** registered rule-selector/resolver
  examples. They are implementation contracts, not verified native successes.
- `unity-mappings-v0.1.json` and `unreal-mappings-v0.1.json`: draft native
  class names and CED associations. Nine CED concepts have a native draft
  mapping on both sides; the names are training labels, not proof of
  equivalent behavior.
- `unity-unreal-preflight-v0.2.json`: additional scoped track, section and
  curve capability labels, plus generic native Timeline aliases. It contains
  `SUPPORTED_UNVERIFIED`, `KNOWN_PARTIAL` and
  `KNOWN_UNSUPPORTED` — none may be promoted to real-engine PASS by
  statistical training alone.

The model is `packages/learning/ced_pretraining.py`. It tokenizes native
CamelCase and CED dotted semantic names, fits corpus-derived TF-IDF weights
and normalized concept vectors, and links learned CED IDs to their known
native draft names, rule IDs and conservative capability/refusal status.
A query is advisory, returns no native execution permission and abstains on
mostly out-of-vocabulary inputs.

Before adding the native aliases to the fit, the evaluation queries each
existing draft native alias against **CED-only** vocabulary. This measures
lexical zero-shot retrieval, which is deliberately difficult. The resulting
top-1/top-3 accuracy cannot be interpreted as engine conversion correctness,
and comparisons with other engines need separate datasets.

## Reproducible training run

The normal GitHub CI for draft PR #128 now executes:

```powershell
python tools/train_ced_policy.py train --output ced-mapping-model-v1.json --summary ced-training-report-v1.json
python tools/train_ced_policy.py verify --model ced-mapping-model-v1.json
python tools/train_ced_policy.py suggest --model ced-mapping-model-v1.json --engine unity --native-name TimelineAsset
```

GitHub Actions publishes the trained checkpoint and a compact evaluation
report under the artifact name `ced-trained-policy-<commit SHA>` for 30 days.
It refuses overwrite of the saved checkpoint. The model checksum and the
input sources are checked, and the complete fitted model must be reproducible
from those sources. Changing one permission or unsupported status and merely
recalculating the model's own SHA256 will fail verification.

The optional CED discovery CLI now accepts:

```powershell
python tools/ced_preflight.py --csir source.csir.json --mapping mapping.json --trained-ced-policy ced-mapping-model-v1.json --out source-ced-report.json
```

Unknown native features receive **read-only** semantic suggestions keyed by
their discovery fingerprints. Studio's normal `ced_preflight.audit()` also
fits the checked-in model once per host process and automatically includes
bounded (up to 32 unique signatures) advisory suggestions, without requiring
the operator to copy a model checkpoint into a project. Saved policy artifacts
are useful for reproducibility and independent replay.

Existing CED status, strict transfer gates, source hashes and candidate
immutability are not changed; a suggested mapping remains
`proposal_only=true` and cannot authorize any Unreal write.
For an actual new adapter, human review, source/target contract evidence,
registered converter code, native readback and held-out engine acceptance are
still required.

## Relationship to reinforcement learning

The earlier `packages/learning/ced_reinforcement.py` contextual-bandit learner
is separate. It can train when real independent native feedback events are
available through `tools/ced_rulebook.py record-feedback` and
`tools/ced_rulebook.py train`. The repository currently contains **no
committed reviewed native-reward dataset** for this run. Therefore this
experiment is **CED-based semantic/supervised pretraining**, NOT engine-reward
reinforcement learning and NOT new retarget/transfer model weights.

## Release boundary

The model aids mapping search and gap triage. It does not change Unreal
Sequencer generation, skeletal retargeting, camera math, native asset imports,
animation baking or transfer execution on its own. Those algorithms remain
deterministic and fail-closed. More independent source projects, verified
native successes/failures and measured fidelity are required before training
an outcome-ranked policy or enabling learned native action selection.

All artifacts are generated in CI or by the local CLI. Nothing was merged into
`main` and this training alone does not close the software-freeze issue.
