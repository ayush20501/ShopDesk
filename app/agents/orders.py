import sqlite3

from ..db import SqlRejected, run_scoped_select
from ..llm import ask_json

PROMPT = """You write one read-only SQLite query to fetch the account data needed to answer a customer's question.

You may only use these views. Each already contains just this customer's rows:
  me(id, name, city, tier, points)
  my_orders(order_id, placed_on, status, payment_method, shipping_method, shipping_fee, cod_fee, total, delivered_on, expected_on)
  my_items(order_id, product, category, qty, unit_price)
  my_refunds(refund_id, order_id, amount, method, status, created_on)
  my_tickets(ticket_id, order_id, subject, status, created_on)
  catalog(product, category, price, stock)

Facts:
- Dates are ISO text (YYYY-MM-DD). Today is {today}.
- Order status is one of: placed, shipped, delivered, cancelled, return_requested, returned. Ticket status is open or closed.
- To count days since delivery use CAST(julianday('{today}') - julianday(delivered_on) AS INTEGER).
- When the question is about returning or cancelling something in an order, return the order row together with its items (product, category, qty, unit_price), delivered_on and days_since_delivery, so the return window can be checked.
- When an order number is given, return every item of that order and do not filter on the product name. If you must match a product name, use LIKE with the main word, for example product LIKE '%fan%' (matching is case-insensitive).
- When the customer does not say which order they mean, return all of their orders, newest first. Do not filter on status unless they ask about a status.
- For questions about shipping charges or fees, include shipping_method, shipping_fee and cod_fee from my_orders and the tier from me.
- Use a single SELECT, no semicolons, and keep it short. Never use any other table.

Reply with JSON only: {{"sql": "<query>"}}. If no account data is needed, reply {{"sql": null}}."""


def run(state, settings):
    system = PROMPT.format(today=settings.store_today.isoformat())
    question = state.get("standalone") or state["question"]
    customer_id = state["customer_id"]
    user = f"Customer question: {question}"
    sql, result, error = None, None, None

    for _ in range(2):
        sql = ask_json(settings, system, user).get("sql")
        if not sql:
            break
        try:
            result = run_scoped_select(settings, customer_id, sql)
            error = None
            break
        except (SqlRejected, sqlite3.Error) as e:
            error = str(e)
            user = f"Customer question: {question}\n\nYour previous query failed.\nQuery: {sql}\nError: {error}\nWrite a corrected query."

    todo = [s for s in state.get("todo", []) if s != "orders"]
    step = {"step": "orders", "sql": sql, "error": error}
    if result is None:
        evidence = [{"type": "db", "sql": sql, "error": error or "no account data requested", "rows": []}]
    else:
        step["rows"] = len(result["rows"])
        evidence = [{"type": "db", "sql": sql, **result}]
    return {"todo": todo, "evidence": state.get("evidence", []) + evidence, "trace": state["trace"] + [step]}
