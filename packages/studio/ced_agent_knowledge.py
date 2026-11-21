"""Backward-compatible Studio façade for the unified hybrid CED service.

One knowledge authority lives in packages/ced/knowledge_service.py. The
Studio/agent API must not maintain its own competing rule or ranking logic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PACKAGES = Path(__file__).resolve().parents[1]
CED_PACKAGE = str(PACKAGES / "ced")
MAX_CONCEPTS = 48
MAX_RULES_PER_CONCEPT = 4


class KnowledgeError(ValueError):
    """Invalid, unavailable or incomplete source-grounded CED knowledge."""


def retrieve(csir: dict[str, Any], *, target_capabilities: dict[str, Any],
             source_version: str = "", target_version: str = "",
             approved_store: Path | None = None,
             case_store: Path | None = None,
             source_capabilities: dict[str, Any] | None = None,
             page: int = 0, page_size: int = MAX_CONCEPTS) -> dict[str, Any]:
    if CED_PACKAGE not in sys.path:
        sys.path.insert(0, CED_PACKAGE)
    from knowledge_service import KnowledgeServiceError, retrieve as knowledge_retrieve
    try:
        return knowledge_retrieve(
            csir, target_capabilities=target_capabilities,
            source_version=source_version, target_version=target_version,
            approved_store=approved_store, case_store=case_store,
            source_capabilities=source_capabilities,
            page=page, page_size=page_size,
        )
    except KnowledgeServiceError as exc:
        raise KnowledgeError(str(exc)) from exc



def model_projection(result: dict[str, Any]) -> dict[str, Any]:
    """Redact private/unknown source semantics before any model transport."""
    if CED_PACKAGE not in sys.path:
        sys.path.insert(0, CED_PACKAGE)
    from knowledge_service import KnowledgeServiceError, redact_for_model
    try:
        return redact_for_model(result)
    except KnowledgeServiceError as exc:
        raise KnowledgeError(str(exc)) from exc
