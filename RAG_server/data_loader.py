from docling.document_converter import DocumentConverter
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core import Document
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import torch
import numpy as np
import os
import re

load_dotenv()

EMBED_MODEL = "BAAI/bge-m3"
EMBED_DIM = 1024
# Maximum batch size for embedding; tune via env var for GTX 1650 (default small)
EMBED_MAX_BATCH = int(os.getenv("EMBED_MAX_BATCH", "16"))

# Use smaller chunks with overlap to improve evidence localization and reduce cross-document drift.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

device = "cuda" if torch.cuda.is_available() else "cpu"

if device == "cuda":
    torch.cuda.empty_cache()

embedding_model = None
md_parser = MarkdownNodeParser()

splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def clean_text(text: str) -> str:
    text = re.sub(r'about:reader\?url=[^\s]+', '', text)
    text = re.sub(r'<!--\s*image\s*-->', '', text)          # strip image placeholders — pure noise
    text = re.sub(r'\b\d+\s+of\s+\d+\b', '', text)
    text = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4},\s*\d{2}:\d{2}\b', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def get_embedding_model() -> SentenceTransformer:
    global embedding_model, device
    if embedding_model is None:
        try:
            embedding_model = SentenceTransformer(EMBED_MODEL, device=device)
        except RuntimeError as exc:
            error_text = str(exc).lower()
            if "out of memory" in error_text and device == "cuda":
                torch.cuda.empty_cache()
                device = "cpu"
                embedding_model = SentenceTransformer(EMBED_MODEL, device=device)
            else:
                raise
    return embedding_model

def load_and_chunk_pdf(path: str, source_id: str | None = None):
    converter = DocumentConverter()
    doc = converter.convert(path).document
    markdown_text = clean_text(doc.export_to_markdown())
    source = source_id or os.path.basename(path)
    llama_doc = Document(text=markdown_text)
    nodes = md_parser.get_nodes_from_documents([llama_doc])
    chunks = [node.get_content() for node in nodes]

    final_chunks = []
    for idx, chunk in enumerate(chunks):
        for sub_idx, split_chunk in enumerate(splitter.split_text(chunk)):
            text = split_chunk.strip()
            if not text:
                continue
            # Prefix with source name so the embedding model gets document context
            enriched_text = f"[{source}]\n{text}"
            final_chunks.append({"id": f"{source}:{idx}-{sub_idx}", "text": enriched_text, "source": source})
    return final_chunks


def _chunk_list(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts with adaptive batching to avoid GPU OOM on small GPUs.

    Tries to use the configured device (GPU if available) and splits the
    inputs into smaller batches controlled by `EMBED_MAX_BATCH`. On a
    RuntimeError (OOM), it will reduce batch size and retry, eventually
    falling back to CPU.
    """
    model = get_embedding_model()

    # Start with a conservative batch size tuned for GTX 1650
    batch_size = EMBED_MAX_BATCH if EMBED_MAX_BATCH > 0 else 16
    all_embeddings = []

    # Helper to encode a list of texts and return numpy array
    def _encode_chunk(chunk_texts, bs):
        return model.encode(chunk_texts, batch_size=bs, show_progress_bar=False, convert_to_numpy=True)

    texts_remaining = list(texts)
    while texts_remaining:
        try:
            for chunk in _chunk_list(texts_remaining, batch_size):
                emb = _encode_chunk(chunk, batch_size)
                all_embeddings.append(emb)
            break
        except RuntimeError as exc:
            err = str(exc).lower()
            if "out of memory" in err and device == "cuda" and batch_size > 1:
                # Reduce batch size and retry
                batch_size = max(1, batch_size // 2)
                torch.cuda.empty_cache()
                continue
            else:
                # Unexpected error: re-raise
                raise

    if not all_embeddings:
        return []

    embeddings = np.vstack(all_embeddings)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / np.maximum(norms, 1e-12)
    return normalized.tolist()