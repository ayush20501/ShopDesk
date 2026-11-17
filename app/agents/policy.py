def run(state, settings, retriever):
    query = state.get("standalone") or state["question"]
    hits = retriever.search(query)
    evidence = [
        {"type": "policy", "id": h.id, "source": h.source, "heading": h.heading, "text": h.text}
        for h in hits
    ]
    todo = [s for s in state.get("todo", []) if s != "policy"]
    step = {"step": "policy", "query": query, "hits": [h.id for h in hits]}
    return {"todo": todo, "evidence": state.get("evidence", []) + evidence, "trace": state["trace"] + [step]}
