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
        # Tag payloads with vendor when source indicates VNPT manuals to allow filtered retrieval
        is_vnpt = "vnpt" in (source_id or "").lower()
        payloads = [
            {
                "source": source_id,
                "text": chunk.text,
                "chunk_id": chunk.id,
                "page": chunk.page,
                "start": chunk.start,
                "end": chunk.end,
                **({"product_vendor": "vnpt"} if is_vnpt else {}),
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
    # Always use local Ollama LLM `llama3.2:3b`
    def _get_adapter(model_choice: str = "llama3.2:3b"):
        return ai.openai.Adapter(
            auth_key="ollama",
            base_url="http://localhost:11434/v1",
            model="llama3.2:3b",
        )

    # Simple heuristic to detect Vietnamese questions (basic)
    # def _is_vietnamese(text: str) -> bool:
    #     if not text:
    #         return False
    #     t = text.lower()
    #     vi_tokens = ["thêm", "làm", "sao", "cách", "camera", "thiết bị", "qr", "mã", "cài đặt"]
    #     if any(tok in t for tok in vi_tokens):
    #         return True
    #     # common diacritics check
    #     if any(ch in t for ch in "ắằẳâấầêếềốồộọữễộđ"):  # some vietnamese chars
    #         return True
    #     return False

    def _search(query: str, top_k: int = 5, selected_files: list = None) -> RAGSearchResult:
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        query_vec = embed_texts([query])[0]
        store = QdrantStorage()
        
        filters = None
        if selected_files:
            filters = Filter(
                must=[FieldCondition(key="source", match=MatchAny(any=selected_files))]
            )
        # elif _is_vietnamese(question):
        #     pass
            
        found = store.search(query_vec, top_k, min_score=0.25, query_filter=filters)
        return RAGSearchResult(hits=found["hits"])

    def _limit_hits_per_source(hits, per_source: int = 1):
        grouped = {}
        for hit in hits:
            grouped.setdefault(hit["source"], []).append(hit)
        selected = []
        for source_hits in grouped.values():
            source_hits.sort(key=lambda h: (h.get("rerank_score") if h.get("rerank_score") is not None else h.get("score") or 0.0), reverse=True)
            selected.extend(source_hits[:per_source])
        selected.sort(key=lambda h: (h.get("rerank_score") if h.get("rerank_score") is not None else h.get("score") or 0.0), reverse=True)
        return selected

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))
    model_choice = ctx.event.data.get("model", "llama3.2:3b")
    per_source_limit = int(ctx.event.data.get("per_source_limit", 5))
    selected_files = ctx.event.data.get("selected_files", [])
    adapter = _get_adapter(model_choice)

    ENABLE_RERANKER = True

    search_query = question

    # Fetch more candidates initially to give reranker more options
    found = await ctx.step.run("embed-and-search", lambda: _search(search_query, max(top_k * 6, 20), selected_files), output_type=RAGSearchResult)

    hits = [hit.model_dump() for hit in found.hits]
    if not hits:
        return {"answer": "Xin lỗi, tôi không tìm thấy thông tin nào liên quan trong tài liệu.", "sources": [], "num_contexts": 0, "citations": []}

    if ENABLE_RERANKER and hits:
        try:
            hits = rerank(question, hits, top_n=len(hits))
        except Exception:
            pass

    hits = _limit_hits_per_source(hits, per_source=per_source_limit)

    selected_hits = hits[:top_k]
    if not selected_hits:
        return {"answer": "Xin lỗi, câu hỏi của bạn không khớp với thông tin nào trong tài liệu.", "sources": [], "num_contexts": 0, "citations": []}

    context_lines = []
    citations = []
    for idx, hit in enumerate(selected_hits, start=1):
        citation = f"[{idx}] {hit['text']} (source: {hit['source']})"
        context_lines.append(citation)
        # Sửa để in hẳn nội dung text ra UI cho bạn dễ debug
        citations.append(f"[{idx}] {hit['source']} - Text: {hit['text']}")

    context_block = "\n\n".join(context_lines)
    # Instruct the LLM to be step-by-step, offer alternatives, and avoid hallucination.
    language_instruction = "Respond in Vietnamese if the question is Vietnamese; otherwise respond in the same language as the question."
    user_content = (
    "Bạn là một chuyên gia hỗ trợ kỹ thuật. BẮT BUỘC TRẢ LỜI 100% BẰNG TIẾNG VIỆT.\n\n"
    "QUY TẮC:\n"
    "1. CHỈ sử dụng thông tin trong phần 'Ngữ cảnh' dưới đây. KHÔNG bịa thêm thông tin, link, hoặc bước nào không có trong tài liệu.\n"
    "2. Trả lời CHÍNH XÁC, NGẮN GỌN nhưng vẫn ĐẦY ĐỦ thông tin quan trọng.\n"
    "3. Nếu có nhiều cách/phương án, hãy liệt kê đầy đủ. Nếu thông tin trong ngữ cảnh không đủ để trả lời chính xác, hãy nói rõ là không có đủ thông tin.\n"
    f"Câu hỏi của người dùng: {question}\n\n"
    f"Ngữ cảnh:\n{context_block}\n\n"
    "Câu trả lời của bạn:"
)

    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,
            "temperature": 0.2, 
            "options": {
                "num_predict": 1024,
                "num_ctx": 4096,      
            },
            "messages": [
                {"role": "system", "content": "Bạn là trợ lý kỹ thuật chính xác, trả lời đầy đủ chi tiết dựa hoàn toàn trên dữ liệu được cung cấp, không bịa thêm.."},
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
