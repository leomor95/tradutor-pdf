from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradutor_pdf.assembly.markdown import compute_file_sha256
from tradutor_pdf.config import find_project_root
from tradutor_pdf.pipeline import Chunk
from tradutor_pdf.translation.prompt import PROMPT_VERSION

logger = logging.getLogger(__name__)


def atomic_write(target_path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text content to target_path atomically using a temporary file in the same directory."""
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(
        f"{path.suffix}.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
    )
    try:
        with open(temp_file, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(path)
    except Exception:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise


@dataclass
class ChunkRecord:
    """Checkpoint metadata for a single document chunk."""

    id: str
    index: int
    page_start: int
    page_end: int
    status: str  # "pending", "translated", "skipped", "error"
    md_file: str | None = None
    token_count: int = 0
    error_message: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChunkRecord:
        return cls(
            id=data["id"],
            index=data.get("index", 0),
            page_start=data.get("page_start", 1),
            page_end=data.get("page_end", 1),
            status=data.get("status", "pending"),
            md_file=data.get("md_file"),
            token_count=data.get("token_count", 0),
            error_message=data.get("error_message"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class CheckpointManifest:
    """Document-level checkpoint manifest tracking translation state."""

    version: str
    sha256: str
    source_name: str
    source_path: str
    total_pages: int
    model: str
    prompt_version: str
    target_language: str
    status: str  # "in_progress", "completed", "error"
    created_at: str
    updated_at: str
    chunks: dict[str, ChunkRecord] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "sha256": self.sha256,
            "source_name": self.source_name,
            "source_path": self.source_path,
            "total_pages": self.total_pages,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "target_language": self.target_language,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "chunks": {
                chunk_id: chunk.to_dict() for chunk_id, chunk in self.chunks.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointManifest:
        chunks_raw = data.get("chunks", {})
        chunks: dict[str, ChunkRecord] = {}
        if isinstance(chunks_raw, dict):
            for cid, cdata in chunks_raw.items():
                chunks[cid] = ChunkRecord.from_dict(cdata)
        elif isinstance(chunks_raw, list):
            for cdata in chunks_raw:
                chunks[cdata["id"]] = ChunkRecord.from_dict(cdata)

        return cls(
            version=data.get("version", "1.0"),
            sha256=data.get("sha256", ""),
            source_name=data.get("source_name", ""),
            source_path=data.get("source_path", ""),
            total_pages=data.get("total_pages", 1),
            model=data.get("model", ""),
            prompt_version=data.get("prompt_version", PROMPT_VERSION),
            target_language=data.get("target_language", "pt-BR"),
            status=data.get("status", "in_progress"),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
            chunks=chunks,
        )


class CheckpointStore:
    """Manages atomic persistence and retrieval of checkpoints in .cache/<sha256>/."""

    def __init__(self, base_cache_dir: Path | None = None) -> None:
        if base_cache_dir is not None:
            self.base_cache_dir = Path(base_cache_dir)
        else:
            cache_env = os.environ.get("TRADUTOR_CACHE_DIR")
            self.base_cache_dir = (
                Path(cache_env) if cache_env else (find_project_root() / ".cache")
            )

    def get_cache_dir(self, source_path: Path, sha256_hash: str | None = None) -> Path:
        source = Path(source_path)
        if sha256_hash is not None:
            sha = sha256_hash
        elif source.is_file():
            sha = compute_file_sha256(source)
        else:
            import hashlib

            sha = hashlib.sha256(source.name.encode("utf-8")).hexdigest()
        return self.base_cache_dir / sha

    def get_manifest_path(
        self, source_path: Path, sha256_hash: str | None = None
    ) -> Path:
        return self.get_cache_dir(source_path, sha256_hash) / "manifest.json"

    def get_chunks_dir(self, source_path: Path, sha256_hash: str | None = None) -> Path:
        return self.get_cache_dir(source_path, sha256_hash) / "chunks"

    def has_checkpoint(self, source_path: Path, sha256_hash: str | None = None) -> bool:
        source = Path(source_path)
        if sha256_hash is None and not source.is_file():
            return False
        manifest_path = self.get_manifest_path(source_path, sha256_hash)
        return manifest_path.is_file()

    def load_manifest(
        self, source_path: Path, sha256_hash: str | None = None
    ) -> CheckpointManifest | None:
        manifest_path = self.get_manifest_path(source_path, sha256_hash)
        if not manifest_path.is_file():
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return CheckpointManifest.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load checkpoint manifest %s: %s", manifest_path, exc
            )
            return None

    def save_manifest(
        self,
        source_path: Path,
        manifest: CheckpointManifest,
        sha256_hash: str | None = None,
    ) -> None:
        manifest_path = self.get_manifest_path(source_path, sha256_hash)
        manifest.updated_at = datetime.now(UTC).isoformat()
        payload = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(manifest_path, payload)

    def init_manifest(
        self,
        source_path: Path,
        total_pages: int,
        model: str,
        prompt_version: str = PROMPT_VERSION,
        target_language: str = "pt-BR",
        sha256_hash: str | None = None,
    ) -> CheckpointManifest:
        existing = self.load_manifest(source_path, sha256_hash)
        if existing is not None:
            return existing

        source = Path(source_path)
        sha = sha256_hash if sha256_hash is not None else compute_file_sha256(source)
        now_iso = datetime.now(UTC).isoformat()

        manifest = CheckpointManifest(
            version="1.0",
            sha256=sha,
            source_name=source.name,
            source_path=str(source.resolve()),
            total_pages=total_pages,
            model=model,
            prompt_version=prompt_version,
            target_language=target_language,
            status="in_progress",
            created_at=now_iso,
            updated_at=now_iso,
            chunks={},
        )
        self.save_manifest(source, manifest, sha256_hash=sha)
        return manifest

    def save_chunk(
        self,
        source_path: Path,
        chunk: Chunk,
        index: int,
        sha256_hash: str | None = None,
    ) -> None:
        """Atomically persist chunk translation to chunks/<id>.md and update manifest.json."""
        source = Path(source_path)
        sha = sha256_hash if sha256_hash is not None else compute_file_sha256(source)
        chunks_dir = self.get_chunks_dir(source, sha)
        chunk_file = chunks_dir / f"{chunk.id}.md"

        content = (
            chunk.translated_text
            if chunk.translated_text is not None
            else chunk.original_text
        )
        atomic_write(chunk_file, content)

        # Update manifest
        manifest = self.load_manifest(source, sha)
        if manifest is None:
            manifest = self.init_manifest(
                source_path=source,
                total_pages=chunk.page_end,
                model="",
                sha256_hash=sha,
            )

        now_iso = datetime.now(UTC).isoformat()
        rel_md_file = f"chunks/{chunk.id}.md"

        manifest.chunks[chunk.id] = ChunkRecord(
            id=chunk.id,
            index=index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            status=chunk.status,
            md_file=rel_md_file,
            token_count=chunk.token_count,
            error_message=chunk.error_message,
            updated_at=now_iso,
        )

        self.save_manifest(source, manifest, sha256_hash=sha)
        logger.debug("Saved chunk %s checkpoint to %s", chunk.id, chunk_file)

    def load_chunk_translation(
        self,
        source_path: Path,
        chunk_id: str,
        sha256_hash: str | None = None,
    ) -> str | None:
        """Read saved translated content for chunk_id if available."""
        source = Path(source_path)
        sha = sha256_hash if sha256_hash is not None else compute_file_sha256(source)
        chunk_file = self.get_chunks_dir(source, sha) / f"{chunk_id}.md"
        if chunk_file.is_file():
            return chunk_file.read_text(encoding="utf-8")
        return None

    def is_chunk_completed(
        self,
        source_path: Path,
        chunk_id: str,
        sha256_hash: str | None = None,
    ) -> bool:
        """Return True if chunk was already translated or skipped in checkpoint."""
        manifest = self.load_manifest(source_path, sha256_hash)
        if not manifest or chunk_id not in manifest.chunks:
            return False
        return manifest.chunks[chunk_id].status in ("translated", "skipped")

    def mark_completed(self, source_path: Path, sha256_hash: str | None = None) -> None:
        """Mark document manifest as completed."""
        manifest = self.load_manifest(source_path, sha256_hash)
        if manifest:
            manifest.status = "completed"
            self.save_manifest(source_path, manifest, sha256_hash)

    def clear(self, source_path: Path, sha256_hash: str | None = None) -> None:
        """Remove checkpoint directory completely."""
        cache_dir = self.get_cache_dir(source_path, sha256_hash)
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
            logger.info("Cleared checkpoint at %s", cache_dir)
