"""CED knowledge retrieval for the agent; no native execution permission.

Combines the CED semantic taxonomy, reviewed adaptive mapping rules, available
native action names, and actual observed target capability flags. Unknowns
remain candidates for investigation, never executable invented mappings.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts" / "dictionary"
MAX_CONCEPTS = 48
MAX_RULES_PER_CONCEPT = 3


class KnowledgeError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= 1024 * 1024):
        raise KnowledgeError("CED taxonomy or baseline rules are missing or unsafe.")
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise KnowledgeError("Invalid CED knowledge document.")
    return result


def _sha(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _semantics(csir: dict[str, Any]) -> Counter:
    """Collect semantic references, not source asset paths, object names or scripts."""
    counts: Counter = Counter()
    def count(value: Any) -> None:
        if not isinstance(value, dict):
            return
        ced = value.get("ced_type")
        if isinstance(ced, str) and len(ced) <= 128:
            counts[ced] += 1

    for kind in ("assets", "entities", "tracks", "relationships"):
        rows = csir.get(kind) or []
        if not isinstance(rows, list):
            raise KnowledgeError("Malformed source semantic inventory.")
        for row in rows[:20000]:
            count(row)
            if kind == "tracks" and isinstance(row, dict):
                for section in (row.get("sections") or [])[:5000]:
                    count(section)
                    if isinstance(section, dict):
                        animation = (section.get("payload") or {}).get("animation") or {}
                        for curve in (animation.get("curves") or [])[:10000]:
                            count(curve)
    return counts


def retrieve(csir: dict[str, Any], *, target_capabilities: dict[str, Any],
             source_version: str = "", target_version: str = "",
             approved_store: Path | None = None) -> dict[str, Any]:
    """Return bounded evidence-backed retrieval; approved rules remain gated.

    This is a structured RAG-style retrieval step, not a native converter.
    An approved CED resolver is still checked against live project evidence by
    the deterministic mapping engine before any native operation.
    """
    if not isinstance(csir, dict) or not isinstance(target_capabilities, dict):
        raise KnowledgeError("Knowledge retrieval requires validated project evidence.")
    categories = _load(CONTRACTS / "cutscene-elements-v0.2.json").get("categories")
    baselines = _load(CONTRACTS / "adaptive-rules-v0.1.json").get("rules")
    if not isinstance(categories, dict) or not isinstance(baselines, list):
        raise KnowledgeError("CED taxonomy or adaptive baseline has an invalid format.")
    all_concepts = {
        name for concepts in categories.values() if isinstance(concepts, list)
        for name in concepts if isinstance(name, str)
    }
    if len(all_concepts) < 100:
        raise KnowledgeError("CED knowledge catalog is incomplete.")
    rules = [(rule, "BASELINE_UNVERIFIED") for rule in baselines]
    if approved_store is not None:
        library = str(ROOT / "readiness")
        if library not in sys.path:
            sys.path.insert(0, library)
        from ced_rulebook import approved_rules
        # This loader independently validates native evidence and approval hashes.
        rules += [(rule, "HUMAN_APPROVED_RULE") for rule in approved_rules(approved_store)]
    for rule, _ in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("ced"), str):
            raise KnowledgeError("Malformed registered CED rule.")
    known_actions = __import__("feature_dispatch").EXPLICIT_ACTIONS
    caps = {
        k for k, v in target_capabilities.items()
        if isinstance(k, str) and v is True
    }
    counts = _semantics(csir)
    selected = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    entries = []
    for ced, occurrences in selected[:MAX_CONCEPTS]:
        matches = []
        for rule, origin in rules:
            if rule["ced"] != ced:
                continue
            source = rule.get("source") or {}
            target = rule.get("target") or {}
            if source.get("engine") != "unity" or target.get("engine") != "unreal":
                continue
            if (source.get("version_prefix")
                    and not source_version.startswith(source["version_prefix"])):
                continue
            if (target.get("version_prefix")
                    and not target_version.startswith(target["version_prefix"])):
                continue
            requirements = set(target.get("capabilities_all") or [])
            missing = sorted(requirements - caps)
            resolution = rule.get("resolution") or {}
            matches.append({
                "rule_id": rule.get("rule_id"),
                "resolver": resolution.get("resolver"),
                "outcome": resolution.get("outcome"),
                "required_evidence": list(resolution.get("required_evidence") or [])[:16],
                "parameter_fields": sorted((resolution.get("parameters") or {}).keys())[:16],
                "origin": origin,
                "capabilities_not_observed": missing,
                "status": ("CAPABILITY_EVIDENCE_MISSING" if missing
                           else "RULE_CANDIDATE_REQUIRES_PREFLIGHT"),
            })
        matches.sort(key=lambda r: (
            r["status"] != "RULE_CANDIDATE_REQUIRES_PREFLIGHT",
            r["origin"] != "HUMAN_APPROVED_RULE", str(r["rule_id"]),
        ))
        entries.append({
            "ced": ced,
            "source_occurrences": occurrences,
            "semantic_known": ced in all_concepts,
            "rules": matches[:MAX_RULES_PER_CONCEPT],
            "native_action_candidates": list(known_actions.get(ced, ()))[:6],
            "resolution_state": (
                "UNKNOWN_SEMANTIC_INVESTIGATE" if ced not in all_concepts else
                "RETRIEVED_CANDIDATES_NEED_NATIVE_PREFLIGHT" if matches
                or known_actions.get(ced) else "KNOWN_SEMANTIC_NO_REGISTERED_MAPPING"
            ),
        })
    result = {
        "kind": "cutsceneai.studio.ced_knowledge_retrieval",
        "schema_version": "1",
        "source_ced_count": len(counts),
        "retrieved_count": len(entries),
        "omitted_count": max(0, len(counts) - len(entries)),
        "observed_target_capabilities": sorted(caps)[:40],
        "entries": entries,
        "no_native_write_permission": True,
    }
    return {**result, "knowledge_sha256": _sha(result)}
