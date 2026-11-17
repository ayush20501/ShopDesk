import sqlite3

import pytest

from app.db import SqlRejected, run_scoped_select


def ids(result):
    return sorted(r[0] for r in result["rows"])


def test_returns_only_own_orders(settings):
    out = run_scoped_select(settings, 1, "SELECT order_id FROM my_orders")
    assert ids(out) == [1001, 1002, 1003]


def test_other_customers_rows_are_invisible(settings):
    out = run_scoped_select(settings, 2, "SELECT order_id FROM my_orders WHERE order_id = 1001")
    assert out["rows"] == []


def test_items_view_joins_catalog(settings):
    out = run_scoped_select(settings, 4, "SELECT product FROM my_items WHERE order_id = 1008 ORDER BY product")
    assert [r[0] for r in out["rows"]] == ["ChargeX 65W Charger", "Orbit Wireless Mouse"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "SELECT * FROM customers",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM pending_actions",
        "SELECT * FROM tickets",
        "SELECT * FROM my_orders o JOIN orders x ON x.id = o.order_id",
        "SELECT load_extension('x')",
        "SELECT * FROM pragma_table_info('orders')",
    ],
)
def test_base_tables_are_blocked(settings, sql):
    with pytest.raises((SqlRejected, sqlite3.DatabaseError)):
        run_scoped_select(settings, 1, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE orders",
        "DELETE FROM my_orders",
        "UPDATE orders SET status = 'cancelled'",
        "INSERT INTO refunds (order_id, amount, method, status, created_on) VALUES (1, 1, 'x', 'x', 'x')",
        "ATTACH DATABASE 'x.db' AS x",
        "PRAGMA table_info(orders)",
        "SELECT 1; DROP TABLE orders",
        "",
        "   ;  ",
    ],
)
def test_anything_but_select_is_rejected(settings, sql):
    with pytest.raises(SqlRejected):
        run_scoped_select(settings, 1, sql)


def test_database_is_untouched_after_attacks(settings):
    for sql in ["DROP TABLE orders", "DELETE FROM my_orders"]:
        with pytest.raises(SqlRejected):
            run_scoped_select(settings, 1, sql)
    conn = sqlite3.connect(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 18


def test_row_cap_is_applied(settings):
    out = run_scoped_select(settings.with_(max_rows=2), 1, "SELECT * FROM catalog")
    assert len(out["rows"]) == 2
    assert out["truncated"] is True


def test_runaway_query_is_stopped(settings):
    slow = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 100000000) "
        "SELECT COUNT(*) FROM c"
    )
    with pytest.raises((SqlRejected, sqlite3.DatabaseError)):
        run_scoped_select(settings, 1, slow)
