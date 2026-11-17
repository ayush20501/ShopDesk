"""Builds data/shop.db with a small, fixed set of customers and orders.

The data is hand written on purpose so the test questions in evals/ have known answers.
Dates are relative to STORE_TODAY (2026-11-20 unless overridden).
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.schema import SCHEMA

CUSTOMERS = [
    (1, "Aarav Mehta", "aarav.mehta@example.com", "Mumbai", "gold", 2350),
    (2, "Diya Sharma", "diya.sharma@example.com", "Delhi", "silver", 740),
    (3, "Rohan Iyer", "rohan.iyer@example.com", "Bengaluru", "basic", 120),
    (4, "Sneha Kapoor", "sneha.kapoor@example.com", "Pune", "silver", 610),
    (5, "Vikram Singh", "vikram.singh@example.com", "Jaipur", "basic", 90),
    (6, "Meera Nair", "meera.nair@example.com", "Kochi", "basic", 310),
    (7, "Arjun Reddy", "arjun.reddy@example.com", "Hyderabad", "gold", 2100),
    (8, "Kavya Joshi", "kavya.joshi@example.com", "Ahmedabad", "basic", 45),
    (9, "Imran Khan", "imran.khan@example.com", "Lucknow", "basic", 0),
    (10, "Ananya Das", "ananya.das@example.com", "Kolkata", "silver", 530),
]

PRODUCTS = [
    (1, "Pebble Buds Pro", "electronics", 2499, 40, 1),
    (2, "Pebble Buds Lite", "electronics", 999, 120, 1),
    (3, "Nova Smartwatch S2", "electronics", 4999, 25, 0),
    (4, "Aero Bluetooth Speaker", "electronics", 1999, 60, 0),
    (5, "Volt Power Bank 20000mAh", "electronics", 1799, 80, 0),
    (6, "Spark USB-C Cable 2m", "accessories", 349, 300, 0),
    (7, "Breeze Table Fan", "appliances", 2799, 15, 0),
    (8, "Brew Mini Coffee Maker", "appliances", 3499, 0, 0),
    (9, "Glow Desk Lamp", "home", 1299, 70, 0),
    (10, "Cozy Throw Blanket", "home", 899, 90, 0),
    (11, "Nest Storage Box Set", "home", 1099, 45, 0),
    (12, "Zen Yoga Mat", "home", 749, 100, 0),
    (13, "Pebble Phone Case", "accessories", 399, 200, 0),
    (14, "ChargeX 65W Charger", "accessories", 1599, 55, 0),
    (15, "Orbit Wireless Mouse", "accessories", 899, 150, 0),
    (16, "Slate Laptop Stand", "accessories", 1499, 35, 0),
]

# id, customer, placed_on, status, payment, shipping, ship_fee, cod_fee, total, delivered_on, expected_on
ORDERS = [
    (1001, 1, "2026-11-02", "delivered", "UPI", "standard", 0, 0, 2898, "2026-11-06", None),
    (1002, 1, "2026-11-15", "shipped", "card", "express", 0, 0, 4999, None, "2026-11-21"),
    (1003, 1, "2026-11-19", "placed", "UPI", "standard", 0, 0, 2598, None, "2026-11-25"),
    (1004, 2, "2026-11-10", "delivered", "card", "standard", 0, 0, 2799, "2026-11-14", None),
    (1005, 2, "2026-10-05", "delivered", "COD", "standard", 0, 49, 2596, "2026-10-09", None),
    (1006, 3, "2026-11-12", "delivered", "UPI", "standard", 79, 0, 1078, "2026-11-16", None),
    (1007, 3, "2026-11-18", "shipped", "UPI", "standard", 0, 0, 1799, None, "2026-11-23"),
    (1008, 4, "2026-11-01", "delivered", "card", "standard", 0, 0, 2498, "2026-11-05", None),
    (1009, 4, "2026-11-17", "cancelled", "UPI", "standard", 0, 0, 3499, None, None),
    (1010, 5, "2026-10-20", "delivered", "netbanking", "standard", 0, 0, 1999, "2026-10-24", None),
    (1011, 6, "2026-11-14", "delivered", "UPI", "standard", 0, 0, 1848, "2026-11-18", None),
    (1012, 7, "2026-11-05", "delivered", "card", "standard", 0, 0, 6498, "2026-11-08", None),
    (1013, 7, "2026-11-19", "placed", "card", "express", 0, 0, 2499, None, "2026-11-21"),
    (1014, 8, "2026-11-08", "returned", "UPI", "standard", 0, 0, 2799, "2026-11-12", None),
    (1015, 8, "2026-11-16", "shipped", "COD", "standard", 0, 49, 2247, None, "2026-11-22"),
    (1016, 9, "2026-11-19", "placed", "UPI", "standard", 0, 0, 1799, None, "2026-11-25"),
    (1017, 10, "2026-10-28", "delivered", "card", "standard", 0, 0, 1648, "2026-11-02", None),
    (1018, 10, "2026-11-14", "delivered", "UPI", "standard", 0, 0, 2499, "2026-11-17", None),
]

# order, product, qty, unit price
ITEMS = [
    (1001, 1, 1, 2499), (1001, 13, 1, 399),
    (1002, 3, 1, 4999),
    (1003, 9, 2, 1299),
    (1004, 7, 1, 2799),
    (1005, 10, 2, 899), (1005, 12, 1, 749),
    (1006, 2, 1, 999),
    (1007, 5, 1, 1799),
    (1008, 14, 1, 1599), (1008, 15, 1, 899),
    (1009, 8, 1, 3499),
    (1010, 4, 1, 1999),
    (1011, 12, 1, 749), (1011, 11, 1, 1099),
    (1012, 3, 1, 4999), (1012, 16, 1, 1499),
    (1013, 1, 1, 2499),
    (1014, 7, 1, 2799),
    (1015, 10, 1, 899), (1015, 9, 1, 1299),
    (1016, 5, 1, 1799),
    (1017, 15, 1, 899), (1017, 12, 1, 749),
    (1018, 1, 1, 2499),
]

REFUNDS = [
    (1009, 3499, "UPI", "processed", "2026-11-17"),
    (1014, 2700, "UPI", "processing", "2026-11-18"),
]

TICKETS = [
    (5001, 5, 1010, "Speaker has a crackling sound", "open", "2026-11-18"),
    (5002, 1, 1001, "Left earbud volume is low", "closed", "2026-11-08"),
]


def build(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    with conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", CUSTOMERS)
        conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", PRODUCTS)
        conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)", ORDERS)
        conn.executemany("INSERT INTO order_items VALUES (?,?,?,?)", ITEMS)
        conn.executemany(
            "INSERT INTO refunds (order_id, amount, method, status, created_on) VALUES (?,?,?,?,?)", REFUNDS
        )
        conn.executemany(
            "INSERT INTO tickets (id, customer_id, order_id, subject, status, created_on) VALUES (?,?,?,?,?,?)",
            TICKETS,
        )
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("customers", "products", "orders", "order_items", "refunds", "tickets")}
    conn.close()
    return counts


if __name__ == "__main__":
    settings = load_settings()
    print("built", settings.db_path, build(settings.db_path))
