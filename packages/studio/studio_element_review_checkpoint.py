"""Crash-resumable, evidence-bound model review checkpoints for Element 3.2.

Only redacted occurrence IDs, registered advisory choices, and model digests
are stored. A checkpoint cannot grant native permission. On resume the model
selection validator must replay EVERY saved page from the original source plan.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024
MODEL_ID = re.compile(r"[A-Za-z0-9_.:/-]{1,160}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


class CheckpointError(ValueError):
    """A persisted model-review page cannot be safely reused."""


def _digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


class ReviewCheckpoint:
    """Exclusive, atomic, small on-disk checkpoint for one evidence snapshot."""

    def __init__(self, path: Path, *, plan_sha256: str,
                 batch_size: int, model_identity: str):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        if (not isinstance(plan_sha256, str) or not HEX.fullmatch(plan_sha256)
                or type(batch_size) is not int or not 1 <= batch_size <= 64
                or not isinstance(model_identity, str)
                or not MODEL_ID.fullmatch(model_identity)):
            raise CheckpointError("Invalid model review checkpoint identity.")
        self.identity = {
            "kind": "cutsceneai.studio.element_model_review_checkpoint",
            "schema_version": "1",
            "baseline_plan_sha256": plan_sha256,
            "model_identity": model_identity,
            "batch_size": batch_size,
        }
        self._lock_fd: int | None = None
        self.pages: list[dict[str, Any]] = []

    def __enter__(self) -> "ReviewCheckpoint":
        parent = self.path.parent
        if parent.is_symlink():
            raise CheckpointError("Checkpoint directory cannot be a symlink.")
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not parent.is_dir() or self.path.is_symlink() or self.lock_path.is_symlink():
            raise CheckpointError("Unsafe model review checkpoint location.")
        try:
            self._lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise CheckpointError(
                "Another review holds this source checkpoint (or a stale lock exists)."
            ) from exc
        try:
            self.pages = self._load()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, _type: Any, _value: Any, _tb: Any) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
            self.lock_path.unlink(missing_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        if (not self.path.is_file() or self.path.is_symlink()
                or self.path.stat().st_size > MAX_CHECKPOINT_BYTES):
            raise CheckpointError("Review checkpoint is unsafe or oversized.")
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise CheckpointError("Review checkpoint is unreadable.") from exc
        if not isinstance(content, dict):
            raise CheckpointError("Malformed review checkpoint.")
        digest = content.get("checkpoint_sha256")
        without_digest = {k: v for k, v in content.items()
                          if k != "checkpoint_sha256"}
        if (set(without_digest) != {*self.identity, "pages"}
                or any(without_digest.get(k) != v for k, v in self.identity.items())
                or not isinstance(digest, str) or digest != _digest(without_digest)
                or not isinstance(content.get("pages"), list)):
            raise CheckpointError("Review checkpoint does not match exact evidence and model.")
        pages = content["pages"]
        for index, page in enumerate(pages):
            if (not isinstance(page, dict)
                    or set(page) != {"page_index", "choices", "answer_sha256",
                                     "model_response_sha256"}
                    or type(page["page_index"]) is not int
                    or page["page_index"] != index
                    or not isinstance(page["choices"], list)
                    or not isinstance(page["answer_sha256"], str)
                    or page["answer_sha256"] != _digest({"choices": page["choices"]})
                    or not isinstance(page["model_response_sha256"], str)
                    or not HEX.fullmatch(page["model_response_sha256"])):
                raise CheckpointError("Review checkpoint has an invalid or skipped model page.")
        return pages

    def add_page(self, *, page_index: int, choices: list[dict[str, str]],
                 model_response_sha256: str) -> None:
        if (type(page_index) is not int or page_index != len(self.pages)
                or not isinstance(choices, list)
                or not isinstance(model_response_sha256, str)
                or not HEX.fullmatch(model_response_sha256)):
            raise CheckpointError("Model review pages must be contiguous and evidenced.")
        page = {
            "page_index": page_index,
            "choices": choices,
            "answer_sha256": _digest({"choices": choices}),
            "model_response_sha256": model_response_sha256,
        }
        pending = [*self.pages, page]
        payload = {**self.identity, "pages": pending}
        payload["checkpoint_sha256"] = _digest(payload)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
            raise CheckpointError("Model review checkpoint exceeds its bounded storage budget.")
        temp = self.path.with_name(self.path.name + "." + str(os.getpid()) + ".tmp")
        if temp.is_symlink():
            raise CheckpointError("Unsafe temporary model checkpoint.")
        descriptor = None
        try:
            descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = None
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            temp.unlink(missing_ok=True)
        self.pages = pending
