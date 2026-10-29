"""Deterministic, read-only CED-first discovery for source cutscenes.

This audit reports what the canonical dictionary *means* separately from what
the active Unity -> Unreal adapter *may construct*. It never infers a verified
conversion from membership in CED, a generic fallback type, or a numeric match.
All issues and occurrence signatures are local unless the user exports them.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts" / "dictionary"
CED_PATH = CONTRACTS / "cutscene-elements-v0.1.json"
CAPABILITIES_PATH = CONTRACTS / "unity-unreal-preflight-v0.1.json"

DISCOVERY_STATES = frozenset({
    "UNKNOWN_CED", "UNKNOWN_NATIVE", "NEEDS_EVIDENCE",
    "KNOWN_UNSUPPORTED", "KNOWN_PARTIAL", "MISSING_TARGET_MAPPING",
})
BLOCKING_STATES = frozenset({
    "UNKNOWN_CED", "UNKNOWN_NATIVE", "NEEDS_EVIDENCE",
    "KNOWN_UNSUPPORTED", "MISSING_TARGET_MAPPING", "KNOWN_PARTIAL",
})
SUPPORTED = "SUPPORTED_UNVERIFIED"


class CEDPreflightError(ValueError):
    """A referenced dictionary/capability definition is missing or malformed."""


def _read(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise CEDPreflightError(f"Unable to load CED reference: {path.name}") from exc
    if not isinstance(obj, dict):
        raise CEDPreflightError(f"Expected JSON object in {path.name}")
    return obj


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(kind: str, ced: str, native: str, semantic: str) -> str:
    # Do not include local project file paths, object names or source content:
    # a new scene with the same novel native feature yields the same signature.
    canonical = json.dumps(
        [kind, ced, native, semantic], separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _mapping_name(mapping: Mapping[str, Any], name: str, key: str) -> bool:
    entry = mapping.get(key, {})
    if not isinstance(entry, dict):
        return False
    mapped = entry.get(name)
    if key == "entities":
        return isinstance(mapped, dict) and bool(mapped.get("actor_label"))
    return bool(mapped)


def _curve_semantic(
    curve: Mapping[str, Any], known: set[str], capabilities: Mapping[str, Any],
    *, unity_animation_clip: bool = False,
) -> tuple[str, str, str]:
    raw = str(curve.get("canonical_semantic") or "").strip()
    native = str(curve.get("property_name") or "").strip()
    aliases = capabilities.get("curve_aliases", {})
    alias = next(
        (target for prefix, target in aliases.items()
         if (raw or native).lower() == prefix.lower()
         or (prefix.endswith(".")
             and (raw or native).lower().startswith(prefix.lower()))),
        "",
    )
    if alias:
        return alias, native, "ALIAS"
    # Extractor-specific canonical channels have known engine-neutral meaning.
    # Do not edit or expand the core CED taxonomy for each native axis.
    for rule in capabilities.get("canonical_curve_patterns", []):
        if re.fullmatch(str(rule["pattern"]), raw):
            return str(rule["ced"]), native, "UNITY_CANONICAL_EXTENSION"
    # Unity's AnimationClip root and Humanoid muscle curves commonly lack a
    # canonical_semantic field. Recognize only explicit documented patterns in
    # a Unity AnimationTrack/AnimationClip context; do not assume that these
    # channels are successfully transferred or retargeted.
    if not raw and unity_animation_clip:
        for rule in capabilities.get("native_curve_patterns", []):
            if re.fullmatch(str(rule["pattern"]), native):
                return str(rule["ced"]), native, "UNITY_ANIMATION_CLIP_CHANNEL"
    if raw in known:
        return raw, native, "CANONICAL"
    for prefix in ("transform.position", "transform.rotation", "transform.scale"):
        if raw.startswith(prefix + ".") and raw[len(prefix)+1:] in {"x", "y", "z", "w"}:
            return prefix, native, "CANONICAL_CHANNEL"
    if raw:
        return raw, native, "UNRECOGNIZED"
    return "", native, "NO_CANONICAL"


def audit(
    csir: Mapping[str, Any],
    mapping: Mapping[str, Any],
    *,
    ced: Mapping[str, Any] | None = None,
    capabilities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit source semantics before planner/Unreal mutation; no I/O unless loading CED.

    All source entities/assets/tracks/sections/curves/relationships are visited.
    Active-element alerts are deduplicated by native/semantic feature signature,
    while every occurrence has a distinct source index and ID.
    """
    ced = ced if ced is not None else _read(CED_PATH)
    capabilities = capabilities if capabilities is not None else _read(CAPABILITIES_PATH)
    categories = ced.get("categories")
    if not isinstance(categories, dict) or any(
        not isinstance(rows, list) or not all(isinstance(x, str) for x in rows)
        for rows in categories.values()
    ):
        raise CEDPreflightError("CED categories must contain lists of semantic IDs")
    if capabilities.get("source_engine") != "unity" or capabilities.get("target_engine") != "unreal":
        raise CEDPreflightError("Unexpected adapter capability engine pair")
    known = {value for values in categories.values() for value in values}
    if not known:
        raise CEDPreflightError("CED has no semantic entries")
    for domain in ("tracks", "sections", "curve_semantics"):
        for ced_id in capabilities.get(domain, {}):
            if ced_id not in known:
                raise CEDPreflightError(
                    f"Adapter claims capability for unknown CED element: {ced_id}"
                )
    for domain in ("generic_native_tracks", "generic_native_sections"):
        for entry in capabilities.get(domain, {}).values():
            if entry.get("ced") not in known:
                raise CEDPreflightError(
                    f"Native alias references unknown CED element: {entry.get('ced')}"
                )
    for domain in ("canonical_curve_patterns", "native_curve_patterns"):
        for entry in capabilities.get(domain, []):
            if entry.get("ced") not in known or not isinstance(entry.get("pattern"), str):
                raise CEDPreflightError(f"Invalid CED pattern entry in {domain}")
            try:
                re.compile(entry["pattern"])
            except re.error as exc:
                raise CEDPreflightError(f"Invalid CED pattern in {domain}: {exc}") from exc

    findings: list[dict[str, Any]] = []
    def add(
        kind: str, path: str, source_id: str, ced_id: str, native: str,
        state: str, explanation: str, *, active: bool = True,
        semantic: str = "",
    ) -> None:
        signature = _fingerprint(kind, ced_id, native, semantic)
        findings.append({
            "kind": kind,
            "source_location": path,
            "source_id": source_id,
            "ced": ced_id,
            "native_type": native,
            "state": state,
            "active": active,
            "reason": explanation,
            "feature_fingerprint": signature,
        })

    def classify(
        kind: str, path: str, source_id: str, ced_id: str, native: str = "",
        *, active: bool = True,
        generic: str = "", semantic: str = "",
    ) -> None:
        if not ced_id:
            state = "NEEDS_EVIDENCE"
            detail = "Source did not provide a canonical CED semantic ID."
        elif ced_id not in known:
            state = "UNKNOWN_CED"
            detail = "No corresponding concept exists in the versioned CED dictionary."
        elif generic and ced_id == generic:
            table = capabilities.get(
                "generic_native_tracks" if kind == "track" else "generic_native_sections", {}
            )
            recognized = table.get(native)
            if recognized:
                state = recognized["state"]
                detail = "Known generic native type, but its actual transfer requires review."
                ced_id = recognized["ced"]
            elif native:
                state = "UNKNOWN_NATIVE"
                detail = (
                    "Generic CED fallback hides a native behavior not recognized by "
                    "the engine-specific mapping registry."
                )
            else:
                state = "NEEDS_EVIDENCE"
                detail = "Generic CED fallback has no native type; semantics are ambiguous."
        elif kind in {"track", "section", "curve"}:
            group = {"track": "tracks", "section": "sections", "curve": "curve_semantics"}[kind]
            configured = capabilities.get(group, {}).get(ced_id)
            state = (configured.get("state") if isinstance(configured, dict) else configured) or "KNOWN_UNSUPPORTED"
            detail = configured.get("detail", "") if isinstance(configured, dict) else ""
            if not detail:
                detail = (
                    "Engine strategy is only a candidate, pending real-engine readback."
                    if state == SUPPORTED else
                    "Known canonical concept, but no verified target capability is registered."
                )
        else:
            state = SUPPORTED
            detail = (
                "CED concept is recognized; object/asset mapping and target "
                "realization remain separate and unverified."
            )
        add(kind, path, source_id, ced_id, native, state, detail,
            active=active, semantic=semantic)

    entities = {
        str(row.get("entity_id", "")): row
        for row in csir.get("entities", []) if isinstance(row, dict)
    }
    asset_index = {
        str(row.get("asset_id", "")): row
        for row in csir.get("assets", []) if isinstance(row, dict)
    }
    # A Timeline AnimationClip can contain property curves for a prop, camera
    # or light. Those curves are realized directly as Unreal Sequencer keys;
    # they do NOT need an imported Unreal AnimSequence. Only a skeletal
    # animation track bound to a character, or an audio track, consumes a
    # separately mapped native target asset. Match csir_plan.build_plan().
    required_asset_ids: set[str] = set()
    for track in csir.get("tracks", []):
        if (not isinstance(track, dict) or track.get("muted") is True
            or not track.get("sections")):
            continue
        track_kind = str(track.get("ced_type") or "")
        bound = entities.get(str(track.get("binding_entity_id") or ""), {})
        needs_clip = (
            track_kind == "animation.track"
            and bound.get("ced_type") == "entity.character"
        )
        needs_audio = track_kind == "audio.track"
        if not (needs_clip or needs_audio):
            continue
        for section in track.get("sections", []):
            if not isinstance(section, dict):
                continue
            asset_id = str(section.get("payload", {}).get("asset_id") or "")
            if asset_id:
                required_asset_ids.add(asset_id)

    for i, entity in enumerate(csir.get("entities", [])):
        if not isinstance(entity, dict):
            continue
        path = f"entities[{i}]"
        eid = str(entity.get("entity_id") or "")
        classify("entity", path, eid, str(entity.get("ced_type") or ""),
                 str(entity.get("metadata", {}).get("native_type") or ""))
    for i, asset in enumerate(csir.get("assets", [])):
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("asset_id") or "")
        path = f"assets[{i}]"
        classify("asset", path, aid, str(asset.get("ced_type") or ""),
                 str(asset.get("metadata", {}).get("native_type") or ""))
        if (aid in required_asset_ids
            and str(asset.get("ced_type") or "") in {"animation.clip", "audio.asset"}
            and not _mapping_name(mapping, str(asset.get("name") or ""), "assets")
        ):
            add("mapping", path, aid, str(asset.get("ced_type") or ""), "",
                "MISSING_TARGET_MAPPING",
                "An active source clip references this asset, but no target asset path was mapped.")

    for i, track in enumerate(csir.get("tracks", [])):
        if not isinstance(track, dict):
            continue
        path = f"tracks[{i}]"
        tid = str(track.get("track_id") or "")
        inactive = track.get("muted") is True or not track.get("sections")
        ced_id = str(track.get("ced_type") or "")
        native = str(track.get("metadata", {}).get("native_type") or "")
        classify("track", path, tid, ced_id, native, active=not inactive,
                 generic="timeline.track")
        eid = str(track.get("binding_entity_id") or "")
        needs_actor = ced_id in {
            "animation.track", "camera.transform", "camera.cut", "light.animation"
        }
        if not inactive and needs_actor:
            entity = entities.get(eid, {})
            if not entity or not _mapping_name(
                mapping, str(entity.get("name") or ""), "entities"
            ):
                add("mapping", path, tid, ced_id, native, "MISSING_TARGET_MAPPING",
                    "Active source track has no uniquely mapped target actor.")
        for j, section in enumerate(track.get("sections", [])):
            if not isinstance(section, dict):
                continue
            section_path = f"{path}.sections[{j}]"
            sid = str(section.get("section_id") or "")
            section_kind = str(section.get("ced_type") or "")
            native_type = str(section.get("native_payload", {}).get("native_asset_type") or "")
            classify("section", section_path, sid, section_kind, native_type,
                     active=not inactive, generic="timeline.clip")
            curves = section.get("payload", {}).get("animation", {}).get("curves", [])
            for k, curve in enumerate(curves if isinstance(curves, list) else []):
                if not isinstance(curve, dict):
                    continue
                curve_path = f"{section_path}.payload.animation.curves[{k}]"
                parsed, native_channel, provenance = _curve_semantic(
                    curve, known, capabilities,
                    unity_animation_clip=(
                        ced_id == "animation.track"
                        and section_kind == "animation.section"
                        and native_type in {"UnityEngine.AnimationClip",
                                            "UnityEngine.Timeline.AnimationPlayableAsset"}
                    ),
                )
                if not parsed and native_channel:
                    add("curve", curve_path, sid, "", native_channel,
                        "NEEDS_EVIDENCE",
                        "Native property channel has no proven canonical semantic.",
                        active=not inactive, semantic=provenance)
                else:
                    classify("curve", curve_path, sid, parsed, native_channel,
                             active=not inactive, semantic=provenance)

    for i, relationship in enumerate(csir.get("relationships", [])):
        if not isinstance(relationship, dict):
            continue
        classify("relationship", f"relationships[{i}]",
                 str(relationship.get("relationship_id") or ""),
                 str(relationship.get("ced_type") or ""))
    alerts = [f for f in findings if f["active"] and f["state"] in DISCOVERY_STATES]
    # A known-but-partial converter needs user review, but is not a
    # *newly discovered semantic*. Keep these counts separate.
    newly_discovered = [
        row for row in alerts
        if row["state"] in {"UNKNOWN_CED", "UNKNOWN_NATIVE", "NEEDS_EVIDENCE"}
    ]
    fingerprints = sorted({row["feature_fingerprint"] for row in newly_discovered})
    # Group repetitive section and bone-curve observations for the user while
    # retaining every indexed source occurrence in the inspectable JSON.
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for finding in alerts:
        key = (str(finding["state"]), str(finding["ced"]))
        grouped.setdefault(key, []).append(finding)
    review_groups = [
        {
            "state": state,
            "ced": ced_id,
            "occurrences": len(rows),
            "distinct_native_types": len({r["native_type"] for r in rows}),
            "sample_locations": [r["source_location"] for r in rows[:3]],
            "example_native_types": sorted({r["native_type"] for r in rows})[:3],
        }
        for (state, ced_id), rows in sorted(grouped.items())
    ]
    return {
        "kind": "cutsceneai.ced_preflight",
        "version": "0.1.0",
        "ced_version": str(ced.get("version", "")),
        "ced_sha256": _sha(CED_PATH) if CED_PATH.is_file() else "",
        "capabilities_version": str(capabilities.get("version", "")),
        "capabilities_sha256": _sha(CAPABILITIES_PATH) if CAPABILITIES_PATH.is_file() else "",
        "source_cutscene_id": str(csir.get("cutscene_id", "")),
        "target_engine": "unreal",
        "status": "REVIEW_REQUIRED" if alerts else "READY_FOR_ENGINE_PREFLIGHT",
        "strict_transfer_allowed": not any(x["state"] in BLOCKING_STATES for x in alerts),
        "counts": dict(sorted(Counter(x["state"] for x in findings).items())),
        "active_alert_count": len(alerts),
        "review_group_count": len(review_groups),
        "review_groups": review_groups,
        "unique_discovery_count": len(fingerprints),
        "discovery_fingerprints": fingerprints,
        "findings": findings,
        "note": (
            "Supported means a known structural converter exists, not target fidelity. "
            "Review unknowns before best-effort transfer; CED is never updated by this run."
        ),
    }
