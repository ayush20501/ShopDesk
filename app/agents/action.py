import re

from .. import actions
from ..llm import ask_json

PROMPT = """A customer of Pebble & Co. wants something done about an order. Pull out the details from their message.

Reply with JSON only:
{{"order_id": <number or null>,
  "items": [<product names they mention, empty list if they mean the whole order>],
  "reason": "defective" | "changed_mind" | "other",
  "subject": "<one short line describing the problem, for a support ticket>"}}

Use "defective" when the item is broken, damaged, faulty, torn, not working or arrived wrong. Use "changed_mind" for wrong size, no longer needed, dislike and similar. Otherwise "other"."""


def _order_id(details, text):
    value = details.get("order_id")
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        return int(value)
    found = re.search(r"\b(\d{4})\b", text)
    return int(found.group(1)) if found else None


def run(state, settings):
    text = state.get("standalone") or state["question"]
    details = ask_json(settings, PROMPT, f"Customer message: {text}")
    order_id = _order_id(details, text)
    intent = state["intent"]
    customer = state["customer_id"]

    if intent == "cancel_request":
        result = actions.prepare_cancel(settings, customer, order_id) if order_id else None
    elif intent == "refund_request":
        reason = "defective" if details.get("reason") == "defective" else "changed_mind"
        items = [i for i in details.get("items") or [] if isinstance(i, str)]
        result = actions.prepare_return(settings, customer, order_id, items, reason) if order_id else None
    else:
        result = actions.prepare_ticket(settings, customer, order_id, details.get("subject") or text)

    if result is None:
        result = {"status": "needs_info", "message": "Which order is this about? Please share the order number."}

    pending = result if result["status"] == "pending_approval" else None
    todo = [s for s in state.get("todo", []) if s != "action"]
    step = {"step": "action", "details": details, "status": result["status"], "action_id": result.get("action_id")}
    return {
        "todo": todo,
        "action_result": result,
        "pending_action": pending,
        "trace": state["trace"] + [step],
    }
