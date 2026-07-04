import json
import sys
import urllib.error
import urllib.request


SEARCH_API_URL = "http://127.0.0.1:8000/api/search"
CHAT_API_URL = "http://127.0.0.1:8000/api/chat"

CASES = [
    {
        "question": "专题验收助手的目标用户是谁？",
        "expected_title": "专题验收助手PRD.md",
    },
    {
        "question": "专题验收助手要解决什么问题？",
        "expected_title": "专题验收助手PRD.md",
    },
    {
        "question": "专题验收助手的目标有哪些？",
        "expected_title": "专题验收助手PRD.md",
    },
    {
        "question": "十七周年庆小程序有哪些需求？",
        "expected_title": "【需求管理】《剑网3》十七周年庆线下活动小程序.docx",
    },
    {
        "question": "专项进度计划表里有哪些阶段？",
        "expected_title": "2026年-剑网3-十七周年庆专项进度计划表@260712.xlsx",
    },
]

CHAT_CASES = [
    {
        "question": "专题验收助手的目标用户是谁？",
        "expected_title": "专题验收助手PRD.md",
    },
    {
        "question": "十七周年庆小程序有哪些需求？",
        "expected_title": "【需求管理】《剑网3》十七周年庆线下活动小程序.docx",
    },
    {
        "question": "火星移民方案预算是多少？",
        "expect_no_evidence": True,
    },
]


def search(question: str, limit: int = 3):
    payload = json.dumps({"query": question, "limit": limit}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        SEARCH_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["results"]


def chat(question: str):
    payload = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        CHAT_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    failures = 0
    for case in CASES:
        try:
            results = search(case["question"])
        except urllib.error.URLError as exc:
            print("API request failed. Is the backend running at http://127.0.0.1:8000?")
            print(exc)
            return 2

        titles = [item["metadata"]["title"] for item in results]
        passed = case["expected_title"] in titles
        if not passed:
            failures += 1

        status = "PASS" if passed else "FAIL"
        print("\n[%s] %s" % (status, case["question"]))
        print("expected:", case["expected_title"])
        for index, item in enumerate(results, start=1):
            metadata = item["metadata"]
            snippet = item["content"].replace("\n", " ")[:100]
            print(
                "%s. score=%.3f title=%s chunk=%s text=%s"
                % (index, item["score"], metadata["title"], metadata["chunk_index"], snippet)
            )

    chat_failures = 0
    for case in CHAT_CASES:
        try:
            result = chat(case["question"])
        except urllib.error.URLError as exc:
            print("API request failed. Is the backend running at http://127.0.0.1:8000?")
            print(exc)
            return 2

        answer = result.get("answer", "")
        citations = result.get("citations", [])
        citation_titles = [item.get("title", "") for item in citations]

        if case.get("expect_no_evidence"):
            passed = "文档中没有找到依据" in answer and not citations
        else:
            passed = case["expected_title"] in citation_titles

        if not passed:
            chat_failures += 1

        status = "PASS" if passed else "FAIL"
        print("\n[%s][CHAT] %s" % (status, case["question"]))
        if case.get("expect_no_evidence"):
            print("expected: no evidence refusal")
        else:
            print("expected citation:", case["expected_title"])
        print("answer:", answer.replace("\n", " ")[:160])
        for index, citation in enumerate(citations[:3], start=1):
            print(
                "%s. score=%.3f title=%s chunk=%s"
                % (
                    index,
                    citation.get("score", 0.0),
                    citation.get("title", ""),
                    citation.get("chunk_index", ""),
                )
            )

    failures += chat_failures
    total = len(CASES) + len(CHAT_CASES)
    print("\nSummary: %s/%s passed" % (total - failures, total))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
