"""Business rules for order overdue and AR collection risk detection."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


ORDER_DEADLINES = {"F": 7, "M": 30}


def apply_order_rules(orders: pd.DataFrame, today: date) -> pd.DataFrame:
    """Apply order overdue and due-soon rules and return enriched order data."""
    df = orders.copy()
    today_ts = pd.Timestamp(today)

    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["deadline_days"] = df["order_type"].map(ORDER_DEADLINES).fillna(30).astype(int)
    df["order_age_days"] = (today_ts - df["order_date"]).dt.days
    df["days_to_deadline"] = df["deadline_days"] - df["order_age_days"]

    active_unsettled = df["settlement_status"].isin(["not_applied", "applied"]) & (df["order_status"] != "cancelled")
    df["order_risk_type"] = np.select(
        [
            active_unsettled & (df["order_age_days"] > df["deadline_days"]),
            active_unsettled & (df["days_to_deadline"].between(0, 7)),
        ],
        ["ORDER_OVERDUE", "ORDER_DUE_SOON"],
        default="NORMAL",
    )

    df["risk_level"] = np.select(
        [
            df["order_risk_type"].eq("ORDER_OVERDUE"),
            df["order_risk_type"].eq("ORDER_DUE_SOON"),
        ],
        ["HIGH", "MEDIUM"],
        default="LOW",
    )
    return df


def apply_ar_rules(ar: pd.DataFrame, today: date) -> pd.DataFrame:
    """Apply AR overdue rules and return enriched invoice data."""
    df = ar.copy()
    today_ts = pd.Timestamp(today)

    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce")
    df["invoice_amount"] = pd.to_numeric(df["invoice_amount"], errors="coerce").fillna(0)
    df["paid_amount"] = pd.to_numeric(df["paid_amount"], errors="coerce").fillna(0)
    df["unpaid_amount"] = (df["invoice_amount"] - df["paid_amount"]).clip(lower=0)
    df["overdue_days"] = (today_ts - df["due_date"]).dt.days
    df["ar_risk_type"] = np.where((df["unpaid_amount"] > 0) & (df["overdue_days"] > 0), "AR_OVERDUE", "NORMAL")

    high = (df["ar_risk_type"].eq("AR_OVERDUE")) & ((df["overdue_days"] > 30) | (df["unpaid_amount"] > 50000))
    medium = (df["ar_risk_type"].eq("AR_OVERDUE")) & (
        (df["overdue_days"].between(1, 30)) | (df["unpaid_amount"].between(10000, 50000))
    )
    df["risk_level"] = np.select([high, medium], ["HIGH", "MEDIUM"], default="LOW")
    return df


def merge_risk_data(orders: pd.DataFrame, ar: pd.DataFrame, mapping: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge rule-enriched data with mapping and order context."""
    mapping_cols = [
        "service_station_code",
        "service_station_name",
        "supervisor_name",
        "supervisor_email",
        "station_email",
        "region",
    ]
    mapping_clean = mapping[mapping_cols].drop_duplicates("service_station_code")

    order_context_cols = [
        "order_id",
        "business_line",
        "product_group",
        "service_station_code",
        "service_station_name",
    ]
    order_context = orders[order_context_cols].drop_duplicates("order_id")

    orders_merged = orders.merge(
        mapping_clean.drop(columns=["service_station_name"]),
        on="service_station_code",
        how="left",
    )

    ar_merged = ar.merge(
        order_context,
        on="order_id",
        how="left",
        suffixes=("", "_order"),
    )
    ar_merged["service_station_code"] = ar_merged["service_station_code"].fillna(ar_merged["service_station_code_order"])
    if "service_station_code_order" in ar_merged:
        ar_merged = ar_merged.drop(columns=["service_station_code_order"])

    ar_merged = ar_merged.merge(
        mapping_clean,
        on="service_station_code",
        how="left",
        suffixes=("", "_mapping"),
    )
    ar_merged["service_station_name"] = ar_merged["service_station_name"].fillna(ar_merged["service_station_name_mapping"])
    if "service_station_name_mapping" in ar_merged:
        ar_merged = ar_merged.drop(columns=["service_station_name_mapping"])

    return orders_merged, ar_merged

