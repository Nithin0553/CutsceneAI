# CutSceneAI continual learning — research design and v0.1 implementation

## Thesis

CutSceneAI should transfer a growing variety of scenes without hard-coded
benchmark names. Source CSIR and its engine-independent geometry/timing
conversion remain authoritative. Learning helps choose mapping policies,
asset/retarget strategies, and failure diagnoses from previously **verified**
examples. No learning algorithm can guarantee identical output for every
engine-specific shader, script, animation rig or physics environment.

**Do not modify network weights from an unvalidated new cutscene.**

## System architecture

    Unity Timeline / new source cutscene
                 |
         CSIR + Project Intelligence
                 |
       Feature/coverage extraction
                 |
       Deterministic adaptive resolver
                 |                  \
                 |             Verified case memory
                 |                    |
                 |            Similar-case suggestions
                 |                    |
                 +------ Reconcile with capability/evidence rules
                               |
                Target conversion (Unreal)
                               |
         Target readback + CineTwin runtime comparison
                               |
          Human review / acceptance of mapping rule
                       /                 \
                 APPROVED             REJECTED / INCOMPLETE
                    |                      |
             Case memory                 Diagnostic memory only
                    |
              Training dataset export
                    |
           Project-grouped evaluation
                    |
          Optional batch model fine-tuning
                    |
        Deploy only if frozen benchmark gates improve

## Two learning mechanisms

**A. Immediate learning (implemented):** keep content-addressed prior cases.
Feature similarity uses track kinds, entity types, curve semantics, blend
structure, and optionally project/engine capabilities. Retrieved mappings
are only suggestions; the deterministic resolver and engine checks remain
authoritative. Every new approved case can inform the next suggestion
without updating any model weights.

**B. Supervised model fine-tuning (future):** a learned mapping-policy
selector, possibly LoRA/QLoRA on a small pretrained encoder/LLM, predicts
CED/target strategy labels from structured input. Never train from the
generator's own unverified output or compare against the same scene in both
train/evaluation. Use frozen project-level holdouts and replay older examples
during periodic updates. Only promote a new model if it improves mapped
feature coverage without violating numerical and validation constraints.

The v0.1 system does NOT train a neural network, retarget skeletons, or
generate an animation based on examples. It prepares trustworthy structured
training evidence and a nonparametric memory baseline.

## Data required per training example

- A frozen CSIR with its source identity and project fingerprint.
- Target mapping and a resolved Adaptive Mapping Dictionary with named
  source/target conversion rules.
- Independent target readback validation (status PASS, no failures or
  incomplete structural checks) and a human review **bound to source and
  mapping hashes**.
- Optional Unity/Unreal behavior-capture comparisons. Their current rig
  diagnostic cannot prove pose parity, so even a verified mapping example is
  labelled "MAPPING_RULES_ONLY_NOT_FULL_CUTSCENE_PARITY".
- Source/target Project Intelligence Profiles when available.

Incomplete scenes, unmapped features, failing checks, and unreviewed
samples are useful for defect diagnostics but cannot be exported as
positive supervised training labels.

## CLI workflow (Python, no Unreal imports)

Use the learning branch and operate from the repository root:

    python tools/cutscene_learning.py review-template \
      --csir "<frozen source.csir.json>" \
      --mapping "<mapping.json>" \
      --out "<case.review.json>"

This creates an UNAPPROVED review. A human compares independent target
validation and source semantics, then fills review reviewer name and
approve_mapping_examples=true only if labels really match source intent.
Reviewing a mapping does NOT approve visual, audio, event or pose fidelity.

    python tools/cutscene_learning.py record \
      --csir "<frozen source.csir.json>" \
      --mapping "<mapping.json>" \
      --resolved "<resolved-dictionary.json>" \
      --validation "<independent.validation.json>" \
      --review "<case.review.json>" \
      --source-profile "<unity-profile.json>" \
      --target-profile "<unreal-profile.json>" \
      --store "<local-case-library>"

Source/target profile arguments are optional. Resolved dictionary
must be the output of the existing Adaptive Mapping resolver, not a raw
actor-label mapping. If validation is missing/failing, a case becomes
CANDIDATE or DIAGNOSTIC_ONLY. Approved rule labels enter training
only when the dictionary has zero unresolved decisions.

    python tools/cutscene_learning.py status --store "<local-case-library>"
    python tools/cutscene_learning.py suggest \
      --csir "<another-cutscene.csir.json>" \
      --store "<local-case-library>" \
      --output "<suggestions.json>"
    python tools/cutscene_learning.py export \
      --store "<local-case-library>" \
      --output "<train_mapping_cases.jsonl>"

Suggestion output includes source case IDs, Jaccard similarity, shared
features, and candidate CED/resolver pairs. It is NOT automatically
applied and has no calibrated confidence number.

Training export contains only APPROVED verified mapping decisions, omits
raw animation files or sensitive asset content, and carries a
source-project group ID for leakage-safe train/evaluation splitting.

## Dataset progression for the research

Create at least three **different cutscene designs per project** and
eventually several **independent** Unity projects/assets/character rigs:

- controlled cameras and props, timeline offsets and varied frame rates;
- multi-actor motion, animation overlap, different rigs and root-motion;
- camera optics/light/audio/events/hierarchy with unfamiliar combinations;
- custom-script/unsupported cases as explicit negative coverage tests.

Benchmark001 and Benchmark002 reuse one Unity project; randomly splitting
their scenes would overstate generalization. Hold out *whole source projects*
and ideally unseen source rigs/assets as independent tests.

## Metrics for a model to earn deployment

- **Mapping accuracy:** correct CED/target strategies on held-out projects.
- **Abstention quality:** unsupported cases identified before target mutation.
- **Coverage:** supported source tracks and parameters retained.
- **Runtime:** successful in-engine generation and independent structural readback.
- **Fidelity:** measured temporal position/rotation, skeletal pose/retarget
  matching, camera optics, light/audio/event equivalence within declared scope.
- **Forgetting:** no degradation on frozen older benchmark suites.
- **Reproducibility:** source hashes, dataset version, target engine profile,
  model checkpoint, exact review and acceptance gates retained.

**Success = improvements on previously unseen projects without regressions**,
not successful fitting of Benchmark002 alone.
