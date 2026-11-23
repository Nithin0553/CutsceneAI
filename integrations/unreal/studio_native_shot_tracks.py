"""Source-bound native Unreal cinematic shot-track construction.

This is an explicitly invoked, reviewed native adapter. It does not register
LLM authority, synthesize an unavailable child sequence, or claim Unity mixer
equivalence. Child sequences must already exist as verified native assets.

The source retains time ordering; no unsupported source timewarps or overlaps
are silently converted to native cinematic sections.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


class NativeShotError(ValueError):
    """Original shot timing, owner, or compensating rollback is unverified."""


_ASSET = re.compile(r"/Game(?:/[A-Za-z0-9_]+)+")
_SHA = re.compile(r"[a-f0-9]{64}")
_MAX_SHOTS = 128


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _time(row: dict) -> float:
    try:
        clock = row["rate"]
        value = float(row["value"])
        numerator = clock["numerator"]
        denominator = clock["denominator"]
        if (type(numerator) is not int or type(denominator) is not int
                or not (0 < numerator <= 240000 and 0 < denominator <= 100000)
                or not math.isfinite(value)):
            raise ValueError("Invalid source timebase")
        value *= denominator/numerator
        if "subframe" in row:
            sub=row["subframe"]
            value += sub["numerator"]/sub["denominator"]*denominator/numerator
    except (TypeError,KeyError,ValueError,ZeroDivisionError,OverflowError) as exc:
        raise NativeShotError("Original source section timebase is invalid.") from exc
    if not math.isfinite(value):
        raise NativeShotError("Source shot timestamp must be finite.")
    return value


def compile_shots(csir: dict, approval: dict, *,
                  csir_sha256: str) -> dict:
    """Compile only explicitly approved, consecutive nonoverlapping shots."""
    if (not isinstance(csir,dict) or not isinstance(approval,dict)
            or not isinstance(csir.get("tracks"),list)
            or not _SHA.fullmatch(str(csir_sha256))):
        raise NativeShotError("Immutable source CSIR identity is required.")
    if (approval.get("kind") != "cutsceneai.studio.approved_native_nested_shots"
            or approval.get("schema_version") != "1"
            or approval.get("source_csir_sha256") != csir_sha256
            or approval.get("reviewed_native_sequence_owners") is not True):
        raise NativeShotError("Reviewed source-specific shot/child ownership is missing.")
    parent = approval.get("parent_sequence_path")
    if not isinstance(parent,str) or not _ASSET.fullmatch(parent):
        raise NativeShotError("Parent Level Sequence path is not a /Game asset.")
    rate = csir.get("timing",{}).get("display_rate") or csir.get("timing",{}).get("source_rate")
    if not isinstance(rate,dict):
        raise NativeShotError("Source display rate is unavailable.")
    numerator,denominator = rate.get("numerator"),rate.get("denominator")
    if (type(numerator) is not int or type(denominator) is not int
            or numerator <= 0 or denominator <= 0):
        raise NativeShotError("Source display rate is not integral.")
    fps = numerator/denominator
    tracks=[track for track in csir["tracks"]
            if isinstance(track,dict) and track.get("ced_type")=="cinematic.shot"
            and track.get("muted") is not True]
    if len(tracks)!=1 or not isinstance(tracks[0].get("sections"),list):
        raise NativeShotError("One unmuted original shot owner is required.")
    track=tracks[0]
    sections=track["sections"]
    approvals=approval.get("shots")
    if (not 1<=len(sections)<=_MAX_SHOTS
            or not isinstance(approvals,list) or len(approvals)!=len(sections)):
        raise NativeShotError("Reviewed shot roster must cover exactly all source sections.")
    if any(track.get(key) not in (None,False,0,"") for key in
           ("subsequence","nested_sequence","timewarp","time_warp",
            "weighted_blend","time_scale_curve")):
        raise NativeShotError("Unresolved track retiming/ownership prohibits native shot creation.")
    emitted=[]
    seen=set()
    for item,review in zip(sections,approvals):
        if not isinstance(item,dict) or not isinstance(review,dict):
            raise NativeShotError("Malformed source shot or approved native sequence.")
        section_id=item.get("section_id")
        child=review.get("child_sequence_path")
        if (not isinstance(section_id,str) or not section_id
                or section_id in seen or review.get("section_id")!=section_id
                or not isinstance(child,str) or not _ASSET.fullmatch(child)
                or child==parent):
            raise NativeShotError("Shot child asset/section identity is missing or self-referential.")
        seen.add(section_id)
        payload=item.get("native_payload") or {}
        if (not isinstance(payload,dict)
                or any(payload.get(key) not in (None,False,0,"") for key in
                       ("blend_in_seconds","blend_out_seconds","ease_in_seconds",
                        "ease_out_seconds","timewarp","time_warp",
                        "weighted_blend","nested_sequence"))
                or item.get("time_scale",1)!=1):
            raise NativeShotError("Source shot blend/retime needs separately measured native mapping.")
        start=_time(item["start"])*fps
        end=_time(item["end"])*fps
        first,last=round(start),round(end)
        if (not 0<=first<last<=100000
                or abs(start-first)>1e-6 or abs(end-last)>1e-6):
            raise NativeShotError("Shot boundaries must land on exact source display frames.")
        emitted.append({"section_id":section_id,
                        "child_sequence_path":child,
                        "start_frame":first,"end_frame":last})
    emitted.sort(key=lambda item:item["start_frame"])
    if emitted[0]["start_frame"] != 0 or any(
            a["end_frame"] != b["start_frame"]
            for a,b in zip(emitted,emitted[1:])):
        raise NativeShotError(
            "Source shots must cover a consecutive, nonoverlapping root Timeline."
        )
    expected_duration = csir.get("timing",{}).get("duration_seconds")
    if (type(expected_duration) not in (int,float)
            or not math.isfinite(expected_duration)
            or abs(emitted[-1]["end_frame"]/fps-expected_duration)>1e-6):
        raise NativeShotError("Source shot coverage does not match playback duration.")
    document={
        "kind":"cutsceneai.studio.source_bound_native_shot_plan",
        "schema_version":"1",
        "source_csir_sha256":csir_sha256,
        "source_cutscene_id":csir.get("cutscene_id"),
        "source_track_id":track.get("track_id"),
        "parent_sequence_path":parent,
        "source_display_rate":rate,
        "shots":emitted,
        "native_shots_generated":False,
        "native_reopened_playback_verified":False,
        "blended_or_retimed_timeline_verified":False,
    }
    document["canonical_plan_sha256"]=_digest(document)
    return document


def _asset_path(asset: Any) -> str:
    return str(asset.get_path_name()).split(".",1)[0]


def _class(asset: Any) -> str:
    return str(asset.get_class().get_name())


def realize(api: Any, source: dict, approval: dict, plan: dict, *,
            source_sha256: str) -> dict:
    """Write one bounded native shot track; rollback if immediate save fails.

    Invoke in the user-approved target Unreal Editor, not in the model.
    Recompute the exact plan, preflight every child and require fresh editor
    native ownership and readback before the first shot mutation.
    """
    if plan!=compile_shots(source,approval,csir_sha256=source_sha256):
        raise NativeShotError("Native shot plan differs from original approved Unity evidence.")
    parent=api.load_asset(plan["parent_sequence_path"])
    if (_class(parent) if parent is not None else "")!="LevelSequence" or (
            _asset_path(parent)!=plan["parent_sequence_path"]):
        raise NativeShotError("Original target parent Level Sequence is missing.")
    ext=getattr(api,"MovieSceneSequenceExtensions",None)
    required=("get_tracks","add_track","remove_master_track")
    if ext is None or any(not callable(getattr(ext,name,None)) for name in required):
        raise NativeShotError("Required native Sequencer master-track APIs are unavailable.")
    shot_class=getattr(api,"MovieSceneCinematicShotTrack",None)
    if shot_class is None:
        raise NativeShotError("Cinematic shot track API unavailable in this Unreal version.")
    if list(ext.get_tracks(parent)):
        raise NativeShotError(
            "Existing root master tracks could conflict with nested shot ownership."
        )
    children=[]
    for row in plan["shots"]:
        child=api.load_asset(row["child_sequence_path"])
        if (child is None or _class(child)!="LevelSequence"
                or _asset_path(child)!=row["child_sequence_path"]
                or child is parent):
            raise NativeShotError("Approved child sequence not independently resolved.")
        if list(ext.get_tracks(child)) and any(
                "SubTrack" in _class(track) or "CinematicShotTrack" in _class(track)
                for track in ext.get_tracks(child)):
            raise NativeShotError("Nested grandchildren need separate cycle and time-owner proof.")
        children.append(child)
    add=ext.add_track
    track=None
    saved=False
    rollback_success=False
    try:
        track=add(parent,shot_class)
        if track is None:
            raise NativeShotError("Unreal did not allocate a cinematic shot track.")
        for row,child in zip(plan["shots"],children):
            section=track.add_section()
            section.set_sequence(child)
            section.set_range(row["start_frame"],row["end_frame"])
        observed=list(track.get_sections())
        if len(observed)!=len(children):
            raise NativeShotError("Native shot section count changed after authoring.")
        section_ext=getattr(api,"MovieSceneSectionExtensions",None)
        get_start=getattr(section_ext,"get_start_frame",None)
        get_end=getattr(section_ext,"get_end_frame",None)
        if not callable(get_start) or not callable(get_end):
            raise NativeShotError("Native shot boundaries cannot be reread.")
        for row,child,section in zip(plan["shots"],children,observed):
            s,e=get_start(section),get_end(section)
            s=getattr(s,"value",s)
            e=getattr(e,"value",e)
            if (s!=row["start_frame"] or e!=row["end_frame"]
                    or section.get_sequence() is not child):
                raise NativeShotError("Native shot binding or boundary differs from source.")
        save=getattr(getattr(api,"EditorAssetLibrary",None),"save_loaded_asset",None)
        if not callable(save) or save(parent) is not True:
            raise NativeShotError("Parent native shot sequence save was not confirmed.")
        saved=True
        return {
            "kind":"cutsceneai.studio.native_nested_shot_receipt",
            "status":"SAVED_NATIVE_SHOTS_REOPENED_CINETWIN_PENDING",
            "canonical_plan_sha256":plan["canonical_plan_sha256"],
            "shot_count":len(children),
            "native_shot_path_readback":True,
            "native_section_boundary_readback":True,
            "native_save_confirmed":True,
            "new_editor_process_readback_verified":False,
            "rendered_cutscene_fidelity_verified":False,
        }
    finally:
        if track is not None and not saved:
            try:
                rollback_success=(ext.remove_master_track(parent,track) is True)
            except (AttributeError,RuntimeError,TypeError,ValueError) as exc:
                raise NativeShotError(
                    "Native shot write failed and master-track rollback is unverified."
                ) from exc
            if (not rollback_success or track in list(ext.get_tracks(parent))):
                raise NativeShotError(
                    "Native shot master-track rollback did not remove partial sections."
                )
