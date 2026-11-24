"""Failure taxonomy and bounded safe recovery for Studio's agent workflow.

This is not a native replay engine. Only proven pre-native, idempotent states
may autonomously retry. Once an Unreal job exists, failures require inspection.
"""
from __future__ import annotations

from typing import Any

OLLAMA_WAIT_SECONDS = 8
MAX_MODEL_RETRIES = 3


def classify(message: str, *, phase: str, native_submitted: bool) -> dict[str, Any]:
    text = str(message).casefold()[:1200]
    category = "UNKNOWN_FAILURE"
    next_action = "Review the source-bound Studio diagnostic before retrying."
    if "local ollama timed out after" in text:
        category = "MODEL_PROVIDER_TIMEOUT"
        next_action = (
            "The local model exceeded the bounded inference timeout. Inspect "
            "available RAM/VRAM and the configured Ollama timeout before starting "
            "a fresh transfer. No native retry is authorized."
        )
    elif "local ollama lacks enough memory" in text:
        category = "MODEL_RESOURCE_EXHAUSTED"
        next_action = (
            "Free memory or choose a smaller local model. Do not replay a "
            "native candidate; inspect the previous run first."
        )
    elif "local ollama model not found" in text:
        category = "MODEL_NOT_INSTALLED"
        next_action = (
            "Check CUTSCENEAI_AGENT_MODEL and 'ollama list' before starting "
            "a fresh pre-native transfer."
        )
    elif ("local ollama connection failed" in text
          or "local ollama is unavailable" in text
          or "ollama did not return" in text):
        category = "MODEL_PROVIDER_UNAVAILABLE"
        next_action = (
            "Check the loopback Ollama service, model and port. Studio will "
            "retry this pre-native reasoning step safely."
        )
    elif "openai_api_key" in text:
        category = "MODEL_CREDENTIALS_MISSING"
        next_action = "Configure the model provider or select local Ollama."
    elif "source" in text and any(
        marker in text for marker in ("missing", "changed", "identity", "hash", "stale")
    ):
        category = "SOURCE_EVIDENCE_UNAVAILABLE"
        next_action = "Re-export and validate the exact Unity source evidence."
    elif any(marker in text for marker in (
        "not supported", "unsupported", "unregistered", "no native adapter",
        "without eligible",
    )):
        category = "UNSUPPORTED_CONVERSION"
        next_action = (
            "Inspect retrieved CED alternative rules and required evidence; "
            "register and independently verify a new adapter if needed."
        )
    elif any(marker in text for marker in ("editor", "disconnected", "worker")):
        category = "ENGINE_DISCONNECTED"
        next_action = "Restore the exact Unity/Unreal editor bridge and level identity."
    elif any(marker in text for marker in ("mismatched", "corrupt", "unsafe", "tamper")):
        category = "INVALID_OR_STALE_EVIDENCE"
        next_action = "Inspect the immutable candidate and native receipts."
    if native_submitted:
        category = "NATIVE_JOB_NEEDS_INSPECTION"
        next_action = (
            "Inspect the exact native job and partial import receipts; "
            "never resubmit this candidate automatically."
        )
    safe_retry = (
        category == "MODEL_PROVIDER_UNAVAILABLE"
        and phase == "ANALYZING_PROJECTS"
        and not native_submitted
    )
    return {
        "category": category,
        "safe_automatic_retry": safe_retry,
        "native_replay_authorized": False,
        "next_action": next_action,
    }
