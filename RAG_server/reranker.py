import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import CrossEncoder
except ImportError:  # pragma: no cover
    CrossEncoder = None

RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
_reranker_model = None


def get_reranker() -> Any:
    global _reranker_model
    if _reranker_model is None:
        if CrossEncoder is None:
            raise RuntimeError("CrossEncoder is not installed")
        _reranker_model = CrossEncoder(RERANKER_MODEL)
    return _reranker_model


def rerank(question: str, hits: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    if not hits:
        return []
    try:
        model = get_reranker()
        pairs = [[question, hit["text"]] for hit in hits]
        scores = model.predict(pairs, convert_to_numpy=True)
        for hit, score in zip(hits, scores):
            hit["rerank_score"] = float(score)
        return sorted(hits, key=lambda item: item["rerank_score"], reverse=True)[:top_n]
    except Exception as exc:
        logger.warning("Reranker failed: %s", exc)
        return hits[:top_n]
