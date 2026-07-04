from app.chunking import build_chunk_records, split_text


def test_split_text_uses_overlap():
    text = "a" * 1000
    chunks = split_text(text, chunk_size=800, overlap=120)

    assert len(chunks) == 2
    assert len(chunks[0]) == 800
    assert chunks[0][-120:] == chunks[1][:120]


def test_split_text_skips_empty_content():
    assert split_text(" \n\n ") == []


def test_build_chunk_records_adds_header_and_questions():
    text = "# 十七周年庆小程序需求\n这里描述活动规则、任务奖励和页面功能。"

    records = build_chunk_records("周年庆.docx", text)

    assert records[0]["chunk_header"] == "十七周年庆小程序需求"
    assert any("有哪些需求" in question for question in records[0]["generated_questions"])
    assert "可能问题" in records[0]["embedding_text"]
