"""Element 3.2: source-bound dependency scheduler (advisory, never a native executor).

The existing element plan is the only authority for occurrence identities and
registered action candidates. This module orders those occurrences, exposes
unsafe cycles / unproven ownership, and gates advisory candidates. In
particular, an execution wave is NOT a native dispatch authorization.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from typing import Any

import studio_element_plan as element_plan

VERSION = "1"
_WRITE_DOMAINS = {
    "animation.track": "transform",
    "camera.transform": "transform",
    "camera.fov": "camera_fov",
    "camera.cut": "camera_cut",
    "light.animation": "light",
    "event.state": "visibility",
}
_BLOCKED = frozenset({
    "SOURCE_DEPENDENCY_MISSING", "DEPENDENCY_CYCLE", "UPSTREAM_BLOCKED",
    "OWNERSHIP_CONFLICT", "UPSTREAM_NOT_PLANNED",
})


class ElementScheduleError(ValueError):
    """An advisory schedule is not independently grounded in its source."""


def _seconds(value: Any) -> float:
    """Interpret the canonical rational CSIR time, rejecting unproven ranges."""
    if not isinstance(value, dict) or not isinstance(value.get("rate"), dict):
        raise ValueError("Missing canonical Timeline time.")
    rate = value["rate"]
    numerator, denominator = rate.get("numerator"), rate.get("denominator")
    ticks = value.get("value")
    if (type(ticks) is not int or type(numerator) is not int
            or type(denominator) is not int or numerator <= 0
            or denominator <= 0):
        raise ValueError("Invalid canonical Timeline rate or ticks.")
    subframe = value.get("subframe")
    fractional = 0.0
    if subframe is not None:
        if (not isinstance(subframe, dict)
                or type(subframe.get("numerator")) is not int
                or type(subframe.get("denominator")) is not int
                or subframe["denominator"] <= 0):
            raise ValueError("Invalid canonical Timeline subframe.")
        fractional = subframe["numerator"] / subframe["denominator"]
    result = ((ticks + fractional) * denominator) / numerator
    if not math.isfinite(result):
        raise ValueError("Nonfinite Timeline time.")
    return result


def _ownership_conflicts(plan: dict, csir: dict) -> list[dict]:
    """Conservatively discover same-binding writers; emit NO raw Unity IDs."""
    by_location = {r["source_location"]: r for r in plan["elements"]}
    by_id = {r["occurrence_id"]: r for r in plan["elements"]}
    groups: dict[tuple[str, str], list[tuple[float, float, str, str]]] = defaultdict(list)
    found: set[tuple[str, tuple[str, ...]]] = set()

    def flag(kind: str, *ids: str) -> None:
        members = tuple(sorted(set(ids)))
        if members:
            found.add((kind, members))

    tracks = csir.get("tracks", [])
    for ti, track in enumerate(tracks):
        if not isinstance(track, dict) or track.get("muted") is True:
            continue
        domain = _WRITE_DOMAINS.get(track.get("ced_type"))
        if domain is None:
            continue
        location = f"tracks[{ti}]"
        owner = by_location[location]
        track_id = owner["occurrence_id"]
        # The existing source-bound dependency resolver, not a second raw-ID
        # lookup, is authoritative for ownership.
        binding = [d for d in owner["dependencies"]
                   if by_id[d]["source_kind"] == "entities"]
        if len(binding) != 1:
            if domain == "transform" and track.get("sections"):
                flag("UNPROVEN_TRACK_BINDING", track_id)
            continue
        key = (binding[0], domain)
        sections = track.get("sections", [])
        if not isinstance(sections, list):
            raise ElementScheduleError("Malformed source Timeline sections.")
        for si, section in enumerate(sections):
            section_id = by_location[f"{location}.sections[{si}]"]["occurrence_id"]
            try:
                start, end = _seconds(section["start"]), _seconds(section["end"])
                if start < 0 or end <= start:
                    raise ValueError("Invalid source clip span.")
                native = section.get("native_payload") or {}
                if not isinstance(native, dict):
                    raise ValueError("Invalid source blend evidence.")
                # -1 is Unity's "not blended" sentinel; positive ease still
                # matters. A blend/ease duration is not proof of a native bake.
                eased = False
                for side in ("in", "out"):
                    blend = float(native.get(f"blend_{side}_seconds", 0.0))
                    ease = float(native.get(f"ease_{side}_seconds", 0.0))
                    if (not math.isfinite(blend) or not math.isfinite(ease)
                            or (blend < 0 and blend != -1.0) or ease < 0):
                        raise ValueError("Invalid blend envelope.")
                    duration = blend if blend > 0 else ease
                    if duration > end - start + 1e-7:
                        raise ValueError("Blend exceeds clip span.")
                    eased |= duration > 0
            except (TypeError, ValueError, KeyError, ZeroDivisionError, OverflowError):
                flag("UNPROVEN_TIMING_OR_BLEND", track_id, section_id)
                continue
            if domain == "transform" and eased:
                flag("UNBAKED_TIMELINE_BLEND", track_id, section_id)
            groups[key].append((start, end, track_id, section_id))

    for (_binding, domain), clips in sorted(groups.items()):
        if domain == "transform":
            track_ids = {r[2] for r in clips}
            if len(track_ids) > 1:
                # Existing native Timeline policy requires one measured
                # owner for source transform / animation blending.
                flag("MULTIPLE_TRANSFORM_TRACK_WRITERS", *(
                    [r[2] for r in clips] + [r[3] for r in clips]
                ))
        ordered = sorted(clips, key=lambda r: (r[0], r[1], r[2], r[3]))
        max_end = -math.inf
        max_row = None
        for row in ordered:
            if max_row is not None and row[0] < max_end - 1e-7:
                flag("OVERLAPPING_SECTION_WRITERS",
                     max_row[2], max_row[3], row[2], row[3])
            if row[1] > max_end:
                max_end, max_row = row[1], row
    return [
        {"kind": kind, "occurrence_ids": list(ids)}
        for kind, ids in sorted(found)
    ]


def _cycle_members(remaining: set[str], deps: dict[str, list[str]],
                   dependents: dict[str, list[str]]) -> set[str]:
    """Iterative SCC detection; a downstream node is not mislabeled a cycle."""
    visited: set[str] = set()
    finished: list[str] = []
    for root in sorted(remaining):
        if root in visited:
            continue
        stack: list[tuple[str, bool]] = [(root, False)]
        while stack:
            node, exit_node = stack.pop()
            if exit_node:
                finished.append(node)
            elif node not in visited:
                visited.add(node)
                stack.append((node, True))
                stack.extend((d, False) for d in reversed(sorted(deps[node]))
                             if d in remaining and d not in visited)
    visited.clear()
    cycles: set[str] = set()
    for root in reversed(finished):
        if root in visited:
            continue
        component: set[str] = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            stack.extend(n for n in dependents[node]
                         if n in remaining and n not in visited)
        if len(component) > 1 or root in deps[root]:
            cycles.update(component)
    return cycles


def build(plan: dict[str, Any], csir: dict[str, Any]) -> dict[str, Any]:
    """Construct a stable DAG and explicit blockers for ALL source occurrences.

    Every candidate requires separately verified native preflight. No schedule
    may modify the native converter or assert that a dependency was executed.
    """
    if (not isinstance(plan, dict) or not isinstance(csir, dict)
            or plan.get("no_native_execution_permission") is not True
            or plan.get("native_conversion_executed") is not False
            or plan.get("source_csir_sha256") != element_plan._digest(csir)
            or plan.get("element_plan_sha256") != element_plan._digest({
                k: v for k, v in plan.items() if k != "element_plan_sha256"
            })):
        raise ElementScheduleError("Dependency schedule requires exact read-only plan evidence.")
    source = plan.get("elements")
    if (not isinstance(source, list) or len(source) != plan.get("source_occurrence_count")
            or len(source) > element_plan.MAX_OCCURRENCES):
        raise ElementScheduleError("Source occurrence inventory is incomplete.")
    by_id = {row["occurrence_id"]: row for row in source}
    if len(by_id) != len(source):
        raise ElementScheduleError("Duplicate occurrence identities cannot be scheduled.")
    deps: dict[str, list[str]] = {}
    dependents: dict[str, list[str]] = defaultdict(list)
    for ident, row in by_id.items():
        links = row["dependencies"]
        if (not isinstance(links, list) or len(links) != len(set(links))
                or any(link not in by_id for link in links)):
            raise ElementScheduleError("Invalid or nonexistent occurrence dependency.")
        deps[ident] = links
        for dep in links:
            dependents[dep].append(ident)

    degree = {ident: len(links) for ident, links in deps.items()}
    ready = [ident for ident, count in degree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    waves: list[list[str]] = []
    wave_index: dict[str, int] = {}
    while ready:
        wave: list[str] = []
        while ready:
            wave.append(heapq.heappop(ready))
        waves.append(wave)
        following: list[str] = []
        for ident in wave:
            wave_index[ident] = len(waves) - 1
            order.append(ident)
            for child in dependents[ident]:
                degree[child] -= 1
                if degree[child] == 0:
                    heapq.heappush(following, child)
        ready = following
    unscheduled = set(by_id) - set(order)
    cycles = _cycle_members(unscheduled, deps, dependents)
    conflicts = _ownership_conflicts(plan, csir)
    conflicted = {ident for finding in conflicts for ident in finding["occurrence_ids"]}
    status: dict[str, str] = {}
    for ident in order:
        row = by_id[ident]
        if row["unresolved_dependencies"]:
            status[ident] = "SOURCE_DEPENDENCY_MISSING"
        elif ident in conflicted:
            status[ident] = "OWNERSHIP_CONFLICT"
        elif any(status[d] in _BLOCKED for d in deps[ident]):
            status[ident] = "UPSTREAM_BLOCKED"
        elif row["selected_action"] == "report_only":
            status[ident] = "REPORT_ONLY"
        elif any(by_id[d]["selected_action"] == "report_only" for d in deps[ident]):
            status[ident] = "UPSTREAM_NOT_PLANNED"
        else:
            status[ident] = "ADVISORY_PREFLIGHT_REQUIRED"
    for ident in unscheduled:
        status[ident] = "DEPENDENCY_CYCLE" if ident in cycles else "UPSTREAM_BLOCKED"
    nodes = [{
        "occurrence_id": ident,
        "dependencies": list(deps[ident]),
        "wave_index": wave_index.get(ident),
        "status": status[ident],
        "selected_action": by_id[ident]["selected_action"],
    } for ident in by_id]
    executable_proposals = [
        [ident for ident in wave if status[ident] == "ADVISORY_PREFLIGHT_REQUIRED"]
        for wave in waves
    ]
    result = {
        "kind": "cutsceneai.studio.element_dependency_schedule",
        "schema_version": VERSION,
        "element_plan_sha256": plan["element_plan_sha256"],
        "source_csir_sha256": plan["source_csir_sha256"],
        "source_occurrence_count": len(source),
        "native_execution_permitted": False,
        "fidelity_verified": False,
        "topological_waves": waves,
        "unscheduled_occurrences": sorted(unscheduled),
        "advisory_candidate_waves": [wave for wave in executable_proposals if wave],
        "conflicts": conflicts,
        "nodes": nodes,
    }
    result["schedule_sha256"] = element_plan._digest(result)
    return result


def verify(schedule: dict[str, Any], plan: dict[str, Any],
           csir: dict[str, Any]) -> None:
    """Rebuild from source to prevent forged order, hidden conflicts, or gaps."""
    expected = build(plan, csir)
    if not isinstance(schedule, dict) or schedule != expected:
        raise ElementScheduleError("Dependency schedule is stale, incomplete or tampered.")
