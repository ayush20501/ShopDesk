from evals import scoring


def item(**kw):
    base = {"must": [], "must_not": [], "intent": None, "action": None, "source": None}
    base.update(kw)
    return base


def test_numbers_with_commas_and_rupee_signs_match():
    assert scoring.check_answer(item(must=[["2898"]]), "You paid ₹2,898 in total.") == []


def test_dash_variants_match():
    assert scoring.check_answer(item(must=[["5-7"]]), "It takes 5–7 business days") == []


def test_missing_group_is_reported():
    assert scoring.check_answer(item(must=[["10 days"]]), "About two weeks")


def test_negative_alias():
    assert scoring.check_answer(item(must=[["@no"]]), "Unfortunately that window has ended") == []
    assert scoring.check_answer(item(must=[["@no"]]), "Yes, go ahead") != []


def test_yes_alias_is_not_fooled_by_can_not():
    assert scoring.check_answer(item(must=[["@yes"]]), "You can't return it") != []
    assert scoring.check_answer(item(must=[["@yes"]]), "Yes, you can return it") == []


def test_forbidden_text():
    assert scoring.check_answer(item(must_not=["Aarav"]), "This belongs to aarav") != []


def test_action_expectations():
    want = {"kind": "refund", "order_id": 1004, "amount": 2700}
    assert scoring.check_action(item(action=want), {"kind": "refund", "order_id": 1004, "amount": 2700}) == []
    assert scoring.check_action(item(action=want), {"kind": "refund", "order_id": 1004, "amount": 2799}) != []
    assert scoring.check_action(item(action=want), None) != []
    assert scoring.check_action(item(), {"kind": "cancel", "order_id": 1}) != []
    assert scoring.check_action(item(), None) == []


def test_retrieval_check_reads_the_policy_step():
    trace = [{"step": "policy", "hits": ["returns.md#2", "refunds.md#0"]}]
    assert scoring.check_retrieval(item(source=["returns.md"]), trace) == []
    assert scoring.check_retrieval(item(source=["shipping.md"]), trace) != []
    assert scoring.check_retrieval(item(), trace) == []


def test_hyphenated_durations_match_plain_ones():
    assert scoring.check_answer(item(must=[["24 months"]]), "It has a 24-month warranty") == []
    assert scoring.check_answer(item(must=[["10 days"]]), "within the 10-day window") == []
    assert scoring.check_answer(item(must=[["5-7"]]), "5-7 business days") == []


def test_still_return_counts_as_yes():
    assert scoring.check_answer(item(must=[["@yes"]]), "So, you can still return it today.") == []
