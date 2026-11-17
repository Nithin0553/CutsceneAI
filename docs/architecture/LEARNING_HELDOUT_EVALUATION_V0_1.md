# CutSceneAI — Project-isolated learning evaluation v0.1

**Scope:** offline CED/target *mapping strategy* evaluation. This evaluates the learning workflow without modifying Unity, Unreal, Studio adapters, LangGraph strategies or model weights.

## Why this exists

The adapter developer is building native engine conversion capabilities. This separate subsystem determines whether accumulated, independently approved mapping examples could support a better general-purpose mapping selector. A training model must not evaluate itself on scenes from the same Unity project used to train it, and a failed conversion must not be treated as a correct training label.

Existing `case_memory.py` already gates promotion on independent readback validation and explicit reviewer approval. The new held-out evaluator consumes those immutable records; it neither widens verification scope nor bypasses approval.

## Reproducible workflow

Use Python 3.11+ and the existing `tools/cutscene_learning.py record` workflow to collect verified examples from different source Unity projects. *Multiple cutscenes within one Unity project count as one group*.

At least **three independent approved source projects** are required to create nonempty train, validation, and final holdout sets. This is only a technical minimum, not a scientifically adequate sample size for releasing a model.

```powershell
python tools/cutscene_learning_evaluate.py --store ".\learning-cases" prepare --seed "experiment-001" --out ".\learning-eval-001"
python tools/cutscene_learning_evaluate.py --store ".\learning-cases" baseline --manifest ".\learning-eval-001\manifest.json" --split validation --out ".\learning-eval-001\baseline-validation.json"
python tools/cutscene_learning_evaluate.py --store ".\learning-cases" baseline --manifest ".\learning-eval-001\manifest.json" --split holdout --out ".\learning-eval-001\baseline-holdout.json"
```

The output directory must be new. It contains a content-bound `manifest.json` and **training-only** `train.jsonl`; held-out mapping labels are not exported into the training file. Every split uses complete project fingerprints, and any duplicate source evidence falsely claimed as two independent projects is rejected. Later changes to the approved case store invalidate the frozen manifest, requiring a new experiment ID.

## Future model adapter

An external mapping-policy model may produce **offline** JSONL predictions keyed to exact held-out `case_id` values:

```json
{"case_id":"<approved-case-id>","abstain":false,"labels":[{"ced":"camera.cut","resolver":"camera.native","outcome":"CONVERTED"}]}
```

To abstain, use `{"case_id":"<approved-case-id>","abstain":true,"labels":[]}`. No native paths, code, strategies' executable parameters or arbitrary files can be included. No generic model tool execution is authorized by this record.

```powershell
python tools/cutscene_learning_evaluate.py --store ".\learning-cases" score --manifest ".\learning-eval-001\manifest.json" --split validation --predictions ".\candidate-validation.jsonl" --out ".\learning-eval-001\candidate-validation-score.json"
```

Do not tune hyperparameters on the final holdout. The evaluation computes policy-label exact match, coverage, abstention, false positives and label precision/recall/F1 **only on attempted cases**. An always-abstaining model receives zero attempted-case accuracy, not a perfect score.

## Release gates still required

- Mapping label equality does not verify numeric parameters or native output fidelity.
- A real model's training-data provenance still needs independent evidence; this evaluator alone cannot prove a model was never exposed to held-out data.
- Model promotion must require a separate signed approval, confidence/abstention calibration, nonregression on frozen projects, and actual Unity/Unreal CineTwin acceptance.
- Production transfer execution must continue to use registered capability adapters and guarded native calls, not directly apply model output.
- Train/validation/holdout cannot establish universal correctness for unknown scripts, shaders, plugins or rigging.

This feature deliberately owns only `packages/learning/heldout_evaluation.py`, `tools/cutscene_learning_evaluate.py`, its tests, and this documentation. Adapter development PRs must remain independent.
