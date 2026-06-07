from docling.document_converter import DocumentConverter
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core import Document
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import torch
import numpy as np
import os

load_dotenv()

EMBED_MODEL = "BAAI/bge-m3"
EMBED_DIM = 1024

# Use smaller chunks with overlap to improve evidence localization and reduce cross-document drift.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

device = "cuda" if torch.cuda.is_available() else "cpu"

if device == "cuda":
    torch.cuda.empty_cache()

embedding_model = None
md_parser = MarkdownNodeParser()

splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


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

# def load_and_chunk_pdf(path: str):
#     converter = DocumentConverter()
#     doc = converter.convert(path).document
#     markdown_text = doc.export_to_markdown()
#     chunks = splitter.split_text(markdown_text)
#     return chunks

def load_and_chunk_pdf(path: str, source_id: str | None = None):
    converter = DocumentConverter()
    doc = converter.convert(path).document
    markdown_text = doc.export_to_markdown()
    source = source_id or os.path.basename(path)
    llama_doc = Document(text=markdown_text)
    nodes = md_parser.get_nodes_from_documents([llama_doc])
    chunks = [node.get_content() for node in nodes]
    
    final_chunks = []
    for idx, chunk in enumerate(chunks):
        split_chunks = splitter.split_text(chunk)
        for sub_idx, split_chunk in enumerate(split_chunks):
            text = split_chunk.strip()
            if not text:
                continue
            chunk_id = f"{source}:{idx}-{sub_idx}"
            final_chunks.append({
                "id": chunk_id,
                "text": text,
                "source": source,
            })
    return final_chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, batch_size=128, show_progress_bar=False, convert_to_numpy=True)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / np.maximum(norms, 1e-12)
    return normalized.tolist()