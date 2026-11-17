"""Business rules for the things the assistant is allowed to prepare.

Nothing here is decided by the language model. The model only works out what the
customer is asking for; these functions decide whether it is allowed, and every
action waits for a human to approve it before the database changes.
"""
import json
from datetime import date, datetime

from .db import writable

RETURN_WINDOWS = {"electronics": 10, "appliances": 10, "accessories": 15, "home": 30}
DEFECT_REPORT_DAYS = 2
PICKUP_FEE = 99


def _result(status, message, **details):
    return {"status": status, "message": message, **details}


def _find_order(conn, customer_id, order_id):
    row = conn.execute(
        "SELECT * FROM orders WHERE id = ? AND customer_id = ?", (order_id, customer_id)
    ).fetchone()
    return dict(row) if row else None


def _order_items(conn, order_id):
    rows = conn.execute(
        "SELECT p.name, p.category, p.hygiene_sensitive, oi.qty, oi.unit_price "
        "FROM order_items oi JOIN products p ON p.id = oi.product_id WHERE oi.order_id = ?",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _existing_pending(conn, kind, order_id):
    row = conn.execute(
        "SELECT id FROM pending_actions WHERE kind = ? AND order_id = ? AND status = 'pending'",
        (kind, order_id),
    ).fetchone()
    return row["id"] if row else None


def _save_pending(conn, customer_id, kind, order_id, payload, today):
    cur = conn.execute(
        "INSERT INTO pending_actions (customer_id, kind, order_id, payload, created_on) VALUES (?,?,?,?,?)",
        (customer_id, kind, order_id, json.dumps(payload), today.isoformat()),
    )
    return cur.lastrowid


def _pending_result(action_id, kind, order_id, message, **details):
    return _result("pending_approval", message, action_id=action_id, kind=kind, order_id=order_id, **details)


def prepare_cancel(settings, customer_id, order_id):
    today = settings.store_today
    with writable(settings) as conn:
        order = _find_order(conn, customer_id, order_id)
        if not order:
            return _result("rejected", f"Order {order_id} was not found on this account.")
        if order["status"] != "placed":
            return _result("rejected", f"Order {order_id} is already {order['status']}, so it cannot be cancelled.")
        dup = _existing_pending(conn, "cancel", order_id)
        if dup:
            return _pending_result(dup, "cancel", order_id, f"A cancellation for order {order_id} is already waiting for approval.")
        refund = 0 if order["payment_method"] == "COD" else order["total"]
        payload = {"refund_amount": refund, "payment_method": order["payment_method"]}
        action_id = _save_pending(conn, customer_id, "cancel", order_id, payload, today)
    return _pending_result(action_id, "cancel", order_id, f"Cancellation of order {order_id} is ready for approval.", amount=refund)


def _match_items(items, wanted):
    if not wanted:
        return items, []
    chosen, unmatched = [], []
    for name in wanted:
        needle = name.lower().strip()
        hit = [i for i in items if needle in i["name"].lower() or i["name"].lower() in needle]
        if hit:
            chosen += [i for i in hit if i not in chosen]
        else:
            unmatched.append(name)
    return chosen, unmatched


def prepare_return(settings, customer_id, order_id, item_names=None, reason="changed_mind"):
    today = settings.store_today
    defective = reason == "defective"
    with writable(settings) as conn:
        order = _find_order(conn, customer_id, order_id)
        if not order:
            return _result("rejected", f"Order {order_id} was not found on this account.")
        if order["status"] != "delivered":
            return _result("rejected", f"Order {order_id} is {order['status']}, so it cannot be returned right now.")
        already = conn.execute("SELECT id FROM refunds WHERE order_id = ?", (order_id,)).fetchone()
        if already:
            return _result("rejected", f"A refund already exists for order {order_id}.")
        dup = _existing_pending(conn, "refund", order_id)
        if dup:
            return _pending_result(dup, "refund", order_id, f"A return for order {order_id} is already waiting for approval.")

        items, unmatched = _match_items(_order_items(conn, order_id), item_names)
        if not items:
            return _result("rejected", f"None of the requested items were found in order {order_id}.")

        days = (today - date.fromisoformat(order["delivered_on"])).days
        if defective and days > DEFECT_REPORT_DAYS:
            return _result(
                "rejected",
                f"Order {order_id} was delivered {days} days ago. Defects must be reported within 48 hours, "
                "so this needs a warranty claim instead of a return.",
                days_since_delivery=days,
            )

        eligible, blocked = [], []
        for item in items:
            window = RETURN_WINDOWS[item["category"]]
            if defective:
                eligible.append(item)
            elif item["hygiene_sensitive"]:
                blocked.append(f"{item['name']}: in-ear earphones cannot be returned for change of mind")
            elif days > window:
                blocked.append(f"{item['name']}: the {window} day return window ended ({days} days since delivery)")
            else:
                eligible.append(item)

        if not eligible:
            return _result("rejected", "Nothing in this request can be returned. " + "; ".join(blocked), days_since_delivery=days)

        amount = sum(i["unit_price"] * i["qty"] for i in eligible)
        fee = 0 if defective else PICKUP_FEE
        amount = max(amount - fee, 0)
        payload = {
            "items": [i["name"] for i in eligible],
            "reason": reason,
            "pickup_fee": fee,
            "refund_amount": amount,
            "payment_method": order["payment_method"],
        }
        action_id = _save_pending(conn, customer_id, "refund", order_id, payload, today)

    note = f" Not eligible: {'; '.join(blocked)}." if blocked else ""
    return _pending_result(
        action_id, "refund", order_id,
        f"Return for {', '.join(payload['items'])} from order {order_id} is ready for approval. "
        f"Refund would be ₹{amount}" + (f" after the ₹{fee} pickup fee." if fee else ".") + note,
        amount=amount, items=payload["items"], days_since_delivery=days, not_eligible=blocked, unmatched=unmatched,
    )


def prepare_ticket(settings, customer_id, order_id, subject):
    today = settings.store_today
    subject = (subject or "Customer needs help").strip()[:200]
    with writable(settings) as conn:
        if order_id is not None and not _find_order(conn, customer_id, order_id):
            return _result("rejected", f"Order {order_id} was not found on this account.")
        if order_id is not None:
            open_ticket = conn.execute(
                "SELECT id, subject FROM tickets WHERE customer_id = ? AND order_id = ? AND status = 'open'",
                (customer_id, order_id),
            ).fetchone()
            if open_ticket:
                return _result(
                    "duplicate",
                    f"There is already an open ticket for order {order_id}: #{open_ticket['id']} ({open_ticket['subject']}).",
                    ticket_id=open_ticket["id"],
                )
        dup = _existing_pending(conn, "ticket", order_id)
        if dup:
            return _pending_result(dup, "ticket", order_id, "A ticket for this order is already waiting for approval.")
        action_id = _save_pending(conn, customer_id, "ticket", order_id, {"subject": subject}, today)
    return _pending_result(action_id, "ticket", order_id, "A support ticket is ready to be opened.", subject=subject)


def list_pending(settings, status="pending"):
    with writable(settings) as conn:
        rows = conn.execute(
            "SELECT * FROM pending_actions WHERE status = ? ORDER BY id DESC", (status,)
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item["payload"])
        out.append(item)
    return out


def resolve(settings, action_id, approve):
    now = datetime.now().isoformat(timespec="seconds")
    with writable(settings) as conn:
        row = conn.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()
        if not row:
            return _result("missing", f"Action {action_id} does not exist.")
        if row["status"] != "pending":
            return _result("rejected", f"Action {action_id} was already {row['status']}.")
        if not approve:
            conn.execute("UPDATE pending_actions SET status='rejected', resolved_on=? WHERE id=?", (now, action_id))
            return _result("rejected", f"Action {action_id} was rejected. Nothing changed.")

        payload = json.loads(row["payload"])
        today = settings.store_today.isoformat()
        kind, order_id = row["kind"], row["order_id"]
        if kind == "cancel":
            moved = conn.execute(
                "UPDATE orders SET status='cancelled' WHERE id=? AND status='placed'", (order_id,)
            ).rowcount
            if not moved:
                conn.execute("UPDATE pending_actions SET status='rejected', resolved_on=? WHERE id=?", (now, action_id))
                return _result("rejected", f"Order {order_id} has moved on since the request, so it was not cancelled.")
            if payload["refund_amount"] > 0:
                conn.execute(
                    "INSERT INTO refunds (order_id, amount, method, status, created_on) VALUES (?,?,?,?,?)",
                    (order_id, payload["refund_amount"], payload["payment_method"], "processing", today),
                )
        elif kind == "refund":
            conn.execute("UPDATE orders SET status='return_requested' WHERE id=?", (order_id,))
            conn.execute(
                "INSERT INTO refunds (order_id, amount, method, status, created_on) VALUES (?,?,?,?,?)",
                (order_id, payload["refund_amount"], payload["payment_method"], "processing", today),
            )
        elif kind == "ticket":
            conn.execute(
                "INSERT INTO tickets (customer_id, order_id, subject, status, created_on) VALUES (?,?,?,?,?)",
                (row["customer_id"], order_id, payload["subject"], "open", today),
            )
        conn.execute("UPDATE pending_actions SET status='approved', resolved_on=? WHERE id=?", (now, action_id))
    return _result("approved", f"Action {action_id} ({kind}) was approved and applied.")
