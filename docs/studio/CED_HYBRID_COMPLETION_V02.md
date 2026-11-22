# Element 2 — Hybrid CED completion acceptance (v0.2)

**Branch:** `feature/ced-hybrid-completion-v0.2`, stacked on the
Element 2 draft PR #134. This document describes **software contracts and
implemented workflows**, not native Unity/Unreal certification.

## Phase completion and responsible boundaries

| Phase | Implemented behavior | Software acceptance |
| --- | --- | --- |
| **2.1 — Knowledge Contracts** | Draft 2020-12 validation for the pinned shared manifest and every strategy recipe at runtime; strict relationship, provenance and nonexecution rules | Reject unknown keys, invalid versions, mismatched relations, invented native code and untrusted release manifest pointers |
| **2.2 — Contextual Retrieval** | Complete multi-page CSIR retrieval with source/rule/feedback fingerprints; dependency context, native capability gaps, lexical unknown investigation, version-scoped prior-outcome ranking; multi-page read-only LLM analysis before final agent choice | Held-out synthetic inventories are fully accounted for; unknowns never become mapped; missing pages, changed rulebooks and failed model reviews block native preparation |
| **2.3 — Local Experience** | Automatic immutable trial/failure diagnostics on Studio native status polling, separately recorded source-bound CineTwin measurements; signed independent process evidence gated by existing release assessor; reviewed per-rule native feedback to contextual ranking | Raw private asset names and error strings never enter shared knowledge; replayed cases detected; one project cannot produce strong confidence; full-cutscene parity never inferred |
| **2.4 — Shared Promotion** | Explicit user consent, sanitized local review queue, two independent Ed25519 reviewer approvals, verified review evidence digests, publisher-signed portable release, pinned publisher trust, ordered signed update chain, revocation and forward-only rollback | No self-trusted download, unauthorized extra data, unsigned rule, replayed/stale version or unregistered native adapter enters the installed trusted knowledge |

### Separation of authorities

- CED is **retrieval and audited knowledge**, not executable native code.
- The agent reasons over actual CSIR/target evidence and all needed CED
  retrieval pages, then chooses an installed, validated conversion strategy.
- The Unreal Editor Worker alone performs registered native operations.
- CineTwin/reopened Unreal comparison supplies independent observations.
- Studio records **private diagnostics automatically**, never a positive
  per-rule training label unless independent native evidence and explicit
  human review authorize it.
- Two trusted human reviewer signatures authenticate the privacy and native
  evidence decisions before a separate authorized publisher can issue a
  release. Signatures establish provenance of claims; they do not make
  simulated benchmark results equivalent to real-engine fidelity.

## Folders and modules

```text
packages/ced/
  contracts.py             # runtime JSON-schema + provenance validator
  semantic_graph.py        # complete source semantic relationship graph
  knowledge_service.py     # contextual cross-page retrieval
  strategy_recipes.py      # typed, nonexecuting strategy candidates
  strategy_ranking.py      # capability/dependency/private evidence ranking
  shared_review.py         # private-to-sanitized proposal
  review_queue.py          # signed independent review decisions
  shared_distribution.py   # signed releases, trust, chain and revocation

packages/contracts/dictionary/
  ced-strategy-recipe-v1.schema.json
  ced-shared-manifest-v1.schema.json
  ced-shared-manifest-v1.json

tools/
  ced_knowledge.py         # operator entry point
  studio_continual_learning.py # immutable native trial/outcome ledger
```

The existing `ced_rulebook`, `adaptive_mapping`, `case_memory`,
`ced_reinforcement` and native adapters remain the source of registered
capabilities and review gates. No alternative engine execution path exists.

## Private learning

Automated Studio polling of a terminal job records a privacy-minimal trial at
`<workspace>/learning/trials/<job_id>.json`. The source CSIR, target mapping
and CED taxonomy are hashed. Native failure stage is drawn from an explicit
finite set; error text and paths are never copied into the ledger.

When an independent native acceptance folder exists, the read-only release
assessor checks source/session/plan binding, observation hashes, editor
independence and measured behavior. Only then does Studio save a separate
`<workspace>/learning/measured-outcomes/<job_id>-<digest>.json`, with the
domain outcome and exact evidence hash.

Neither record is a per-rule positive label. For a specific **reviewed**
mapping, an operator may use `ced_reinforcement.record_native_experience`
through the CLI below to add an experience to the private store. Positive
reward requires source-bound native persistence, another Unreal process,
independent measurement and explicit human review. Offline ranking uses
version-matched cases and distinct project groups; unresolved or negative
events remain advisory failure warnings.

### Local CLI

Inspect all source CED concepts without silently losing later pages:

```powershell
python tools/ced_knowledge.py query `
  --csir "C:\Path\To\source.csir.json" `
  --target-capabilities "C:\Path\To\observed-capabilities.json" `
  --source-version 6000.3 --target-version 5.8 --all-pages
```

Record a specifically identified native rule after checking actual engine
receipts and observed evidence:

```powershell
python tools/ced_knowledge.py review-native `
  --comparison "C:\Evidence\comparison.json" `
  --sampling-plan "C:\Evidence\sampling-plan.json" `
  --ledger "$HOME\.cutsceneai-studio\ced-experiences.jsonl" `
  --ced "camera.fov" --rule-id "an-installed-rule-id" `
  --source-version 6000.3 --target-version 5.8 `
  --explicit-human-review
```

Absence of the explicit review switch does **not** create a positive reward.

## Shared review and signed distribution

The previously implemented `stage-review` produces a **sanitized,
review-only** bundle. The following steps are offline and require the user
or release maintainer to take explicit action; no source files are uploaded.

1. **Submit** a sanitized bundle:
   `python tools/ced_knowledge.py queue-review --bundle <staged.json>
   --queue <local_queue_directory> --explicit-sharing-consent`.
2. **Review separately** with at least two authorized identities, one for
   `NATIVE_EVIDENCE` and one for `PRIVACY`. Each signer supplies three
   evidence files (native, heldout, regression) and an Ed25519 private key
   held *outside Git and Studio*. The `sign-review` command creates a
   signed decision tied to the bundle and exact evidence file hashes.
3. **Publish** with `sign-release`: supply a JSON array of the signed
   decisions, an operator-maintained JSON map of reviewer IDs to separately
   trusted Ed25519 public-key files, and the authorized publisher private
   key. Explicit release consent and a revision number are mandatory.
4. **Install** with `install-release`: supply the signed release file, a
   **separately provisioned trusted publisher public key**, and an existing
   safe release store. Explicit install consent is mandatory.
5. **Deprecate/revoke** with `sign-release --revoke-rule <rule_id>`,
   publishing the *next* signed revision. Rollback of a previous bad rule
   is also a forward-only signed successor, never a silent downgrade.

The default local installer location is
`~/.cutsceneai-studio/ced-shared-releases/`, with its independently
trusted public key at `~/.cutsceneai-studio/ced-trust/publisher.pem`.
These directories are **user-managed**; Studio never fetches a public key
from the release bundle itself. A rule whose CED concept or native adapter
is not registered is rejected even when its bundle has a valid signature.

**No production publisher or independent reviewer keys are checked in,
generated automatically or provisioned by this PR.** Deploying a real shared
CED release requires human trustees, actual engine readback evidence,
held-out trials and an approved release identity.

## Remaining external / native verification

Automated CI and synthetic held-out cases can validate control flow and
failure behavior. They **cannot establish** that Unreal rendered the target
cutscene correctly or that an uploaded native evidence report is genuine.
A real independent Unity/Unreal acceptance run is required to authenticate
new mapping fidelity, skeletal retargeting, camera optics, materials,
environment behavior and third-party components.

The broad arbitrary per-component AI planner also remains part of **Element 3**
rather than CED: Element 2 returns relevant, validated and version-aware
knowledge and evidence, but never synthesizes unbounded native code.

**Software acceptance is conditional on the full CI suite passing on the
final branch head.** A passing test result will not change these explicit
real-engine and human-review requirements.
