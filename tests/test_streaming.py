import pytest

from app.agents import action, checker, orders, responder, router
from app.graph import FALLBACK, SupportDesk
from tests.test_graph_flow import FakeRetriever, Script


@pytest.fixture
def stream_for(settings, monkeypatch):
    def make(script, pieces=("Your order ", "is **shipped**.")):
        monkeypatch.setattr(router, "ask_json", script.router)
        monkeypatch.setattr(orders, "ask_json", script.orders)
        monkeypatch.setattr(action, "ask_json", script.action)
        monkeypatch.setattr(checker, "ask_json", script.checker)

        def fake_stream(settings, system, user):
            script.calls["responder"] += 1
            yield from pieces

        monkeypatch.setattr(responder, "stream_text", fake_stream)
        return SupportDesk(settings, retriever=FakeRetriever())

    return make


def kinds(events):
    return [e["type"] for e in events]


def test_events_come_in_the_right_order(stream_for):
    events = list(stream_for(Script("order_question")).ask_stream(1, "where is my order"))
    assert kinds(events)[-1] == "done"
    first_token = kinds(events).index("token")
    steps_before = [e["step"] for e in events[:first_token] if e["type"] == "step" and e["state"] == "start"]
    assert steps_before == ["router", "orders", "responder"]
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Your order is **shipped**."


def test_step_details_are_friendly_values_not_raw_data(stream_for):
    events = list(stream_for(Script("order_question")).ask_stream(1, "where is my order"))
    done = {e["step"]: e["detail"] for e in events if e["type"] == "step" and e["state"] == "done"}
    assert done["router"] == "order_question"
    assert done["orders"] == 3
    assert done["checker"] is True


def test_final_event_carries_the_checked_answer_and_no_trace(stream_for):
    final = list(stream_for(Script("policy_question")).ask_stream(1, "q"))[-1]
    assert final["type"] == "done"
    assert final["verified"] is True
    assert final["sources"] == ["returns.md > Return windows"]


def test_a_rewrite_sends_a_restart_event(stream_for):
    events = list(stream_for(Script(verdicts=[False, True])).ask_stream(1, "q"))
    assert kinds(events).count("restart") == 1
    assert kinds(events).count("token") == 4
    assert kinds(events)[-1] == "done"


def test_fallback_replaces_the_streamed_text(stream_for):
    final = list(stream_for(Script(verdicts=[False])).ask_stream(1, "q"))[-1]
    assert final["answer"] == FALLBACK


def test_chitchat_streams_without_a_checker(stream_for):
    events = list(stream_for(Script("chitchat")).ask_stream(1, "hi"))
    steps = [e["step"] for e in events if e["type"] == "step" and e["state"] == "start"]
    assert "checker" not in steps
    assert "token" in kinds(events)


def test_blocked_prompt_ends_with_a_safe_done_event(stream_for, monkeypatch):
    from app.llm import Blocked

    def blocked(settings, system, user):
        raise Blocked("filtered")

    desk = stream_for(Script())
    monkeypatch.setattr(router, "ask_json", blocked)
    events = list(desk.ask_stream(1, "bad"))
    assert events[-1]["type"] == "done"
    assert events[-1]["intent"] == "blocked"
