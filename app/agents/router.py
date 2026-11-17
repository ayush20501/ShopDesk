from ..llm import ask_json

INTENT_STEPS = {
    "policy_question": ["policy"],
    "order_question": ["orders"],
    "eligibility_question": ["orders", "policy"],
    "refund_request": ["orders", "policy", "action"],
    "cancel_request": ["orders", "policy", "action"],
    "ticket_request": ["orders", "action"],
    "chitchat": [],
    "out_of_scope": [],
}

PROMPT = """You route messages for the support chat of Pebble & Co., an online store that sells electronics, appliances and home items. Today's date is {today}.

Pick exactly one intent for the customer's latest message:
- policy_question: a general question about our rules (returns, refunds, shipping, warranty, payments, loyalty points, support hours) that is not about one of their own orders.
- order_question: asks about their own orders, deliveries, refunds, tickets, loyalty points or tier.
- eligibility_question: asks whether something is possible for one of their orders (can I return it, can I cancel it, why was I charged).
- refund_request: wants to return an item or get a refund.
- cancel_request: wants to cancel an order.
- ticket_request: wants to report a problem or open a ticket without asking for a refund.
- chitchat: greeting, thanks or goodbye.
- out_of_scope: anything unrelated to the store.

Rules for the tricky cases:
- eligibility_question is only for a question about a specific order or item the customer owns (an order number, or "my order"), such as "can I return the fan from order 1004?" or "why wasn't I charged for shipping on order 1002?". These only ask, nothing should be changed.
- refund_request and cancel_request are only for messages that clearly ask you to do it ("cancel my order 1003", "I want to return it", "please refund"). A question like "can I cancel order 1003?" is an eligibility_question, not a cancel_request.
- A general question that does not point at one of their orders ("can I return opened earphones?", "my money was deducted but the order was not placed, what now?") is a policy_question.

Also rewrite the latest message as a standalone question, using the chat history to fill in anything it refers to ("it", "that order", "and for a lamp?"). If it is already standalone, copy it.

Reply with JSON only: {{"intent": "<intent>", "standalone_question": "<text>"}}"""


def run(state, settings):
    history = state.get("history") or []
    lines = [f"{t['role']}: {t['content']}" for t in history[-6:]]
    user = "Chat history:\n" + ("\n".join(lines) or "(none)") + f"\n\nLatest message: {state['question']}"
    out = ask_json(settings, PROMPT.format(today=settings.store_today.isoformat()), user)

    intent = out.get("intent")
    if intent not in INTENT_STEPS:
        intent = "policy_question"
    standalone = (out.get("standalone_question") or state["question"]).strip()
    return {
        "intent": intent,
        "standalone": standalone,
        "todo": list(INTENT_STEPS[intent]),
        "evidence": [],
        "attempts": 0,
        "trace": [{"step": "router", "intent": intent, "standalone": standalone}],
    }
