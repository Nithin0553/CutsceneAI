"""Bounded, swappable model interface for Studio's planning and repair agents.

Only redacted JSON summaries cross this boundary. A local Ollama server is
limited to loopback to prevent accidentally exporting private project data.
All results are data-only and must be revalidated by the caller's native gates.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_TASK = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class ModelProviderError(ValueError):
    """The configured model is unavailable, malformed or violates the contract."""


@dataclass(frozen=True)
class ModelResult:
    answer: dict[str, Any]
    provider: str
    model: str
    response_id: str
    response_sha256: str


def provider_name() -> str:
    """Explicit preference wins; otherwise keep existing OpenAI opt-in compatible."""
    choice = os.environ.get("CUTSCENEAI_MODEL_PROVIDER", "").strip().lower()
    if not choice:
        choice = "openai" if os.environ.get("OPENAI_API_KEY") else "ollama"
    if choice not in {"openai", "ollama"}:
        raise ModelProviderError(
            "CUTSCENEAI_MODEL_PROVIDER must be 'ollama' or 'openai'."
        )
    return choice


def _model_name(provider: str) -> str:
    name = os.environ.get(
        "CUTSCENEAI_AGENT_MODEL",
        "qwen2.5:7b-instruct" if provider == "ollama" else "gpt-5-mini",
    )
    if not name or len(name) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in name):
        raise ModelProviderError("Model name must be a bounded printable identifier.")
    return name


def _payload_bytes(payload: dict[str, Any]) -> bytes:
    if not isinstance(payload, dict):
        raise ModelProviderError("Only structured, redacted JSON evidence is accepted.")
    try:
        data = json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelProviderError("Model evidence is not valid JSON.") from exc
    if len(data) > MAX_REQUEST_BYTES:
        raise ModelProviderError("Model evidence exceeds the safe prompt budget.")
    return data


def _local_url() -> str:
    raw = os.environ.get("CUTSCENEAI_OLLAMA_URL", "http://127.0.0.1:11434")
    target = parse.urlsplit(raw)
    if (target.scheme != "http" or target.hostname not in _LOCAL_HOSTS
            or target.username is not None or target.password is not None
            or target.path not in {"", "/"} or target.query or target.fragment
            or target.port is None and raw != "http://127.0.0.1:11434"):
        raise ModelProviderError(
            "Local Ollama URL must be a loopback HTTP origin, e.g. "
            "http://127.0.0.1:11434."
        )
    port = target.port
    if port is None or not 1 <= port <= 65535:
        raise ModelProviderError("Invalid local Ollama port.")
    return f"http://{target.hostname if target.hostname != '::1' else '[::1]'}:{port}"


def _ollama_timeout_seconds() -> int:
    """Bounded local inference budget; slow open-weight models need more than 40s."""
    raw = os.environ.get("CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS", "120").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ModelProviderError(
            "CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS must be an integer from 10 to 300."
        ) from exc
    if not 10 <= value <= 300:
        raise ModelProviderError(
            "CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS must be an integer from 10 to 300."
        )
    return value


def _answer(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ModelProviderError("Model returned empty or oversized JSON.")
    try:
        result = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ModelProviderError("Model did not return a JSON object.") from exc
    if not isinstance(result, dict):
        raise ModelProviderError("Model result must be a structured JSON object.")
    return result


def complete_json(*, task: str, instructions: str, payload: dict[str, Any],
                  schema: dict[str, Any]) -> ModelResult:
    """Invoke one real provider, never execute returned commands or code."""
    if not isinstance(task, str) or not _TASK.fullmatch(task):
        raise ModelProviderError("Invalid bounded model task identifier.")
    data = _payload_bytes(payload)
    if not isinstance(instructions, str) or len(instructions) > 12000:
        raise ModelProviderError("Invalid model instructions.")
    if not isinstance(schema, dict) or len(json.dumps(schema)) > 12000:
        raise ModelProviderError("Invalid model result schema.")
    provider = provider_name()
    model = _model_name(provider)
    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise ModelProviderError(
                "OPENAI_API_KEY is not configured. For a local open-weight model, "
                "set CUTSCENEAI_MODEL_PROVIDER=ollama and start Ollama."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ModelProviderError("Install the openai Python SDK for the OpenAI provider.") from exc
        response = OpenAI(timeout=25.0, max_retries=0).responses.create(
            model=model,
            instructions=instructions,
            input=data.decode("utf-8"),
            text={"format": {
                "type": "json_schema", "name": task, "strict": True,
                "schema": schema,
            }},
        )
        raw = response.output_text
        response_id = getattr(response, "id", None)
        response_id = response_id if isinstance(response_id, str) else ""
        origin = "OPENAI_RESPONSES"
    else:
        uri = _local_url() + "/api/chat"
        body = {
            "model": model, "stream": False, "format": schema,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": data.decode("utf-8")},
            ],
            "options": {"temperature": 0},
        }
        req = request.Request(
            uri, data=json.dumps(body, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = _ollama_timeout_seconds()
        try:
            with request.urlopen(req, timeout=timeout) as stream:
                response_bytes = stream.read(MAX_RESPONSE_BYTES + 1)
        except error.HTTPError as exc:
            # HTTPError is also a URLError: distinguish server/model failures
            # from an offline Ollama service without leaking response contents.
            detail = ""
            try:
                body = json.loads(exc.read(2048))
                if isinstance(body, dict):
                    detail = str(body.get("error", ""))[:400].lower()
            except (OSError, ValueError, TypeError):
                pass
            if exc.code == 404:
                raise ModelProviderError(
                    "Local Ollama model not found (HTTP 404). Verify the exact "
                    "CUTSCENEAI_AGENT_MODEL with 'ollama list'; no native job was submitted."
                ) from exc
            if "memory" in detail or "allocation" in detail:
                raise ModelProviderError(
                    "Local Ollama lacks enough memory to run the configured model. "
                    "Free RAM/VRAM or choose a smaller model; no native job was submitted."
                ) from exc
            raise ModelProviderError(
                f"Local Ollama returned HTTP {exc.code} from /api/chat; "
                "inspect Ollama logs before retrying. No native job was submitted."
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            reason = exc.reason if isinstance(exc, error.URLError) else exc
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise ModelProviderError(
                    f"Local Ollama timed out after {timeout} seconds during /api/chat. "
                    "Check available RAM/VRAM or configure a bounded "
                    "CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS; no native job was submitted."
                ) from exc
            raise ModelProviderError(
                "Local Ollama connection failed at the configured loopback address. "
                "Check the Ollama service and local port; no native job was submitted."
            ) from exc
        if len(response_bytes) > MAX_RESPONSE_BYTES:
            raise ModelProviderError("Ollama response exceeds the safe budget.")
        try:
            envelope = json.loads(response_bytes)
            raw = envelope["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelProviderError("Ollama did not return a valid chat response.") from exc
        if not isinstance(raw, str):
            raise ModelProviderError("Ollama response must contain JSON text.")
        response_id = ""
        origin = "OLLAMA_LOCAL"
    answer = _answer(raw)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return ModelResult(
        answer=answer, provider=origin, model=model,
        response_id=response_id, response_sha256=digest,
    )
