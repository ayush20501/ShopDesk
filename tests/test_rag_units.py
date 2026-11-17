from app.rag.chunker import MAX_SECTION_CHARS, chunk_by_heading, chunk_fixed, make_chunks
from app.rag.retriever import fuse

DOC = """# Returns

## Return windows
Electronics: 10 days
Home: 30 days

## Items that cannot be returned
Opened earphones.
"""


def test_heading_chunks_keep_the_section_title():
    chunks = chunk_by_heading("returns.md", DOC)
    assert len(chunks) == 2
    assert chunks[0]["text"].startswith("Returns > Return windows")
    assert "10 days" in chunks[0]["text"]
    assert chunks[1]["heading"] == "Items that cannot be returned"


def test_fixed_chunks_overlap_and_cover_everything():
    text = "abcdefghij" * 120
    chunks = chunk_fixed("x.md", text)
    assert all(len(c["text"]) <= 500 for c in chunks)
    assert chunks[0]["text"][-50:] == chunks[1]["text"][:50]
    assert "".join(c["text"][:450] for c in chunks[:-1]) in text


def test_long_sections_are_split():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(8))
    chunks = chunk_by_heading("long.md", f"# Doc\n\n## Section\n{body}")
    assert len(chunks) > 1
    assert all(len(c["text"]) < MAX_SECTION_CHARS + 400 for c in chunks)


def test_unknown_mode_is_an_error():
    try:
        make_chunks("a.md", "text", "magic")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_fusion_rewards_agreement():
    vector = ["a", "b", "c"]
    keyword = ["b", "d", "a"]
    ranked = [item for item, _ in fuse([vector, keyword])]
    assert ranked[:2] == ["b", "a"]
    assert set(ranked) == {"a", "b", "c", "d"}


def test_fusion_with_one_list_keeps_order():
    assert [i for i, _ in fuse([["x", "y", "z"]])] == ["x", "y", "z"]
