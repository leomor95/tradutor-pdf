from tradutor_pdf.extraction.cleaner import (
    clean_blocks,
    dehyphenate_text,
    is_standalone_page_number,
    remove_repeated_headers_footers,
)
from tradutor_pdf.pipeline import Block, BlockType


def test_dehyphenate_text_line_breaks():
    assert dehyphenate_text("distrib-\nuted systems") == "distributed systems"
    assert dehyphenate_text("implemen-\n  tation") == "implementation"
    assert dehyphenate_text("PARAL-\nLEL") == "PARALLEL"
    assert dehyphenate_text("asynchro-\r\nnous execution") == "asynchronous execution"


def test_dehyphenate_text_preserves_compound_words():
    # Intact hyphens on the same line must not be merged
    assert dehyphenate_text("high-availability cluster") == "high-availability cluster"
    assert dehyphenate_text("state-of-the-art model") == "state-of-the-art model"
    assert dehyphenate_text("real-time processing") == "real-time processing"


def test_is_standalone_page_number():
    assert is_standalone_page_number("1") is True
    assert is_standalone_page_number(" 42 ") is True
    assert is_standalone_page_number("Page 5") is True
    assert is_standalone_page_number("pág. 12") is True
    assert is_standalone_page_number("- 3 -") is True
    assert is_standalone_page_number("[ 7 ]") is True
    assert is_standalone_page_number("4 / 10") is True
    assert is_standalone_page_number("12 of 30") is True

    # Real text must return False
    assert is_standalone_page_number("Chapter 1: The Beginning") is False
    assert is_standalone_page_number("There are 3 workers in the pool.") is False
    assert is_standalone_page_number("Section 2.1 Overview") is False
    assert is_standalone_page_number("") is False


def test_remove_repeated_headers_footers():
    blocks = [
        # Page 1
        Block(
            id="b0",
            type=BlockType.HEADING,
            content="Chapter 1: Concurrency",
            page=1,
        ),
        Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            content="Content of chapter 1.",
            page=1,
        ),
        Block(id="b2", type=BlockType.PARAGRAPH, content="Page 1", page=1),
        # Page 2
        Block(
            id="b3",
            type=BlockType.PARAGRAPH,
            content="Concurrency in Practice",
            page=2,
        ),  # Running header
        Block(
            id="b4",
            type=BlockType.PARAGRAPH,
            content="Content of page 2.",
            page=2,
        ),
        Block(id="b5", type=BlockType.PARAGRAPH, content="Page 2", page=2),
        # Page 3
        Block(
            id="b6",
            type=BlockType.PARAGRAPH,
            content="Concurrency in Practice",
            page=3,
        ),  # Running header
        Block(
            id="b7",
            type=BlockType.PARAGRAPH,
            content="Content of page 3.",
            page=3,
        ),
        Block(id="b8", type=BlockType.PARAGRAPH, content="Page 3", page=3),
    ]

    cleaned = remove_repeated_headers_footers(blocks)
    contents = [b.content for b in cleaned]

    # Running headers and footers removed
    assert "Concurrency in Practice" not in contents
    assert "Page 1" not in contents
    assert "Page 2" not in contents
    assert "Page 3" not in contents

    # Unique content preserved
    assert "Chapter 1: Concurrency" in contents
    assert "Content of chapter 1." in contents
    assert "Content of page 2." in contents
    assert "Content of page 3." in contents


def test_remove_explicit_page_header_footer():
    blocks = [
        Block(
            id="b0",
            type=BlockType.PARAGRAPH,
            content="Top Header",
            page=1,
            metadata={"label": "page_header"},
        ),
        Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            content="Legitimate content.",
            page=1,
            metadata={"label": "text"},
        ),
        Block(
            id="b2",
            type=BlockType.PARAGRAPH,
            content="Bottom Footer",
            page=1,
            metadata={"label": "page_footer"},
        ),
    ]
    cleaned = remove_repeated_headers_footers(blocks)
    assert len(cleaned) == 1
    assert cleaned[0].content == "Legitimate content."


def test_clean_blocks_end_to_end():
    blocks = [
        Block(
            id="b0",
            type=BlockType.PARAGRAPH,
            content="Doc Header",
            page=1,
        ),
        Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            content="High-concur-\nrency message broker.",
            page=1,
        ),
        Block(id="b2", type=BlockType.PARAGRAPH, content="1", page=1),
        Block(
            id="b3",
            type=BlockType.PARAGRAPH,
            content="Doc Header",
            page=2,
        ),
        Block(
            id="b4",
            type=BlockType.PARAGRAPH,
            content="Scalable archi-\ntecture.",
            page=2,
        ),
        Block(id="b5", type=BlockType.PARAGRAPH, content="2", page=2),
    ]

    cleaned = clean_blocks(blocks)

    # 2 content blocks remain, re-indexed b0, b1
    assert len(cleaned) == 2
    assert cleaned[0].id == "b0"
    assert cleaned[0].content == "High-concurrency message broker."
    assert cleaned[1].id == "b1"
    assert cleaned[1].content == "Scalable architecture."
