# Element 2 — Hybrid CED Knowledge Base v1

**Development branch:** \`feature/ced-hybrid-knowledge-service-v0.1\`,
stacked on Element 1 (Unity Source Intelligence) and the agent-centric
architecture work. **Native engine validation, complete cross-domain
planning, and signed shared knowledge distribution are NOT certified.**

## Goal and trust boundary

**CED is knowledge; the agent is the brain; registered native tools are the
hands; CineTwin is the eyes.** The hybrid CED service combines:

1. **Shared baseline** — checked-in Git-versioned taxonomy and rulebook,
   no runtime external download or execution permission. Existing baseline
   rules remain *registered/advisory*, not falsely marked as independently
   native-fidelity-verified.
2. **Private local experience** — immutable, reviewed mapping cases and
   independently approved rules. No automatic publication or export.
3. **Review staging** — an explicit, consented, sanitized bundle that
   cannot be installed, published, or used to authorize engine writes.

The service returns structured retrieval facts and original source relationship
context for the agent, rather than selecting the conversion strategy itself.

## New contracts and modules

| Location | Responsibility |
| --- | --- |
| \`packages/contracts/dictionary/ced-shared-manifest-v1.json\` | Pinned, read-only shared baseline policy and declared source files |
| \`packages/contracts/dictionary/ced-strategy-recipe-v1.schema.json\` | Versioned bounded recipe schema: semantics, relationships, applicability, alternatives, verification domains and provenance |
| \`packages/ced/semantic_graph.py\` | Full occurrence accounting and read-only parent/binding/containment/dependency graph from source CSIR |
| \`packages/ced/knowledge_service.py\` | Unified, paginated read-only retrieval across shared rules, reviewed local rules, native action candidates and private verified cases |
| \`packages/ced/strategy_recipes.py\` | Constructs source-relevant typed recipe candidates from existing registered rules, never code or native write permissions |
| \`packages/ced/shared_review.py\` | Explicit consent and privacy screening for a non-executable shared review bundle |
| \`packages/studio/ced_agent_knowledge.py\` | Compatibility façade delegating to the **single** CED knowledge service |
| \`tools/ced_knowledge.py\` | Read-only page inspection and local approved-rule review staging commands |

The existing \`ced_rulebook.py\`, \`adaptive_mapping.py\`,
\`case_memory.py\`, \`ced_pretraining.py\`, \`ced_reinforcement.py\`,
\`ced_discovery_registry.py\` and native \`feature_dispatch.py\`
are retained. There is no second approval authority.

## Retrieval and dependency relationships

\`\`\`text
Unity CSIR + scene graph + optional local approved cases
       |
       v
semantic_graph.analyze()
  - source assets/entities/tracks/sections/curves/relationships
  - actual parent relationships, track bindings and containment
  - unresolved dependency count (never fake resolution)
  - counts EVERY source CED occurrence
       |
       v
knowledge_service.retrieve(page=N)
  - pinned shared baseline
  - evidence-validated approved local rule overlay
  - registered native action candidates
  - verified private case suggestions (mapping-only)
  - engine version and capability requirement checks
       |
       v
source-bound knowledge digest + coverage ledger
  - rules and typed recipe references
  - related semantic dependencies
  - missing native capabilities and preflight requirements
  - explicit unknowns and paging status
       |
       v
LangGraph conversion agent
  - chooses only installed conversion options
  - retains independent source and target provenance gates
  - no arbitrary Python/Unreal code or invented adapters
\`\`\`

Retrieval returns \`source_ced_count\`, \`source_occurrence_count\`,
\`relationship_count\`, \`coverage_ledger\`, \`coverage_ledger_sha256\`,
\`page\`, \`page_count\`, \`next_page\`, and \`retrieval_complete\`.
The detailed page size is between 1 and 48; the full ledger still accounts
for every encountered semantic even when a second retrieval is necessary.
It **does not** claim a model has analyzed every omitted detail. Model
payload limits continue to apply, and full multi-page reasoning is an
outstanding improvement.

Unknown semantics remain \`UNKNOWN_SEMANTIC_INVESTIGATE\`. They do not
become \`EXACT\`, \`RESOLVED\`, or executable because of lexical similarity.
Relationship output is aggregated by semantic concept, never raw Unity
GameObject ID, project path, asset name, or script/source code.

### Source and target capability interpretation

When actual source/target capabilities are passed, candidate rules report
missing capabilities. Absence is not assumed to mean support. The current
worker's capability vocabulary is smaller than the complete CED capability
catalog, so missing evidence must remain explicit until the engine provides
a verified capability. Native preflight remains the final guard.

**Recipe trust:** A recipe is only a source-contextual representation of
an already registered rule, with native *candidate* action names and required
verification domains. The embedded \`execution_authorized\` value is always
false. The recipe SHA can support provenance, but not authenticity,
runtime authority, or cinematic fidelity.

## Private learning

The checked-in CED baseline is not modified by transfers or model responses.
The pretransfer planner now optionally reads verified mapping-only cases at
\`~/.cutsceneai-studio/ced-cases/\` and locally approved rules at
\`~/.cutsceneai-studio/ced-knowledge/\`.
Both stores remain on the user workstation. Missing directories are treated
as empty; altered/malformed approvals fail safe.

Existing case memory \`build_case\`, \`save_case\`, and \`suggest\` still
require independent structural validation and explicit review before a case
can be labeled \`MAPPING_VERIFIED\`. Suggested private cases are advisory,
not generalized proof of full cutscene parity. Offline CED pretraining
and contextual-bandit rewards remain advisory, with no unreviewed
model training or rule promotion.

The post-generation agent also maintains its existing per-workspace
\`learning/approved-cases\` store. Converging that local path and the
new persistent cross-project private case store is a further migration
task; the two stores are **not** automatically synchronized.

## Explicit reviewed promotion

Existing \`ced_rulebook.propose\` and \`ced_rulebook.promote\` still require
an eligible registered adapter, native readback comparison evidence, separate
held-out/regression claims and a human reviewer. JSON claims are checked for
consistency but cannot themselves prove native evidence authenticity.

\`shared_review.stage_for_review\` additionally requires:

- explicit consent for this exact operation;
- a caller-selected list of immutable, locally approved candidate IDs;
- successful revalidation of each approved native receipt;
- restrictive allowlisting of shared rule fields and parameter values;
- exclusion of freeform notes, reviewer usernames, project IDs, source
  artifacts, names, paths and native capture/readback contents;
- a new output file, no overwrite, with immutable content digest.

**The resulting bundle is \`REVIEW_ONLY_NOT_TRUSTED_NOT_EXECUTABLE\`.**
It cannot be imported by \`knowledge_service\` or installed through Studio
and is not automatically sent to GitHub or a remote service. Independent
native evidence authenticity verification, a proper code review, signed
shared release bundles, compatibility policy and revocation/deprecation
support are still required before distributing external updates.

A SHA-256 digest alone proves file integrity relative to the recorded digest;
it does **not** prove who published the file.

## Local developer workflows

Source-specific read-only retrieval (replace paths with files from your
own approved Studio session):

\`\`\`powershell
python tools/ced_knowledge.py query \`
  --csir "B:\Path\To\source.csir.json" \`
  --target-capabilities "B:\Path\To\target-capabilities.json" \`
  --source-version "6000.3" --target-version "5.8" --page 0
\`\`\`

To inspect more than one page, increment \`--page\` while \`next_page\`
is not null. Capability input should contain observed Boolean capability
flags, not guessed native support.

Stage **only** one explicitly selected previously reviewed candidate:

\`\`\`powershell
python tools/ced_knowledge.py stage-review \`
  --approved-store "$HOME\.cutsceneai-studio\ced-knowledge" \`
  --candidate-id "<real-64-character-approved-candidate-hash>" \`
  --output "$HOME\Desktop\ced-reviewed-proposal.json" \`
  --explicit-sharing-consent
\`\`\`

This creates a local review artifact, not a publication or authorization.

## Verification and honest limits

CI must continue to verify:
- previously installed CED and agent contracts and frozen benchmarks;
- generic, previously unseen combinations of nested character/camera/asset
  dependencies, with no raw names in model knowledge;
- exact concept accounting, pagination and unknown state retention;
- absent source capability evidence remaining unverified;
- reviewed private case suggestions never granting target mutation;
- unapproved, unconsented, unsafe-path and altered review attempts failing;
- no regression in native conversion, agent retry, frontend or release gates.

**Still unverified in real engines:** unknown third-party component
identification completeness, source/target native version capability discovery,
cross-project learned strategy generalization, multi-page agent reasoning,
automatic new adapter construction, real CineTwin fidelity for unfamiliar
cutscenes, and signed shared release distribution. These are explicit
Element 2 follow-on acceptance items, not automatically solved by this PR.
