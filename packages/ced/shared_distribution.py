"""Offline signed shared CED releases, trusted installation and safe revocation.

Publisher signatures authenticate reviewed *knowledge*, not native execution.
No remote fetch, auto-promotion or arbitrary engine code is supported.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from review_queue import (
    ReviewError, canonical, digest, read, validated_bundle, verify_reviews,
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}\Z")


class DistributionError(ValueError):
    """Untrusted, stale, unsigned or incompatible shared CED release."""


def _publisher_key(path: Path) -> Ed25519PublicKey:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= 16 * 1024):
        raise DistributionError("Trusted CED publisher public key is missing or unsafe.")
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (ValueError, TypeError) as exc:
        raise DistributionError("Invalid trusted CED publisher public key.") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise DistributionError("CED publisher must use Ed25519.")
    return key


def _fingerprint(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def _validate_rules(rules: list[dict[str, Any]]) -> None:
    import sys
    library = str(Path(__file__).resolve().parents[1] / "readiness")
    if library not in sys.path:
        sys.path.insert(0, library)
    import ced_rulebook
    if not isinstance(rules, list) or len(rules) > 64:
        raise DistributionError("Shared release has an invalid bounded rule set.")
    seen = set()
    baseline = ced_rulebook._baseline()
    baseline_ids = {rule["rule_id"] for rule in baseline}
    concepts = ced_rulebook._concepts()
    known_caps = {
        cap for rule in baseline for selector in ("source", "target")
        for cap in rule[selector].get("capabilities_all", [])
    }
    known_evidence = {
        value for rule in baseline
        for value in rule["resolution"].get("required_evidence", [])
    }
    for rule in rules:
        try:
            ced_rulebook.validate_candidate(rule)
        except ValueError as exc:
            raise DistributionError("Signed CED release rule is malformed.") from exc
        if (rule["rule_id"] in seen or rule["rule_id"] in baseline_ids
                or rule["ced"] not in concepts
                or not ced_rulebook._eligible_adapter(rule)
                or not set(rule["source"].get("capabilities_all", [])) <= known_caps
                or not set(rule["target"].get("capabilities_all", [])) <= known_caps
                or not set(rule["resolution"].get("required_evidence", []))
                    <= known_evidence):
            raise DistributionError(
                "Signed rule is duplicate, contains private unknown declarations "
                "or has no registered native adapter."
            )
        seen.add(rule["rule_id"])


def _release_body(
    bundle: dict[str, Any], *, revision: int, previous_sha256: str | None,
    revoked_ids: list[str], publisher_fingerprint: str,
    reviewer_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    if type(revision) is not int or not 1 <= revision <= 1000000:
        raise DistributionError("Invalid monotonically increasing CED release revision.")
    if ((revision == 1 and previous_sha256 is not None)
            or (revision > 1 and not isinstance(previous_sha256, str))
            or (previous_sha256 is not None and not _SHA.fullmatch(previous_sha256))):
        raise DistributionError("Signed release predecessor identity is invalid.")
    if (not isinstance(revoked_ids, list) or len(revoked_ids) > 64
            or len(set(revoked_ids)) != len(revoked_ids)
            or any(not isinstance(v, str) or not _ID.fullmatch(v) for v in revoked_ids)):
        raise DistributionError("Revoked rule identities are invalid.")
    rules = [row["rule"] for row in bundle["rules"]
             if row["rule"]["rule_id"] not in revoked_ids]
    _validate_rules(rules)
    return {
        "kind": "cutsceneai.ced.signed_release",
        "schema_version": "1",
        "release_revision": revision,
        "previous_release_sha256": previous_sha256,
        "review_bundle_sha256": bundle["bundle_sha256"],
        "publisher_key_fingerprint": publisher_fingerprint,
        "review_approvals": sorted([
            {
                "role": decision["role"],
                # Avoid distributing reviewer usernames.
                "review_record_sha256": digest(decision),
                "native_evidence_sha256": decision["native_evidence_sha256"],
                "heldout_report_sha256": decision["heldout_report_sha256"],
                "regression_report_sha256": decision["regression_report_sha256"],
            }
            for decision in reviewer_decisions
        ], key=lambda record: record["role"]),
        "rules": rules,
        "revoked_rule_ids": sorted(revoked_ids),
        "runtime_execution_authorized": False,
        "fidelity_certified_for_unseen_projects": False,
        "approval": "INDEPENDENT_SIGNED_REVIEWS_KNOWLEDGE_ONLY",
    }


def sign_release(
    bundle_file: Path, *, review_decisions: list[dict[str, Any]],
    trusted_reviewers: dict[str, bytes], publisher_private_key: Path,
    revision: int, previous_release_sha256: str | None,
    revoked_rule_ids: list[str], output_file: Path,
    explicit_release_consent: bool,
) -> dict[str, Any]:
    if explicit_release_consent is not True:
        raise DistributionError("Explicit publisher consent is required.")
    bundle = validated_bundle(read(bundle_file))
    try:
        verified = verify_reviews(bundle, review_decisions, trusted_reviewers)
    except ReviewError as exc:
        raise DistributionError("Independent reviewer evidence is incomplete: " + str(exc)) from exc
    if publisher_private_key.is_symlink() or not publisher_private_key.is_file():
        raise DistributionError("Publisher signing key is missing or redirected.")
    try:
        key = serialization.load_pem_private_key(
            publisher_private_key.read_bytes(), password=None,
        )
    except (TypeError, ValueError) as exc:
        raise DistributionError("Invalid publisher private signing key.") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise DistributionError("Publisher private key must use Ed25519.")
    body = _release_body(
        bundle, revision=revision, previous_sha256=previous_release_sha256,
        revoked_ids=revoked_rule_ids,
        publisher_fingerprint=_fingerprint(key.public_key()),
        reviewer_decisions=verified,
    )
    envelope = {**body, "signature_ed25519": key.sign(canonical(body)).hex()}
    content = json.dumps(envelope, sort_keys=True, indent=2) + "\n"
    if (output_file.exists() or output_file.is_symlink()
            or not output_file.parent.is_dir()
            or len(content.encode("utf-8")) > 512 * 1024):
        raise DistributionError("Signed release destination is unsafe or already exists.")
    with output_file.open("x", encoding="utf-8") as file:
        file.write(content)
    return envelope


def verify_release(envelope: Any, trusted_key: Ed25519PublicKey) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise DistributionError("Signed CED release must be a JSON object.")
    expected = {
        "kind", "schema_version", "release_revision", "previous_release_sha256",
        "review_bundle_sha256", "publisher_key_fingerprint", "review_approvals",
        "rules", "revoked_rule_ids", "runtime_execution_authorized",
        "fidelity_certified_for_unseen_projects", "approval", "signature_ed25519",
    }
    body = {k: v for k, v in envelope.items() if k != "signature_ed25519"}
    if (set(envelope) != expected
            or envelope.get("kind") != "cutsceneai.ced.signed_release"
            or envelope.get("schema_version") != "1"
            or envelope.get("runtime_execution_authorized") is not False
            or envelope.get("fidelity_certified_for_unseen_projects") is not False
            or envelope.get("approval") != "INDEPENDENT_SIGNED_REVIEWS_KNOWLEDGE_ONLY"
            or envelope.get("publisher_key_fingerprint") != _fingerprint(trusted_key)
            or type(envelope.get("release_revision")) is not int
            or envelope["release_revision"] < 1
            or not isinstance(envelope.get("review_bundle_sha256"), str)
            or not _SHA.fullmatch(envelope["review_bundle_sha256"])
            or not isinstance(envelope.get("review_approvals"), list)
            or len(envelope["review_approvals"]) != 2
            or {entry.get("role") for entry in envelope["review_approvals"]
                if isinstance(entry, dict)} != {"PRIVACY", "NATIVE_EVIDENCE"}):
        raise DistributionError("Untrusted or malformed CED signed release manifest.")
    previous = envelope["previous_release_sha256"]
    if ((envelope["release_revision"] == 1 and previous is not None)
            or (envelope["release_revision"] > 1 and
                (not isinstance(previous, str) or not _SHA.fullmatch(previous)))):
        raise DistributionError("Invalid CED signed release predecessor.")
    for approval in envelope["review_approvals"]:
        if (not isinstance(approval, dict)
                or set(approval) != {
                    "role", "review_record_sha256", "native_evidence_sha256",
                    "heldout_report_sha256", "regression_report_sha256",
                }
                or any(not isinstance(value, str) or not _SHA.fullmatch(value)
                       for key, value in approval.items() if key != "role")):
            raise DistributionError("Signed CED reviewer proof metadata is invalid.")
    try:
        signature = envelope["signature_ed25519"]
        if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("Bad signature")
        trusted_key.verify(bytes.fromhex(signature), canonical(body))
    except (ValueError, InvalidSignature) as exc:
        raise DistributionError("CED release publisher signature is invalid.") from exc
    revocations = envelope.get("revoked_rule_ids")
    if (not isinstance(revocations, list) or len(revocations) > 64
            or len(set(revocations)) != len(revocations)
            or any(not isinstance(name, str) or not _ID.fullmatch(name)
                   for name in revocations)):
        raise DistributionError("CED revocation identities are invalid.")
    _validate_rules(envelope["rules"])
    if any(rule["rule_id"] in revocations for rule in envelope["rules"]):
        raise DistributionError("CED release includes an explicitly revoked rule.")
    return envelope


def install_release(release_file: Path, *, trust_key_file: Path,
                    store: Path, explicit_install_consent: bool) -> dict[str, Any]:
    if explicit_install_consent is not True:
        raise DistributionError("Explicit CED knowledge installation consent is required.")
    trusted = _publisher_key(trust_key_file)
    incoming = verify_release(read(release_file), trusted)
    if store.is_symlink() or not store.is_dir():
        raise DistributionError("CED signed release store must already exist and be safe.")
    active = store / "active.json"
    if active.is_symlink():
        raise DistributionError("Active CED release cannot be a symlink.")
    if active.exists():
        current = verify_release(read(active), trusted)
        if digest(incoming) == digest(current):
            return {
                "status": "SIGNED_SHARED_KNOWLEDGE_ALREADY_INSTALLED",
                "revision": current["release_revision"],
                "release_sha256": digest(current),
                "native_execution_authorized": False,
            }
        # Only advance along the signed predecessor chain. A rollback must
        # itself be published as a new authenticated revision.
        if (incoming["release_revision"] != current["release_revision"] + 1
                or incoming["previous_release_sha256"] != digest(current)):
            raise DistributionError(
                "CED release is stale, out of order or not a signed successor."
            )
    elif (incoming["release_revision"] != 1
          or incoming["previous_release_sha256"] is not None):
        raise DistributionError("First shared CED installation must begin at revision 1.")
    saved = json.dumps(incoming, indent=2, sort_keys=True) + "\n"
    archive = store / ("release-%06d.json" % incoming["release_revision"])
    temporary = store / "active.pending"
    # Reject changed or redirected pending data; only the exact same signed
    # bytes from an interrupted install may be resumed.
    for path in (archive, temporary):
        if path.is_symlink() or (path.exists() and
                (not path.is_file() or path.read_text(encoding="utf-8") != saved)):
            raise DistributionError("Conflicting or redirected interrupted CED installation.")
    if not archive.exists():
        with archive.open("x", encoding="utf-8") as stream:
            stream.write(saved)
            stream.flush()
            os.fsync(stream.fileno())
    if not temporary.exists():
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(saved)
            stream.flush()
            os.fsync(stream.fileno())
    os.replace(temporary, active)
    return {
        "status": "SIGNED_SHARED_KNOWLEDGE_INSTALLED",
        "revision": incoming["release_revision"],
        "release_sha256": digest(incoming),
        "native_execution_authorized": False,
    }


def installed_rules(store: Path, *, trust_key_file: Path) -> list[dict[str, Any]]:
    active = store / "active.json"
    if not active.exists():
        return []
    verified = verify_release(read(active), _publisher_key(trust_key_file))
    revoked = set(verified["revoked_rule_ids"])
    return [rule for rule in verified["rules"] if rule["rule_id"] not in revoked]
