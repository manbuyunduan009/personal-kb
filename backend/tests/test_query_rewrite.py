from app.query_rewrite import MAX_QUERY_CHARS, rewrite_queries


def test_rewrite_queries_falls_back_without_api_key():
    result = rewrite_queries(
        "请问 周年庆是哪个游戏的？",
        fallback_queries=["周年庆 游戏 项目", "周年庆 项目归属"],
        api_key="",
        base_url="https://example.com/v1",
        model="test-model",
        max_queries=5,
    )

    assert result["used_llm"] is False
    assert "OPENAI_API_KEY" in result["error"]
    assert result["queries"][0] == "请问 周年庆是哪个游戏的？"
    assert "周年庆 游戏 项目" in result["queries"]


def test_rewrite_queries_uses_llm_json_and_cleans_output():
    long_query = "周年庆活动项目归属字段应该如何从需求基础信息表格中定位出来" * 4

    def fake_llm(prompt):
        assert "只输出 JSON 字符串数组" in prompt
        return """
        ```json
        [
          "周年庆是哪个游戏",
          "周年庆是哪个游戏",
          "查询1：周年庆 项目/部门所属 游戏",
          "以下是解释，不应该作为 query",
          "%s"
        ]
        ```
        """ % long_query

    result = rewrite_queries(
        "周年庆是哪个游戏的？",
        fallback_queries=["周年庆 游戏"],
        api_key="fake-key",
        base_url="https://example.com/v1",
        model="test-model",
        max_queries=3,
        llm_callable=fake_llm,
    )

    assert result["used_llm"] is True
    assert result["error"] is None
    assert result["queries"] == [
        "周年庆是哪个游戏",
        "周年庆 项目/部门所属 游戏",
        long_query[:MAX_QUERY_CHARS],
    ]
    assert all(len(query) <= MAX_QUERY_CHARS for query in result["queries"])


def test_rewrite_queries_parses_numbered_lines_when_json_is_not_available():
    def fake_llm(_prompt):
        return """
        以下是改写：
        1. 十七周年庆 小程序 需求
        2. 周年庆 活动 预约 授权
        - 周年庆 小程序 功能模块
        """

    result = rewrite_queries(
        "十七周年庆小程序有哪些需求？",
        fallback_queries=[],
        api_key="fake-key",
        base_url="",
        model="",
        max_queries=5,
        llm_callable=fake_llm,
    )

    assert result["used_llm"] is True
    assert result["queries"][:3] == [
        "十七周年庆 小程序 需求",
        "周年庆 活动 预约 授权",
        "周年庆 小程序 功能模块",
    ]


def test_rewrite_queries_falls_back_when_llm_raises():
    def broken_llm(_prompt):
        raise RuntimeError("network timeout")

    result = rewrite_queries(
        "用户反馈入口在哪？",
        fallback_queries=["用户反馈 入口"],
        api_key="fake-key",
        base_url="",
        model="",
        max_queries=5,
        llm_callable=broken_llm,
    )

    assert result["used_llm"] is False
    assert "network timeout" in result["error"]
    assert result["queries"] == ["用户反馈入口在哪？", "用户反馈 入口"]


class FakeMessage:
    content = '["项目归属 字段", "需求基础信息 项目/部门所属"]'


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = FakeChat()


def test_rewrite_queries_supports_fake_openai_client_factory():
    created_clients = []

    def fake_client_factory(**kwargs):
        client = FakeClient(**kwargs)
        created_clients.append(client)
        return client

    result = rewrite_queries(
        "周年庆是哪个游戏的？",
        fallback_queries=[],
        api_key="fake-key",
        base_url="https://example.com/v1",
        model="test-model",
        max_queries=5,
        client_factory=fake_client_factory,
    )

    assert result["used_llm"] is True
    assert result["queries"][:2] == ["项目归属 字段", "需求基础信息 项目/部门所属"]
    assert created_clients[0].kwargs["api_key"] == "fake-key"
    assert created_clients[0].kwargs["base_url"] == "https://example.com/v1"
    call = created_clients[0].chat.completions.calls[0]
    assert call["model"] == "test-model"
    assert call["temperature"] == 0
