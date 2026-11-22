"""Explicit CED review queue and authenticated independent reviewer decisions.

A signature proves which authorized reviewer signed a bounded assertion, NOT
that an engine's behavior is correct. Native evidence authenticity, held-out
validation and independent privacy inspection remain required human gates.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ROLES = frozenset({"NATIVE_EVIDENCE", "PRIVACY"})
_MAX_BYTES = 512 * 1024


class ReviewError(ValueError):
    """A CED review would bypass consent, privacy or trusted signatures."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read(path: Path) -> dict[str, Any]:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= _MAX_BYTES):
        raise ReviewError("Review input is missing, redirected or oversized.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReviewError("Review input is invalid JSON.") from exc
    if not isinstance(data, dict):
        raise ReviewError("CED review input must be a JSON object.")
    return data


def validated_bundle(value: Any) -> dict[str, Any]:
    if (not isinstance(value, dict)
            or value.get("kind") != "cutsceneai.ced.shared_review_bundle"
            or value.get("schema_version") != "1"
            or value.get("status") != "REVIEW_ONLY_NOT_TRUSTED_NOT_EXECUTABLE"
            or value.get("raw_private_evidence_attached") is not False
            or value.get("verified_shared_release") is not False
            or value.get("native_execution_permission") is not False
            or value.get("new_engine_adapter_permission") is not False
            or not isinstance(value.get("rules"), list)
            or not 1 <= len(value["rules"]) <= 32):
        raise ReviewError("CED bundle must be the inert, sanitized staging format.")
    saved = value.get("bundle_sha256")
    unsigned = {k: v for k, v in value.items() if k != "bundle_sha256"}
    if not isinstance(saved, str) or saved != digest(unsigned):
        raise ReviewError("CED review bundle content hash does not match.")
    import sys
    from pathlib import Path as _Path
    readiness = str(_Path(__file__).resolve().parents[1] / "readiness")
    if readiness not in sys.path:
        sys.path.insert(0, readiness)
    from ced_rulebook import validate_candidate
    from shared_review import _public
    seen: set[str] = set()
    for row in value["rules"]:
        if (not isinstance(row, dict)
                or row.get("origin") != "PRIVATELY_APPROVED_PENDING_SHARED_REVIEW"
                or row.get("runtime_authorized") is not False
                or row.get("independent_authenticity_recheck_required") is not True
                or not isinstance(row.get("local_candidate_id"), str)
                or not _SHA.fullmatch(row["local_candidate_id"])
                or not isinstance(row.get("review_evidence_sha256"), str)
                or not _SHA.fullmatch(row["review_evidence_sha256"])
                or not isinstance(row.get("rule"), dict)):
            raise ReviewError("Staged CED rule is missing reviewed provenance.")
        sanitized = _public(row["rule"])
        if sanitized != row["rule"]:
            raise ReviewError("CED rule contains unsafe private source parameters.")
        try:
            validate_candidate(row["rule"])
        except ValueError as exc:
            raise ReviewError("Staged CED rule is invalid.") from exc
        identity = row["rule"]["rule_id"]
        if identity in seen:
            raise ReviewError("Staged review duplicates a rule.")
        seen.add(identity)
    return value


def submit(bundle_file: Path, queue_folder: Path, *,
           explicit_consent: bool) -> dict[str, Any]:
    if explicit_consent is not True:
        raise ReviewError("Explicit sharing consent required for review queue.")
    bundle = validated_bundle(read(bundle_file))
    if queue_folder.is_symlink() or not queue_folder.is_dir():
        raise ReviewError("Review queue must be an existing safe local folder.")
    target = queue_folder / (bundle["bundle_sha256"] + ".json")
    serialized = json.dumps(bundle, sort_keys=True, indent=2) + "\n"
    if target.exists():
        if target.is_symlink() or target.read_text(encoding="utf-8") != serialized:
            raise ReviewError("Conflicting staged review request.")
    else:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    return {"status": "PENDING_INDEPENDENT_REVIEW",
            "bundle_sha256": bundle["bundle_sha256"],
            "shared_release_published": False}


def public_key(private_key_pem: Path) -> bytes:
    if private_key_pem.is_symlink() or private_key_pem.stat().st_size > 16 * 1024:
        raise ReviewError("Unsafe reviewer private key file.")
    key = serialization.load_pem_private_key(private_key_pem.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ReviewError("CED reviewers must sign with Ed25519 keys.")
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _sign(private_key_pem: Path, payload: dict[str, Any]) -> str:
    if private_key_pem.is_symlink() or private_key_pem.stat().st_size > 16 * 1024:
        raise ReviewError("Unsafe reviewer signing key.")
    key = serialization.load_pem_private_key(private_key_pem.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ReviewError("CED reviewer key must use Ed25519.")
    return key.sign(canonical(payload)).hex()


def _sha_file(path: Path) -> str:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= 64 * 1024 * 1024):
        raise ReviewError("Independent evidence file is absent or unsafe.")
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def sign_review(bundle_file: Path, *, reviewer: str, role: str,
                reviewer_private_key: Path, native_evidence: Path,
                heldout_report: Path, regression_report: Path,
                explicitly_approved: bool) -> dict[str, Any]:
    if explicitly_approved is not True:
        raise ReviewError("Reviewer must explicitly approve this evidence.")
    if not isinstance(reviewer, str) or not _ID.fullmatch(reviewer) or role not in _ROLES:
        raise ReviewError("Reviewer identity or independent role is invalid.")
    bundle = validated_bundle(read(bundle_file))
    statement = {
        "kind": "cutsceneai.ced.authenticated_review",
        "schema_version": "1",
        "bundle_sha256": bundle["bundle_sha256"],
        "reviewer": reviewer,
        "role": role,
        "decision": "APPROVE_FOR_SHARED_RELEASE_REVIEW",
        "native_evidence_sha256": _sha_file(native_evidence),
        "heldout_report_sha256": _sha_file(heldout_report),
        "regression_report_sha256": _sha_file(regression_report),
        "runtime_execution_authorized": False,
    }
    return {**statement, "signature_ed25519": _sign(reviewer_private_key, statement)}


def verify_reviews(bundle: dict[str, Any], decisions: list[dict[str, Any]],
                   trusted_reviewers: dict[str, bytes]) -> list[dict[str, Any]]:
    validated_bundle(bundle)
    if not isinstance(decisions, list) or len(decisions) < 2 or len(decisions) > 8:
        raise ReviewError("At least two independent CED reviewers are required.")
    roles: set[str] = set()
    identities: set[str] = set()
    evidence: set[tuple[str, str, str]] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ReviewError("Invalid CED reviewer decision.")
        unsigned = {k: v for k, v in decision.items() if k != "signature_ed25519"}
        signer = unsigned.get("reviewer")
        role = unsigned.get("role")
        if (not isinstance(signer, str) or signer not in trusted_reviewers
                or role not in _ROLES or signer in identities
                or role in roles or unsigned.get("bundle_sha256") != bundle["bundle_sha256"]
                or unsigned.get("kind") != "cutsceneai.ced.authenticated_review"
                or unsigned.get("schema_version") != "1"
                or unsigned.get("decision") != "APPROVE_FOR_SHARED_RELEASE_REVIEW"
                or unsigned.get("runtime_execution_authorized") is not False):
            raise ReviewError("Untrusted, repeated or conflicting reviewer approval.")
        digests = tuple(unsigned.get(field) for field in (
            "native_evidence_sha256", "heldout_report_sha256",
            "regression_report_sha256",
        ))
        if any(not isinstance(x, str) or not _SHA.fullmatch(x) for x in digests):
            raise ReviewError("Signed CED evidence references are incomplete.")
        signature = decision.get("signature_ed25519")
        if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ReviewError("CED reviewer signature is missing.")
        key = trusted_reviewers[signer]
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(
                bytes.fromhex(signature), canonical(unsigned)
            )
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise ReviewError("CED review signature failed authentication.") from exc
        roles.add(role)
        identities.add(signer)
        evidence.add(digests)
    if roles != _ROLES or len(evidence) != 1:
        raise ReviewError("Independent privacy and native reviewers must agree on evidence.")
    return decisions
