"""Offline contextual-bandit reinforcement learning for CED mapping choices.

A conversion is a one-step decision with observed reward, making a contextual
bandit (horizon-one RL) appropriate. This module learns *suggestions*, not
engine adapters, mutable mapping approvals, or unrestricted code execution.
Only independently validated outcomes receive positive rewards. Project-group
splits prevent train/held-out leakage, and low-sample actions remain uncertain.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

POLICY_VERSION = "1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
OUTCOMES = {"PASS", "FAIL", "INCOMPLETE"}
REWARDS = {"PASS": 1.0, "FAIL": -1.0, "INCOMPLETE": -0.5}


class CEDLearningError(ValueError):
    pass


def _digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def validate_experience(row: Any) -> dict:
    if not isinstance(row, dict) or set(row) != {
        "kind", "schema_version", "case_sha256", "project_group_sha256",
        "ced", "rule_id", "source_engine", "target_engine",
        "source_version", "target_version", "test_outcome",
        "native_readback_verified", "human_reviewed", "evidence_sha256",
    }:
        raise CEDLearningError("Invalid or incomplete CED learning experience.")
    if row["kind"] != "cutsceneai.ced.mapping_experience" or row["schema_version"] != POLICY_VERSION:
        raise CEDLearningError("Unknown CED learning event version.")
    if any(not isinstance(row[key], str) or not _SHA.fullmatch(row[key])
           for key in ("case_sha256", "project_group_sha256", "evidence_sha256")):
        raise CEDLearningError("Learning case/project/evidence SHA256 is required.")
    if any(not isinstance(row[key], str) or not _ID.fullmatch(row[key])
           for key in ("ced", "rule_id")) or "." not in row["ced"]:
        raise CEDLearningError("Invalid CED or mapping action identity.")
    if row["source_engine"] != "unity" or row["target_engine"] != "unreal":
        raise CEDLearningError("Unknown engine direction in feedback.")
    if (any(not isinstance(row[key], str) or
            not re.fullmatch(r"[0-9A-Za-z._-]{1,40}", row[key])
            for key in ("source_version", "target_version"))
            or row["test_outcome"] not in OUTCOMES
            or type(row["native_readback_verified"]) is not bool
            or type(row["human_reviewed"]) is not bool):
        raise CEDLearningError("Invalid experience context or measured outcome.")
    if row["test_outcome"] == "PASS" and (
            not row["native_readback_verified"] or not row["human_reviewed"]):
        raise CEDLearningError("Positive RL reward requires human-reviewed native readback.")
    if len(json.dumps(row)) > 4096:
        raise CEDLearningError("Experience contains excessive or private context.")
    return row


def _context(row: dict) -> tuple[str, str, str, str, str]:
    # Version-specific learning never transfers a policy blindly to a new
    # engine/version pair. No user asset names or project file paths are used.
    return (row["ced"], row["source_engine"], row["source_version"],
            row["target_engine"], row["target_version"])


def train_offline(experiences: list[dict], *, minimum_cases: int = 3,
                  prior_reward: float = -0.5, prior_count: int = 2) -> dict:
    """Deterministic TD(0) contextual-bandit Q update and held-out evaluation.

    Each observation updates Q(context,action) with alpha=1/(prior_count+n),
    equivalent to a conservative sample mean with pessimistic virtual trials.
    Return ranking candidates only; no model-weight or live-rule mutations.
    """
    if (type(minimum_cases) is not int or minimum_cases < 2
            or type(prior_count) is not int or prior_count < 1
            or type(prior_reward) not in (int, float)
            or not -1.0 <= prior_reward <= 0.0):
        raise CEDLearningError("Invalid offline RL training configuration.")
    checked = [validate_experience(row) for row in experiences]
    if len({_digest(x) for x in checked}) != len(checked):
        raise CEDLearningError("Duplicated or replayed feedback event.")
    by_case = {row["case_sha256"] for row in checked}
    if len(by_case) != len(checked):
        raise CEDLearningError("One held-out case cannot provide repeated rewards.")

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in checked:
        grouped[(*_context(row), row["rule_id"])].append(row)

    # A held-out project group is never selected as both train and eval for
    # the same action. To avoid accidental leakage, reserve the lexically last
    # distinct group for evaluation whenever there are >= 2 groups.
    results = []
    for identity, rows in sorted(grouped.items()):
        projects = sorted({row["project_group_sha256"] for row in rows})
        if len(projects) < 2:
            training, heldout = [], rows
        else:
            heldout_group = projects[-1]
            training = [r for r in rows if r["project_group_sha256"] != heldout_group]
            heldout = [r for r in rows if r["project_group_sha256"] == heldout_group]
        q = float(prior_reward)
        count = prior_count
        for item in sorted(training, key=lambda r: r["case_sha256"]):
            reward = REWARDS[item["test_outcome"]]
            count += 1
            q += (reward - q) / count
        heldout_reward = (sum(REWARDS[item["test_outcome"]] for item in heldout)
                          / len(heldout)) if heldout else None
        distinct_train_projects = len({r["project_group_sha256"] for r in training})
        enough = (len(training) >= minimum_cases
                  and distinct_train_projects >= 2
                  and heldout_reward is not None and heldout_reward > 0
                  and q > 0)
        results.append({
            "ced": identity[0], "source_engine": identity[1],
            "source_version": identity[2], "target_engine": identity[3],
            "target_version": identity[4], "rule_id": identity[5],
            "q_value": round(q, 6),
            "train_cases": len(training), "train_project_groups": distinct_train_projects,
            "heldout_cases": len(heldout),
            "heldout_mean_reward": (round(heldout_reward, 6)
                                    if heldout_reward is not None else None),
            "policy": ("RECOMMEND_FOR_HUMAN_REVIEW" if enough
                       else "INSUFFICIENT_VALIDATION_NO_PROMOTION"),
        })
    return {
        "kind": "cutsceneai.ced.offline_rl_policy",
        "schema_version": POLICY_VERSION,
        "algorithm": "CONTEXTUAL_BANDIT_TD0_PESSIMISTIC_PRIOR",
        "training_feedback_sha256": _digest(sorted(checked, key=lambda r: r["case_sha256"])),
        "experiences": len(checked), "actions": results,
        "can_authorize_native_transfer": False,
        "can_promote_ced_rules": False,
        "native_engine_training_executed": False,
    }


def export_policy(experiences_file: str | Path, output_file: str | Path,
                  *, minimum_cases: int = 3) -> dict:
    source, output = Path(experiences_file), Path(output_file)
    if (source.is_symlink() or not source.is_file()
            or source.stat().st_size > 32 * 1024 * 1024
            or output.exists() or output.is_symlink()
            or not output.parent.is_dir()):
        raise CEDLearningError("Learning source/output path must be safe and new.")
    rows = []
    try:
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    raise CEDLearningError("Blank training event is not allowed.")
                rows.append(json.loads(line))
                if len(rows) > 100000:
                    raise CEDLearningError("Learning dataset exceeds case budget.")
    except (OSError, ValueError) as exc:
        raise CEDLearningError("Unable to decode CED learning dataset.") from exc
    policy = train_offline(rows, minimum_cases=minimum_cases)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(policy, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return policy
