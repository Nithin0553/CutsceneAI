# CutSceneAI Studio — agent-centric transfer architecture (experimental v1)

**Branch:** `feature/agent-driven-ced-orchestration-v0.1` (stacked on the
software release candidate, not merged to `main`). **Native Unity/Unreal
acceptance remains outstanding.** A green CI run is not a fidelity claim.

## Architecture audit and disposition

| Existing module | Previously overlapping responsibility | Change |
| --- | --- | --- |
| `studio_autopilot.py` | UI-facing coordinator also owned simple pretransfer decisions | Retain durable editor/job state and native no-replay; delegate model selection to LangGraph |
| `studio_transfer_ai.py` | OpenAI-only singleton global policy selection | Reuse trusted source/target evidence, retrieve CED knowledge, call agent planning graph, bind knowledge hash |
| `ced_preflight.py`, `adaptive_mapping.py`, `ced_rulebook.py` | Disparate discovery, mapping, approval and taxonomy surfaces | Retain existing independent evidence governance; expose their source-specific knowledge via `ced_agent_knowledge.py` |
| `feature_dispatch.py`, `transfer_backend.py` | Broad deterministic semantic/action handling | Retain executable adapters, coordinate math, native safety checks and source hash validation; no AI arbitrary code |
| `studio_agent_graph.py` | Post-generation LangGraph reasoning with static broad taxonomy prompt | Use source-specific CED retrieval, common model provider, bounded native repair evidence |
| Unreal worker | Native operation and readback authority | Retain immutable job contract, whitelisted operations, project/level checks and exactly-once receipts |
| CineTwin | Independent source/target observer | Retain; never let model generated descriptions substitute for genuine measured readback |
| `studio_model_provider.py` | Previously absent | Introduce local Ollama or optional OpenAI transport for redacted JSON-only decisions |
| `studio_recovery_policy.py` | Previously ad hoc errors | Classify errors; only pre-native model disconnection supports bounded autonomous retry |

The goal is to remove *policy overlap*, not delete well-tested mathematical
conversion modules or frozen research evidence.

## Responsibility boundaries and contracts

**Unity Bridge (source intelligence):** Source project identity, consent,
CSIR, component census, GUID/material/FBX dependencies, Play Mode CineTwin
samples. It never silently starts Play Mode or mutates source assets.

**CED (knowledge):** Versioned semantic vocabulary, baseline adaptive rules,
native-action candidates and only independently reviewed approved rules.
`ced_agent_knowledge.retrieve` accepts a source CSIR and observed target
capability booleans and returns bounded, **redacted** matching rules, required
evidence, capability gaps, registered native action candidates, unknown
semantics, and an SHA-256 snapshot. It does **not** approve or execute a rule.
Unknown/unsupported types remain explicit investigation cases; a hypothetical
adapter is not an executable alternative. A retrieved rule stays subject to
the independent adaptive-mapping and native-capability preflight.

**AI Agent (brain):** Receives aggregate source/target evidence and relevant
CED candidates; selects an *existing* source-backed strategy and eligible
character motion choice; proposes a reason. The decision is bound to source
CSIR, capture, census, mapping and Unreal project file hashes **and the CED
retrieval digest**. The current executable plan vocabulary is still limited
to registered strategies. Per-element arbitrary semantic tool synthesis is
**not implemented** and must not be inferred.

**LangGraph (orchestration):** `studio_conversion_graph.select` now performs
ground -> reason -> independent validation -> optional alternative reasoning
(up to 2 model attempts). Invalid model JSON, unregistered tools,
ineligible partial activation and unapproved animation choices are refused
before native transfer. The existing post-transfer `studio_agent_graph`
executes only authorized registered repair strategies, with per-job claim and
receipt verification, progress checks, and a fixed repair budget.

**Studio Backend (coordination):** Long-lived localhost API, editor
heartbeats, project selection, locks, one candidate/job submission, immutable
receipts, restart continuity and progress. `WAITING_FOR_MODEL` permits
*up to three* delayed retries of an Ollama-unavailable **pre-native** planning
step. Native queued/running/uncertain jobs are never retried automatically.

**Unreal Worker (hands):** Structured approved native importer/Sequencer
builder, exact project/map identity, asset and rig preflight, save and
independent readback. The model cannot submit Python, shell, arbitrary
Blueprint or invented Unreal SDK calls.

**CineTwin (eyes):** Produces source-matched behavioral observations and
discrepancy reports; records missing evidence separately from verified
mismatch. `GENERATED_UNVERIFIED` is a generated sequence, not a fidelity
PASS. Independent fresh-process Unreal readback and domain-specific
camera/character/material/audio/event evidence remain mandatory.

## Source-to-target state graph

```text
Select projects / consent
  -> WAITING_FOR_UNITY -> WAITING_FOR_UNITY_CAPTURE -> CONNECTING
  -> ANALYZING_PROJECTS
       CED retrieval + source/target provenance
       -> LangGraph: ground -> reason -> validate
             | unsupported/invalid -> bounded alternate reason -> stop
             | local Ollama temporarily offline -> WAITING_FOR_MODEL
                  -> bounded read-only retry, never native replay
       -> approved plan (exact hashes + CED knowledge digest)
  -> PREPARING -> WAITING_FOR_UNREAL -> UNREAL_RUNNING
  -> GENERATED_UNVERIFIED
       -> independent native readback and CineTwin discrepancy analysis
       -> optional bounded LangGraph repair -> native receipt -> remeasure
       -> verified supported subset or explicit INCOMPLETE/BLOCKED
```

All state transitions that cross into native mutation keep existing
non-overwriting candidate and exactly-once job identities.

## Local open-weight model (Windows)

Install Ollama on your own machine. Run in a terminal:

```powershell
ollama pull qwen2.5:7b-instruct
ollama serve
```

If the service is already running, it may report that the port is occupied;
do not start a second service. In the PowerShell that launches Studio:

```powershell
cd "B:\Research\CutSceneAI\CutsceneAI"
$env:CUTSCENEAI_MODEL_PROVIDER = "ollama"
$env:CUTSCENEAI_AGENT_MODEL = "qwen2.5:7b-instruct"
.\tools\start_studio.ps1
```

No `OPENAI_API_KEY` is required for Ollama. The model and server must
be installed **separately**; the Python setup diagnostic does not download
model weights or verify a live Ollama inference. Larger cutscenes can require
more memory. You may select a different locally installed model; verify
structured-JSON support and evaluation quality first.

The provider deliberately refuses non-loopback Ollama addresses to prevent
accidental project metadata disclosure through a remote endpoint. Only a
bounded, redacted semantic summary is sent. Prompt responses are untrusted
JSON and independently validated. For explicit legacy cloud mode set
`$env:CUTSCENEAI_MODEL_PROVIDER = "openai"`, configure
`OPENAI_API_KEY` securely and optionally select
`CUTSCENEAI_AGENT_MODEL`. Without explicit provider selection, Studio
chooses OpenAI only when a key already exists, otherwise local Ollama.

## Validation strategy and honest limits

Automated contracts must cover:
- Existing Benchmark001/002 fixtures without modifying frozen evidence.
- New, unseen combinations of cameras, characters, custom semantics and
  native capability gaps: retrieval must report unknown features honestly.
- Unauthorized model action/injection refusal; lossy adapter gates;
  missing files/hash changes; local-only model transport; absent provider.
- Model-induced strategy changes with actual plan conversion-option
  changes, plus source/target revalidation before native execution.
- No-progress correction stops, existing exactly-once native receipt tests,
  source/target job identity and local server restart continuity.

**Not yet demonstrated:** generalized automatic semantic
per-component native plan generation, full open-weight model
decision-quality evaluation on real engines, broad multi-domain autonomous
repairs, exact skeletal/visual/audio/event parity, or native same-frame
fidelity on a held-out Unity scene. Newly discovered CED candidates require
registered adapters, review, and independent source-target acceptance
before promotion. These are engineering/research milestones, not optional
validation shortcuts.
