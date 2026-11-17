from ..llm import ask_json
from .responder import _format

PROMPT = """You check a support answer against the evidence it was written from. Today's date is {today}.

Find every concrete claim in the answer (numbers, days, fees, dates, statuses, eligibility decisions, promises) and check it against the evidence. A claim is supported if the evidence states it or if it follows directly from comparing numbers or dates in the evidence. A claim that the store does or does not offer something is a claim too: if the evidence is silent about it, mark it unsupported. Ignore greetings and offers to help.

Reply with JSON only: {{"supported": true or false, "problems": ["<each unsupported or wrong claim, briefly>"]}}"""


def run(state, settings):
    attempts = state.get("attempts", 0) + 1
    if not settings.use_checker:
        return {"verified": None, "attempts": attempts, "feedback": ""}

    user = (
        f"Customer message: {state['question']}\n\n"
        f"Answer to check:\n{state['answer']}\n\n"
        f"Evidence:\n{_format(state.get('evidence', []), state.get('action_result'))}"
    )
    out = ask_json(settings, PROMPT.format(today=settings.store_today.isoformat()), user)
    verified = bool(out.get("supported"))
    problems = [p for p in out.get("problems") or [] if isinstance(p, str)]
    step = {"step": "checker", "verified": verified, "problems": problems}
    return {
        "verified": verified,
        "attempts": attempts,
        "feedback": "; ".join(problems),
        "trace": state["trace"] + [step],
    }
