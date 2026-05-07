from docling.document_converter import DocumentConverter
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core import Document
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import torch
# import numpy as np
# np.random.seed(42)
# torch.manual_seed(42)
# torch.cuda.manual_seed_all(42)

load_dotenv()

EMBED_MODEL = "BAAI/bge-m3"
EMBED_DIM = 1024

device = "cuda" if torch.cuda.is_available() else "cpu"

if device == "cuda":
    torch.cuda.empty_cache()

embedding_model = None
md_parser = MarkdownNodeParser()

splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)


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

def load_and_chunk_pdf(path: str):
    converter = DocumentConverter()
    doc = converter.convert(path).document
    markdown_text = doc.export_to_markdown()
    llama_doc = Document(text=markdown_text)
    nodes = md_parser.get_nodes_from_documents([llama_doc])
    chunks = [node.get_content() for node in nodes]
    
    # Single-stage split: use SentenceSplitter on all chunks
    final_chunks = []
    for chunk in chunks:
        split_chunks = splitter.split_text(chunk)
        final_chunks.extend(split_chunks)
    return final_chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, batch_size=2, show_progress_bar=False)

    # Convert the numpy array back to a standard Python list of lists
    return embeddings.tolist()