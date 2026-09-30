from tradutor_pdf.pipeline import Block, BlockType, Segmenter
from tradutor_pdf.segmentation.naive import NaiveSegmenter, estimate_tokens


def test_naive_segmenter_protocol():
    segmenter = NaiveSegmenter()
    assert isinstance(segmenter, Segmenter)


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") == 2
    assert estimate_tokens("one two three four five") >= 5


def test_segment_empty():
    segmenter = NaiveSegmenter()
    assert segmenter.segment([]) == []


def test_segment_single_chunk():
    segmenter = NaiveSegmenter()
    blocks = [
        Block(
            id="b1",
            type=BlockType.HEADING,
            content="Introduction",
            page=1,
            metadata={"heading_level": 1},
        ),
        Block(
            id="b2",
            type=BlockType.PARAGRAPH,
            content="This is the first paragraph.",
            page=1,
        ),
        Block(
            id="b3",
            type=BlockType.LIST_ITEM,
            content="First item",
            page=2,
        ),
    ]

    chunks = segmenter.segment(blocks, max_tokens=100)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.id == "chunk-0"
    assert len(chunk.blocks) == 3
    assert chunk.page_start == 1
    assert chunk.page_end == 2
    assert "# Introduction" in chunk.original_text
    assert "This is the first paragraph." in chunk.original_text
    assert "- First item" in chunk.original_text


def test_segment_splits_on_max_tokens():
    segmenter = NaiveSegmenter()
    blocks = [
        Block(
            id=f"b{i}",
            type=BlockType.PARAGRAPH,
            content="Word " * 50,  # ~65 tokens each
            page=i,
        )
        for i in range(1, 5)
    ]

    # With max_tokens=100, each block (~65 tokens) cannot be combined with another
    chunks = segmenter.segment(blocks, max_tokens=100)
    assert len(chunks) >= 4
    for i, chunk in enumerate(chunks):
        assert chunk.id == f"chunk-{i}"
        assert chunk.page_start == i + 1


def test_semantic_segmenter_protocol():
    from tradutor_pdf.segmentation.semantic import SemanticSegmenter

    segmenter = SemanticSegmenter()
    assert isinstance(segmenter, Segmenter)


def test_semantic_segmenter_separates_non_translatable():
    from tradutor_pdf.segmentation.semantic import SemanticSegmenter

    segmenter = SemanticSegmenter()
    blocks = [
        Block(
            id="b0",
            type=BlockType.HEADING,
            content="Architecture",
            page=1,
            metadata={"heading_level": 1},
        ),
        Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            content="Here is a description of the system.",
            page=1,
        ),
        Block(
            id="b2",
            type=BlockType.CODE,
            content="def run():\n    pass",
            page=1,
            translatable=False,
            metadata={"language": "python"},
        ),
        Block(
            id="b3",
            type=BlockType.PARAGRAPH,
            content="And here is a summary following the code.",
            page=1,
        ),
        Block(
            id="b4",
            type=BlockType.TABLE,
            content="| Col1 | Col2 |\n|---|---|\n| A | B |",
            page=2,
            translatable=False,
        ),
        Block(
            id="b5",
            type=BlockType.IMAGE,
            content="assets/img_001.png",
            page=2,
            translatable=False,
            metadata={"alt": "Sample Diagram"},
        ),
    ]

    chunks = segmenter.segment(blocks, max_tokens=800)

    # Expected chunks:
    # 0: Heading + Paragraph (translatable)
    # 1: Code (skipped, non-translatable)
    # 2: Paragraph (translatable)
    # 3: Table (skipped, non-translatable)
    # 4: Image (skipped, non-translatable)
    assert len(chunks) == 5

    assert chunks[0].status == "pending"
    assert "# Architecture" in chunks[0].original_text
    assert "Here is a description" in chunks[0].original_text

    assert chunks[1].status == "skipped"
    assert "```python\ndef run():\n    pass\n```" in chunks[1].original_text
    assert chunks[1].translated_text == chunks[1].original_text

    assert chunks[2].status == "pending"
    assert "And here is a summary" in chunks[2].original_text

    assert chunks[3].status == "skipped"
    assert "| Col1 | Col2 |" in chunks[3].original_text

    assert chunks[4].status == "skipped"
    assert "![Sample Diagram](assets/img_001.png)" in chunks[4].original_text


def test_semantic_segmenter_heading_levels_and_lists():
    from tradutor_pdf.segmentation.semantic import SemanticSegmenter

    segmenter = SemanticSegmenter()
    blocks = [
        Block(
            id="b0",
            type=BlockType.HEADING,
            content="Main Title",
            page=1,
            metadata={"heading_level": 1},
        ),
        Block(
            id="b1",
            type=BlockType.HEADING,
            content="Subtitle Section",
            page=1,
            metadata={"heading_level": 2},
        ),
        Block(
            id="b2",
            type=BlockType.HEADING,
            content="Subsection Detail",
            page=1,
            metadata={"heading_level": 3},
        ),
        Block(
            id="b3",
            type=BlockType.LIST_ITEM,
            content="First item",
            page=1,
        ),
        Block(
            id="b4",
            type=BlockType.LIST_ITEM,
            content="- Already bulleted",
            page=1,
        ),
    ]

    chunks = segmenter.segment(blocks, max_tokens=800)
    assert len(chunks) == 1
    text = chunks[0].original_text
    assert "# Main Title" in text
    assert "## Subtitle Section" in text
    assert "### Subsection Detail" in text
    assert "- First item" in text
    assert "- Already bulleted" in text
