import sqlite3

import pytest

from app.agents import action, checker, orders, responder, router
from app.graph import FALLBACK, SupportDesk
from app.rag.retriever import Hit


class FakeRetriever:
    def search(self, query, k=None):
        return [Hit("returns.md#0", "returns.md", "Return windows", "Electronics: 10 days", 1.0)]


class Script:
    """Stands in for the language model and records what it was asked."""

    def __init__(self, intent="policy_question", sql=None, verdicts=(True,), order_id=1003):
        self.intent = intent
        self.sql = list(sql or ["SELECT order_id, status FROM my_orders"])
        self.verdicts = list(verdicts)
        self.order_id = order_id
        self.calls = {"router": 0, "orders": 0, "action": 0, "responder": 0, "checker": 0}

    def router(self, settings, system, user):
        self.calls["router"] += 1
        return {"intent": self.intent, "standalone_question": "standalone"}

    def orders(self, settings, system, user):
        self.calls["orders"] += 1
        return {"sql": self.sql.pop(0) if len(self.sql) > 1 else self.sql[0]}

    def action(self, settings, system, user):
        self.calls["action"] += 1
        return {"order_id": self.order_id, "items": [], "reason": "changed_mind", "subject": "help"}

    def responder(self, settings, system, user):
        self.calls["responder"] += 1
        return f"answer {self.calls['responder']}"

    def checker(self, settings, system, user):
        self.calls["checker"] += 1
        ok = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
        return {"supported": ok, "problems": [] if ok else ["wrong number"]}


@pytest.fixture
def desk_for(settings, monkeypatch):
    def make(script):
        monkeypatch.setattr(router, "ask_json", script.router)
        monkeypatch.setattr(orders, "ask_json", script.orders)
        monkeypatch.setattr(action, "ask_json", script.action)
        monkeypatch.setattr(responder, "ask_text", script.responder)
        monkeypatch.setattr(checker, "ask_json", script.checker)
        return SupportDesk(settings, retriever=FakeRetriever())

    return make


def steps(out):
    return [t["step"] for t in out["trace"]]


def test_policy_question_skips_the_database(desk_for):
    script = Script("policy_question")
    out = desk_for(script).ask(1, "return window?")
    assert steps(out) == ["router", "policy", "responder", "checker"]
    assert out["verified"] is True
    assert out["sources"] == ["returns.md > Return windows"]
    assert script.calls["orders"] == 0


def test_order_question_skips_the_policy_search(desk_for):
    out = desk_for(Script("order_question")).ask(1, "where is my order")
    assert steps(out) == ["router", "orders", "responder", "checker"]


def test_cancel_runs_orders_policy_then_action(desk_for, settings):
    out = desk_for(Script("cancel_request")).ask(1, "cancel 1003")
    assert steps(out) == ["router", "orders", "policy", "action", "responder", "checker"]
    assert out["pending_action"]["kind"] == "cancel"
    conn = sqlite3.connect(settings.db_path)
    assert conn.execute("SELECT status FROM orders WHERE id=1003").fetchone()[0] == "placed"
    assert conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0] == 1


def test_chitchat_does_not_call_the_checker(desk_for):
    script = Script("chitchat")
    out = desk_for(script).ask(1, "hi")
    assert steps(out) == ["router", "responder"]
    assert script.calls["checker"] == 0
    assert out["verified"] is None


def test_unknown_intent_falls_back_to_policy(desk_for):
    out = desk_for(Script("something_else")).ask(1, "hmm")
    assert out["intent"] == "policy_question"


def test_checker_objection_triggers_one_rewrite(desk_for):
    script = Script(verdicts=[False, True])
    out = desk_for(script).ask(1, "q")
    assert script.calls["responder"] == 2
    assert out["answer"] == "answer 2"
    assert out["verified"] is True


def test_answer_that_never_passes_is_replaced_by_the_fallback(desk_for):
    script = Script(verdicts=[False])
    out = desk_for(script).ask(1, "q")
    assert script.calls["responder"] == 2
    assert out["answer"] == FALLBACK
    assert out["sources"] == []


def test_checker_can_be_switched_off(desk_for, settings):
    script = Script(verdicts=[False])
    desk = desk_for(script)
    desk.settings = settings.with_(use_checker=False)
    desk.graph = desk._build()
    out = desk.ask(1, "q")
    assert script.calls["checker"] == 0
    assert out["answer"] == "answer 1"


def test_bad_sql_is_retried_once_with_the_error(desk_for):
    script = Script("order_question", sql=["DROP TABLE orders", "SELECT order_id FROM my_orders"])
    out = desk_for(script).ask(1, "my orders")
    assert script.calls["orders"] == 2
    orders_step = next(t for t in out["trace"] if t["step"] == "orders")
    assert orders_step["error"] is None
    assert orders_step["rows"] == 3


def test_missing_order_number_asks_for_it(desk_for):
    script = Script("cancel_request", order_id=None)
    out = desk_for(script).ask(1, "cancel my order")
    assert out["action_result"]["status"] == "needs_info"
    assert out["pending_action"] is None


def test_content_filter_block_returns_a_safe_answer(desk_for, monkeypatch):
    from app.llm import Blocked

    def blocked(settings, system, user):
        raise Blocked("filtered")

    desk = desk_for(Script())
    monkeypatch.setattr(router, "ask_json", blocked)
    out = desk.ask(1, "something the filter dislikes")
    assert out["intent"] == "blocked"
    assert "can't help" in out["answer"]
    assert out["pending_action"] is None
