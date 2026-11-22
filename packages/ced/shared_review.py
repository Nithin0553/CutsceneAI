"""Explicit, privacy-screened CED knowledge promotion *staging*.

A prepared bundle is not an approved release and cannot be loaded as runtime
native permission. Installation/publication requires a separate source-control
review and independent evidence authentication. No network client is present.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

PACKAGES = Path(__file__).resolve().parents[1]
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_CANDIDATE = re.compile(r"[0-9a-f]{64}\Z")


class SharedReviewError(ValueError):
    """A proposed shared bundle would expose private data or bypass review."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf-8")


def _public(value: Any, *, depth: int = 0) -> Any:
    """Allow only bounded declarative identifiers and numeric/boolean settings.

    Reject paths, URLs, names with spaces, script snippets and arbitrary
    source payload text. This deliberately errs on the side of non-sharing.
    """
    if depth > 6:
        raise SharedReviewError("Shared rule parameter depth exceeds safe limits.")
    if value is None or type(value) is bool:
        return value
    if type(value) in (int, float):
        if type(value) is float and not math.isfinite(value):
            raise SharedReviewError("Nonfinite value cannot be included in a shared rule.")
        return value
    if isinstance(value, str):
        if not _TOKEN.fullmatch(value):
            raise SharedReviewError(
                "Unreviewed text, path or project-specific value cannot be shared."
            )
        return value
    if isinstance(value, list) and len(value) <= 40:
        return [_public(item, depth=depth + 1) for item in value]
    if isinstance(value, dict) and len(value) <= 40:
        if any(not isinstance(key, str) or not _TOKEN.fullmatch(key) for key in value):
            raise SharedReviewError("Unrecognized private mapping parameter key.")
        return {
            key: _public(item, depth=depth + 1)
            for key, item in sorted(value.items())
        }
    raise SharedReviewError("Unbounded or private mapping value cannot be shared.")


def _read(path: Path) -> dict[str, Any]:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= 2 * 1024 * 1024):
        raise SharedReviewError("Missing or unsafe reviewed CED record.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SharedReviewError("Invalid reviewed CED record.") from exc
    if not isinstance(data, dict):
        raise SharedReviewError("Expected a JSON CED review record.")
    return data


def stage_for_review(
    store: str | Path, output: str | Path, *,
    candidate_ids: list[str], explicit_sharing_consent: bool,
) -> dict[str, Any]:
    """Create an inert, sanitized candidate bundle for manual code review.

    No local source assets, captures, project names, paths or case bodies are
    uploaded, copied or made executable. User must explicitly choose IDs.
    """
    if explicit_sharing_consent is not True:
        raise SharedReviewError("Explicit user consent is required to stage shared CED knowledge.")
    if (not isinstance(candidate_ids, list) or not 1 <= len(candidate_ids) <= 32
            or len(set(candidate_ids)) != len(candidate_ids)
            or any(not isinstance(i, str) or not _CANDIDATE.fullmatch(i)
                   for i in candidate_ids)):
        raise SharedReviewError("Select unique, reviewed CED candidate identities.")
    root = Path(store)
    if root.is_symlink() or not root.is_dir():
        raise SharedReviewError("Private CED knowledge store is missing or unsafe.")
    target = Path(output)
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise SharedReviewError("Shared review output must be a new safe file.")

    location = str(PACKAGES / "readiness")
    if location not in sys.path:
        sys.path.insert(0, location)
    import ced_rulebook
    # This validates every locally approved record against immutable native
    # evidence and existing registered adapters, before we stage anything.
    approved = ced_rulebook.approved_rules(root)
    eligible = {item["rule_id"]: item for item in approved}
    gathered = []
    for candidate_id in sorted(candidate_ids):
        candidate = _read(root / "candidates" / (candidate_id + ".json"))
        approval = _read(root / "approvals" / (candidate_id + ".json"))
        rule = candidate.get("rule")
        if not isinstance(rule, dict):
            raise SharedReviewError("Invalid private CED candidate.")
        rule_id = rule.get("rule_id")
        if (rule_id not in eligible or eligible[rule_id] != rule
                or approval.get("candidate_id") != candidate_id
                or approval.get("status") != "APPROVED_FOR_GUARDED_RESOLUTION"
                or approval.get("held_out_passed") is not True
                or approval.get("regression_passed") is not True):
            raise SharedReviewError("Requested mapping has no independent local approval.")
        # Never export freeform candidate notes, reviewer usernames, source
        # fingerprints, raw native readback or local case examples.
        sanitized = {
            "rule_id": _public(rule_id),
            "ced": _public(rule["ced"]),
            "priority": rule.get("priority", 0),
            "source": _public(rule["source"]),
            "target": _public(rule["target"]),
            "resolution": _public(rule["resolution"]),
        }
        gathered.append({
            "rule": sanitized,
            "origin": "PRIVATELY_APPROVED_PENDING_SHARED_REVIEW",
            "review_evidence_sha256": approval["native_evidence_sha256"],
            "local_candidate_id": candidate_id,
            "human_reviewed_native_receipt_claim": True,
            "independent_authenticity_recheck_required": True,
            "runtime_authorized": False,
        })
    document = {
        "kind": "cutsceneai.ced.shared_review_bundle",
        "schema_version": "1",
        "status": "REVIEW_ONLY_NOT_TRUSTED_NOT_EXECUTABLE",
        "source": "EXPLICITLY_CONSENTED_SANITIZED_LOCAL_RULES",
        "raw_private_evidence_attached": False,
        "verified_shared_release": False,
        "native_execution_permission": False,
        "new_engine_adapter_permission": False,
        "required_review": (
            "Privacy, registered adapter, actual native evidence authenticity, "
            "held-out source projects, signatures and regression approval"
        ),
        "rules": gathered,
    }
    document["bundle_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    content = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if len(content.encode("utf-8")) > 256 * 1024:
        raise SharedReviewError("Shared CED review bundle is too large.")
    with target.open("x", encoding="utf-8") as stream:
        stream.write(content)
    return document
