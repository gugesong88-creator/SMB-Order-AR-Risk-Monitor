"""Generate realistic simulated order, AR, and service-station mapping data."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import random

import numpy as np
import pandas as pd

try:
    from src.utils import DATA_DIR
except ModuleNotFoundError:
    DATA_DIR = Path(__file__).resolve().parents[1] / "data"


RANDOM_SEED = 20260603


def build_mapping(n_stations: int = 30) -> pd.DataFrame:
    """Create service station mapping data with fictional names and emails."""
    regions = ["East", "North", "South", "West", "Central", "Northeast"]
    rows = []
    for idx in range(1, n_stations + 1):
        code = f"SS{idx:03d}"
        station_name = f"Demo Service Station {idx:03d}"
        supervisor_id = ((idx - 1) % 12) + 1
        rows.append(
            {
                "service_station_code": code,
                "service_station_name": station_name,
                "supervisor_name": f"Supervisor {supervisor_id:02d}",
                "supervisor_email": f"supervisor{supervisor_id:02d}@example.test",
                "station_email": f"station{idx:03d}@example.test",
                "region": regions[(idx - 1) % len(regions)],
            }
        )
    return pd.DataFrame(rows)


def build_orders(mapping: pd.DataFrame, n_orders: int = 360, today: date | None = None) -> pd.DataFrame:
    """Create simulated service order data with overdue, due-soon, and normal cases."""
    today = today or date.today()
    rng = np.random.default_rng(RANDOM_SEED)
    random.seed(RANDOM_SEED)

    rows = []
    stations = mapping.to_dict("records")
    risk_buckets = ["overdue", "due_soon", "normal_recent", "normal_old", "cancelled"]
    bucket_probs = [0.26, 0.22, 0.28, 0.14, 0.10]

    for idx in range(1, n_orders + 1):
        station = random.choice(stations)
        order_type = rng.choice(["F", "M"], p=[0.58, 0.42])
        deadline_days = 7 if order_type == "F" else 30
        bucket = rng.choice(risk_buckets, p=bucket_probs)

        if bucket == "overdue":
            age_days = int(deadline_days + rng.integers(1, 45))
            order_status = rng.choice(["pending", "completed"], p=[0.68, 0.32])
            settlement_status = rng.choice(["not_applied", "applied"], p=[0.58, 0.42])
        elif bucket == "due_soon":
            age_days = int(max(0, deadline_days - rng.integers(0, 8)))
            order_status = rng.choice(["pending", "completed"], p=[0.62, 0.38])
            settlement_status = rng.choice(["not_applied", "applied"], p=[0.50, 0.50])
        elif bucket == "normal_old":
            age_days = int(deadline_days + rng.integers(3, 60))
            order_status = "completed"
            settlement_status = "settled"
        elif bucket == "cancelled":
            age_days = int(rng.integers(0, 75))
            order_status = "cancelled"
            settlement_status = rng.choice(["not_applied", "applied", "settled"], p=[0.45, 0.25, 0.30])
        else:
            age_days = int(max(0, deadline_days - rng.integers(8, deadline_days + 18)))
            order_status = rng.choice(["pending", "completed"], p=[0.45, 0.55])
            settlement_status = rng.choice(["not_applied", "applied", "settled"], p=[0.26, 0.24, 0.50])

        rows.append(
            {
                "order_id": f"ORD{idx:05d}",
                "order_date": today - timedelta(days=age_days),
                "order_type": order_type,
                "business_line": rng.choice(["SMB", "CON"], p=[0.72, 0.28]),
                "product_group": str(rng.choice(["40", "54"], p=[0.56, 0.44])),
                "service_station_code": station["service_station_code"],
                "service_station_name": station["service_station_name"],
                "channel": rng.choice(["APOS", "Offline", "Partner"], p=[0.42, 0.36, 0.22]),
                "order_status": order_status,
                "settlement_status": settlement_status,
                "order_amount": round(float(rng.uniform(900, 88000)), 2),
                "sales_account": f"Sales Account {int(rng.integers(1, 28)):02d}",
            }
        )
    return pd.DataFrame(rows)


def build_ar(orders: pd.DataFrame, n_invoices: int = 220, today: date | None = None) -> pd.DataFrame:
    """Create simulated AR invoices connected to a subset of orders."""
    today = today or date.today()
    rng = np.random.default_rng(RANDOM_SEED + 7)
    sampled_orders = orders.sample(n=n_invoices, replace=False, random_state=RANDOM_SEED + 7)
    rows = []

    for idx, (_, order) in enumerate(sampled_orders.iterrows(), start=1):
        invoice_lag = int(rng.integers(0, 18))
        invoice_date = pd.to_datetime(order["order_date"]).date() + timedelta(days=invoice_lag)
        term_days = int(rng.choice([15, 30, 45, 60], p=[0.20, 0.45, 0.22, 0.13]))

        bucket = rng.choice(["overdue_long", "overdue_short", "current", "paid"], p=[0.21, 0.25, 0.34, 0.20])
        if bucket == "overdue_long":
            due_date = today - timedelta(days=int(rng.integers(31, 95)))
        elif bucket == "overdue_short":
            due_date = today - timedelta(days=int(rng.integers(1, 31)))
        else:
            due_date = max(invoice_date + timedelta(days=term_days), today + timedelta(days=int(rng.integers(1, 45))))

        invoice_amount = round(float(max(order["order_amount"] * rng.uniform(0.55, 1.15), 500)), 2)
        if bucket == "paid":
            paid_amount = invoice_amount
        elif bucket == "current":
            paid_amount = round(float(invoice_amount * rng.choice([0, 0.25, 0.50, 0.80])), 2)
        else:
            paid_amount = round(float(invoice_amount * rng.choice([0, 0.10, 0.35, 0.60])), 2)

        rows.append(
            {
                "invoice_id": f"INV{idx:05d}",
                "order_id": order["order_id"],
                "invoice_date": invoice_date,
                "due_date": due_date,
                "invoice_amount": invoice_amount,
                "paid_amount": min(paid_amount, invoice_amount),
                "customer_name": f"Demo Customer {int(rng.integers(1, 90)):03d}",
                "service_station_code": order["service_station_code"],
            }
        )
    return pd.DataFrame(rows)


def generate_sample_data(output_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate all sample datasets and save them as CSV files."""
    output_dir = output_dir or DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = build_mapping()
    orders = build_orders(mapping)
    ar = build_ar(orders)

    orders.to_csv(output_dir / "sample_orders.csv", index=False)
    ar.to_csv(output_dir / "sample_ar.csv", index=False)
    mapping.to_csv(output_dir / "sample_mapping.csv", index=False)
    return orders, ar, mapping


if __name__ == "__main__":
    generated = generate_sample_data()
    print(
        "Generated sample data:",
        f"orders={len(generated[0])}",
        f"ar={len(generated[1])}",
        f"mapping={len(generated[2])}",
    )

