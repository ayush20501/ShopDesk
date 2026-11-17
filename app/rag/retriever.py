import re
from dataclasses import dataclass

import chromadb
from rank_bm25 import BM25Okapi

from .chunker import make_chunks

RRF_K = 60
CANDIDATES = 8


@dataclass
class Hit:
    id: str
    source: str
    heading: str
    text: str
    score: float


def _tokens(text):
    return re.findall(r"[a-z0-9₹]+", text.lower())


def fuse(rankings, k=RRF_K):
    scores = {}
    for ranking in rankings:
        for pos, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + pos + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def collection_name(chunking):
    return f"policies_{chunking}"


def ingest(settings, chunking=None):
    chunking = chunking or settings.chunking
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    name = collection_name(chunking)
    try:
        client.delete_collection(name)
    except Exception:
        pass
    col = client.create_collection(name)

    chunks = []
    for path in sorted(settings.policies_dir.glob("*.md")):
        chunks += make_chunks(path.name, path.read_text(encoding="utf-8"), chunking)
    col.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[{"source": c["source"], "heading": c["heading"]} for c in chunks],
    )
    return len(chunks)


class Retriever:
    def __init__(self, settings):
        self.settings = settings
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.col = client.get_collection(collection_name(settings.chunking))
        data = self.col.get()
        self.by_id = {
            i: Hit(i, m["source"], m["heading"], d, 0.0)
            for i, d, m in zip(data["ids"], data["documents"], data["metadatas"])
        }
        self.order = list(self.by_id)
        self.bm25 = BM25Okapi([_tokens(self.by_id[i].text) for i in self.order])

    def _vector(self, query):
        res = self.col.query(query_texts=[query], n_results=min(CANDIDATES, len(self.order)))
        return res["ids"][0]

    def _keyword(self, query):
        scores = self.bm25.get_scores(_tokens(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self.order[i] for i in ranked[:CANDIDATES] if scores[i] > 0]

    def search(self, query, k=None):
        k = k or self.settings.top_k
        mode = self.settings.retrieval
        if mode == "vector":
            ranked = [(i, 1.0 / (RRF_K + p + 1)) for p, i in enumerate(self._vector(query))]
        elif mode == "bm25":
            ranked = [(i, 1.0 / (RRF_K + p + 1)) for p, i in enumerate(self._keyword(query))]
        elif mode == "hybrid":
            ranked = fuse([self._vector(query), self._keyword(query)])
        else:
            raise ValueError(f"unknown retrieval mode: {mode}")
        hits = []
        for item, score in ranked[:k]:
            hit = self.by_id[item]
            hits.append(Hit(hit.id, hit.source, hit.heading, hit.text, score))
        return hits
