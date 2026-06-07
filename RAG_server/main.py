import logging
from fastapi import FastAPI
import inngest
import inngest.fast_api
from dotenv import load_dotenv
import uuid
import os
from inngest.experimental import ai
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage
from custom_types import RAGChunkAndSrc, RAGSearchResult, RAGUpsertResult, RAGQueryResult
from reranker import rerank

load_dotenv()

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer()

)

@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf")
)
async def rag_ingest_pdf(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", os.path.basename(pdf_path))
        chunks = load_and_chunk_pdf(pdf_path, source_id=source_id)
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)
    
    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id
        text_list = [chunk.text for chunk in chunks]
        vecs = embed_texts(text_list)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{chunk.id}")) for chunk in chunks]
        payloads = [
            {
                "source": source_id,
                "text": chunk.text,
                "chunk_id": chunk.id,
                "page": chunk.page,
                "start": chunk.start,
                "end": chunk.end,
            }
            for chunk in chunks
        ]
        QdrantStorage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))
    
    chunks_and_src = await ctx.step.run("load-and-chunk", lambda: _load(ctx), output_type=RAGChunkAndSrc)
    ingested = await ctx.step.run("embed-and-upsert", lambda: _upsert(chunks_and_src), output_type=RAGUpsertResult)
    return ingested.model_dump()

@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    def _get_adapter(model_choice: str):
        return ai.openai.Adapter(
            auth_key="ollama",
            base_url="http://localhost:11434/v1",
            model="llama3:8b",
        )

    async def _clarify_question(question: str, adapter) -> str:
        prompt = (
            "Rewrite the user question into a concise, retrieval-friendly search query that preserves the original meaning. "
            "If the question is already specific, return it unchanged.\n\n"
            f"User question: {question}\n"
            "Search query:"
        )
        res = await ctx.step.ai.infer(
            "clarify-question",
            adapter=adapter,
            body={
                "max_tokens": 64,
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": "You rewrite questions for document retrieval."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        return res["choices"][0]["message"]["content"].strip() or question

    def _search(query: str, top_k: int = 5) -> RAGSearchResult:
        query_vec = embed_texts([query])[0]
        store = QdrantStorage()
        found = store.search(query_vec, top_k, min_score=0.18)
        return RAGSearchResult(hits=found["hits"])

    def _limit_hits_per_source(hits, per_source: int = 1):
        grouped = {}
        for hit in hits:
            grouped.setdefault(hit["source"], []).append(hit)
        selected = []
        for source_hits in grouped.values():
            source_hits.sort(key=lambda h: (h.get("score") or 0.0), reverse=True)
            selected.extend(source_hits[:per_source])
        selected.sort(key=lambda h: (h.get("rerank_score") if h.get("rerank_score") is not None else h.get("score") or 0.0), reverse=True)
        return selected

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))
    model_choice = ctx.event.data.get("model", "llama")
    per_source_limit = int(ctx.event.data.get("per_source_limit", 1))
    adapter = _get_adapter(model_choice)

    clarified_query = await _clarify_question(question, adapter)
    search_query = clarified_query or question

    found = await ctx.step.run("embed-and-search", lambda: _search(search_query, max(top_k * 4, 12)), output_type=RAGSearchResult)

    hits = [hit.model_dump() for hit in found.hits]
    if not hits:
        return {"answer": "I don't know. There is no relevant information in the ingested documents.", "sources": [], "num_contexts": 0, "citations": []}

    hits = _limit_hits_per_source(hits, per_source=per_source_limit)
    if hits:
        hits = rerank(question, hits, top_n=top_k)
    else:
        hits = hits[:top_k]

    selected_hits = hits[:top_k]
    if not selected_hits:
        return {"answer": "I don't know. The query does not match any reliable document evidence.", "sources": [], "num_contexts": 0, "citations": []}

    context_lines = []
    citations = []
    for idx, hit in enumerate(selected_hits, start=1):
        citation = f"[{idx}] {hit['text']} (source: {hit['source']})"
        context_lines.append(citation)
        citations.append(f"[{idx}] {hit['source']}:{hit['id']}")

    context_block = "\n\n".join(context_lines)
    user_content = (
        "Answer the question using only the numbered contexts below. "
        "Do not add any information that is not supported by the provided contexts. "
        "For each factual claim, cite the supporting context number in brackets. "
        "If the answer cannot be derived from the contexts, say 'I don't know' or 'I cannot answer based on the provided documents.'\n\n"
        f"Original question: {question}\n"
        f"Search query: {search_query}\n\n"
        f"Context:\n{context_block}\n\n"
        "Answer:"
    )

    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 8192,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "You answer questions using only the provided document evidence and cite context numbers."},
                {"role": "user", "content": user_content},
            ],
        },
    )

    answer = res["choices"][0]["message"]["content"].strip()
    return {
        "answer": answer,
        "sources": list({hit["source"] for hit in selected_hits}),
        "num_contexts": len(selected_hits),
        "citations": citations,
    }

app = FastAPI()

inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])
