import re

ALIASES = {
    "@no": [
        "cannot", "can't", "can not", "not eligible", "not be returned", "not returnable", "unfortunately",
        "no longer", "isn't", "is not", "not possible", "not allowed", "has passed", "have passed",
        "has ended", "have ended", "expired", "unable", "not covered", "not within", "past the", "no,",
        "doesn't", "does not", "don't", "do not",
    ],
    "@yes": [
        "yes", "can still return", "is eligible", "are eligible", "you can return", "can be returned", "still within",
        "still eligible", "within the return window", "you're within", "you are within",
        "within the 15", "within the 30", "within the 10",
    ],
    "@idk": [
        "don't have", "do not have", "no information", "not sure", "can't find", "cannot find",
        "couldn't find", "not covered", "unable", "isn't", "not available", "don't see", "no details",
        "not able", "support ticket", "not something",
    ],
}


def norm(text):
    text = (text or "").lower()
    text = text.replace("–", "-").replace("—", "-").replace("₹", " ").replace("’", "'")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"(\d+)-(day|month|year)s?\b", r"\1 \2s", text)
    return re.sub(r"\s+", " ", text)


def _options(group):
    out = []
    for item in group:
        out += ALIASES.get(item, [item])
    return [norm(o) for o in out]


def check_answer(item, answer):
    failures = []
    text = norm(answer)
    for group in item["must"]:
        if not any(opt in text for opt in _options(group)):
            failures.append(f"missing one of {group}")
    for bad in item["must_not"]:
        if norm(bad) in text:
            failures.append(f"should not contain '{bad}'")
    return failures


def check_intent(item, intent):
    if item["intent"] and item["intent"] != intent:
        return [f"routed to {intent}, expected {item['intent']}"]
    return []


def check_action(item, pending):
    want = item.get("action")
    if not want:
        return [f"unexpected {pending['kind']} action prepared"] if pending else []
    if not pending:
        return [f"expected a {want['kind']} action on order {want['order_id']}, none prepared"]
    failures = []
    if pending.get("kind") != want["kind"]:
        failures.append(f"action kind {pending.get('kind')}, expected {want['kind']}")
    if pending.get("order_id") != want["order_id"]:
        failures.append(f"action order {pending.get('order_id')}, expected {want['order_id']}")
    if "amount" in want and pending.get("amount") != want["amount"]:
        failures.append(f"refund amount {pending.get('amount')}, expected {want['amount']}")
    return failures


def retrieved_sources(trace):
    for step in trace:
        if step.get("step") == "policy":
            return [h.split("#")[0] for h in step["hits"]]
    return None


def check_retrieval(item, trace):
    wanted = item.get("source")
    if not wanted:
        return []
    got = retrieved_sources(trace)
    if got is None or not set(wanted) & set(got):
        return [f"retrieval missed {wanted}, got {sorted(set(got or []))}"]
    return []
