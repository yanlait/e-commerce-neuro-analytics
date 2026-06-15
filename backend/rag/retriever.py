import chromadb
from pathlib import Path
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
CHROMA_DIR = Path(__file__).parent.parent.parent / "data/chroma"

_embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_collection = _client.get_or_create_collection("docs", embedding_function=_embed_fn)


def index_docs():
    ids, docs, metas = [], [], []
    for md in DOCS_DIR.glob("*.md"):
        text = md.read_text()
        # split into ~500 char chunks with overlap
        chunk_size, overlap = 500, 50
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size].strip()
            if not chunk:
                continue
            ids.append(f"{md.stem}_{i}")
            docs.append(chunk)
            metas.append({"source": md.name})
    if ids:
        _collection.upsert(ids=ids, documents=docs, metadatas=metas)
    print(f"Indexed {len(ids)} chunks from {DOCS_DIR}")


def retrieve(query: str, n: int = 3) -> list[dict]:
    results = _collection.query(query_texts=[query], n_results=n)
    if not results["documents"]:
        return []
    return [
        {"text": doc, "source": meta["source"]}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]
