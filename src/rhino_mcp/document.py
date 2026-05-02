"""Process-wide document registry.

Standalone mode keeps one or more ``rhino3dm.File3dm`` instances alive in
memory and refers to them by ``doc_id``. The default doc_id is ``"active"``,
which is auto-created on first access. In bridge mode the same ``doc_id``
namespace is reserved but operations are forwarded to the live ``RhinoDoc``
inside Rhino; the bridge plugin owns its own object table.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import rhino3dm as r3

from rhino_mcp.utils.error_handling import not_found_error
from rhino_mcp.utils.logging import get_logger

log = get_logger("document")


@dataclass
class DocumentHandle:
    """Bookkeeping wrapper around a ``rhino3dm.File3dm``."""

    doc_id: str
    file3dm: r3.File3dm
    path: Path | None = None
    object_index: dict[str, int] = field(default_factory=dict)

    def add_index(self, gid: UUID | str) -> str:
        sgid = str(gid)
        # rhino3dm's ObjectTable supports FindId; we keep a flat list ourselves
        # so we can look up insertion order without scanning the whole table.
        self.object_index[sgid] = len(self.object_index)
        return sgid

    def find_object(self, gid: str) -> r3.File3dmObject:
        obj = self.file3dm.Objects.FindId(gid)
        if obj is None:
            raise not_found_error("object", gid)
        return obj


class DocumentRegistry:
    """Thread-safe, process-wide collection of in-memory ``rhino3dm`` documents."""

    def __init__(self) -> None:
        self._docs: dict[str, DocumentHandle] = {}
        self._lock = threading.RLock()

    def get_or_create(self, doc_id: str = "active") -> DocumentHandle:
        with self._lock:
            handle = self._docs.get(doc_id)
            if handle is None:
                handle = DocumentHandle(doc_id=doc_id, file3dm=r3.File3dm())
                self._docs[doc_id] = handle
                log.debug("Created document %s", doc_id)
            return handle

    def get(self, doc_id: str) -> DocumentHandle:
        with self._lock:
            handle = self._docs.get(doc_id)
            if handle is None:
                raise not_found_error("document", doc_id)
            return handle

    def open(self, path: str | Path, doc_id: str | None = None) -> DocumentHandle:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise not_found_error("file", str(p))
        f = r3.File3dm.Read(str(p))
        if f is None:
            raise not_found_error("3dm document", str(p))
        chosen = doc_id or f"doc-{uuid4().hex[:8]}"
        handle = DocumentHandle(doc_id=chosen, file3dm=f, path=p)
        with self._lock:
            self._docs[chosen] = handle
        log.info("Opened %s as doc_id=%s (%d objects)", p, chosen, len(f.Objects))
        return handle

    def save(self, doc_id: str, path: str | Path | None = None, version: int = 8) -> Path:
        handle = self.get(doc_id)
        target = Path(path).expanduser().resolve() if path else handle.path
        if target is None:
            raise not_found_error("save path", "no path supplied and document was created in-memory")
        target.parent.mkdir(parents=True, exist_ok=True)
        ok = handle.file3dm.Write(str(target), version)
        if not ok:
            raise RuntimeError(f"rhino3dm refused to write {target}")
        handle.path = target
        log.info("Wrote doc_id=%s to %s", doc_id, target)
        return target

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._docs.keys())

    def reset(self) -> None:
        """Clear all documents. Primarily for tests."""
        with self._lock:
            self._docs.clear()


_REGISTRY = DocumentRegistry()


def registry() -> DocumentRegistry:
    return _REGISTRY
