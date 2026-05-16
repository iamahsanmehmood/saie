"""core/history.py — Append-only operation log per project.

Every successful `model.apply` writes one line to
`projects/<name>/history/operations.jsonl`. Each record carries enough info
to undo (the inverse op) and to replay from empty.

JSONL format keeps the log streamable and grep-able. We don't try to be
clever about compaction or rotation — disk is cheap, debugging isn't.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .logger import get_logger

log = get_logger(__name__)


@dataclass
class OpRecord:
    """One entry in operations.jsonl."""

    op_id: str
    ts: float  # epoch seconds, with fractional precision
    kind: str  # e.g. "WallCreated", "OpeningModified", "BatchApplied"
    entity_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    inverse: dict[str, Any] = field(default_factory=dict)  # the op that undoes this
    label: str | None = None  # human-readable summary for `history.list`

    @classmethod
    def new(
        cls,
        kind: str,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
        inverse: dict[str, Any] | None = None,
        label: str | None = None,
    ) -> OpRecord:
        return cls(
            op_id=str(uuid.uuid4()),
            ts=time.time(),
            kind=kind,
            entity_id=entity_id,
            payload=payload or {},
            inverse=inverse or {},
            label=label,
        )

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":")) + "\n"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OpRecord:
        return cls(
            op_id=d["op_id"],
            ts=d["ts"],
            kind=d["kind"],
            entity_id=d.get("entity_id"),
            payload=d.get("payload") or {},
            inverse=d.get("inverse") or {},
            label=d.get("label"),
        )


class History:
    """Append-only operation log, per project.

    Usage:
        h = History(project_dir / "history" / "operations.jsonl")
        h.append(OpRecord.new("WallCreated", entity_id="W1", payload={...}))
        for record in h.iter_records():
            ...
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: OpRecord) -> None:
        """Append a single record. Atomic at the line level on POSIX/NTFS
        because JSONL line is < 4KB (well under PIPE_BUF / sector size)."""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(record.to_jsonl())
        log.debug("history.append op_id=%s kind=%s", record.op_id, record.kind)

    def append_many(self, records: Iterable[OpRecord]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            for r in records:
                f.write(r.to_jsonl())

    def iter_records(self) -> Iterable[OpRecord]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield OpRecord.from_dict(json.loads(raw))
                except (json.JSONDecodeError, KeyError) as e:
                    log.warning("history: skipping malformed line: %s", e)

    def list_recent(self, limit: int = 20) -> list[OpRecord]:
        """Last N records, newest first. For `history.list` tool."""
        all_records = list(self.iter_records())
        return list(reversed(all_records[-limit:]))

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def clear(self) -> None:
        """Wipe the log. Used by `history.replay(from_empty=True)` callers."""
        if self.path.exists():
            self.path.unlink()
