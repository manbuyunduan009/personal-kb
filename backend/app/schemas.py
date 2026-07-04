from typing import List

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
    summary: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
