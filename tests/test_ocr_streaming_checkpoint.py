from pathlib import Path
from unittest.mock import MagicMock

import pypdfium2 as pdfium
import typst
from fpdf import FPDF

from tradutor_pdf.assembly.markdown import MarkdownAssembler
from tradutor_pdf.checkpoint.store import CheckpointStore
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.segmentation.semantic import SemanticSegmenter


def test_ocr_streaming_windows_and_checkpoint(tmp_path: Path):
    # Create 4-page mixed document:
    # Page 1: digital
    # Page 2: scanned
    # Page 3: digital
    # Page 4: scanned

    pdf1 = FPDF()
    pdf1.add_page()
    pdf1.set_font("Helvetica", "B", 14)
    pdf1.cell(text="Digital Page 1", new_x="LMARGIN", new_y="NEXT")
    pdf1.set_font("Helvetica", size=11)
    pdf1.multi_cell(0, 8, "Digital text on first page with ample words for layer.")
    p1 = tmp_path / "p1.pdf"
    pdf1.output(str(p1))

    typ2 = tmp_path / "p2.typ"
    typ2.write_text("= Scanned Page 2\n\nImage-only page processed with Tesseract.\n")
    d2 = pdfium.PdfDocument(typst.compile(typ2))
    img2 = d2.get_page(0).render(scale=2.0).to_pil()
    d2.close()
    p2 = tmp_path / "p2.pdf"
    img2.save(str(p2), format="PDF")

    pdf3 = FPDF()
    pdf3.add_page()
    pdf3.set_font("Helvetica", "B", 14)
    pdf3.cell(text="Digital Page 3", new_x="LMARGIN", new_y="NEXT")
    pdf3.set_font("Helvetica", size=11)
    pdf3.multi_cell(0, 8, "Digital text on third page with ample words for layer.")
    p3 = tmp_path / "p3.pdf"
    pdf3.output(str(p3))

    typ4 = tmp_path / "p4.typ"
    typ4.write_text("= Scanned Page 4\n\nSecond image-only page processed with OCR.\n")
    d4 = pdfium.PdfDocument(typst.compile(typ4))
    img4 = d4.get_page(0).render(scale=2.0).to_pil()
    d4.close()
    p4 = tmp_path / "p4.pdf"
    img4.save(str(p4), format="PDF")

    merged = pdfium.PdfDocument.new()
    for p_path in [p1, p2, p3, p4]:
        d = pdfium.PdfDocument(str(p_path))
        merged.import_pages(d)
        d.close()

    mixed_doc_path = tmp_path / "mixed_4p.pdf"
    merged.save(str(mixed_doc_path))
    merged.close()

    # 1. Test streaming windows of 2 pages each
    assets_dir = tmp_path / "assets"
    extractor = DoclingExtractor(
        do_ocr="auto",
        assets_dir=assets_dir,
        default_window_size=2,
    )

    windows = list(extractor.iter_windows(mixed_doc_path, window_size=2))
    assert len(windows) == 2
    assert windows[0][0] == (1, 2)
    assert windows[1][0] == (3, 4)

    w1_blocks = windows[0][1]
    w2_blocks = windows[1][1]

    # Verify OCR tags on blocks
    p1_blocks = [b for b in w1_blocks if b.page == 1]
    p2_blocks = [b for b in w1_blocks if b.page == 2]
    p3_blocks = [b for b in w2_blocks if b.page == 3]
    p4_blocks = [b for b in w2_blocks if b.page == 4]

    assert len(p1_blocks) >= 1
    assert all(b.metadata.get("ocr") is False for b in p1_blocks)
    assert len(p2_blocks) >= 1
    assert all(b.metadata.get("ocr") is True for b in p2_blocks)

    assert len(p3_blocks) >= 1
    assert all(b.metadata.get("ocr") is False for b in p3_blocks)
    assert len(p4_blocks) >= 1
    assert all(b.metadata.get("ocr") is True for b in p4_blocks)

    # 2. Test segmentation and checkpoint resumption
    all_blocks = extractor.extract(mixed_doc_path, window_size=2)
    segmenter = SemanticSegmenter()
    chunks = segmenter.segment(all_blocks, max_tokens=15)
    assert len(chunks) >= 3

    store = CheckpointStore(base_cache_dir=tmp_path / "cache")
    store.init_manifest(
        source_path=mixed_doc_path,
        total_pages=4,
        model="qwen2.5:7b-instruct-q4_K_M",
    )

    # Translate first 2 chunks and simulate crash/interruption
    mock_translator = MagicMock()
    mock_translator.translate.side_effect = lambda c, previous_context=None: (
        setattr(c, "translated_text", f"[TRADUZIDO: {c.original_text[:20]}]")
        or setattr(c, "status", "translated")
    )

    for i in range(2):
        chunk = chunks[i]
        mock_translator.translate(chunk)
        store.save_chunk(mixed_doc_path, chunk, index=i)

    assert store.is_chunk_completed(mixed_doc_path, chunks[0].id)
    assert store.is_chunk_completed(mixed_doc_path, chunks[1].id)
    assert not store.is_chunk_completed(mixed_doc_path, chunks[2].id)

    # Reset mock and resume pipeline
    mock_translator.reset_mock()
    dest_md = tmp_path / "output.md"
    assembler = MarkdownAssembler()

    for i, chunk in enumerate(chunks):
        if store.is_chunk_completed(mixed_doc_path, chunk.id):
            chunk.translated_text = store.load_chunk_translation(
                mixed_doc_path, chunk.id
            )
            chunk.status = "translated"
            continue

        mock_translator.translate(chunk)
        store.save_chunk(mixed_doc_path, chunk, index=i)

    # Verify mock_translator was only called for remaining chunks (chunks 2 onwards)
    assert mock_translator.translate.call_count == len(chunks) - 2

    # Assemble final markdown
    final_path = assembler.assemble(chunks, dest_md)
    store.mark_completed(mixed_doc_path)

    assert final_path.is_file()
    content = final_path.read_text(encoding="utf-8")
    assert "[TRADUZIDO:" in content
    manifest = store.load_manifest(mixed_doc_path)
    assert manifest.status == "completed"
