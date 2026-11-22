"""Runtime CED contracts: strict validation, provenance and trust isolation.

This module validates *knowledge*; validated data NEVER grants native execution.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMAS = Path(__file__).resolve().parents[1] / "contracts" / "dictionary"


class ContractError(ValueError):
    """Malformed or incompatible CED knowledge; no native authorization."""


def _schema(name: str) -> dict[str, Any]:
    names = {
        "recipe": "ced-strategy-recipe-v1.schema.json",
        "manifest": "ced-shared-manifest-v1.schema.json",
    }
    if name not in names:
        raise ContractError("Unknown CED schema.")
    path = SCHEMAS / names[name]
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ContractError("CED schema is unavailable or unsafe.")
    data = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(data)
    return data


def validate(name: str, value: Any) -> dict[str, Any]:
    """Reject unknown keys, incorrect types and unrecognized schema versions."""
    if not isinstance(value, dict):
        raise ContractError("CED contract requires a structured JSON object.")
    try:
        errors = sorted(Draft202012Validator(_schema(name)).iter_errors(value),
                        key=lambda item: str(item.json_path))
    except (TypeError, ValueError, KeyError) as exc:
        raise ContractError("CED contract schema is invalid.") from exc
    if errors:
        error = errors[0]
        raise ContractError(
            "Invalid " + name + " contract at " + error.json_path[:120] +
            ": " + error.message[:240]
        )
    return value


def validate_recipe(value: Any) -> dict[str, Any]:
    document = validate("recipe", value)
    if not document["semantic_ids"] or document["semantic_ids"][0] != document["recipe_id"]:
        # Recipe ID is a registered rule identity rather than a semantic ID;
        # this check must NOT mix those independent namespaces.
        pass
    semantic_ids = set(document["semantic_ids"])
    for edge in document["relationships"]:
        if edge["from"] not in semantic_ids or edge["to"] not in semantic_ids:
            raise ContractError("CED recipe relation references a missing concept.")
    if not all(option["registered_rule_id"] == document["recipe_id"]
               for option in document["alternatives"]):
        raise ContractError("CED recipe alternative references an unrelated rule.")
    if document["provenance"]["status"] == "SHARED_APPROVED":
        raise ContractError("Runtime recipes cannot self-declare shared approval.")
    return document


def validate_manifest(value: Any) -> dict[str, Any]:
    document = validate("manifest", value)
    if document["runtime_execution_authority"] is not False:
        raise ContractError("CED baseline cannot grant native tool authority.")
    return document
