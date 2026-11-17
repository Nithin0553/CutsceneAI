"""Persistent, evidence-gated learning ledger for CutSceneAI transfer attempts.

Every terminal run is recorded locally (no model calls). Failed or unverified
runs remain diagnostics, never positive training labels. Only reviewed records
from packages/learning/case_memory.py are eligible for case suggestions.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

JOB_RE = re.compile(r"[0-9a-f]{32}\Z")
CED = Path(__file__).resolve().parents[1] / "packages/contracts/dictionary/cutscene-elements-v0.2.json"
CASE_MEMORY = Path(__file__).resolve().parents[1] / "packages/learning"


class LearningLedgerError(ValueError):
    """Unsafe or incomplete learning provenance."""


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dir(workspace: Path, relative: str, create: bool = False) -> Path:
    base = workspace.resolve()
    path = base / relative
    if path.is_symlink() or not path.resolve().is_relative_to(base):
        raise LearningLedgerError("Unsafe learning folder location.")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def record_terminal(workspace: Path, job: dict) -> dict:
    """Idempotently freeze terminal transfer diagnostics; never imply fidelity."""
    job_id = str(job.get("job_id") or "")
    if JOB_RE.fullmatch(job_id) is None:
        raise LearningLedgerError("Invalid job identity.")
    if job.get("status") in {"RUNNING", "QUEUED"}:
        return {"status": "WAITING_FOR_NATIVE_RESULT", "recorded": False}
    root = workspace.resolve()
    candidate_id = str(job.get("candidate_id") or "")
    if not candidate_id or not re.fullmatch(r"[a-zA-Z0-9_]{1,96}", candidate_id):
        raise LearningLedgerError("Invalid candidate identity.")
    candidate = (root / "candidates" / candidate_id).resolve()
    if (not candidate.is_relative_to(root / "candidates")
            or candidate != Path(str(job.get("candidate_dir") or "")).resolve()):
        raise LearningLedgerError("Job candidate does not belong to this workspace.")
    csir = Path(str(job.get("csir") or "")).resolve()
    mapping = Path(str(job.get("mapping") or "")).resolve()
    if not csir.is_file() or not mapping.is_file() or not CED.is_file():
        raise LearningLedgerError("Missing original source/mapping/CED evidence.")
    trials = _dir(root, "learning/trials", create=True)
    output = trials / (job_id + ".json")
    if output.is_symlink():
        raise LearningLedgerError("Redirected learning record.")
    if output.is_file():
        data = json.loads(output.read_text(encoding="utf-8"))
        if data.get("job_id") != job_id or data.get("candidate_id") != candidate_id:
            raise LearningLedgerError("Existing learning record identity mismatch.")
        return {"status": "RECORDED", "recorded": True, "job_id": job_id}

    # Capture *only* evidence identities and bounded outcomes. Local project
    # paths, source scripts, raw frames and private assets are never exported.
    document = {
        "kind": "cutsceneai.learning.transfer_diagnostic",
        "schema_version": "1",
        "job_id": job_id,
        "candidate_id": candidate_id,
        "source_sha256": _sha(csir),
        "mapping_sha256": _sha(mapping),
        "ced_sha256": _sha(CED),
        "engine_pair": "unity_to_unreal",
        "native_job_status": str(job.get("status") or "")[:120],
        "generation_status": str(job.get("generation_status") or "")[:120],
        "ai_agent_requested": job.get("ai_agents_enabled") is True,
        "fidelity_verified": False,
        "eligible_for_training": False,
        "classification": "UNREVIEWED_DIAGNOSTIC_ONLY",
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return {"status": "RECORDED", "recorded": True, "job_id": job_id}


def report(workspace: Path, csir: Path | None = None) -> dict:
    """Read verified mapping suggestions, not learned executable commands."""
    trials_dir = _dir(workspace, "learning/trials")
    count = len(list(trials_dir.glob("[0-9a-f]" * 32 + ".json"))) if trials_dir.is_dir() else 0
    sys.path.insert(0, str(CASE_MEMORY)) if str(CASE_MEMORY) not in sys.path else None
    import case_memory

    case_store = _dir(workspace, "learning/approved-cases")
    cases = case_memory.list_cases(case_store)
    verified = [c for c in cases if c.get("status") == "MAPPING_VERIFIED"]
    suggestions = []
    if csir is not None and csir.is_file():
        source = case_memory.read_json(csir)
        suggestions = case_memory.suggest(
            source, cases,
            exclude_project_fingerprint=str(
                source.get("source", {}).get("project_fingerprint") or ""),
            limit=3,
        )
    return {
        "kind": "cutsceneai.learning.status",
        "completed_trials_recorded": count,
        "verified_mapping_cases": len(verified),
        "suggestions": suggestions,
        "proposal_only": True,
        "training_automatic": False,
        "model_weights_updated": False,
        "fidelity_verified": False,
        "next_step": "Independently verify and approve mapping cases before reuse or fine-tuning.",
    }
