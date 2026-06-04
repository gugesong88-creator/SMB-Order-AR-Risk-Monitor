"""Metric and aggregation calculations for the dashboard."""

from __future__ import annotations

import pandas as pd


def calculate_kpis(orders: pd.DataFrame, ar: pd.DataFrame) -> dict[str, float]:
    """Calculate headline KPI values used by the dashboard."""
    overdue_ar = ar[ar["ar_risk_type"].eq("AR_OVERDUE")]
    return {
        "total_orders": int(len(orders)),
        "due_soon_orders": int(orders["order_risk_type"].eq("ORDER_DUE_SOON").sum()),
        "overdue_orders": int(orders["order_risk_type"].eq("ORDER_OVERDUE").sum()),
        "overdue_ar_count": int(len(overdue_ar)),
        "overdue_ar_amount": float(overdue_ar["unpaid_amount"].sum()),
    }


def build_summary_tables(orders: pd.DataFrame, ar: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build grouped summary tables for charts and report sheets."""
    risk_orders = orders[orders["order_risk_type"].ne("NORMAL")].copy()
    overdue_ar = ar[ar["ar_risk_type"].eq("AR_OVERDUE")].copy()

    risk_by_business_line = (
        risk_orders.groupby("business_line", dropna=False)
        .size()
        .reset_index(name="risk_order_count")
        .sort_values("risk_order_count", ascending=False)
    )
    risk_by_product_group = (
        risk_orders.groupby("product_group", dropna=False)
        .size()
        .reset_index(name="risk_order_count")
        .sort_values("risk_order_count", ascending=False)
    )
    ar_station_top10 = (
        overdue_ar.groupby("service_station_name", dropna=False)["unpaid_amount"]
        .sum()
        .reset_index(name="overdue_ar_amount")
        .sort_values("overdue_ar_amount", ascending=False)
        .head(10)
    )
    supervisor_top10 = (
        risk_orders.groupby("supervisor_name", dropna=False)
        .size()
        .reset_index(name="abnormal_order_count")
        .sort_values("abnormal_order_count", ascending=False)
        .head(10)
    )

    order_amount_by_region = (
        risk_orders.groupby("region", dropna=False)["order_amount"]
        .sum()
        .reset_index(name="risk_order_amount")
    )
    ar_amount_by_region = (
        overdue_ar.groupby("region", dropna=False)["unpaid_amount"]
        .sum()
        .reset_index(name="overdue_ar_amount")
    )
    region_risk_amount = order_amount_by_region.merge(ar_amount_by_region, on="region", how="outer").fillna(0)
    region_risk_amount["risk_amount"] = region_risk_amount["risk_order_amount"] + region_risk_amount["overdue_ar_amount"]
    region_risk_amount = region_risk_amount.sort_values("risk_amount", ascending=False)

    return {
        "risk_by_business_line": risk_by_business_line,
        "risk_by_product_group": risk_by_product_group,
        "ar_station_top10": ar_station_top10,
        "supervisor_top10": supervisor_top10,
        "region_risk_amount": region_risk_amount,
    }

