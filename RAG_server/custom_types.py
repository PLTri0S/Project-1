import pydantic
from typing import List, Optional


class RAGChunk(pydantic.BaseModel):
    id: str
    text: str
    source: str
    page: Optional[int] = None
    start: Optional[int] = None
    end: Optional[int] = None


class RAGChunkAndSrc(pydantic.BaseModel):
    chunks: List[RAGChunk]
    source_id: Optional[str] = None


class RAGUpsertResult(pydantic.BaseModel):
    ingested: int


class RAGSearchHit(pydantic.BaseModel):
    id: str
    text: str
    source: str
    score: Optional[float] = None
    page: Optional[int] = None
    start: Optional[int] = None
    end: Optional[int] = None
    rerank_score: Optional[float] = None


class RAGSearchResult(pydantic.BaseModel):
    hits: List[RAGSearchHit]


class RAGQueryResult(pydantic.BaseModel):
    answer: str
    sources: List[str]
    num_contexts: int
    citations: Optional[List[str]] = None