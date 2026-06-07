from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from typing import List, Optional, Dict, Any

class QdrantStorage: 
    def __init__(self, url="http://localhost:6333", collection="docs", dim=1024):
        self.client = QdrantClient(url=url, timeout=300)
        self.collection = collection
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, ids: List[str], vectors: List[List[float]], payloads: List[Dict[str, Any]]):
        points = [PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i]) for i in range(len(ids))]
        self.client.upsert(self.collection, points=points)

    def search(
        self,
        query_vector,
        top_k: int = 5,
        min_score: Optional[float] = None,
        query_filter=None,
    ):
        response = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            with_payload=True,
            limit=top_k,
            score_threshold=min_score,
        )

        hits = []
        sources = set()
        for point in response.points:
            payload = getattr(point, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            if not text:
                continue

            hits.append({
                "id": str(getattr(point, "id", "")),
                "text": text,
                "source": source,
                "score": float(getattr(point, "score", 0.0)) if getattr(point, "score", None) is not None else None,
                "page": payload.get("page"),
                "start": payload.get("start"),
                "end": payload.get("end"),
            })
            sources.add(source)

        return {"hits": hits, "sources": list(sources)}