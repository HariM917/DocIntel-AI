"""Storage abstraction for uploaded documents (Phase 2).

The application never writes uploads using a client-supplied filename. Callers
generate a *storage key* (see :func:`build_storage_key`) derived from immutable
server-side identifiers; the storage backend is responsible for confining every
operation to its configured root.

``LocalStorageService`` is used for development and is fully functional.
``S3StorageService`` is the architectural extension point for S3-compatible
object storage and intentionally raises until it is implemented in a later
phase (no AWS credentials are needed for local development).
"""
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional

from app.config import settings, UPLOAD_DIR

logger = logging.getLogger("docintel.storage")

_CHUNK_SIZE = 1024 * 1024  # 1 MB streaming chunks
_UNSAFE_SEGMENT_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_SAFE_EXTENSION = re.compile(r"^\.[A-Za-z0-9]{1,8}$")


class StorageError(Exception):
    """Raised for storage failures that should surface as a clean HTTP error."""


def _safe_segment(value: Optional[str], fallback: str = "unassigned") -> str:
    """Normalises an arbitrary identifier into a safe single path segment."""
    cleaned = _UNSAFE_SEGMENT_CHARS.sub("_", (value or "").strip()).strip("._")
    return (cleaned or fallback)[:128]


def build_storage_key(
    document_id: str,
    extension: str,
    owner_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> str:
    """Builds a safe, generated storage key.

    The original client filename is *never* used as a path component; only
    generated identifiers and a validated extension are used.
    """
    scope = _safe_segment(organization_id or owner_id or "unassigned")
    safe_doc_id = _safe_segment(document_id, "document")
    safe_ext = extension if _SAFE_EXTENSION.match(extension or "") else ""
    return f"documents/{scope}/{safe_doc_id}{safe_ext}"


class StorageService(ABC):
    """Interface every storage backend must implement."""

    @abstractmethod
    def save(self, stream: BinaryIO, storage_key: str, max_bytes: int) -> int:
        """Streams ``stream`` to ``storage_key``, aborting past ``max_bytes``."""

    @abstractmethod
    def get_path(self, storage_key: str) -> Optional[Path]:
        """Returns a readable local path for ``storage_key`` if it exists."""

    @abstractmethod
    def read_bytes(self, storage_key: str) -> Optional[bytes]:
        """Returns the raw bytes for ``storage_key`` if it exists."""

    @abstractmethod
    def delete(self, storage_key: str) -> bool:
        """Removes ``storage_key``; returns True when something was deleted."""

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Returns True when ``storage_key`` exists."""


class LocalStorageService(StorageService):
    """Filesystem-backed storage confined to a single root directory."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Optional[Path]:
        """Resolves a storage key, refusing traversal and absolute paths."""
        if not storage_key:
            return None
        key = storage_key.replace("\\", "/")
        if key.startswith("/") or ".." in Path(key).parts:
            logger.warning("Rejected unsafe storage key.")
            return None
        resolved = (self.root / key).resolve()
        if resolved == self.root or self.root not in resolved.parents:
            logger.warning("Rejected storage key escaping storage root.")
            return None
        return resolved

    def save(self, stream: BinaryIO, storage_key: str, max_bytes: int) -> int:
        target = self._resolve(storage_key)
        if target is None:
            raise StorageError("Invalid storage key.")
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with open(target, "wb") as buffer:
                while True:
                    chunk = stream.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise StorageError(
                            f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB"
                        )
                    buffer.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return written

    def get_path(self, storage_key: str) -> Optional[Path]:
        resolved = self._resolve(storage_key)
        if resolved and resolved.is_file():
            return resolved
        return None

    def read_bytes(self, storage_key: str) -> Optional[bytes]:
        resolved = self._resolve(storage_key)
        if resolved and resolved.is_file():
            return resolved.read_bytes()
        return None

    def delete(self, storage_key: str) -> bool:
        resolved = self._resolve(storage_key)
        if resolved and resolved.exists():
            try:
                resolved.unlink()
                return True
            except OSError:
                logger.warning("Could not delete stored object.")
                return False
        return False

    def exists(self, storage_key: str) -> bool:
        resolved = self._resolve(storage_key)
        return bool(resolved and resolved.exists())


class S3StorageService(StorageService):
    """S3-compatible storage backend (architectural placeholder).

    Phase 2 deliberately does not require S3. Selecting ``STORAGE_BACKEND=s3``
    fails fast with a clear message rather than silently degrading, so that a
    future implementation can be added without touching call sites.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "S3 storage backend is not implemented yet. Set STORAGE_BACKEND=local."
        )

    def save(self, stream: BinaryIO, storage_key: str, max_bytes: int) -> int:  # pragma: no cover
        raise NotImplementedError

    def get_path(self, storage_key: str) -> Optional[Path]:  # pragma: no cover
        raise NotImplementedError

    def read_bytes(self, storage_key: str) -> Optional[bytes]:  # pragma: no cover
        raise NotImplementedError

    def delete(self, storage_key: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def exists(self, storage_key: str) -> bool:  # pragma: no cover
        raise NotImplementedError


def build_storage_service() -> StorageService:
    """Instantiates the configured storage backend."""
    backend = (settings.STORAGE_BACKEND or "local").lower()
    if backend == "s3":
        return S3StorageService()
    root = Path(settings.STORAGE_LOCAL_ROOT) if settings.STORAGE_LOCAL_ROOT else UPLOAD_DIR
    return LocalStorageService(root)


storage_service: StorageService = build_storage_service()
