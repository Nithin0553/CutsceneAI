"""Local-only append-only registry for genuinely novel CED observations.

Events are deliberately redacted: no source paths, user asset names, native
class names or source CSIR content are written to disk. Known-partial and
mapping-missing findings stay in the preflight coverage report, not this queue.
One operator process should write to a registry at a time.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REGISTRY_VERSION = "0.1.0"
NOVEL_STATES = frozenset({"UNKNOWN_CED", "UNKNOWN_NATIVE", "NEEDS_EVIDENCE"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_CONCEPT = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class DiscoveryRegistryError(ValueError):
    """Refuse invalid, ambiguous, or privacy-unsafe discovery registry input."""


def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_ced(value: Any) -> str:
    token = str(value or "")
    # A malicious / unconventional CED may include project paths or filenames.
    # Preserve the stable signature for triage, not the raw untrusted text.
    return token if _SAFE_CONCEPT.fullmatch(token) else "<unclassified>"


def discoveries(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Summarize one source's novel components (one per stable fingerprint)."""
    if report.get("kind") != "cutsceneai.ced_preflight":
        raise DiscoveryRegistryError("Expected a CED preflight report.")
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise DiscoveryRegistryError("CED report requires its complete findings array.")
    for field in ("ced_version", "capabilities_version"):
        if not isinstance(report.get(field), str) or not report[field]:
            raise DiscoveryRegistryError(f"CED preflight missing {field}.")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        if not isinstance(finding, dict):
            raise DiscoveryRegistryError("Invalid CED finding.")
        if finding.get("active") is not True or finding.get("state") not in NOVEL_STATES:
            continue
        fingerprint = finding.get("feature_fingerprint")
        if not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint):
            raise DiscoveryRegistryError("Discovery fingerprint must be SHA-256.")
        grouped[fingerprint].append(finding)

    source_hash = report.get("source_csir_sha256")
    if source_hash is not None:
        if not isinstance(source_hash, str) or not _SHA256.fullmatch(source_hash):
            raise DiscoveryRegistryError("Source CSIR digest must be SHA-256.")
    else:
        # Backward compatibility for V1/V2 preflight files without source hash.
        # Require a nonempty source identity to avoid conflating unrelated data.
        cutscene_id = str(report.get("source_cutscene_id", "")).strip()
        if not cutscene_id:
            raise DiscoveryRegistryError(
                "Report needs source_csir_sha256 or source_cutscene_id."
            )
        source_hash = _sha(cutscene_id)

    results = []
    for fingerprint in sorted(grouped):
        observations = grouped[fingerprint]
        statuses = {f["state"] for f in observations}
        kinds = {str(f.get("kind", "")) for f in observations}
        ceds = {_safe_ced(f.get("ced")) for f in observations}
        if len(statuses) != 1 or len(kinds) != 1 or len(ceds) != 1:
            raise DiscoveryRegistryError(
                "One discovery fingerprint has conflicting classification."
            )
        candidate = {
            "version": REGISTRY_VERSION,
            "kind": "ced.discovery",
            "fingerprint": fingerprint,
            "classification": next(iter(statuses)),
            "feature_kind": next(iter(kinds)),
            "ced": next(iter(ceds)),
            "source_digest": source_hash,
            "ced_version": report["ced_version"],
            "capabilities_version": report["capabilities_version"],
            "ced_sha256": str(report.get("ced_sha256", "")),
            "capabilities_sha256": str(report.get("capabilities_sha256", "")),
            "occurrences": len(observations),
        }
        # Event ID is deterministic per fingerprint, source snapshot and rules.
        candidate["observation_id"] = _sha([
            candidate["fingerprint"], candidate["source_digest"],
            candidate["ced_version"], candidate["capabilities_version"],
            candidate["ced_sha256"], candidate["capabilities_sha256"],
        ])
        results.append(candidate)
    return results


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if not path.is_file():
        raise DiscoveryRegistryError("Discovery registry path is not a file.")
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise DiscoveryRegistryError(f"Empty registry line {number}.")
        try:
            data = json.loads(line)
        except ValueError as exc:
            raise DiscoveryRegistryError(f"Malformed registry line {number}.") from exc
        if not isinstance(data, dict) or data.get("version") != REGISTRY_VERSION:
            raise DiscoveryRegistryError(f"Unknown registry schema at line {number}.")
        if not isinstance(data.get("observation_id"), str) or not _SHA256.fullmatch(data["observation_id"]):
            raise DiscoveryRegistryError(f"Invalid observation ID on line {number}.")
        if not isinstance(data.get("fingerprint"), str) or not _SHA256.fullmatch(data["fingerprint"]):
            raise DiscoveryRegistryError(f"Invalid fingerprint on line {number}.")
        entries.append(data)
    ids = [x["observation_id"] for x in entries]
    if len(ids) != len(set(ids)):
        raise DiscoveryRegistryError("Duplicate observation ID in existing registry.")
    return entries


def record(
    report: Mapping[str, Any],
    registry_path: str | Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add only genuinely new observation events.

    No file is created if a report has no novel unknowns; existing events
    are never replaced, and no GitHub/email/notification action is executed.
    """
    path = Path(registry_path)
    items = discoveries(report)
    existing = read_events(path)
    seen = {x["observation_id"] for x in existing}
    known_fingerprints = {x["fingerprint"] for x in existing}
    to_add = [x for x in items if x["observation_id"] not in seen]
    new_signatures = {x["fingerprint"] for x in to_add} - known_fingerprints
    if to_add and not dry_run:
        if not path.parent.is_dir():
            raise DiscoveryRegistryError("Registry parent directory does not exist.")
        timestamp = datetime.now(timezone.utc).isoformat()
        lines = [
            json.dumps(
                {**item, "recorded_at_utc": timestamp}, sort_keys=True,
                ensure_ascii=False,
            ) + "\n"
            for item in to_add
        ]
        # Append-only with exclusive creation. Single-writer semantics until
        # an explicit locking implementation is added.
        with path.open("a" if path.exists() else "x", encoding="utf-8") as handle:
            handle.writelines(lines)
    return {
        "registry_kind": "cutsceneai.ced_discovery_registry_summary",
        "novel_observation_groups": len(items),
        "new_feature_signatures": len(new_signatures),
        "new_observations": len(to_add),
        "already_recorded": len(items) - len(to_add),
        "total_events_after_commit": len(existing) + (0 if dry_run else len(to_add)),
        "dry_run": dry_run,
        "remote_notifications_sent": False,
        "ced_modified": False,
    }
