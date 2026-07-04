from pathlib import Path

from app.db import DocumentRepository


def test_feedback_summary_counts_helpful_and_unhelpful(tmp_path: Path):
    repository = DocumentRepository(tmp_path / "kb.sqlite3")

    repository.add_feedback("问题", "a.md", 0, "标题", 1)
    repository.add_feedback("问题", "a.md", 0, "标题", -1)
    repository.add_feedback("问题", "a.md", 0, "标题", 1)

    summary = repository.feedback_summary()

    assert summary[0]["source_path"] == "a.md"
    assert summary[0]["chunk_index"] == 0
    assert summary[0]["helpful_count"] == 2
    assert summary[0]["unhelpful_count"] == 1
    assert summary[0]["feedback_score"] == 1

