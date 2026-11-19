# CED as a continuously improving mapping rules book (v1 software architecture)

## Goal and distinction

The **Cutscene Element Dictionary (CED)** remains the engine-neutral semantic
vocabulary in `packages/contracts/dictionary/cutscene-elements-v0.2.json`.
It is not a claim that all conceivable Unity/Unreal features are solved or
that a particular conversion has passed engine testing.

The versioned **CED Mapping Rulebook** in
`packages/contracts/dictionary/ced-mapping-rulebook-v1.json` indexes the
existing taxonomy, baseline adaptive conversions, unknown concepts, proposed
rules, verified reviews and local re-use. It can grow to represent new semantics
and strategies without silently editing existing source scenes. Every CED
concept is listed as either having a registered candidate rule or requiring
mapping. A registered rule is NOT a fidelity certificate.

## Source -> decision -> target -> feedback loop

1. Unity generates immutable CSIR, CineTwin capture and source project/profile
   evidence. Destination preflight measures supported Unreal capabilities.
2. CED preflight audits every source element. The existing redacted
   `ced_discovery_registry` queues unknown semantics; it never fabricates a
   conversion strategy.
3. Adaptive mapping first evaluates the registered baseline rules plus **only**
   QA-approved rules in the persistent local `ced-knowledge` directory. It
   matches source/target engine versions, capabilities, source/target evidence
   and settings, rejecting ambiguity and missing evidence.
4. The agent selects only available typed conversion adapters. The native
   Unreal preflight and immutable candidate/receipt protections stay mandatory;
   no learned rule can authorize arbitrary Python, Blueprint or C++.
5. Actual source-vs-target samples and native save/reopen readback are measured.
   Failures, mismatches, unsupported formats or new semantics become local
   discovery/feedback items. The user may also submit a **structured** new
   mapping proposal from Studio. User proposals are persistent but inert.
6. After an independently reviewed test case and held-out regression pass, a
   matching **registered** adapter may be promoted to local approved rules.
   The same rule is then available to future adaptive mapping resolutions on
   the machine, still subject to each new job's exact evidence and preflight.
7. Offline contextual-bandit reinforcement learning estimates per-engine,
   per-version mapping rewards from feedback events and proposes better
   strategies. It does **not** write model weights to production, automatically
   add native converters, approve candidates or trigger engine mutation.

## Data separation and privacy

- **Shared taxonomy:** canonical CED meanings, not proprietary user scene data.
- **Baseline rule set:** source/target selectors, resolver ID, typed parameters,
  evidence requirements and current known strategy.
- **Candidate store:** `~/.cutsceneai-studio/ced-knowledge/candidates/`;
  immutable hash-named JSON records with `USER`, `TESTING`, or `TRAINING`
  origin and source-feature digest, not raw source scenes.
- **Approval store:** `~/.cutsceneai-studio/ced-knowledge/approvals/`;
  reviewed evidence hashes, case identity and registered resolver contract.
- **Native evidence:** `~/.cutsceneai-studio/ced-knowledge/native_evidence/`;
  saved source-bound reopened comparison files, subject to explicit QA.
- **Offline RL training:** local JSONL with `case_sha256`,
  `project_group_sha256`, CED, rule, Unity/Unreal versions and outcome.
  No private character names, asset paths, screenshots, or imported source
  files are part of the training event contract.

The store is **local**. No automatic upload, central shared learning, or
global model update is present. Sharing between installations would require
an explicitly opt-in, privacy-preserving review and distribution service.

## How a new user mapping becomes reusable

A user submits a structured mapping proposal through the token-protected local
endpoint `POST /api/ced-rulebook/propose` with `{"rule": <adaptive-rule>}`.
The HTTP response is **PROPOSED_NOT_EXECUTABLE** and has a stable candidate ID.
Duplicate identical submissions are idempotent. `GET /api/ced-rulebook`
returns catalog counts (not private project content).

Operator CLI, run from the repository root:

```powershell
python tools/ced_rulebook.py coverage
python tools/ced_rulebook.py propose --rule proposal.json --origin USER --feature-sha256 <64-hex-source-feature-digest>
python tools/ced_rulebook.py list-approved
```

After native saved/reopened validation and independent human QA, copy the
approved native comparison JSON into the rulebook `native_evidence` folder
and explicitly record approval:

```powershell
python tools/ced_rulebook.py approve --candidate-id <64-hex-candidate-id> --evidence-name comparison.json --reviewer qa_reviewer --held-out-passed --regressions-passed
```

This only works when the CED concept already exists in the taxonomy and the
candidate uses a registered adapter/resolver with no weaker capabilities,
parameters or required evidence than its approved baseline contract.
**A new native conversion algorithm requires code, unit/security tests,
appropriate engine APIs and separate real-engine acceptance before its
resolver can be registered.** Inventing an adapter name in a proposal is not
enough. Approved rules are never overwritten; the loader checks hashes and
rejects modified or missing evidence. Corrections use a new, reviewed rule
identity rather than modifying an earlier approval.

## Offline RL training

A single mapping action followed by a measured outcome forms a **horizon-one
reinforcement-learning problem (contextual bandit)**. The initial deterministic
learner is `packages/learning/ced_reinforcement.py`:

- State/context: CED concept, source and target engine versions and direction.
- Action: an identified mapping resolver/rule.
- Reward: +1 independently reviewed native PASS, -1 FAIL, -0.5 INCOMPLETE.
- Training: pessimistic-prior temporal-difference Q update; one case reward
  per unique case hash; separate held-out source-project group per action.
- Output: ranked `RECOMMEND_FOR_HUMAN_REVIEW` or
  `INSUFFICIENT_VALIDATION_NO_PROMOTION`, with training/evaluation counts and
  provenance hash. It is not a native execution policy.
- Restrictions: no positive rewards for unreviewed/non-native evidence,
  exact version isolation, no train/holdout project overlap per action,
  conservative minimum-case threshold, and fail-closed evidence validation.

Run a prepared, independently reviewed feedback JSONL:

```powershell
python tools/ced_rulebook.py train --feedback approved-experiences.jsonl --output new-ced-policy.json --minimum-cases 3
```

The policy output can help choose **what to test next**. The conversion
planner does not adopt new rankings automatically. A production RL deployment
would additionally need a controlled training environment, genuine native
reward collection, counterfactual/off-policy evaluation, regression benchmarks,
review, rollback/versioning and security/privacy safeguards.

## Coverage and current claim boundary

This software adds a catalog query for every current CED taxonomy concept;
local persistent user proposals; explicit approval/immutability checks;
approved-rule reuse in `resolve_dictionary`; Studio localhost proposal API;
offline contextual-bandit feedback training; and unit/API/security tests.

This does **not** assert that all possible engine features, assets, materials,
scripts, physics or animation formats are transferable. A new semantic feature
must receive a reviewed taxonomy extension; a new conversion requires a real
adapter. No native Unity/Unreal acceptance was performed for these additions.
Do not merge the draft PR to main, switch on unattended learning, or freeze the
software release based on synthetic tests alone.
