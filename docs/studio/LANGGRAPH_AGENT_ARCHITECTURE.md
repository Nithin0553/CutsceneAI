# CutSceneAI Studio — optional LangGraph agent architecture

## User interaction

1. User connects real Unity and Unreal projects, selects an exported cutscene
   and a fresh saved destination level, and confirms source import rights.
2. **Enable AI agents** is unchecked by default. If unchecked, the normal
   deterministic CED/CSIR transfer plus existing native audits runs unchanged.
3. If checked, approval is bound to that exact immutable candidate and copied
   to the queued job. The normal deterministic transfer still runs **first**.
4. When the job finishes, the Studio service checks its independent CineTwin
   diagnostic and native visual audit. No detected gaps means no model call.
5. If something is missing or mismatched, a **real LangGraph StateGraph** runs:
   inspect → reason (LLM) → approved strategy dispatch → native Unreal repair →
   native re-audit → feedback. It loops only while genuine improvement was
   measured, with a hard bound of two repair requests.
6. Results show native generation success independently from agent completion.
   Incomplete evidence, unsupported CED domains and missing model configuration
   are visible. **A generated sequence is not proof of perfect fidelity.**

## Implementation boundaries

- LangGraph and the OpenAI Python SDK run in the **local Studio Python
  process**, not inside the Unreal Editor Python interpreter.
- The Studio daemon resumes jobs from source-bound files in
  \`~/.cutsceneai-studio/runs/candidates/<candidate-id>/\`. It does not require
  keeping the browser tab open. A running Unreal Editor companion is required
  for any native repair execution.
- Model prompts include a **minimal diagnostic summary**, not project assets,
  raw scripts, scene files, local paths, credentials or arbitrary user source.
- The model returns a structured, validated strategy choice. Its choices are
  restricted to \`report_only\` and \`restore_source_albedo\`. No arbitrary
  Python, Unreal console commands, agent-authored scripts or shell access are
  accepted from the model.
- The source-backed material repair requires an immutable Unity material
  texture GUID reference, the exact native imported FBX material slot,
  a fallback material on a newly staged actor, the same active job, an exact
  Unreal project and level identity, an existing generated sequence and a
  matching baseline visual audit. User/nondefault materials are preserved.
- Every native request has a unique job-bound, candidate-bound ID. It is
  executed **once** by the editor tick and acknowledged by a matching receipt.
  A missing receipt resumes without replay, and a failed/stale receipt stops.
- Material repairs are followed by independent native material readback and
  level persistence. If the fallback slot count does not decrease, stop.
  The agent cannot claim full pixel, skeletal, camera, light, audio or event
  fidelity merely because the material counts improve.
- Other mismatches receive an agent-generated **diagnosis**, but no automatic
  executable repair until a source-provenanced CED adapter and corresponding
  independent acceptance test actually exist. No unlimited loop is allowed.
- If the normal native transfer fails before a CineTwin report exists, the
  agent receives the failure stage/status for diagnosis, **not** permission
  to replay a partially mutated cutscene.

## Install in the Studio host environment

From the repository root in a PowerShell terminal (with the same Python used
by \`tools/start_studio.ps1\`):

\`\`\`powershell
python -m pip install -e ".[agents]"
\`\`\`

Before opening Studio with **Enable AI agents**, configure
\`OPENAI_API_KEY\` in that Studio process's environment. A separate SDK model
setting \`CUTSCENEAI_AGENT_MODEL\` may be used to change the default
\`gpt-5-mini\`; the model must support the OpenAI Responses API structured
output format. The key is not stored in Studio's reports or sent to Unreal.
This is a potentially billable, opt-in API interaction. Do not put credentials
inside the project, command history, GitHub issues or logs.

\`\`\`powershell
powershell -ExecutionPolicy Bypass -File .\tools\start_studio.ps1
\`\`\`

Then open http://127.0.0.1:8765 and connect the projects. The Results view
shows the LangGraph status, selected reasoning (if available), number of
guarded repair iterations, and failures.

## Test and actual-engine acceptance

GitHub CI runs Python regression tests with the genuine LangGraph package
installed. The tests cover: opt-in/off, graph structure, model-configuration
failure, allowed strategy gating, request/receipt matching, no progress,
bounded retries, unsupported strategies and preserving source identity.
It also runs browserless UI/API integration tests.

**Still required before claiming a validated real-engine agent transfer:**

- Run the consented flow in the actual Unity source and Unreal staging editor.
- Test model access with a real configured API account and capture an actual
  source-matched CineTwin report.
- Verify repair candidate material GUIDs, native actor slots, save/reopen
  persistence and measured changes in a separate Unreal staging project.
- Validate rendered-frame differences, dynamic lighting, camera lenses and
  cuts, skeletal animation/retargeting, full audio time alignment, scene
  hierarchy, event behavior and CED feature coverage.
- Add **new source-backed executable adapters** for unsupported categories;
  an LLM suggestion alone cannot create their native engine semantics.

The graph implementation is real and the host/editor request protocol is
connected, but a full game-industry cutscene fidelity guarantee is neither
technically justified nor represented as completed by this architecture.
