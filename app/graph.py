import logging
import time

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph

from .agents import action, checker, orders, policy, responder, router
from .llm import Blocked
from .rag.retriever import Retriever
from .state import ChatState

log = logging.getLogger("shopdesk.graph")

MAX_ANSWER_ATTEMPTS = 2
NO_EVIDENCE_INTENTS = ("chitchat", "out_of_scope")
BLOCKED = "I can't help with that request. I can answer questions about Pebble & Co. orders and policies."
FALLBACK = (
    "I couldn't confirm that answer against our policies and your account data, so I'd rather not guess. "
    "I haven't changed anything. If you like, I can open a support ticket so a person can follow up."
)


def _next_step(state):
    todo = state.get("todo") or []
    return todo[0] if todo else "responder"


def _after_responder(state):
    return "finish" if state["intent"] in NO_EVIDENCE_INTENTS else "checker"


def _make_after_checker(settings):
    def after_checker(state):
        if not settings.use_checker or state.get("verified"):
            return "finish"
        return "responder" if state["attempts"] < MAX_ANSWER_ATTEMPTS else "finish"

    return after_checker


def _last_step(update):
    trace = update.get("trace") or []
    return trace[-1] if trace else {}


def _detail(name, update):
    step = _last_step(update)
    if name == "router":
        return step.get("intent")
    if name == "orders":
        return step.get("rows") if not step.get("error") else None
    if name == "policy":
        return sorted({h.split("#")[0] for h in step.get("hits", [])})
    if name == "action":
        return step.get("status")
    if name == "checker":
        return step.get("verified")
    return None


def _timed(name, fn):
    def wrapper(state):
        emit = get_stream_writer() if state.get("stream") else None
        if emit:
            emit({"type": "step", "step": name, "state": "start", "retry": state.get("attempts", 0) > 0})
        started = time.perf_counter()
        update = fn(state)
        step = _last_step(update)
        if step:
            step["ms"] = round((time.perf_counter() - started) * 1000)
        log.info("%s done in %.0f ms", name, (time.perf_counter() - started) * 1000)
        if emit:
            emit({"type": "step", "step": name, "state": "done", "detail": _detail(name, update)})
        return update

    return wrapper


def _result(final):
    return {
        "answer": final.get("answer", ""),
        "intent": final.get("intent"),
        "sources": final.get("sources", []),
        "pending_action": final.get("pending_action"),
        "action_result": final.get("action_result"),
        "verified": final.get("verified"),
        "trace": final.get("trace", []),
    }


def _blocked_result():
    return {"answer": BLOCKED, "intent": "blocked", "sources": [], "pending_action": None,
            "action_result": None, "verified": None, "trace": [{"step": "blocked"}]}


class SupportDesk:
    def __init__(self, settings, retriever=None):
        self.settings = settings
        self.retriever = retriever or Retriever(settings)
        self.graph = self._build()

    def _build(self):
        s = self.settings
        g = StateGraph(ChatState)
        g.add_node("router", _timed("router", lambda st: router.run(st, s)))
        g.add_node("orders", _timed("orders", lambda st: orders.run(st, s)))
        g.add_node("policy", _timed("policy", lambda st: policy.run(st, s, self.retriever)))
        g.add_node("action", _timed("action", lambda st: action.run(st, s)))
        g.add_node("responder", _timed("responder", lambda st: responder.run(st, s)))
        g.add_node("checker", _timed("checker", lambda st: checker.run(st, s)))
        g.add_node("finish", self._finish)

        g.set_entry_point("router")
        routes = {"orders": "orders", "policy": "policy", "action": "action", "responder": "responder"}
        for node in ("router", "orders", "policy", "action"):
            g.add_conditional_edges(node, _next_step, routes)
        g.add_conditional_edges("responder", _after_responder, {"checker": "checker", "finish": "finish"})
        g.add_conditional_edges(
            "checker", _make_after_checker(s), {"responder": "responder", "finish": "finish"}
        )
        g.add_edge("finish", END)
        return g.compile()

    def _finish(self, state):
        if self.settings.use_checker and state.get("verified") is False:
            return {"answer": FALLBACK, "sources": []}
        return {}

    def _start_state(self, customer_id, message, history, stream=False):
        state = {"customer_id": customer_id, "question": message.strip(), "history": history or []}
        if stream:
            state["stream"] = True
        return state

    def ask(self, customer_id, message, history=None):
        try:
            final = self.graph.invoke(self._start_state(customer_id, message, history))
        except Blocked:
            return _blocked_result()
        return _result(final)

    def ask_stream(self, customer_id, message, history=None):
        """Yields progress events, answer pieces, and a final 'done' event."""
        final = None
        try:
            start = self._start_state(customer_id, message, history, stream=True)
            for mode, payload in self.graph.stream(start, stream_mode=["custom", "values"]):
                if mode == "custom":
                    yield payload
                else:
                    final = payload
        except Blocked:
            yield {"type": "done", **_blocked_result()}
            return
        yield {"type": "done", **_result(final or {})}
