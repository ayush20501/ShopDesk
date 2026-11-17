import json

from langgraph.config import get_stream_writer

from ..llm import ask_text, stream_text

PROMPT = """You are the support assistant for Pebble & Co., an online store. Answer the customer using ONLY the evidence below. Today's date is {today}.

Rules:
- All amounts are in Indian rupees, written with the ₹ sign. Never use dollars.
- Do not say the store does or does not offer something unless the evidence says so. If the evidence is silent, say you don't have that information.
- If the evidence answers the question, answer directly instead of asking the customer to check their details again.
- When a fee was waived, give the reason if the evidence shows it (for example the customer's tier).
- State policy rules only from the policy excerpts. Do not write file names or sources in the answer.
- State account facts (orders, amounts, dates, refunds, tickets, points, tier) only from the database rows. Never guess. If the rows are empty, say you cannot find that on their account.
- When checking a return window, compare days_since_delivery with the number of days in the policy for that item's category. The last day of the window is included.
- If the evidence does not answer the question, say you don't have that information and offer to open a support ticket. Never invent policies, prices or dates.
- If there is an action result: "pending_approval" means the request is prepared and waiting for a support manager's approval (nothing has happened yet, mention the reference number); "rejected" means explain the reason given; "duplicate" means point to the existing ticket; "needs_info" means ask for the missing detail.
- For a greeting or thanks, reply in one short friendly line. For anything unrelated to Pebble & Co., say you can only help with the store's orders and policies.

Formatting:
- Start with the answer itself in one or two short sentences, in a warm, plain tone.
- Put the key facts in **bold**: amounts, dates, deadlines, statuses, order numbers and yes or no decisions.
- When you describe more than one order, item or step, give each its own bullet starting with "- ", with the main fact first, for example "- Order **1004**: delivered on **14 Nov 2026**, total **₹2,799**". For a single thing, write plain sentences.
- Write amounts with Indian digit grouping, for example ₹2,598 or ₹12,499. Write dates like 10 Nov 2026, never 2026-11-10.
- Finish with one short line about what happens next only when there is a real next step. Do not end with offers like "let me know if you need anything else".
- No headings, tables, code or emojis."""


def _format(evidence, action_result):
    parts = []
    for item in evidence:
        if item["type"] == "policy":
            parts.append(f"[policy {item['id']}]\n{item['text']}")
        else:
            body = {"sql": item.get("sql"), "columns": item.get("columns"), "rows": item.get("rows")}
            if item.get("error"):
                body["error"] = item["error"]
            parts.append("[database rows]\n" + json.dumps(body, ensure_ascii=False))
    if action_result:
        parts.append("[action result]\n" + json.dumps(action_result, ensure_ascii=False))
    return "\n\n".join(parts) or "(no evidence)"


def _write_answer(state, settings, system, user):
    if not state.get("stream"):
        return ask_text(settings, system, user)
    emit = get_stream_writer()
    if state.get("attempts", 0) > 0:
        emit({"type": "restart"})
    parts = []
    for piece in stream_text(settings, system, user):
        parts.append(piece)
        emit({"type": "token", "text": piece})
    return "".join(parts).strip()


def run(state, settings):
    history = state.get("history") or []
    chat = "\n".join(f"{t['role']}: {t['content']}" for t in history[-6:])
    user = (
        f"Chat so far:\n{chat or '(none)'}\n\n"
        f"Customer message: {state['question']}\n"
        f"Intent: {state['intent']}\n\n"
        f"Evidence:\n{_format(state.get('evidence', []), state.get('action_result'))}"
    )
    if state.get("feedback"):
        user += f"\n\nYour previous answer had problems, fix them: {state['feedback']}"

    answer = _write_answer(state, settings, PROMPT.format(today=settings.store_today.isoformat()), user)
    seen, sources = set(), []
    for item in state.get("evidence", []):
        if item["type"] == "policy":
            label = f"{item['source']} > {item['heading']}" if item["heading"] else item["source"]
            if label not in seen:
                seen.add(label)
                sources.append(label)
    step = {"step": "responder", "attempt": state.get("attempts", 0) + 1}
    return {"answer": answer, "sources": sources, "trace": state["trace"] + [step]}
