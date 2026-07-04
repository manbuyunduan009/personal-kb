from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class Citation(BaseModel):
    title: str
    source_path: str
    file_type: str
    chunk_index: int
    chunk_header: str = ""
    summary: str
    score: float
    feedback_score: float = 0.0


class CitationCheck(BaseModel):
    status: str
    support_score: float
    reasons: List[str]
    checked_claim_count: int


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    citation_check: Optional[CitationCheck] = None


class FeedbackRequest(BaseModel):
    question: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    chunk_header: str = ""
    rating: Literal[-1, 1]
    note: str = Field(default="", max_length=500)


class ChangeAnalysisRequest(BaseModel):
    old_document_id: str = Field(min_length=1)
    new_document_id: str = Field(min_length=1)
