import sqlite3
import time
from contextlib import contextmanager

SCOPED_VIEWS = {
    "me": "SELECT id, name, city, tier, points FROM customers WHERE id = {cid}",
    "my_orders": (
        "SELECT id AS order_id, placed_on, status, payment_method, shipping_method, shipping_fee, "
        "cod_fee, total, delivered_on, expected_on FROM orders WHERE customer_id = {cid}"
    ),
    "my_items": (
        "SELECT oi.order_id, p.name AS product, p.category, oi.qty, oi.unit_price "
        "FROM order_items oi JOIN products p ON p.id = oi.product_id "
        "JOIN orders o ON o.id = oi.order_id WHERE o.customer_id = {cid}"
    ),
    "my_refunds": (
        "SELECT r.id AS refund_id, r.order_id, r.amount, r.method, r.status, r.created_on "
        "FROM refunds r JOIN orders o ON o.id = r.order_id WHERE o.customer_id = {cid}"
    ),
    "my_tickets": (
        "SELECT id AS ticket_id, order_id, subject, status, created_on "
        "FROM tickets WHERE customer_id = {cid}"
    ),
    "catalog": "SELECT name AS product, category, price, stock FROM products",
}

SAFE_FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "round", "abs", "coalesce", "ifnull", "nullif",
    "lower", "upper", "length", "substr", "trim", "replace", "date", "julianday", "strftime",
    "cast", "like", "typeof", "group_concat", "iif",
}

QUERY_TIME_LIMIT = 2.0


class SqlRejected(Exception):
    pass


@contextmanager
def writable(settings):
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _authorizer(allowed):
    def check(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            if source is not None:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_OK if arg1 in allowed else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            return sqlite3.SQLITE_OK if (arg2 or "").lower() in SAFE_FUNCTIONS else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY

    return check


def _clean(sql):
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise SqlRejected("empty query")
    if ";" in sql:
        raise SqlRejected("only one statement is allowed")
    if sql.split(None, 1)[0].lower() not in ("select", "with"):
        raise SqlRejected("only SELECT queries are allowed")
    return sql


def run_scoped_select(settings, customer_id, sql):
    """Run a model-written query against views that only contain this customer's rows."""
    cid = int(customer_id)
    sql = _clean(sql)
    uri = settings.db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        for name, body in SCOPED_VIEWS.items():
            conn.execute(f"CREATE TEMP VIEW {name} AS {body.format(cid=cid)}")
        conn.set_authorizer(_authorizer(set(SCOPED_VIEWS)))
        deadline = time.monotonic() + QUERY_TIME_LIMIT
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        try:
            cur = conn.execute(sql)
            columns = [c[0] for c in cur.description or []]
            rows = cur.fetchmany(settings.max_rows + 1)
        except sqlite3.DatabaseError as e:
            if "not authorized" in str(e) or "interrupted" in str(e):
                raise SqlRejected(str(e))
            raise
        truncated = len(rows) > settings.max_rows
        return {"columns": columns, "rows": [list(r) for r in rows[: settings.max_rows]], "truncated": truncated}
    finally:
        conn.close()
