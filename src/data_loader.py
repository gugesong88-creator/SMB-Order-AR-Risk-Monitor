"""Data loading and schema validation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from src.utils import DATA_DIR, normalize_code_series


ORDER_COLUMNS = [
    "order_id",
    "order_date",
    "order_type",
    "business_line",
    "product_group",
    "service_station_code",
    "service_station_name",
    "channel",
    "order_status",
    "settlement_status",
    "order_amount",
    "sales_account",
]

AR_COLUMNS = [
    "invoice_id",
    "order_id",
    "invoice_date",
    "due_date",
    "invoice_amount",
    "paid_amount",
    "customer_name",
    "service_station_code",
]

MAPPING_COLUMNS = [
    "service_station_code",
    "service_station_name",
    "supervisor_name",
    "supervisor_email",
    "station_email",
    "region",
]


def _read_file(uploaded_file, default_path: Path) -> pd.DataFrame:
    """Read a default or uploaded CSV/Excel file into a DataFrame."""
    if uploaded_file is None:
        return pd.read_csv(default_path)

    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    st.error(f"不支持的文件类型：{uploaded_file.name}。请上传 CSV、XLSX 或 XLS 文件。")
    st.stop()


def _validate_columns(df: pd.DataFrame, required_columns: Iterable[str], dataset_name: str) -> pd.DataFrame:
    """Validate required columns and stop the Streamlit app on schema errors."""
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        st.error(f"{dataset_name} 缺少必要字段：{', '.join(missing)}")
        st.stop()
    return df.copy()


def _coerce_common_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common id-like and amount columns after loading."""
    for col in ["order_id", "invoice_id", "service_station_code", "product_group"]:
        if col in df.columns:
            df[col] = normalize_code_series(df[col])

    for col in ["order_date", "invoice_date", "due_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in ["order_amount", "invoice_amount", "paid_amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def load_orders(uploaded_file=None) -> pd.DataFrame:
    """Load order data from an uploaded file or the default sample CSV."""
    df = _read_file(uploaded_file, DATA_DIR / "sample_orders.csv")
    df = _validate_columns(df, ORDER_COLUMNS, "订单明细")
    return _coerce_common_columns(df)


def load_ar(uploaded_file=None) -> pd.DataFrame:
    """Load AR invoice data from an uploaded file or the default sample CSV."""
    df = _read_file(uploaded_file, DATA_DIR / "sample_ar.csv")
    df = _validate_columns(df, AR_COLUMNS, "AR 明细")
    return _coerce_common_columns(df)


def load_mapping(uploaded_file=None) -> pd.DataFrame:
    """Load service-station mapping data from an uploaded file or the default sample CSV."""
    df = _read_file(uploaded_file, DATA_DIR / "sample_mapping.csv")
    df = _validate_columns(df, MAPPING_COLUMNS, "Mapping 表")
    return _coerce_common_columns(df)

