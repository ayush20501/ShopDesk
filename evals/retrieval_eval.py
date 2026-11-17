"""Compares chunking and retrieval strategies on retrieval alone (no language model, no cost).

For every policy question we check whether the expected policy file shows up in the top results.

    python -m evals.retrieval_eval
"""
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.rag.retriever import Retriever, ingest

EVALS = Path(__file__).resolve().parent
KS = (1, 4)


def main():
    base = load_settings()
    questions = [
        json.loads(line)
        for line in (EVALS / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = [q for q in questions if q.get("source")]
    rows = []
    for chunking, retrieval in itertools.product(("fixed", "heading"), ("vector", "bm25", "hybrid")):
        ingest(base, chunking)
        retriever = Retriever(base.with_(chunking=chunking, retrieval=retrieval))
        hits = {k: 0 for k in KS}
        reciprocal = 0.0
        for q in questions:
            found = [h.source for h in retriever.search(q["q"], k=max(KS))]
            first = next((i for i, s in enumerate(found) if s in q["source"]), None)
            for k in KS:
                hits[k] += first is not None and first < k
            reciprocal += 1 / (first + 1) if first is not None else 0
        rows.append((chunking, retrieval, {k: hits[k] / len(questions) for k in KS}, reciprocal / len(questions)))

    ingest(base, base.chunking)
    lines = [
        f"# Retrieval comparison ({len(questions)} policy questions)", "",
        "| Chunking | Search | Right file at #1 | Right file in top 4 | MRR |", "|---|---|---|---|---|",
    ]
    for chunking, retrieval, hit, mrr in rows:
        lines.append(f"| {chunking} | {retrieval} | {hit[1] * 100:.0f}% | {hit[4] * 100:.0f}% | {mrr:.2f} |")
    report = "\n".join(lines) + "\n"
    (EVALS / "results").mkdir(exist_ok=True)
    (EVALS / "results" / "retrieval.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
