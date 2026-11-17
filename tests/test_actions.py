import sqlite3

from app import actions


def row(settings, sql, *args):
    conn = sqlite3.connect(settings.db_path)
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def test_cancel_a_placed_order(settings):
    res = actions.prepare_cancel(settings, 1, 1003)
    assert res["status"] == "pending_approval"
    assert res["amount"] == 2598


def test_cannot_cancel_a_shipped_order(settings):
    res = actions.prepare_cancel(settings, 1, 1002)
    assert res["status"] == "rejected"
    assert "shipped" in res["message"]


def test_cannot_touch_someone_elses_order(settings):
    assert actions.prepare_cancel(settings, 2, 1003)["status"] == "rejected"
    assert actions.prepare_return(settings, 2, 1001)["status"] == "rejected"


def test_cod_cancellation_has_nothing_to_refund(settings):
    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE orders SET status='placed', payment_method='COD' WHERE id=1005")
    conn.commit()
    conn.close()
    assert actions.prepare_cancel(settings, 2, 1005)["amount"] == 0


def test_same_cancel_twice_reuses_the_pending_one(settings):
    first = actions.prepare_cancel(settings, 1, 1003)
    second = actions.prepare_cancel(settings, 1, 1003)
    assert first["action_id"] == second["action_id"]
    assert row(settings, "SELECT COUNT(*) FROM pending_actions")[0] == 1


def test_return_inside_window_deducts_pickup_fee(settings):
    res = actions.prepare_return(settings, 2, 1004, ["table fan"], "changed_mind")
    assert res["status"] == "pending_approval"
    assert res["amount"] == 2799 - 99


def test_last_day_of_the_window_still_counts(settings):
    res = actions.prepare_return(settings, 4, 1008)
    assert res["days_since_delivery"] == 15
    assert res["status"] == "pending_approval"
    assert res["amount"] == 1599 + 899 - 99


def test_return_after_window_is_rejected(settings):
    res = actions.prepare_return(settings, 2, 1005, ["blanket"])
    assert res["status"] == "rejected"
    assert "30 day" in res["message"]


def test_each_item_uses_its_own_window(settings):
    res = actions.prepare_return(settings, 1, 1001)
    assert res["status"] == "pending_approval"
    assert res["items"] == ["Pebble Phone Case"]
    assert res["amount"] == 399 - 99
    assert any("Pebble Buds Pro" in b for b in res["not_eligible"])


def test_earphones_blocked_for_change_of_mind_even_inside_window(settings):
    res = actions.prepare_return(settings, 10, 1018, ["Pebble Buds Pro"], "changed_mind")
    assert res["status"] == "rejected"
    assert "earphones" in res["message"]


def test_defective_earphones_inside_window_are_fine(settings):
    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE orders SET delivered_on='2026-11-19' WHERE id=1018")
    conn.commit()
    conn.close()
    res = actions.prepare_return(settings, 10, 1018, ["Pebble Buds Pro"], "defective")
    assert res["status"] == "pending_approval"
    assert res["amount"] == 2499


def test_defect_reported_too_late_points_to_warranty(settings):
    res = actions.prepare_return(settings, 1, 1001, ["Pebble Buds Pro"], "defective")
    assert res["status"] == "rejected"
    assert "warranty" in res["message"]


def test_unknown_item_name(settings):
    res = actions.prepare_return(settings, 2, 1004, ["toaster"])
    assert res["status"] == "rejected"


def test_cannot_return_something_not_delivered(settings):
    assert actions.prepare_return(settings, 3, 1007)["status"] == "rejected"
    assert actions.prepare_return(settings, 8, 1014)["status"] == "rejected"


def test_open_ticket_blocks_a_duplicate(settings):
    res = actions.prepare_ticket(settings, 5, 1010, "crackling")
    assert res["status"] == "duplicate"
    assert res["ticket_id"] == 5001


def test_new_ticket_is_prepared(settings):
    res = actions.prepare_ticket(settings, 3, 1006, "earbuds disconnect")
    assert res["status"] == "pending_approval"


def test_approving_a_cancel_changes_the_database(settings):
    pending = actions.prepare_cancel(settings, 1, 1003)
    assert row(settings, "SELECT status FROM orders WHERE id=1003")[0] == "placed"
    done = actions.resolve(settings, pending["action_id"], approve=True)
    assert done["status"] == "approved"
    assert row(settings, "SELECT status FROM orders WHERE id=1003")[0] == "cancelled"
    assert row(settings, "SELECT amount, status FROM refunds WHERE order_id=1003") == (2598, "processing")


def test_approving_twice_does_nothing_the_second_time(settings):
    pending = actions.prepare_cancel(settings, 1, 1003)
    actions.resolve(settings, pending["action_id"], approve=True)
    again = actions.resolve(settings, pending["action_id"], approve=True)
    assert again["status"] == "rejected"
    assert row(settings, "SELECT COUNT(*) FROM refunds WHERE order_id=1003")[0] == 1


def test_rejecting_changes_nothing(settings):
    pending = actions.prepare_cancel(settings, 1, 1003)
    actions.resolve(settings, pending["action_id"], approve=False)
    assert row(settings, "SELECT status FROM orders WHERE id=1003")[0] == "placed"
    assert row(settings, "SELECT status FROM pending_actions WHERE id=?", pending["action_id"])[0] == "rejected"


def test_cancel_is_refused_at_approval_time_if_the_order_shipped_meanwhile(settings):
    pending = actions.prepare_cancel(settings, 1, 1003)
    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE orders SET status='shipped' WHERE id=1003")
    conn.commit()
    conn.close()
    res = actions.resolve(settings, pending["action_id"], approve=True)
    assert res["status"] == "rejected"
    assert row(settings, "SELECT COUNT(*) FROM refunds WHERE order_id=1003")[0] == 0


def test_approved_return_creates_a_refund(settings):
    pending = actions.prepare_return(settings, 2, 1004, ["table fan"])
    actions.resolve(settings, pending["action_id"], approve=True)
    assert row(settings, "SELECT status FROM orders WHERE id=1004")[0] == "return_requested"
    assert row(settings, "SELECT amount FROM refunds WHERE order_id=1004")[0] == 2700
