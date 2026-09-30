from pathlib import Path

from tradutor_pdf.checkpoint.store import (
    CheckpointStore,
    atomic_write,
)
from tradutor_pdf.pipeline import Block, BlockType, Chunk


def test_atomic_write(tmp_path: Path):
    target = tmp_path / "subdir" / "test.txt"
    content = "Hello, atomic world!"
    atomic_write(target, content)

    assert target.is_file()
    assert target.read_text(encoding="utf-8") == content

    # Test overwrite
    new_content = "Overwritten content"
    atomic_write(target, new_content)
    assert target.read_text(encoding="utf-8") == new_content


def test_checkpoint_store_manifest_init_and_save(tmp_path: Path):
    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)

    dummy_pdf = tmp_path / "document.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 test")

    manifest = store.init_manifest(
        source_path=dummy_pdf,
        total_pages=5,
        model="test-model",
        prompt_version="1.0.0",
        target_language="pt-BR",
    )

    assert manifest.total_pages == 5
    assert manifest.model == "test-model"
    assert manifest.status == "in_progress"
    assert store.has_checkpoint(dummy_pdf)

    # Reload from disk
    loaded = store.load_manifest(dummy_pdf)
    assert loaded is not None
    assert loaded.sha256 == manifest.sha256
    assert loaded.total_pages == 5
    assert loaded.model == "test-model"


def test_checkpoint_store_save_and_load_chunk(tmp_path: Path):
    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)

    dummy_pdf = tmp_path / "document.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 test")

    store.init_manifest(
        source_path=dummy_pdf,
        total_pages=2,
        model="test-model",
    )

    block = Block(
        id="b0",
        type=BlockType.PARAGRAPH,
        content="Original English text",
        page=1,
    )
    chunk = Chunk(
        id="chunk_0000",
        blocks=[block],
        original_text="Original English text",
        translated_text="Texto traduzido em português",
        page_start=1,
        page_end=1,
        status="translated",
        token_count=15,
    )

    store.save_chunk(dummy_pdf, chunk, index=0)

    assert store.is_chunk_completed(dummy_pdf, "chunk_0000")
    assert not store.is_chunk_completed(dummy_pdf, "chunk_0001")

    saved_text = store.load_chunk_translation(dummy_pdf, "chunk_0000")
    assert saved_text == "Texto traduzido em português"

    manifest = store.load_manifest(dummy_pdf)
    assert manifest is not None
    assert "chunk_0000" in manifest.chunks
    assert manifest.chunks["chunk_0000"].status == "translated"
    assert manifest.chunks["chunk_0000"].page_start == 1


def test_checkpoint_store_clear(tmp_path: Path):
    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)

    dummy_pdf = tmp_path / "document.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 test")

    store.init_manifest(dummy_pdf, total_pages=1, model="test-model")
    assert store.has_checkpoint(dummy_pdf)

    store.clear(dummy_pdf)
    assert not store.has_checkpoint(dummy_pdf)
