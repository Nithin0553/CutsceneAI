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
from collections import Counter
from pathlib import Path
from typing import Any, Callable

KINDS = frozenset({"native_source", "source_materials", "visual_activation_partial"})
SCHEMA = "cutsceneai.studio.ai_conversion_decision"
VERSION = "1"


class TransferAIError(ValueError):
    pass


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
        raise TransferAIError("Required local source/target evidence is unavailable.")
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise TransferAIError("Malformed project evidence.")
    return result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_summary(path: Path) -> dict:
    data = _read(path)
    plugins = [row for row in data.get("Plugins", [])
               if isinstance(row, dict) and row.get("Enabled") is True]
    return {
        "engine_association": str(data.get("EngineAssociation") or "")[:40],
        "enabled_plugin_count": len(plugins),
        "has_enabled_plugins": bool(plugins),
    }


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


def inspect(config: dict, census_path: str, worker: dict) -> dict:
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
    safe_classes = {}
    for name, count in sorted(inventory["class_counts"].items())[:24]:
        if (not isinstance(name, str) or len(name) > 72
                or not name.replace("_", "").isalnum()
                or type(count) is not int or count < 0):
            raise TransferAIError("Unreal level inventory contains invalid native class counts.")
        safe_classes[name] = count
    source = Path(config["csir"]).resolve()
    capture = Path(config["capture"]).resolve()
    mapping = Path(config["mapping"]).resolve()
    target = Path(config["target_project"]).resolve()
    census = Path(census_path).resolve()
    docs = {key: _read(path) for key, path in (
        ("csir", source), ("capture", capture), ("mapping", mapping),
        ("census", census)
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
    types = Counter(
        str(t.get("ced_type") or "unknown")[:72]
        for t in tracks if isinstance(t, dict)
    )
    materials = sum(len((e.get("metadata") or {}).get("source_material_assets") or [])
                    for e in entities if isinstance(e, dict))
    models = sum(len((e.get("metadata") or {}).get("source_model_assets") or [])
                 for e in entities if isinstance(e, dict))
    eligible = _activation_eligible(csir, scene_mapping)
    return {
        "kind": "cutsceneai.studio.ai_conversion_evidence",
        "schema_version": VERSION,
        "fingerprints": {key: _sha(p) for key, p in (
            ("csir", source), ("capture", capture),
            ("mapping", mapping), ("census", census), ("uproject", target)
        )},
        "selected_target_level": config["level_path"],
        "target_project": str(target),
        "summary": {
            "source_engine": "unity",
            "source_version": str(csir.get("source", {}).get("engine_version") or "unknown")[:50],
            "source_entity_count": len(entities),
            "source_track_count": len(tracks),
            "source_track_types": dict(sorted(types.items())[:30]),
            "source_model_reference_count": models,
            "source_material_reference_count": materials,
            "source_capture_sample_count": len(docs["capture"].get("samples") or []),
            "source_census_present": bool(census_obj),
            "target_engine": "unreal",
            "target_connected": True,
            "target_worker_version": str(worker.get("worker_version") or "")[:50],
            "target_project_metadata": _project_summary(target),
            "target_level_selected": True,
            "target_level_actor_count": inventory["actor_count"],
            "target_level_actor_class_counts": safe_classes,
            "target_level_inventory_partial": bool(inventory.get("truncated")),
            "target_new_level_planned": bool(config.get("auto_create_level")),
            "safe_partial_visibility_adapter_available": eligible,
        },
        "allowed_strategies": (["native_source", "source_materials"] +
                               (["visual_activation_partial"] if eligible else [])),
        "fidelity_verified": False,
    }


def _model_choose(summary: dict) -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        raise TransferAIError("AI transfer requires OPENAI_API_KEY in the Studio server process.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise TransferAIError("Install the openai package in the Studio Python environment.") from exc
    response = OpenAI(timeout=25, max_retries=0).responses.create(
        model=os.environ.get("CUTSCENEAI_AGENT_MODEL", "gpt-5-mini"),
        instructions=(
            "You are CutSceneAI's pre-conversion planning model. Analyze ONLY the "
            "redacted Unity and Unreal evidence. Choose ONE registered native "
            "conversion policy. 'native_source' preserves the existing safe "
            "planner defaults. 'source_materials' requests the built-in embedded "
            "FBX material importer. 'visual_activation_partial' requests the "
            "explicitly lossy Unity ActivationTrack to Unreal visibility adapter; "
            "it does NOT reproduce scripts, physics, or activation semantics. "
            "Use partial activation ONLY if the provided installed adapter is "
            "eligible; otherwise prefer source_materials for material references "
            "and native_source for remaining scenes. Never invent mappings, "
            "engine commands, new adapters, paths, imports or fidelity claims."
        ),
        input=json.dumps({
            "evidence": summary["summary"],
            "allowed_strategies": summary["allowed_strategies"],
        }, sort_keys=True)[:12000],
        text={"format": {"type": "json_schema",
                         "name": "cutsceneai_pretransfer_choice", "strict": True,
                         "schema": {
                             "type": "object", "additionalProperties": False,
                             "properties": {
                                 "strategy": {"type": "string", "enum": sorted(KINDS)},
                                 "reason": {"type": "string"}
                             },
                             "required": ["strategy", "reason"]
                         }}},
    )
    answer = json.loads(response.output_text)
    return answer


def decide(config: dict, census_path: str, worker: dict,
           *, reasoner: Callable[[dict], dict] | None = None) -> dict:
    evidence = inspect(config, census_path, worker)
    try:
        answer = (reasoner or _model_choose)(evidence)
    except Exception as exc:
        raise TransferAIError("Pre-transfer AI reasoning failed: " + str(exc)[:400]) from exc
    if not isinstance(answer, dict) or answer.get("strategy") not in KINDS:
        raise TransferAIError("AI returned an unregistered conversion strategy.")
    strategy = answer["strategy"]
    if strategy not in evidence["allowed_strategies"]:
        raise TransferAIError("AI selected a strategy not supported by the Unity source.")
    summary = evidence["summary"]
    # Never let model preference disable the existing source-material import
    # guarantee when provenance documents source materials. This policy is a
    # deterministic safety floor, not an LLM decision.
    need_materials = summary["source_material_reference_count"] > 0
    enable_materials = need_materials or strategy == "source_materials"
    options: dict[str, bool] = {
        "enable_fbx_embedded_material_import": bool(enable_materials),
        "enable_actor_visibility_fallback": strategy == "visual_activation_partial",
    }
    return {
        "kind": SCHEMA, "schema_version": VERSION, "strategy": strategy,
        "reason": str(answer.get("reason") or "")[:600],
        "input_sha256": evidence["fingerprints"],
        "summary": summary, "allowed_strategies": evidence["allowed_strategies"],
        "conversion_options": options,
        "model_invoked": True, "native_conversion_executed": False,
        "source_and_target_fidelity_verified": False,
        "activation_semantics_partial": options["enable_actor_visibility_fallback"],
    }


def verify(decision: dict, config: dict, census_path: str, worker: dict) -> dict:
    """Recompute all input hashes and safe actions immediately before prepare."""
    current = inspect(config, census_path, worker)
    if (decision.get("kind") != SCHEMA
            or decision.get("schema_version") != VERSION
            or decision.get("input_sha256") != current["fingerprints"]
            or decision.get("strategy") not in current["allowed_strategies"]):
        raise TransferAIError("AI decision is stale or belongs to another source/target.")
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
    return expected
