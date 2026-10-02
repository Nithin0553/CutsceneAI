"""Deterministic project-aware CED mapping resolution.

The canonical CutScene Element Dictionary (CED) does not mutate per engine. Instead,
project analysis produces source/target Project Intelligence Profiles, and this module
resolves the stable CED through conditional mapping rules into a transfer-specific
Resolved Mapping Dictionary.

That distinction is intentional:
- CED = stable meaning
- CSIR = stable source ground truth
- Project profiles = observed engine/version/project facts
- Resolved dictionary = dynamic mapping for one source/target pair
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


class MappingResolutionError(ValueError):
    pass


JsonObject = Mapping[str, Any]


def _engine(profile: JsonObject) -> str:
    return str(profile.get("engine", {}).get("name", "")).strip().lower()


def _version(profile: JsonObject) -> str:
    return str(profile.get("engine", {}).get("version", "")).strip()


def _supported_capabilities(profile: JsonObject) -> set[str]:
    result: set[str] = set()
    for item in profile.get("capabilities", []):
        if not isinstance(item, Mapping):
            continue
        if str(item.get("state", "")).upper() == "SUPPORTED":
            capability_id = str(item.get("id", "")).strip()
            if capability_id:
                result.add(capability_id)
    return result


def _dotted_get(value: JsonObject, dotted_path: str) -> Any:
    current: Any = value
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current


def _selector_matches(selector: JsonObject, profile: JsonObject) -> bool:
    engine = selector.get("engine")
    if engine is not None and _engine(profile) != str(engine).strip().lower():
        return False

    version_prefix = selector.get("version_prefix")
    if version_prefix is not None and not _version(profile).startswith(str(version_prefix)):
        return False

    required = {str(item) for item in selector.get("capabilities_all", [])}
    if not required <= _supported_capabilities(profile):
        return False

    settings_equals = selector.get("settings_equals", {})
    if isinstance(settings_equals, Mapping):
        for path, expected in settings_equals.items():
            if _dotted_get(profile.get("settings", {}), str(path)) != expected:
                return False

    return True


def _selector_specificity(selector: JsonObject) -> int:
    score = 0
    if selector.get("engine") is not None:
        score += 100
    if selector.get("version_prefix") is not None:
        score += 20
    score += 5 * len(selector.get("capabilities_all", []))
    settings = selector.get("settings_equals", {})
    if isinstance(settings, Mapping):
        score += 3 * len(settings)
    return score


def _rule_score(rule: JsonObject) -> int:
    return (
        int(rule.get("priority", 0)) * 1000
        + _selector_specificity(rule.get("source", {}))
        + _selector_specificity(rule.get("target", {}))
    )


def _candidate_rules(
    ced_id: str,
    source_profile: JsonObject,
    target_profile: JsonObject,
    rules: Iterable[JsonObject],
) -> list[JsonObject]:
    candidates: list[JsonObject] = []
    for rule in rules:
        if str(rule.get("ced", "")) != ced_id:
            continue
        if not _selector_matches(rule.get("source", {}), source_profile):
            continue
        if not _selector_matches(rule.get("target", {}), target_profile):
            continue
        candidates.append(rule)
    return sorted(candidates, key=lambda item: (-_rule_score(item), str(item.get("rule_id", ""))))


def _evidence_ids(profile: JsonObject) -> set[str]:
    result: set[str] = set()
    for item in profile.get("evidence", []):
        if isinstance(item, Mapping):
            evidence_id = str(item.get("evidence_id", "")).strip()
            if evidence_id:
                result.add(evidence_id)
    return result


def resolve_dictionary(
    ced_ids: Iterable[str],
    source_profile: JsonObject,
    target_profile: JsonObject,
    rule_set: JsonObject,
    *,
    ced_version: str = "0.1.0",
) -> dict[str, Any]:
    """Resolve stable CED concepts against observed source and target project facts."""

    rules = rule_set.get("rules", [])
    if not isinstance(rules, list):
        raise MappingResolutionError("rule_set.rules must be an array")

    source_evidence = _evidence_ids(source_profile)
    target_evidence = _evidence_ids(target_profile)
    known_evidence = source_evidence | target_evidence

    entries: list[dict[str, Any]] = []
    for ced_id in sorted({str(value) for value in ced_ids}):
        candidates = _candidate_rules(ced_id, source_profile, target_profile, rules)
        if not candidates:
            entries.append(
                {
                    "ced": ced_id,
                    "status": "BLOCKED",
                    "outcome": "BLOCKED",
                    "resolver": "unresolved.no_matching_rule",
                    "parameters": {},
                    "evidence": [],
                    "confidence": 0.0,
                }
            )
            continue

        best = candidates[0]
        best_score = _rule_score(best)
        tied = [rule for rule in candidates if _rule_score(rule) == best_score]
        if len(tied) > 1:
            resolutions = {
                (
                    str(rule.get("resolution", {}).get("outcome", "")),
                    str(rule.get("resolution", {}).get("resolver", "")),
                    repr(rule.get("resolution", {}).get("parameters", {})),
                )
                for rule in tied
            }
            if len(resolutions) > 1:
                ids = ", ".join(str(rule.get("rule_id", "")) for rule in tied)
                raise MappingResolutionError(
                    f"Ambiguous adaptive mapping for {ced_id}: equal-specificity rules {ids}"
                )

        resolution = best.get("resolution", {})
        required_evidence = [str(item) for item in resolution.get("required_evidence", [])]
        observed_required = [item for item in required_evidence if item in known_evidence]
        confidence = 1.0 if not required_evidence else len(observed_required) / len(required_evidence)

        outcome = str(resolution.get("outcome", "BLOCKED"))
        entries.append(
            {
                "ced": ced_id,
                "status": "BLOCKED" if outcome == "BLOCKED" else "RESOLVED",
                "outcome": outcome,
                "resolver": str(resolution.get("resolver", "unresolved.invalid_rule")),
                "rule_id": str(best.get("rule_id", "")),
                "parameters": deepcopy(resolution.get("parameters", {})),
                "evidence": observed_required,
                "confidence": confidence,
            }
        )

    return {
        "version": "0.1.0",
        "source_profile_id": str(source_profile.get("profile_id", "")),
        "target_profile_id": str(target_profile.get("profile_id", "")),
        "ced_version": ced_version,
        "entries": entries,
    }
