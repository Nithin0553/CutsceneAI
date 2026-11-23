"""Cross-engine sampled cinematic behavior comparison for six effect families.

The caller must supply raw, independently captured Unity/Unreal observations
on the exact same time grid, keyed to approved immutable source IDs. This is
a *measurement* contract, not a claim that custom shaders, audio codecs, VFX
systems, gameplay scripts or rigid-body solvers were translated.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class EffectComparisonError(ValueError):
    pass


DOMAINS={
    "lighting":{"intensity":(0.02,0.1),"color_linear_rgb":(0.02,0.01)},
    "shaders_materials":{"roughness":(0.01,0.01),"metallic":(0.01,0.01),
                         "opacity":(0.01,0.01),"linear_rgb":(0.02,0.01)},
    "audio":{"rms":(0.04,0.02),"peak":(0.04,0.02)},
    "vfx":{"alive_particles":(0,0),"centroid_m":(0.02,0.01)},
    "events":{"fire_count":(0,0)},
    "physics":{"position_m":(0.02,0.01),"velocity_mps":(0.05,0.03),
               "angular_velocity_rps":(0.05,0.03)},
}
BOOLEANS={
    "lighting":("shadow_enabled",),
    "shaders_materials":(),
    "audio":("playing",),
    "vfx":(),
    "events":("state_sha256",),
    "physics":("contact_ids",),
}
HASH=lambda value:hashlib.sha256(json.dumps(
    value,sort_keys=True,separators=(",",":"),allow_nan=False,
).encode("utf-8")).hexdigest()


def _numeric(value: Any, *, label: str) -> tuple[float,...]:
    if type(value) in (int,float):
        row=(float(value),)
    elif isinstance(value,(tuple,list)) and 1<=len(value)<=8:
        row=tuple(value)
    else:
        raise EffectComparisonError("Missing or nonnumeric sampled "+label)
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e9
           for v in row):
        raise EffectComparisonError("Nonfinite sampled "+label)
    return tuple(float(v) for v in row)


def _source_ids(observations: Any, family: str) -> dict[str,dict]:
    if not isinstance(observations,list) or len(observations)>10000:
        raise EffectComparisonError("Invalid "+family+" captured occurrence roster.")
    rows={}
    for row in observations:
        if not isinstance(row,dict):
            raise EffectComparisonError("Malformed "+family+" source occurrence.")
        ident=row.get("source_id")
        if not isinstance(ident,str) or not ident or ident in rows:
            raise EffectComparisonError("Missing/duplicate "+family+" source occurrence ID.")
        rows[ident]=row
    return rows


def compare(source: dict, target: dict, *,
            source_csir_sha256: str, target_project_sha256: str,
            required: tuple[str,...] = tuple(DOMAINS)) -> dict:
    """Compare every required observed domain at every exact source timestamp.

    Domain completeness is mandatory. Two absent domains NEVER count as a
    pass. Returning PASS only means typed observations fall within bounds,
    not rendered/deformed/physics/gameplay equivalence.
    """
    if (not isinstance(source,dict) or not isinstance(target,dict)
            or source.get("source_csir_sha256")!=source_csir_sha256
            or target.get("source_csir_sha256")!=source_csir_sha256
            or target.get("target_project_sha256")!=target_project_sha256
            or not all(isinstance(hash_,str) and len(hash_)==64 and all(
                c in "0123456789abcdef" for c in hash_)
                for hash_ in (source_csir_sha256,target_project_sha256))):
        raise EffectComparisonError("Original source/native editor identity is mismatched.")
    if (not isinstance(required,(tuple,list)) or not required
            or len(set(required))!=len(required)
            or any(key not in DOMAINS for key in required)):
        raise EffectComparisonError("Effect comparison domains must be explicit and supported.")
    src=source.get("samples")
    dst=target.get("samples")
    if (not isinstance(src,list) or not isinstance(dst,list)
            or len(src)!=len(dst) or not 2<=len(src)<=4001):
        raise EffectComparisonError("Exact source/target effect time grid is required.")
    grid=[]
    per_domain={name:{"measured_occurrences":0,"max_normalized_error":0.,
                      "mismatched_samples":0,"missing_samples":0}
                for name in required}
    previous_time=None
    for frame,(a,b) in enumerate(zip(src,dst)):
        if not isinstance(a,dict) or not isinstance(b,dict):
            raise EffectComparisonError("Malformed effect sample.")
        ta,tb=a.get("time_seconds"),b.get("time_seconds")
        if (type(ta) not in (int,float) or type(tb) not in (int,float)
                or not math.isfinite(ta) or not math.isfinite(tb)
                or abs(ta-tb)>1e-7
                or (previous_time is not None and ta<=previous_time)):
            raise EffectComparisonError("Source/native effect sample grid is shifted or repeated.")
        previous_time=ta
        grid.append(float(ta))
        for family in required:
            left=(a.get("effects") or {}).get(family)
            right=(b.get("effects") or {}).get(family)
            if not isinstance(left,list) or not isinstance(right,list):
                per_domain[family]["missing_samples"]+=1
                continue
            src_items=_source_ids(left,family)
            tgt_items=_source_ids(right,family)
            if not src_items or set(src_items)!=set(tgt_items):
                per_domain[family]["missing_samples"]+=1
                continue
            for key,x in src_items.items():
                y=tgt_items[key]
                per_domain[family]["measured_occurrences"]+=1
                differs=False
                for prop,(absolute,relative) in DOMAINS[family].items():
                    xvec=_numeric(x.get(prop),label=family+"/"+prop)
                    yvec=_numeric(y.get(prop),label=family+"/"+prop)
                    if len(xvec)!=len(yvec):
                        raise EffectComparisonError("Sampled effect channel width is ambiguous.")
                    for va,vb in zip(xvec,yvec):
                        tolerance=absolute+relative*max(abs(va),abs(vb))
                        error=abs(va-vb)
                        ratio=(error/tolerance if tolerance>0 else
                               (0. if error==0 else float("inf")))
                        per_domain[family]["max_normalized_error"]=max(
                            per_domain[family]["max_normalized_error"],ratio)
                        if ratio>1.:
                            differs=True
                for prop in BOOLEANS[family]:
                    ax,bx=x.get(prop),y.get(prop)
                    if family=="events" and prop=="state_sha256":
                        for digest in (ax,bx):
                            if (not isinstance(digest,str) or len(digest)!=64):
                                raise EffectComparisonError("Event state hash missing.")
                    if family=="physics" and prop=="contact_ids":
                        if (not isinstance(ax,list) or not isinstance(bx,list)
                                or any(not isinstance(z,str) for z in ax+bx)):
                            raise EffectComparisonError("Physics contact identities are missing.")
                        ax,bx=sorted(ax),sorted(bx)
                    if ax is None or bx is None:
                        raise EffectComparisonError("Missing "+family+" discrete state "+prop)
                    if ax!=bx:
                        differs=True
                per_domain[family]["mismatched_samples"]+=int(differs)
    for family,summary in per_domain.items():
        if summary["missing_samples"]>0 or summary["measured_occurrences"]==0:
            summary["status"]="UNMEASURED_OR_SOURCE_OCCURRENCE_UNMAPPED"
        elif summary["mismatched_samples"]:
            summary["status"]="OBSERVED_BEHAVIOR_DIFFERENCE"
        else:
            summary["status"]="TYPED_SAMPLED_VALUES_WITHIN_TOLERANCE"
        if not math.isfinite(summary["max_normalized_error"]):
            summary["max_normalized_error"]=1e10
    result={
        "kind":"cutsceneai.cinetwin.phase10_2.six_domain_observation_comparison",
        "schema_version":"1",
        "source_csir_sha256":source_csir_sha256,
        "target_project_sha256":target_project_sha256,
        "source_frame_count":len(grid),
        "domains":per_domain,
        "status":(
            "MEASURED_DOMAINS_WITHIN_TOLERANCE"
            if all(v["status"]=="TYPED_SAMPLED_VALUES_WITHIN_TOLERANCE"
                   for v in per_domain.values())
            else "UNVERIFIED_OR_DIFFERENT"
        ),
        "unobserved_semantic_equivalence_never_inferred":True,
        "rendered_audio_and_physics_fidelity_verified":False,
    }
    result["comparison_sha256"]=HASH(result)
    return result
