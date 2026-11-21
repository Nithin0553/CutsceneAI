"""Unified, versioned CED hybrid knowledge retrieval.

Shared checked-in taxonomy/rules are read-only. Independently approved local
rules and reviewed local cases are private overlays, not global trust. All
outputs are advisory; native tools and fidelity gates decide executability.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from semantic_graph import SemanticGraphError, analyze
from strategy_recipes import StrategyRecipeError, from_rule as recipe_from_rule

PACKAGES = Path(__file__).resolve().parents[1]
DICTIONARY = PACKAGES / "contracts" / "dictionary"
MAX_PAGE_SIZE = 48
MAX_CONCEPTS = 1024
MAX_RULES_PER_CONCEPT = 4
MAX_RESPONSE_RELATIONS = 10
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}\Z")


class KnowledgeServiceError(ValueError):
    """A knowledge input, review, rule or retrieval contract was invalid."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read(path: Path, max_bytes: int = 1024 * 1024) -> dict[str, Any]:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= max_bytes):
        raise KnowledgeServiceError("CED baseline is missing, oversized or symlinked.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise KnowledgeServiceError("CED baseline JSON is invalid.") from exc
    if not isinstance(data, dict):
        raise KnowledgeServiceError("CED baseline must contain JSON objects.")
    return data


def _module(folder: str, name: str):
    location = str(PACKAGES / folder)
    if location not in sys.path:
        sys.path.insert(0, location)
    return __import__(name)


def _baseline() -> tuple[dict[str, Any], set[str], list[dict[str, Any]], dict[str, tuple]]:
    manifest = _read(DICTIONARY / "ced-shared-manifest-v1.json")
    if (manifest.get("kind") != "cutsceneai.ced.shared_baseline_manifest"
            or manifest.get("schema_version") != "1"
            or manifest.get("runtime_execution_authority") is not False
            or manifest.get("distribution") != "GIT_VERSIONED_READ_ONLY_NO_REMOTE_AUTO_UPDATE"):
        raise KnowledgeServiceError("Shared CED baseline trust policy is invalid.")
    # Never read paths supplied by a downloaded manifest. The checked-in
    # allowlist is an explicit implementation trust boundary.
    expected = {
        "taxonomy": "cutscene-elements-v0.2.json",
        "baseline_rules": "adaptive-rules-v0.1.json",
        "rulebook": "ced-mapping-rulebook-v1.json",
    }
    if any(manifest.get(k) != v for k, v in expected.items()):
        raise KnowledgeServiceError("CED baseline manifest attempted to redirect an input.")
    taxonomy = _read(DICTIONARY / expected["taxonomy"])
    baseline = _read(DICTIONARY / expected["baseline_rules"])
    concepts = taxonomy.get("categories")
    rules = baseline.get("rules")
    if (not isinstance(concepts, dict) or not isinstance(rules, list)
            or not all(isinstance(v, list) for v in concepts.values())):
        raise KnowledgeServiceError("Invalid CED taxonomy or registered baseline rules.")
    tokens = {
        item for values in concepts.values() for item in values
        if isinstance(item, str) and _TOKEN.fullmatch(item)
    }
    if len(tokens) < 100:
        raise KnowledgeServiceError("CED taxonomy is incomplete.")
    dispatch = _module("studio", "feature_dispatch")
    return manifest, tokens, rules, dispatch.EXPLICIT_ACTIONS


def _local_rules(store: Path | None) -> list[dict[str, Any]]:
    if store is None:
        return []
    rulebook = _module("readiness", "ced_rulebook")
    # The existing approved-rule loader verifies immutable candidates,
    # reviewed native evidence, held-out gates and adapter compatibility.
    return rulebook.approved_rules(store)


def _private_cases(csir: dict[str, Any], store: Path | None) -> list[dict[str, Any]]:
    if store is None:
        return []
    local = _module("learning", "case_memory")
    suggestions = local.suggest(csir, local.list_cases(store), limit=6)
    # Internal local case summaries can contain user-specific property names.
    # Only safe stable rule metadata is permitted into agent retrieval JSON.
    results = []
    for suggestion in suggestions:
        labels = []
        for value in suggestion.get("candidate_resolutions", []):
            if not isinstance(value, dict):
                continue
            ced, resolver = value.get("ced"), value.get("resolver")
            if (isinstance(ced, str) and _TOKEN.fullmatch(ced)
                    and isinstance(resolver, str) and _TOKEN.fullmatch(resolver)):
                labels.append({"ced": ced, "resolver": resolver,
                               "outcome": str(value.get("outcome") or "")[:32]})
        case_id = suggestion.get("case_id")
        if isinstance(case_id, str) and re.fullmatch(r"[a-f0-9]{24}", case_id):
            results.append({
                "case_id": case_id,
                "similarity": suggestion["similarity"],
                "mapping_labels": labels[:16],
                "scope": "PRIVATE_VERIFIED_MAPPING_ONLY",
                "native_execution_permission": False,
                "cross_project_fidelity_claim": False,
            })
    return results


def _rule_matches(rule: dict[str, Any], ced: str, source_version: str,
                  target_version: str) -> bool:
    if not isinstance(rule, dict) or rule.get("ced") != ced:
        return False
    source, target = rule.get("source"), rule.get("target")
    if not isinstance(source, dict) or not isinstance(target, dict):
        raise KnowledgeServiceError("CED rule has malformed source/target selectors.")
    if source.get("engine") != "unity" or target.get("engine") != "unreal":
        return False
    return not (
        source.get("version_prefix") and
        not source_version.startswith(source["version_prefix"])
        or target.get("version_prefix") and
        not target_version.startswith(target["version_prefix"])
    )


def _rule_summary(rule: dict[str, Any], origin: str, target_caps: set[str],
                  source_caps: set[str] | None) -> dict[str, Any]:
    source, target, res = rule["source"], rule["target"], rule.get("resolution") or {}
    missing_target = sorted(set(target.get("capabilities_all") or ()) - target_caps)
    missing_source = (
        sorted(set(source.get("capabilities_all") or ()) - source_caps)
        if source_caps is not None else []
    )
    status = ("CAPABILITY_EVIDENCE_MISSING"
              if missing_target or missing_source
              else "RULE_CANDIDATE_REQUIRES_PREFLIGHT")
    return {
        "rule_id": rule.get("rule_id"),
        "resolver": res.get("resolver"),
        "outcome": res.get("outcome"),
        "origin": origin,
        "status": status,
        "required_evidence": list(res.get("required_evidence") or [])[:32],
        "parameter_fields": sorted((res.get("parameters") or {}).keys())[:32],
        "capabilities_not_observed": missing_target,
        "source_capabilities_not_observed": missing_source,
        "source_capability_check": ("NOT_INSPECTED" if source_caps is None else "INSPECTED"),
        "registered_adapter_must_preflight": True,
        "verified_for_this_cutscene": False,
    }


def retrieve(
    csir: dict[str, Any], *, target_capabilities: dict[str, Any],
    source_version: str = "", target_version: str = "",
    approved_store: Path | None = None, case_store: Path | None = None,
    source_capabilities: dict[str, Any] | None = None,
    page: int = 0, page_size: int = 48,
) -> dict[str, Any]:
    """Return context-aware, page-addressable, source-bound CED knowledge.

    No silent truncation: every source semantic is in the coverage ledger.
    Detailed rules are page-specific; incomplete paging is explicit and
    must not be treated as complete per-component planning by the caller.
    """
    if (not isinstance(csir, dict) or not isinstance(target_capabilities, dict)
            or (source_capabilities is not None and not isinstance(source_capabilities, dict))
            or type(page) is not int or page < 0
            or type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE):
        raise KnowledgeServiceError("Invalid CED project evidence or retrieval page.")
    if (not isinstance(source_version, str) or not isinstance(target_version, str)
            or len(source_version) > 64 or len(target_version) > 64):
        raise KnowledgeServiceError("Invalid bounded engine-version identifiers.")
    try:
        graph = analyze(csir)
    except SemanticGraphError as exc:
        raise KnowledgeServiceError("Cannot build source semantic knowledge: " + str(exc)) from exc
    if len(graph.counts) > MAX_CONCEPTS:
        raise KnowledgeServiceError("Too many distinct source semantics for bounded retrieval.")
    manifest, known, baseline, actions = _baseline()
    approved = _local_rules(approved_store)
    # Keep the shared and private sources distinct even when a rule ID
    # collides. Approval loaders independently reject conflicting rules.
    rules = [(rule, "BASELINE_REGISTERED_UNVERIFIED") for rule in baseline]
    rules.extend((rule, "LOCAL_REVIEWED_NATIVE_MAPPING") for rule in approved)
    for rule, origin in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("ced"), str):
            raise KnowledgeServiceError("Malformed " + origin + " CED rule.")

    caps = {k for k, v in target_capabilities.items() if isinstance(k, str) and v is True}
    source_caps = (
        {k for k, v in source_capabilities.items() if isinstance(k, str) and v is True}
        if source_capabilities is not None else None
    )
    ordered = sorted(graph.counts.items(), key=lambda pair: (-pair[1], pair[0]))
    page_count = max(1, (len(ordered) + page_size - 1) // page_size)
    if page >= page_count:
        raise KnowledgeServiceError("Requested CED retrieval page does not exist.")
    first, last = page * page_size, (page + 1) * page_size
    entries = []
    for ced, count in ordered[first:last]:
        native = sorted(set(actions.get(ced, ())))
        relations = graph.relations.get(ced, [])
        matches = []
        for rule, origin in rules:
            if not _rule_matches(rule, ced, source_version, target_version):
                continue
            item = _rule_summary(rule, origin, caps, source_caps)
            try:
                recipe = recipe_from_rule(
                    rule, origin=origin,
                    related_semantics=relations[:16], installed_actions=native,
                )
            except StrategyRecipeError as exc:
                raise KnowledgeServiceError(
                    "Installed CED conversion recipe is invalid: " + str(exc)
                ) from exc
            item["strategy_recipe"] = {
                "recipe_id": recipe["recipe_id"],
                "recipe_sha256": recipe["recipe_sha256"],
                "related_concepts": recipe["semantic_ids"][1:],
                "required_native_actions": recipe["alternatives"][0]["required_native_actions"],
                "verification_domains": recipe["alternatives"][0]["verification_domains"],
                "knowledge_status": recipe["provenance"]["status"],
                "runtime_execution_authorized": False,
            }
            matches.append(item)
        matches.sort(key=lambda item: (
            item["status"] != "RULE_CANDIDATE_REQUIRES_PREFLIGHT",
            item["origin"] != "LOCAL_REVIEWED_NATIVE_MAPPING",
            str(item["rule_id"]),
        ))
        entries.append({
            "ced": ced, "source_occurrences": count,
            "semantic_known": ced in known,
            "related_semantics": relations[:MAX_RESPONSE_RELATIONS],
            "related_semantics_omitted_count": max(0, len(relations) - MAX_RESPONSE_RELATIONS),
            "rules": matches[:MAX_RULES_PER_CONCEPT],
            "rules_omitted_count": max(0, len(matches) - MAX_RULES_PER_CONCEPT),
            "native_action_candidates": native[:6],
            "resolution_state": (
                "UNKNOWN_SEMANTIC_INVESTIGATE" if ced not in known else
                "RETRIEVED_CANDIDATES_NEED_NATIVE_PREFLIGHT" if matches or native
                else "KNOWN_SEMANTIC_NO_REGISTERED_MAPPING"
            ),
            "execution_authorized": False,
        })
    private_cases = _private_cases(csir, case_store)
    result = {
        "kind": "cutsceneai.studio.ced_knowledge_retrieval",
        "schema_version": "2",
        "baseline_release_id": manifest["release_id"],
        "baseline_manifest_sha256": _digest(manifest),
        "source_ced_count": len(ordered),
        "source_occurrence_count": graph.occurrence_count,
        "relationship_count": graph.edge_count,
        "unresolved_source_reference_count": graph.unresolved_reference_count,
        "retrieved_count": len(entries),
        "omitted_count": len(ordered) - len(entries),
        "page": page, "page_size": page_size,
        "page_count": page_count,
        "next_page": page + 1 if page + 1 < page_count else None,
        "retrieval_complete": page_count == 1,
        # All concepts are accounted for, even if details require another page.
        "coverage_ledger": [
            {"ced": concept, "source_occurrences": count}
            for concept, count in ordered
        ],
        "coverage_ledger_sha256": _digest(ordered),
        "observed_target_capabilities": sorted(caps)[:64],
        "entries": entries,
        "private_verified_case_suggestions": private_cases,
        "no_native_write_permission": True,
        "shared_promotion_authorized": False,
    }
    result["knowledge_sha256"] = _digest(result)
    return result



def redact_for_model(result: dict[str, Any]) -> dict[str, Any]:
    """Project-local unknown semantics and local review IDs never reach an LLM.

    Local Studio may inspect the full source-bound result, but both local and
    cloud model prompts receive a strictly weaker redacted projection.
    Arbitrary unknown CED names can encode user project/namespace identifiers.
    """
    if (not isinstance(result, dict)
            or result.get("kind") != "cutsceneai.studio.ced_knowledge_retrieval"
            or result.get("no_native_write_permission") is not True
            or not isinstance(result.get("entries"), list)
            or not isinstance(result.get("coverage_ledger"), list)):
        raise KnowledgeServiceError("Model projection requires verified CED retrieval.")
    _, known, baseline, _ = _baseline()
    baseline_ids = {
        rule["rule_id"] for rule in baseline
        if isinstance(rule, dict) and isinstance(rule.get("rule_id"), str)
    }
    baseline_resolvers = {
        rule["resolution"]["resolver"] for rule in baseline
        if (isinstance(rule, dict)
            and isinstance(rule.get("resolution"), dict)
            and isinstance(rule["resolution"].get("resolver"), str))
    }
    known_parameters = {
        key for rule in baseline
        if isinstance(rule, dict)
        for key in ((rule.get("resolution") or {}).get("parameters") or {})
        if isinstance(key, str)
    }
    known_requirements = {
        req for rule in baseline
        if isinstance(rule, dict)
        for req in ((rule.get("resolution") or {}).get("required_evidence") or [])
        if isinstance(req, str)
    }
    known_capabilities = {
        cap for rule in baseline if isinstance(rule, dict)
        for selector in ("source", "target")
        for cap in ((rule.get(selector) or {}).get("capabilities_all") or [])
        if isinstance(cap, str)
    }
    known_capabilities.update({
        "fbx_asset_import", "sequencer_visibility_track",
        "sequencer_skeletal_animation_track", "cine_camera_actor",
    })
    known_outcomes = {
        "EXACT", "CONVERTED", "RETARGETED", "BAKED",
        "RECONSTRUCTED", "TARGET_MAPPED", "BLOCKED",
    }
    # Anonymous aliases are unique within the source's ordered coverage ledger
    # but reveal neither native class names nor stable cross-project hashes.
    unknown = [
        row.get("ced") for row in result["coverage_ledger"]
        if isinstance(row, dict) and row.get("ced") not in known
    ]
    aliases = {
        name: "unknown.unclassified." + str(i + 1)
        for i, name in enumerate(unknown)
        if isinstance(name, str)
    }

    def safe_ced(value: Any) -> str:
        if not isinstance(value, str):
            return "unknown.unclassified"
        return value if value in known else aliases.get(value, "unknown.unclassified")

    def safe_relation(value: Any) -> str:
        if not isinstance(value, str):
            return "unknown_relation"
        if value in {"parent", "binds", "contains", "uses_asset",
                     "reverse:parent", "reverse:binds", "reverse:contains",
                     "reverse:uses_asset"}:
            return value
        reverse = value.startswith("reverse:")
        core = value[8:] if reverse else value
        if core in known:
            return value
        return "reverse:unknown_relation" if reverse else "unknown_relation"

    projected = dict(result)
    projected["observed_target_capabilities"] = sorted(
        cap for cap in result.get("observed_target_capabilities", [])
        if cap in known_capabilities
    )
    projected["unrecognized_target_capability_count"] = sum(
        1 for cap in result.get("observed_target_capabilities", [])
        if cap not in known_capabilities
    )
    projected["coverage_ledger"] = [
        {"ced": safe_ced(row.get("ced")),
         "source_occurrences": row.get("source_occurrences")}
        for row in result["coverage_ledger"] if isinstance(row, dict)
    ]
    entries = []
    for entry in result["entries"]:
        if not isinstance(entry, dict):
            raise KnowledgeServiceError("Malformed CED retrieval entry.")
        safe = dict(entry)
        safe["ced"] = safe_ced(entry.get("ced"))
        safe["related_semantics"] = [
            {"relation": safe_relation(edge.get("relation")),
             "concept": safe_ced(edge.get("concept")),
             "count": edge.get("count")}
            for edge in entry.get("related_semantics", [])
            if isinstance(edge, dict)
        ]
        safe_rules = []
        for index, row in enumerate(entry.get("rules", [])):
            if not isinstance(row, dict):
                raise KnowledgeServiceError("Malformed CED rule provenance.")
            item = dict(row)
            item["required_evidence"] = [
                value if value in known_requirements else "private_evidence_requirement"
                for value in item.get("required_evidence", [])
            ]
            item["parameter_fields"] = [
                value if value in known_parameters else "private_parameter"
                for value in item.get("parameter_fields", [])
            ]
            item["capabilities_not_observed"] = [
                value if value in known_capabilities else "private_capability"
                for value in item.get("capabilities_not_observed", [])
            ]
            item["source_capabilities_not_observed"] = [
                value if value in known_capabilities else "private_capability"
                for value in item.get("source_capabilities_not_observed", [])
            ]
            native_id = item.get("rule_id")
            if native_id not in baseline_ids:
                item["rule_id"] = "local_reviewed_rule_" + str(index + 1)
            if item.get("resolver") not in baseline_resolvers:
                item["resolver"] = "reviewed_native_resolver"
            recipe = item.get("strategy_recipe")
            if isinstance(recipe, dict):
                recipe = dict(recipe)
                recipe["recipe_id"] = item["rule_id"]
                recipe["related_concepts"] = [
                    safe_ced(concept) for concept in recipe.get("related_concepts", [])
                ]
                # Recipe SHA is for the full internal verified knowledge
                # snapshot, not the reduced model-visible projection.
                recipe["recipe_sha256"] = item["strategy_recipe"]["recipe_sha256"]
                item["strategy_recipe"] = recipe
            safe_rules.append(item)
        safe["rules"] = safe_rules
        entries.append(safe)
    projected["entries"] = entries
    projected["private_verified_case_suggestions"] = [
        {
            "case_id": "private_reviewed_case_" + str(i + 1),
            "similarity": case.get("similarity"),
            "mapping_labels": [
                {"ced": safe_ced(row.get("ced")),
                 "resolver": row.get("resolver")
                 if row.get("resolver") in baseline_resolvers
                 else "reviewed_native_resolver",
                 "outcome": (row.get("outcome") if row.get("outcome")
                             in known_outcomes else "UNVERIFIED_MAPPING_OUTCOME")}
                for row in case.get("mapping_labels", [])
                if isinstance(row, dict)
            ],
            "scope": "PRIVATE_VERIFIED_MAPPING_ONLY",
            "native_execution_permission": False,
            "cross_project_fidelity_claim": False,
        }
        for i, case in enumerate(result.get("private_verified_case_suggestions", []))
        if isinstance(case, dict)
    ]
    projected["privacy_projection"] = "MODEL_SAFE_REDACTED_UNKNOWN_CONCEPTS_AND_LOCAL_CASE_IDS"
    projected["shared_promotion_authorized"] = False
    return projected
