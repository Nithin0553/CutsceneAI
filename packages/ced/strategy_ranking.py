"""Advisory CED strategy ranking from capability evidence and local outcomes.

No benchmark IDs, no native execution authorization and no cross-engine
fidelity claim. Negative observations may warn; positive credit is gated by
independent readback, explicit review and distinct held-out project groups.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

MAX_FEEDBACK_BYTES = 32 * 1024 * 1024
MAX_FEEDBACK_ROWS = 8000
_VERSION = re.compile(r"[A-Za-z0-9_.-]{0,64}\Z")


class RankingError(ValueError):
    pass


def load_feedback(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_FEEDBACK_BYTES):
        raise RankingError("Private learning ledger is unsafe or oversized.")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise RankingError("Private feedback ledger contains an empty record.")
        try:
            row = json.loads(line)
        except (ValueError, TypeError) as exc:
            raise RankingError("Private feedback ledger contains invalid JSON.") from exc
        if (not isinstance(row, dict)
                or row.get("kind") != "cutsceneai.ced.mapping_experience"
                or row.get("schema_version") != "1"):
            raise RankingError("Private feedback ledger has an unsupported record.")
        rows.append(row)
        if len(rows) > MAX_FEEDBACK_ROWS:
            raise RankingError("Private feedback ledger exceeds its record budget.")
    # Reuse the existing offline experience validation rather than create a
    # competing positive-label authority.
    import sys
    learning = str(Path(__file__).resolve().parents[1] / "learning")
    if learning not in sys.path:
        sys.path.insert(0, learning)
    import ced_reinforcement
    seen = set()
    for row in rows:
        ced_reinforcement.validate_experience(row)
        if row["case_sha256"] in seen:
            raise RankingError("Private experience contains a replayed case.")
        seen.add(row["case_sha256"])
    return rows


def signal(rule: dict[str, Any], *, ced: str, source_version: str,
           target_version: str, feedback: list[dict[str, Any]]) -> dict[str, Any]:
    if not _VERSION.fullmatch(source_version) or not _VERSION.fullmatch(target_version):
        raise RankingError("Invalid version scope for local strategy ranking.")
    rule_id = rule.get("rule_id")
    matched = [row for row in feedback
               if row["ced"] == ced and row["rule_id"] == rule_id
               and row["source_version"] == source_version
               and row["target_version"] == target_version
               and row["source_engine"] == "unity"
               and row["target_engine"] == "unreal"]
    groups: dict[str, set[str]] = defaultdict(set)
    for row in matched:
        outcome = row["test_outcome"]
        group = row["project_group_sha256"]
        if (outcome == "PASS" and row["native_readback_verified"]
                and row["human_reviewed"]):
            groups[group].add("reviewed_pass")
        elif outcome == "FAIL":
            groups[group].add("observed_failure")
        else:
            groups[group].add("unverified")
    passed = sum(1 for values in groups.values()
                 if "reviewed_pass" in values and "observed_failure" not in values)
    failed = sum(1 for values in groups.values() if "observed_failure" in values)
    conflicting = sum(1 for values in groups.values()
                      if "reviewed_pass" in values and "observed_failure" in values)
    # Distinct project groups cannot be confused with hundreds of attempts
    # from the same original benchmark or a single re-run.
    positive_weight = min(passed, 5) if passed >= 3 and not conflicting else 0
    penalty = min(failed, 5) * 3 + (2 if conflicting else 0)
    return {
        "score_adjustment": positive_weight - penalty,
        "reviewed_success_project_groups": passed,
        "failed_project_groups": failed,
        "conflicting_project_groups": conflicting,
        "evidence_level": ("MULTI_PROJECT_REVIEWED" if passed >= 3 and not conflicting
                           else "NEGATIVE_OBSERVATION" if failed
                           else "INSUFFICIENT_INDEPENDENT_EVIDENCE"),
        "native_execution_permission": False,
        "full_cutscene_fidelity_verified": False,
    }


def rank_rules(rules: list[dict[str, Any]], *, ced: str,
               source_version: str, target_version: str,
               feedback: list[dict[str, Any]],
               relations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return candidates sorted by independent evidence, not guessed fitness."""
    output = []
    neighbor_count = len(relations or [])
    for item in rules:
        if not isinstance(item, dict):
            raise RankingError("Malformed strategy candidate.")
        result = dict(item)
        native_gaps = len(item.get("capabilities_not_observed", []))
        source_gaps = len(item.get("source_capabilities_not_observed", []))
        # No parameter names, object identifiers or benchmark names enter this
        # signal; relationship context only adds a small generic contribution.
        prior = signal(item, ced=ced, source_version=source_version,
                       target_version=target_version, feedback=feedback)
        score = (
            (6 if item.get("origin") == "LOCAL_REVIEWED_NATIVE_MAPPING" else 1)
            + (2 if item.get("status") == "RULE_CANDIDATE_REQUIRES_PREFLIGHT" else -6)
            + min(neighbor_count, 3)
            - 4 * (native_gaps + source_gaps)
            + prior["score_adjustment"]
        )
        result["advisory_ranking"] = {
            "context_score": score,
            "independent_experience": prior,
            "fidelity_claim": "NONE",
            "native_tool_authority": False,
        }
        output.append(result)
    return sorted(output, key=lambda item: (
        -item["advisory_ranking"]["context_score"], str(item["rule_id"]),
    ))


def similar_known(unknown: str, known: set[str], *, limit: int = 3) -> list[dict[str, Any]]:
    """Investigative lexical hints, explicitly not candidate mappings."""
    if not isinstance(unknown, str) or not 0 < len(unknown) <= 128:
        return []
    candidates = []
    for target in known:
        similarity = SequenceMatcher(None, unknown.casefold(), target.casefold()).ratio()
        # A low similarity score is uninformative: do not guess native support.
        if similarity >= 0.58:
            candidates.append((similarity, target))
    candidates.sort(key=lambda entry: (-entry[0], entry[1]))
    return [{
        "semantic_id": name,
        "lexical_similarity": round(score, 3),
        "evidence_status": "INVESTIGATION_ONLY_NOT_NATIVE_MAPPING",
        "execution_authorized": False,
    } for score, name in candidates[:limit]]
