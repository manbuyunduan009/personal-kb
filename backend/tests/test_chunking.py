from app.chunking import build_chunk_records, extract_field_facts, split_text


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


def test_build_chunk_records_propagates_document_fields_to_chunks():
    text = "\n".join(
        [
            "# 十七周年庆小程序需求",
            "这里描述预约、授权、活动任务和页面功能。" * 4,
            "*项目/部门所属 | K1-剑网 3 | *需求对接人 | @谢侗聃",
            "这里继续描述上线排期、验收标准和后台配置。" * 4,
        ]
    )

    records = build_chunk_records("周年庆.docx", text, chunk_size=80, overlap=0)

    assert len(records) > 1
    for record in records:
        assert any(
            fact["label"] == "项目/部门所属" and "剑网" in fact["value"]
            for fact in record["field_facts"]
        )
        assert "文档属性" in record["embedding_text"]


def test_build_chunk_records_adds_bounded_parent_context_groups():
    text = ("A" * 10) + ("B" * 10) + ("C" * 10) + ("D" * 10) + ("E" * 10)

    records = build_chunk_records(
        "parent.md",
        text,
        chunk_size=10,
        overlap=0,
        parent_child_count=3,
        parent_context_max_chars=80,
    )

    assert [record["parent_index"] for record in records] == [0, 0, 0, 1, 1]
    assert "AAAAAAAAAA" in records[1]["parent_context"]
    assert "CCCCCCCCCC" in records[1]["parent_context"]
    assert "DDDDDDDDDD" not in records[1]["parent_context"]
    assert "DDDDDDDDDD" in records[3]["parent_context"]
    assert len(records[0]["parent_context"]) <= 80


def test_extract_field_facts_ignores_sentence_like_labels():
    text = "提交后校验订单号和身份证信息是否匹配后台有效订单：校验失败需 toast 提示具体原因。"

    assert extract_field_facts(text) == []
