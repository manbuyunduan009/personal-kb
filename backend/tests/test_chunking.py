from app.chunking import split_text


def test_split_text_uses_overlap():
    text = "a" * 1000
    chunks = split_text(text, chunk_size=800, overlap=120)

    assert len(chunks) == 2
    assert len(chunks[0]) == 800
    assert chunks[0][-120:] == chunks[1][:120]


def test_split_text_skips_empty_content():
    assert split_text(" \n\n ") == []
