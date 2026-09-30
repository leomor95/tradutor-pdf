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
