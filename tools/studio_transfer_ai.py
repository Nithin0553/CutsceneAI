"""Evidence-bound AI conversion planning BEFORE Unity -> Unreal candidate creation.

The LLM sees a redacted summary of the selected Unity CSIR/capture/census and
the connected Unreal .uproject/worker. It may propose ONLY options implemented
by the existing deterministic transfer planner. Validation is repeated against
trusted source data; AI cannot invent mappings, import paths or native commands.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

KINDS = frozenset({"native_source", "source_materials", "visual_activation_partial"})
SCHEMA = "cutsceneai.studio.ai_conversion_decision"
VERSION = "1"
ROOT = Path(__file__).resolve().parents[1]
# Keep small project documents bounded independently of source behavior data.
# The Unity source bridge already validates CineTwin captures up to 128 MiB;
# applying the generic 64 MiB cap again rejected valid 88 MiB captures.
PROJECT_EVIDENCE_MAX_BYTES = 64 * 1024 * 1024
CINETWIN_CAPTURE_MAX_BYTES = 128 * 1024 * 1024


class TransferAIError(ValueError):
    pass


def _read(path: Path, *, kind: str = "project evidence") -> dict[str, Any]:
    limit = (
        CINETWIN_CAPTURE_MAX_BYTES if kind == "CineTwin capture"
        else PROJECT_EVIDENCE_MAX_BYTES
    )
    if path.is_symlink() or not path.is_file():
        raise TransferAIError(
            f"{kind} is missing or unsafe; verify the selected project's evidence export."
        )
    if path.stat().st_size > limit:
        raise TransferAIError(
            f"{kind} exceeds the {limit // (1024 * 1024)} MiB evidence limit. "
            "The source file was not modified; use a supported fresh export "
            "rather than truncating animation evidence."
        )
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise TransferAIError(f"Malformed {kind} JSON evidence.")
    return result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_summary(path: Path) -> dict:
    data = _read(path)
    plugins = [row for row in data.get("Plugins", [])
               if isinstance(row, dict) and row.get("Enabled") is True]
    return {
        "engine_association": _version(data.get("EngineAssociation")),
        "enabled_plugin_count": len(plugins),
        "has_enabled_plugins": bool(plugins),
    }


def _version(value) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"\d{1,4}(?:\.\d{1,4}){1,3}(?:[a-z]\d{1,5})?", value) else "unknown"


def character_policy():
    for part in ("packages/studio", "packages/cinetwin", "integrations/unreal"):
        path = str(ROOT / part)
        if path not in sys.path:
            sys.path.insert(0, path)
    import animation_conversion_policy
    return animation_conversion_policy


def target_probe(config: dict, worker: dict, workspace: Path, run_id: str, *, write=None) -> tuple[bool, dict | None]:
    """Request the native snapshot using installed code and exact mapped assets."""
    if (not config.get("unity_project") or not worker.get("connected")
            or (worker.get("scene_inventory") or {}).get("character_compatibility_probe") is not True):
        return False, None
    policy = character_policy()
    request = policy.make_probe_request(config, _read(Path(config["csir"])), _read(Path(config["mapping"])), run_id=run_id)
    if request is None:
        return False, None
    path = workspace / policy.PROBE_REQUEST
    if write is not None and (not path.is_file() or _read(path) != request):
        write(path, request)
    result_path = workspace / policy.PROBE_RESULT
    if not result_path.is_file():
        return True, None
    result = _read(result_path)
    if result.get("request_sha256") != policy.compatibility.digest(request):
        return True, None
    if result.get("error"):
        raise TransferAIError("Native character inspection failed: " + result["error"])
    identity = result.get("observed_identity", {})
    if identity.get("level") != worker.get("level") or identity.get("editor_pid") != worker.get("editor_pid"):
        return True, None
    return True, result


def _activation_eligible(csir: dict, mapping: dict) -> bool:
    """Eligibility is proven by the installed adapter, never by the LLM."""
    if not any(t.get("ced_type") == "event.state" and
               t.get("muted") is not True for t in csir.get("tracks", [])
               if isinstance(t, dict)):
        return False
    import sys
    root = Path(__file__).resolve().parents[1]
    studio = str(root / "packages" / "studio")
    unreal = str(root / "integrations" / "unreal")
    for directory in (studio, unreal):
        if directory not in sys.path:
            sys.path.insert(0, directory)
    import visual_activation
    for track in csir.get("tracks", []):
        if (not isinstance(track, dict) or track.get("muted") is True
                or track.get("ced_type") != "event.state"):
            continue
        try:
            visual_activation.build_action(csir, mapping, track)
        except (ValueError, KeyError, TypeError):
            return False
    return True


def inspect(config: dict, census_path: str, worker: dict, *, native_character_probe: dict | None = None) -> dict:
    """Native file metadata and exact transfer connection; no model calls."""
    if (worker.get("connected") is not True
            or not isinstance(worker.get("project"), str)
            or os.path.normcase(str(Path(worker["project"]).resolve())) !=
            os.path.normcase(str(Path(config["target_project"]).resolve()))
            or (not config.get("auto_create_level") and
                worker.get("level") != config["level_path"])):
        raise TransferAIError("Unreal Editor is not connected to the selected target project/level.")
    inventory = worker.get("scene_inventory")
    if (not isinstance(inventory, dict) or inventory.get("available") is not True
            or type(inventory.get("actor_count")) is not int
            or inventory["actor_count"] < 0
            or not isinstance(inventory.get("class_counts"), dict)):
        raise TransferAIError(
            "Unreal native level inventory is missing. Restart Unreal Editor "
            "and load the updated CutSceneAI worker before AI conversion."
        )
    native_capabilities = inventory.get("native_capabilities")
    supported_caps = (
        "fbx_asset_import", "sequencer_visibility_track",
        "sequencer_skeletal_animation_track", "cine_camera_actor",
    )
    if (not isinstance(native_capabilities, dict)
            or any(type(native_capabilities.get(key)) is not bool
                   for key in supported_caps)):
        raise TransferAIError(
            "Unreal target capability probe is incomplete. Restart the updated editor worker."
        )
    safe_classes = {}
    public_native_classes = {"Actor", "SkeletalMeshActor", "StaticMeshActor", "CineCameraActor", "CameraActor",
                             "DirectionalLight", "PointLight", "SpotLight", "SkyLight", "LevelSequenceActor",
                             "PlayerStart", "WorldSettings", "Brush", "ExponentialHeightFog", "SkyAtmosphere"}
    for name, count in sorted(inventory["class_counts"].items())[:24]:
        if (not isinstance(name, str) or len(name) > 72
                or not name.replace("_", "").isalnum()
                or type(count) is not int or count < 0):
            raise TransferAIError("Unreal level inventory contains invalid native class counts.")
        key = name if name in public_native_classes else "Other"
        safe_classes[key] = safe_classes.get(key, 0) + count
    source = Path(config["csir"]).resolve()
    capture = Path(config["capture"]).resolve()
    mapping = Path(config["mapping"]).resolve()
    target = Path(config["target_project"]).resolve()
    census = Path(census_path).resolve()
    docs = {key: _read(path, kind=label) for key, path, label in (
        ("csir", source, "Unity CSIR"),
        ("capture", capture, "CineTwin capture"),
        ("mapping", mapping, "Target mapping"),
        ("census", census, "Unity source census"),
    )}
    csir, scene_mapping = docs["csir"], docs["mapping"]
    if (csir.get("source", {}).get("engine") != "unity"
            or csir.get("schema_version") != "0.1.0"
            or docs["capture"].get("cutscene_id") != csir.get("cutscene_id")
            or docs["capture"].get("kind") != "cinetwin.behavior_capture"):
        raise TransferAIError("Source capture and Unity export identity do not match.")
    # The existing source census verifier runs before this step in the
    # autopilot and again at candidate preparation. Its raw data never goes
    # to the model; only bounded counts and types.
    census_obj = docs["census"]
    tracks = csir.get("tracks")
    entities = csir.get("entities")
    if not isinstance(tracks, list) or not isinstance(entities, list):
        raise TransferAIError("Malformed Unity cutscene track/entity inventory.")
    # Treat Unity names and extension types as untrusted metadata. Do not
    # send arbitrary strings or asset paths to the external reasoning model.
    known_types = {"animation.track", "camera.transform", "camera.cut", "audio.track", "light.animation",
                   "event.state", "event.signal", "event.trigger", "timeline.marker", "timeline.opaque"}
    types = Counter(t.get("ced_type") if t.get("ced_type") in known_types else "other"
                    for t in tracks if isinstance(t, dict))
    materials = sum(len((e.get("metadata") or {}).get("source_material_assets") or [])
                    for e in entities if isinstance(e, dict))
    models = sum(len((e.get("metadata") or {}).get("source_model_assets") or [])
                 for e in entities if isinstance(e, dict))
    eligible = (
        native_capabilities["sequencer_visibility_track"]
        and _activation_eligible(csir, scene_mapping)
    )
    if models and not native_capabilities["fbx_asset_import"]:
        raise TransferAIError(
            "Unreal FBX import capability is unavailable; cannot plan sourced 3D meshes."
        )
    fingerprints = {key: _sha(p) for key, p in (
        ("csir", source), ("capture", capture), ("mapping", mapping), ("census", census), ("uproject", target)
    )}
    evidence = {
        "kind": "cutsceneai.studio.ai_conversion_evidence",
        "schema_version": VERSION,
        "fingerprints": fingerprints,
        "selected_target_level": config["level_path"],
        "target_project": str(target),
        "summary": {
            "source_engine": "unity",
            "source_version": _version(csir.get("source", {}).get("engine_version")),
            "source_entity_count": len(entities),
            "source_track_count": len(tracks),
            "source_track_types": dict(sorted(types.items())[:30]),
            "source_model_reference_count": models,
            "source_material_reference_count": materials,
            "source_capture_sample_count": len(docs["capture"].get("samples") or []),
            "source_census_present": bool(census_obj),
            "target_engine": "unreal",
            "target_connected": True,
            "target_worker_version": (worker["worker_version"] if isinstance(worker.get("worker_version"), str)
                                      and re.fullmatch(r"studio-editor-v\d{1,3}\.\d{1,3}", worker["worker_version"])
                                      else "unknown"),
            "target_project_metadata": _project_summary(target),
            "target_level_selected": True,
            "target_level_actor_count": inventory["actor_count"],
            "target_level_actor_class_counts": safe_classes,
            "target_level_inventory_partial": bool(inventory.get("truncated")),
            "target_native_capabilities": {
                key: native_capabilities[key] for key in supported_caps
            },
            "target_new_level_planned": bool(config.get("auto_create_level")),
            "safe_partial_visibility_adapter_available": eligible,
        },
        "allowed_strategies": (["native_source", "source_materials"] +
                               (["visual_activation_partial"] if eligible else [])),
        "fidelity_verified": False,
    }
    if config.get("unity_project") and any(entity.get("ced_type") == "entity.character" for entity in entities):
        policy = character_policy()
        if native_character_probe is not None:
            observed = native_character_probe.get("observed_identity") or {}
            if (observed.get("editor_pid") != worker.get("editor_pid")
                    or observed.get("project") != worker.get("project")
                    or observed.get("level") != worker.get("level")):
                raise TransferAIError("Character probe belongs to another native worker, project or map.")
        report = policy.compatibility.inspect(config, csir, docs["capture"], scene_mapping, fingerprints, native_character_probe)
        evidence["character_compatibility"] = report
        evidence["summary"]["character_compatibility"] = policy.report_for_model(report)
        evidence["animation_choices"] = policy.available_choices(report)
    knowledge = _agent_module("ced_agent_knowledge").retrieve_all(
        csir, target_capabilities=native_capabilities,
        source_version=str(csir.get("source", {}).get("engine_version") or ""),
        target_version=str(worker.get("engine_version") or ""),
        approved_store=Path.home() / ".cutsceneai-studio" / "ced-knowledge",
        case_store=Path.home() / ".cutsceneai-studio" / "ced-cases",
        feedback_store=Path.home() / ".cutsceneai-studio" / "ced-experiences.jsonl",
    )
    evidence["ced_knowledge"] = knowledge
    # Every extracted CSIR occurrence is independently inventoried before
    # any agent call. This is advisory and never overrides the native compiler.
    evidence["element_plan"] = _agent_module("studio_element_plan").prepare(
        csir, knowledge, native_capabilities,
    )
    # The dependency graph is derived from the same source-bound plan and is
    # informational only. It does not reorder or authorize native builder calls.
    evidence["element_schedule"] = _agent_module("studio_element_schedule").build(
        evidence["element_plan"], csir,
    )
    # Element 3.3 uses the existing CED ranking and native source branch,
    # but comparisons never grant native actions or fidelity claims.
    evidence["element_strategy"] = _agent_module("studio_element_strategy").build(
        evidence["element_plan"], evidence["element_schedule"],
        knowledge, csir, native_capabilities,
    )
    # Complete, read-only per-occurrence investigation inventory. Existing
    # preflight discovery registry remains the only registry for novel cases.
    evidence["element_investigation"] = _agent_module(
        "studio_element_investigation"
    ).build(
        evidence["element_plan"], evidence["element_schedule"],
        evidence["element_strategy"], knowledge, csir, native_capabilities,
    )
    return evidence


def _agent_module(name: str):
    location = str(ROOT / "packages" / "studio")
    if location not in sys.path:
        sys.path.insert(0, location)
    return __import__(name)


def _model_choose(summary: dict) -> dict:
    """Model reasoning with retrieved CED semantics, no raw source files."""
    provider = _agent_module("studio_model_provider")
    properties = {"strategy": {"type": "string", "enum": summary["allowed_strategies"]},
                  "reason": {"type": "string"}}
    if summary.get("animation_choices"):
        properties["animation_choice_id"] = {
            "type": "string",
            "enum": ["keep_native", *summary["animation_choices"]],
        }
    public_knowledge = _agent_module("ced_agent_knowledge").model_projection(
        summary["ced_knowledge"]
    )
    if public_knowledge.get("retrieval_complete") is not True:
        raise TransferAIError("Incomplete CED page coverage cannot be accepted by the agent.")
    entries = public_knowledge.get("entries")
    if not isinstance(entries, list) or len(entries) != public_knowledge["source_ced_count"]:
        raise TransferAIError("CED knowledge has missing source concepts.")
    # Large source inventories are reviewed by the model in separate bounded
    # batches, not silently trimmed to the first 48 concepts.
    PAGE_SIZE = 24
    page_notes = []
    for index in range(0, len(entries), PAGE_SIZE):
        if len(entries) <= PAGE_SIZE:
            break
        page_index = index // PAGE_SIZE
        batch = entries[index:index + PAGE_SIZE]
        observation = provider.complete_json(
            task="cutsceneai_ced_page_review",
            instructions=(
                "You are CutSceneAI's read-only knowledge investigator. "
                "For the supplied CED concept batch, identify native "
                "capability gaps, semantic dependencies, and promising "
                "installed conversion approaches. Unknown mappings are "
                "investigation cases, not successful conversions. "
                "Use only given facts, no project names or code execution. "
                "Reply with JSON using the exact schema."
            ),
            payload={
                "page_index": page_index,
                "source_concepts": batch,
                "allowed_strategies": summary["allowed_strategies"],
            },
            schema={
                "type": "object", "additionalProperties": False,
                "properties": {
                    "page_index": {"type": "integer"},
                    "risks": {"type": "string"},
                    "candidate_approaches": {"type": "string"},
                },
                "required": ["page_index", "risks", "candidate_approaches"],
            },
        ).answer
        if (type(observation.get("page_index")) is not int
                or observation["page_index"] != page_index
                or not all(isinstance(observation.get(key), str)
                           and len(observation[key]) <= 750
                           for key in ("risks", "candidate_approaches"))):
            raise TransferAIError("AI returned an ungrounded CED page review.")
        page_notes.append(observation)
    if page_notes:
        model_knowledge = {
            "kind": public_knowledge["kind"],
            "schema_version": public_knowledge["schema_version"],
            "source_ced_count": len(entries),
            "source_occurrence_count": public_knowledge["source_occurrence_count"],
            "coverage_ledger_sha256": public_knowledge["coverage_ledger_sha256"],
            "knowledge_sha256": public_knowledge["knowledge_sha256"],
            "pages_reviewed": len(page_notes),
            "expected_pages": (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE,
            "page_analyses": page_notes,
            "native_write_permission": False,
        }
    else:
        model_knowledge = public_knowledge
    response = provider.complete_json(
        task="cutsceneai_pretransfer_choice",
        instructions=(
            "You are CutSceneAI's conversion agent. Use the verified, redacted "
            "Unity/Unreal capability evidence and the dynamically retrieved "
            "CED knowledge. CED rule candidates grant NO execution permission. "
            "Choose a registered native strategy, not a benchmark-specific "
            "assumption. native_source uses the existing source-backed planner. "
            "source_materials enables the registered FBX material importer. "
            "visual_activation_partial is a deliberately lossy visibility "
            "approximation and only eligible when registered and validated; it "
            "does not replicate GameObject activation, scripts or physics. "
            "Choose an animation_choice_id only for an independently validated "
            "rig/motion action; otherwise keep_native. The approved in-place "
            "IK action needs true in-place motion. The actor-world trajectory "
            "action bake_verified_actor_world_trajectory needs a source-backed "
            "actor-relative root and frame-matched translation/rotation. "
            "Explore missing mapping "
            "candidates in the evidence but never invent commands, classes, "
            "asset paths, adapters or fidelity claims. Return only JSON."
        ),
        payload={
            "evidence": summary["summary"],
            "allowed_strategies": summary["allowed_strategies"],
            "animation_choices": summary.get("animation_choices", []),
            "ced_knowledge": model_knowledge,
            "planning_feedback": summary.get("planning_feedback", ""),
        },
        schema={
            "type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties),
        },
    )
    answer = dict(response.answer)
    answer["_provider_name"] = response.provider
    answer["_provider_model"] = response.model
    answer["_provider_response_sha256"] = response.response_sha256
    if response.response_id:
        answer["_provider_response_id"] = response.response_id
    return answer

def decide(config: dict, census_path: str, worker: dict,
           *, reasoner: Callable[[dict], dict] | None = None, native_character_probe: dict | None = None) -> dict:
    evidence = inspect(config, census_path, worker, native_character_probe=native_character_probe)
    try:
        # LangGraph owns evidence grounding, alternative-model proposals,
        # registered-strategy validation, and a bounded planning retry loop.
        graph = _agent_module("studio_conversion_graph")
        answer = graph.select(
            evidence, reasoner=reasoner or _model_choose,
            attempts=1 if reasoner is not None else 2,
        )
    except Exception as exc:
        raise TransferAIError("Pre-transfer AI reasoning failed: " + str(exc)[:500]) from exc
    strategy = answer["strategy"]
    summary = evidence["summary"]
    element_planner = _agent_module("studio_element_plan")
    element_plan = evidence["element_plan"]
    element_response_hashes = []
    # Phase 3.1 rollout: the full source inventory and immutable safety
    # contract run for everyone. Per-occurrence additional model invocations
    # are explicitly opt-in until multi-element cost/latency UX is accepted.
    planning_mode = os.environ.get("CUTSCENEAI_ELEMENT_PLANNING", "inventory")
    if planning_mode not in {"inventory", "model"}:
        raise TransferAIError("Invalid CUTSCENEAI_ELEMENT_PLANNING setting.")
    if reasoner is None and planning_mode == "model":
        # Large scenes save every independently validated redacted model page.
        # A bounded interrupted run is resumable, but NEVER a native approval.
        try:
            provider = _agent_module("studio_model_provider")
            large = element_plan["source_occurrence_count"] > 256
            checkpoint_path = None
            model_identity = "unspecified"
            page_budget = None
            if large:
                provider_name = provider.provider_name()
                # Bind durable pages to the source/knowledge/capability snapshot,
                # ranked options and selected provider/model, not only source IDs.
                model_identity = hashlib.sha256((
                    provider_name + "/" + provider._model_name(provider_name) +
                    "/" + evidence["element_strategy"]["comparison_sha256"]
                ).encode("utf-8")).hexdigest()
                checkpoint_path = (
                    Path.home() / ".cutsceneai-studio" / "element-reviews" /
                    (element_plan["element_plan_sha256"] + ".json")
                )
                raw_limit = os.environ.get("CUTSCENEAI_ELEMENT_REVIEW_MAX_NEW_PAGES", "32")
                if not re.fullmatch(r"[1-9][0-9]{0,3}", raw_limit):
                    raise TransferAIError("Invalid per-run model review page budget.")
                page_budget = int(raw_limit)
            blocking_statuses = {
                "SOURCE_DEPENDENCY_MISSING", "DEPENDENCY_CYCLE",
                "UPSTREAM_BLOCKED", "OWNERSHIP_CONFLICT",
            }
            blockers = {
                row["occurrence_id"]: row["status"]
                for row in evidence["element_schedule"]["nodes"]
                if row["status"] in blocking_statuses
            }
            element_plan, element_response_hashes = element_planner.review_with_model(
                element_plan, provider=provider, checkpoint_path=checkpoint_path,
                model_identity=model_identity, max_new_pages=page_budget,
                blocked_occurrences=blockers,
                strategy_hints=_agent_module(
                    "studio_element_strategy"
                ).proposal_hints(evidence["element_strategy"]),
            )
        except Exception as exc:
            raise TransferAIError(
                "Per-element AI planning failed before native execution: "
                + str(exc)[:400]
            ) from exc
    source_csir = _read(Path(config["csir"]))
    element_planner.verify(
        element_plan, source_csir,
        evidence["ced_knowledge"],
        evidence["summary"]["target_native_capabilities"],
    )
    element_schedule = _agent_module("studio_element_schedule").build(
        element_plan, source_csir,
    )
    element_strategy = _agent_module("studio_element_strategy").build(
        element_plan, element_schedule, evidence["ced_knowledge"], source_csir,
        evidence["summary"]["target_native_capabilities"],
    )
    investigator = _agent_module("studio_element_investigation")
    element_investigation = investigator.build(
        element_plan, element_schedule, element_strategy,
        evidence["ced_knowledge"], source_csir,
        evidence["summary"]["target_native_capabilities"],
    )
    # Element 4: independently validate the WHOLE selected source graph,
    # including native-route eligibility, ownership and selected dependencies.
    # An invalid global combination is not a source-bound conversion plan.
    gate_module = _agent_module("studio_element4_validation")
    gate = gate_module.build(
        element_plan, element_schedule, element_strategy,
        element_investigation, evidence["ced_knowledge"], source_csir,
        evidence["summary"]["target_native_capabilities"],
        global_strategy=strategy, allowed_strategies=evidence["allowed_strategies"],
    )
    alternative_audit = []
    if not gate["accepted_for_source_bound_plan"]:
        if reasoner is not None or planning_mode != "model":
            raise TransferAIError(
                "Element 4 rejected the selected source graph; "
                "enable bounded per-element model review or report the limitation."
            )
        try:
            provider = _agent_module("studio_model_provider")
            (element_plan, element_schedule, element_strategy,
             element_investigation, gate, alternative_audit) = (
                gate_module.reason_bounded(
                    element_plan, evidence["ced_knowledge"], source_csir,
                    evidence["summary"]["target_native_capabilities"],
                    global_strategy=strategy,
                    allowed_strategies=evidence["allowed_strategies"],
                    provider=provider,
                )
            )
        except gate_module.StrategyValidationError as exc:
            raise TransferAIError(
                "Element 4 bounded alternative reasoning failed before "
                "native preparation: " + str(exc)[:350]
            ) from exc
    if not gate["accepted_for_source_bound_plan"]:
        raise TransferAIError("Element 4 refused an unvalidated source-bound strategy.")
    investigation_hashes = []
    investigation_mode = os.environ.get(
        "CUTSCENEAI_ELEMENT_INVESTIGATION", "inventory"
    )
    if investigation_mode not in {"inventory", "model"}:
        raise TransferAIError("Invalid CUTSCENEAI_ELEMENT_INVESTIGATION setting.")
    if reasoner is None and investigation_mode == "model":
        try:
            provider = _agent_module("studio_model_provider")
            case_count = sum(bool(r["available_investigation_steps"])
                             for r in element_investigation["findings"])
            large = case_count > 256
            checkpoint_path = None
            model_identity = "unspecified"
            page_budget = None
            if large:
                provider_name = provider.provider_name()
                model_identity = hashlib.sha256((
                    provider_name + "/" + provider._model_name(provider_name)
                    + "/" + element_investigation["investigation_sha256"]
                ).encode("utf-8")).hexdigest()
                checkpoint_path = (
                    Path.home() / ".cutsceneai-studio" / "element-investigations" /
                    (element_investigation["investigation_sha256"] + ".json")
                )
                raw_limit = os.environ.get(
                    "CUTSCENEAI_ELEMENT_INVESTIGATION_MAX_NEW_PAGES", "32"
                )
                if not re.fullmatch(r"[1-9][0-9]{0,3}", raw_limit):
                    raise TransferAIError("Invalid per-run investigation model page budget.")
                page_budget = int(raw_limit)
            element_investigation, investigation_hashes = investigator.review_with_model(
                element_investigation, plan=element_plan,
                schedule=element_schedule, strategy=element_strategy,
                knowledge=evidence["ced_knowledge"], csir=source_csir,
                target_capabilities=evidence["summary"]["target_native_capabilities"],
                provider=provider, checkpoint_path=checkpoint_path,
                model_identity=model_identity, max_new_pages=page_budget,
            )
        except Exception as exc:
            raise TransferAIError(
                "Read-only element investigation failed before native execution: "
                + str(exc)[:400]
            ) from exc
    investigator.verify(
        element_investigation, element_plan, element_schedule, element_strategy,
        evidence["ced_knowledge"], source_csir,
        evidence["summary"]["target_native_capabilities"],
    )
    # Investigation model choices are already independently verified here.
    # Recreate the Element 4 gate with the final investigation digest.
    gate = gate_module.build(
        element_plan, element_schedule, element_strategy,
        element_investigation, evidence["ced_knowledge"], source_csir,
        evidence["summary"]["target_native_capabilities"],
        global_strategy=strategy, allowed_strategies=evidence["allowed_strategies"],
    )
    if not gate["accepted_for_source_bound_plan"]:
        raise TransferAIError("Element 4 final source strategy is no longer valid.")
    # Never let model preference disable the existing source-material import
    # guarantee when provenance documents source materials. This policy is a
    # deterministic safety floor, not an LLM decision.
    need_materials = summary["source_material_reference_count"] > 0
    enable_materials = need_materials or strategy == "source_materials"
    options: dict[str, bool] = {
        "enable_fbx_embedded_material_import": bool(enable_materials),
        "enable_actor_visibility_fallback": strategy == "visual_activation_partial",
    }
    decision = {
        "kind": SCHEMA, "schema_version": VERSION, "strategy": strategy,
        "reason": str(answer.get("reason") or "")[:600],
        "input_sha256": evidence["fingerprints"],
        "summary": summary, "allowed_strategies": evidence["allowed_strategies"],
        "conversion_options": options,
        "ced_knowledge_sha256": evidence["ced_knowledge"]["knowledge_sha256"],
        "ced_retrieved_concepts": evidence["ced_knowledge"]["retrieved_count"],
        "element_plan": element_plan,
        "element_plan_sha256": element_plan["element_plan_sha256"],
        "element_schedule": element_schedule,
        "element_schedule_sha256": element_schedule["schedule_sha256"],
        "element_scheduling_advisory_only": True,
        "element_strategy": element_strategy,
        "element_strategy_sha256": element_strategy["comparison_sha256"],
        "element_strategy_advisory_only": True,
        "element_investigation": element_investigation,
        "element_investigation_sha256": element_investigation["investigation_sha256"],
        "element_investigation_advisory_only": True,
        "element4_validation": gate,
        "element4_validation_sha256": gate["validation_sha256"],
        "element4_validation_advisory_only": True,
        "element4_alternative_reasoning_audit": alternative_audit,
        "element4_alternative_reasoning_limit": gate_module.MAX_REASONING_ROUNDS,
        "element_investigation_model_reviewed_count": element_investigation[
            "model_reviewed_count"],
        "element_investigation_model_response_sha256s": investigation_hashes,
        "element_investigation_mode": (
            "MODEL_REVIEWED" if investigation_hashes else "INVENTORY_ONLY"
        ),
        "element_model_reviewed_count": element_plan["model_reviewed_count"],
        "element_model_response_sha256s": element_response_hashes,
        "element_planning_mode": (
            "MODEL_REVIEWED" if element_response_hashes else "INVENTORY_ONLY"
        ),
        "element_decisions_advisory_only": True,
        "model_invoked": True,
        "model_provider": (answer.get("_provider_name") or "INJECTED_REASONER")
        if reasoner is None else "INJECTED_REASONER",
        "native_conversion_executed": False,
        "source_and_target_fidelity_verified": False,
        "activation_semantics_partial": options["enable_actor_visibility_fallback"],
    }
    if reasoner is None:
        model = answer.get("_provider_model")
        digest = answer.get("_provider_response_sha256")
        if (isinstance(model, str) and model
                and isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest)):
            decision["model_name"] = model
            decision["model_response_sha256"] = digest
        provider_id = answer.get("_provider_response_id")
        if (decision["model_provider"] == "OPENAI_RESPONSES"
                and isinstance(provider_id, str)
                and re.fullmatch(r"resp_[A-Za-z0-9_]{1,120}", provider_id)):
            decision["model_response_id"] = provider_id
    report = evidence.get("character_compatibility")
    choice = answer.get("animation_choice_id", "keep_native")
    if choice != "keep_native":
        if choice not in evidence.get("animation_choices", []):
            raise TransferAIError("AI selected an animation action without eligible source and target evidence.")
        decision["animation_conversion"] = character_policy().decision_for(report, choice)
    if report is not None:
        try:
            character_policy().require_motion_choice(report, decision.get("animation_conversion"))
        except ValueError as exc:
            raise TransferAIError(str(exc)) from exc
        decision["character_compatibility_sha256"] = character_policy().compatibility.digest(report)
        decision["character_compatibility"] = report
    return decision


def verify(decision: dict, config: dict, census_path: str, worker: dict, *, native_character_probe: dict | None = None) -> dict:
    """Recompute all input hashes and safe actions immediately before prepare."""
    current = inspect(config, census_path, worker, native_character_probe=native_character_probe)
    if (decision.get("kind") != SCHEMA
            or decision.get("schema_version") != VERSION
            or decision.get("input_sha256") != current["fingerprints"]
            or decision.get("strategy") not in current["allowed_strategies"]
            or decision.get("ced_knowledge_sha256") !=
            current["ced_knowledge"]["knowledge_sha256"]):
        raise TransferAIError(
            "AI decision or CED knowledge is stale or belongs to another source/target."
        )
    strategy = decision["strategy"]
    opts = decision.get("conversion_options")
    expected = {
        "enable_fbx_embedded_material_import": (
            current["summary"]["source_material_reference_count"] > 0
            or strategy == "source_materials"),
        "enable_actor_visibility_fallback":
            strategy == "visual_activation_partial",
    }
    if opts != expected:
        raise TransferAIError("AI conversion options do not match supported native policy.")
    if (decision.get("element_decisions_advisory_only") is not True
            or decision.get("element_plan_sha256") !=
            (decision.get("element_plan") or {}).get("element_plan_sha256")):
        raise TransferAIError("Per-element AI evidence or read-only guard is missing.")
    element_planner = _agent_module("studio_element_plan")
    try:
        element_planner.verify(
            decision["element_plan"], _read(Path(config["csir"])),
            current["ced_knowledge"],
            current["summary"]["target_native_capabilities"],
        )
    except element_planner.ElementPlanError as exc:
        raise TransferAIError("Per-element AI plan is stale or tampered: " + str(exc)) from exc
    schedule = decision.get("element_schedule")
    if (decision.get("element_scheduling_advisory_only") is not True
            or not isinstance(schedule, dict)
            or decision.get("element_schedule_sha256") != schedule.get("schedule_sha256")):
        raise TransferAIError("Dependency schedule evidence or read-only guard is missing.")
    scheduler = _agent_module("studio_element_schedule")
    try:
        scheduler.verify(schedule, decision["element_plan"],
                         _read(Path(config["csir"])))
    except scheduler.ElementScheduleError as exc:
        raise TransferAIError("Dependency schedule is stale or tampered: " + str(exc)) from exc
    comparison = decision.get("element_strategy")
    if (decision.get("element_strategy_advisory_only") is not True
            or not isinstance(comparison, dict)
            or decision.get("element_strategy_sha256") != comparison.get("comparison_sha256")):
        raise TransferAIError("Adaptive element strategy evidence or safety guard is missing.")
    adaptive = _agent_module("studio_element_strategy")
    try:
        adaptive.verify(
            comparison, decision["element_plan"], schedule,
            current["ced_knowledge"], _read(Path(config["csir"])),
            current["summary"]["target_native_capabilities"],
        )
        options_by_id = adaptive.proposal_hints(comparison)
        for row in decision["element_plan"]["elements"]:
            if (row["selected_action"] != "report_only"
                    and row["selected_action"] not in {
                        alt["action"] for alt in options_by_id[
                            row["occurrence_id"]]["alternatives"]
                    }):
                raise adaptive.AdaptiveStrategyError(
                    "AI selected an action excluded by current source-route strategy evidence."
                )
    except adaptive.AdaptiveStrategyError as exc:
        raise TransferAIError("Adaptive element strategy is stale or unsafe: " + str(exc)) from exc
    investigation = decision.get("element_investigation")
    if (decision.get("element_investigation_advisory_only") is not True
            or not isinstance(investigation, dict)
            or decision.get("element_investigation_sha256")
            != investigation.get("investigation_sha256")):
        raise TransferAIError("Source investigation record or read-only guard is missing.")
    investigator = _agent_module("studio_element_investigation")
    try:
        investigator.verify(
            investigation, decision["element_plan"], schedule, comparison,
            current["ced_knowledge"], _read(Path(config["csir"])),
            current["summary"]["target_native_capabilities"],
        )
    except investigator.ElementInvestigationError as exc:
        raise TransferAIError(
            "Source investigation is stale, incomplete or unsafe: " + str(exc)
        ) from exc
    # The gate is a PREPARED STRATEGY decision, never a native runtime
    # assertion. Rebuild all source/knowledge/target/graph facts again.
    gate_module = _agent_module("studio_element4_validation")
    candidate_gate = decision.get("element4_validation")
    if (decision.get("element4_validation_advisory_only") is not True
            or not isinstance(candidate_gate, dict)
            or decision.get("element4_validation_sha256")
            != candidate_gate.get("validation_sha256")):
        raise TransferAIError("Element 4 validation gate provenance is absent.")
    try:
        gate_module.verify(
            candidate_gate, decision["element_plan"], schedule, comparison,
            investigation, current["ced_knowledge"], _read(Path(config["csir"])),
            current["summary"]["target_native_capabilities"],
            global_strategy=decision["strategy"],
            allowed_strategies=current["allowed_strategies"],
        )
        if not candidate_gate["accepted_for_source_bound_plan"]:
            raise gate_module.StrategyValidationError(
                "An unsafe combination of selected source actions cannot proceed."
            )
    except gate_module.StrategyValidationError as exc:
        raise TransferAIError(
            "Element 4 source strategy validation failed: " + str(exc)[:300]
        ) from exc
    reasoning = decision.get("element4_alternative_reasoning_audit")
    if (not isinstance(reasoning, list)
            or len(reasoning) > gate_module.MAX_REASONING_ROUNDS
            or decision.get("element4_alternative_reasoning_limit")
            != gate_module.MAX_REASONING_ROUNDS):
        raise TransferAIError("Element 4 bounded retry provenance is invalid.")
    for round_no, item in enumerate(reasoning, 1):
        if (not isinstance(item, dict)
                or set(item) != {
                    "round", "rejected_count", "validated_replacement_count",
                    "previous_validation_sha256", "new_plan_sha256",
                    "responses", "native_execution_authorized",
                }
                or item["round"] != round_no
                or type(item["rejected_count"]) is not int
                or type(item["validated_replacement_count"]) is not int
                or not 1 <= item["validated_replacement_count"] <= item["rejected_count"]
                or item["rejected_count"] > candidate_gate["source_occurrence_count"]
                or item["native_execution_authorized"] is not False
                or not all(isinstance(item[key], str)
                           and re.fullmatch(r"[a-f0-9]{64}", item[key])
                           for key in ("previous_validation_sha256", "new_plan_sha256"))
                or not isinstance(item["responses"], list)
                or not 1 <= len(item["responses"]) <= (
                    item["rejected_count"] + gate_module.BATCH_SIZE - 1
                ) // gate_module.BATCH_SIZE):
            raise TransferAIError("Element 4 bounded attempt record is invalid.")
        for index, response in enumerate(item["responses"]):
            if (not isinstance(response, dict)
                    or set(response) != {
                        "page_index", "response_sha256", "reviewed_count",
                    }
                    or response["page_index"] != index
                    or type(response["reviewed_count"]) is not int
                    or not 1 <= response["reviewed_count"] <= gate_module.BATCH_SIZE
                    or not isinstance(response["response_sha256"], str)
                    or not re.fullmatch(r"[a-f0-9]{64}", response["response_sha256"])):
                raise TransferAIError("Element 4 alternative page provenance is invalid.")
        if sum(x["reviewed_count"] for x in item["responses"]) != item["rejected_count"]:
            raise TransferAIError("Element 4 alternative model omitted source occurrences.")
    if reasoning and (
            reasoning[-1]["new_plan_sha256"] != candidate_gate["element_plan_sha256"]
            or decision.get("element_planning_mode") != "MODEL_REVIEWED"):
        raise TransferAIError("Element 4 alternatives are not bound to final reviewed plan.")
    investigation_reviewed = investigation["model_reviewed_count"]
    if (decision.get("element_investigation_model_reviewed_count")
            != investigation_reviewed
            or decision.get("element_investigation_mode") != (
                "MODEL_REVIEWED" if investigation_reviewed else "INVENTORY_ONLY"
            )):
        raise TransferAIError("Source investigation model review count is inconsistent.")
    investigation_digests = decision.get("element_investigation_model_response_sha256s")
    eligible_cases = sum(bool(r["available_investigation_steps"])
                         for r in investigation["findings"])
    if (not isinstance(investigation_digests, list)
            or any(not isinstance(d, str)
                   or not re.fullmatch(r"[0-9a-f]{64}", d)
                   for d in investigation_digests)
            or (not investigation_digests and investigation_reviewed != 0)
            or (investigation_digests
                and investigation_reviewed != eligible_cases)
            or (investigation_digests and len(investigation_digests) != (
                eligible_cases + investigator.BATCH_SIZE - 1
            ) // investigator.BATCH_SIZE)):
        raise TransferAIError("Source investigation model provenance is incomplete.")
    reviewed = decision["element_plan"]["model_reviewed_count"]
    if decision.get("element_planning_mode") != (
            "MODEL_REVIEWED" if reviewed else "INVENTORY_ONLY"):
        raise TransferAIError("Element agent mode contradicts verified model evidence.")
    digests = decision.get("element_model_response_sha256s")
    if (decision.get("element_model_reviewed_count") != reviewed
            or not isinstance(digests, list)
            or any(not isinstance(value, str) or
                   not re.fullmatch(r"[0-9a-f]{64}", value) for value in digests)
            or (not digests and reviewed != 0)
            or (digests and reviewed != decision["element_plan"]["source_occurrence_count"])
            or (digests and len(digests) != (
                reviewed + element_planner.MODEL_BATCH_SIZE - 1
            ) // element_planner.MODEL_BATCH_SIZE)):
        raise TransferAIError("Per-element model provenance is missing or incomplete.")
    report = current.get("character_compatibility")
    if report is not None or decision.get("character_compatibility_sha256") or decision.get("animation_conversion"):
        policy = character_policy()
        if report is None or decision.get("character_compatibility_sha256") != policy.compatibility.digest(report):
            raise TransferAIError("The character compatibility report has stale source or target evidence.")
        if decision.get("animation_conversion") is not None:
            policy.selected(report, decision["animation_conversion"])
        try:
            policy.require_motion_choice(report, decision.get("animation_conversion"))
        except ValueError as exc:
            raise TransferAIError(str(exc)) from exc
    return expected
