"""Streamlit app for SMB order overdue and AR risk monitoring."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from src.data_generator import generate_sample_data
from src.data_loader import load_ar, load_mapping, load_orders
from src.metrics import build_summary_tables, calculate_kpis
from src.report_generator import generate_email_list, generate_excel_report, generate_html_notice
from src.rules import apply_ar_rules, apply_order_rules, merge_risk_data
from src.utils import DATA_DIR, format_currency


st.set_page_config(
    page_title="SMB Order & AR Risk Monitor",
    page_icon="📊",
    layout="wide",
)


def ensure_sample_data() -> None:
    """Generate default sample files when the data directory is empty."""
    required_files = ["sample_orders.csv", "sample_ar.csv", "sample_mapping.csv"]
    if not all((DATA_DIR / filename).exists() for filename in required_files):
        generate_sample_data(DATA_DIR)


def inject_styles() -> None:
    """Apply lightweight CSS for a cleaner dashboard presentation."""
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
        .hero-note {
            border-left: 4px solid #2A9D8F;
            background: #F6FBFA;
            padding: 1rem 1.1rem;
            border-radius: 8px;
            color: #1C2B2A;
            margin-bottom: 1rem;
        }
        div[data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #E6E8EC;
            border-radius: 8px;
            padding: 0.85rem 1rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }
        div[data-testid="stMetricLabel"] p {font-size: 0.9rem;}
        div[data-testid="stMetricValue"] {font-size: 1.55rem;}
        h1, h2, h3 {letter-spacing: 0;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def filter_options(df: pd.DataFrame, column: str) -> list[str]:
    """Return sorted non-empty string options for a filter column."""
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str)
    return sorted([value for value in values.unique().tolist() if value and value.lower() != "nan"])


def apply_filters(orders: pd.DataFrame, ar: pd.DataFrame, filters: dict[str, list[str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply sidebar filters consistently to order and AR datasets."""
    filtered_orders = orders.copy()
    filtered_ar = ar.copy()

    shared_columns = ["business_line", "product_group", "region", "supervisor_name", "risk_level"]
    for column in shared_columns:
        selected = filters.get(column, [])
        if selected:
            if column in filtered_orders.columns:
                filtered_orders = filtered_orders[filtered_orders[column].astype(str).isin(selected)]
            if column in filtered_ar.columns:
                filtered_ar = filtered_ar[filtered_ar[column].astype(str).isin(selected)]

    risk_types = filters.get("risk_type", [])
    if risk_types:
        order_types = [item for item in risk_types if item.startswith("ORDER_") or item == "NORMAL"]
        ar_types = [item for item in risk_types if item.startswith("AR_") or item == "NORMAL"]
        if order_types:
            filtered_orders = filtered_orders[filtered_orders["order_risk_type"].isin(order_types)]
        else:
            filtered_orders = filtered_orders.iloc[0:0]
        if ar_types:
            filtered_ar = filtered_ar[filtered_ar["ar_risk_type"].isin(ar_types)]
        else:
            filtered_ar = filtered_ar.iloc[0:0]

    return filtered_orders, filtered_ar


def plot_bar(df: pd.DataFrame, x: str, y: str, title: str, orientation: str = "v"):
    """Build a Plotly bar chart with consistent styling."""
    if df.empty:
        st.info(f"{title}：当前筛选范围内暂无数据。")
        return
    fig = px.bar(
        df,
        x=x,
        y=y,
        orientation=orientation,
        title=title,
        color=y if orientation == "v" else x,
        color_continuous_scale=["#2A9D8F", "#E9C46A", "#E76F51"],
    )
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=55, b=10),
        title_font_size=17,
        coloraxis_showscale=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    st.plotly_chart(fig, width="stretch")


def main() -> None:
    """Run the Streamlit dashboard."""
    ensure_sample_data()
    inject_styles()

    st.title("SMB Order & AR Risk Monitor")
    st.caption("中小企业服务订单与应收账款风险预警系统")

    with st.sidebar:
        st.header("数据与筛选")
        order_file = st.file_uploader("上传订单明细 CSV / Excel", type=["csv", "xlsx", "xls"])
        ar_file = st.file_uploader("上传 AR 明细 CSV / Excel", type=["csv", "xlsx", "xls"])
        mapping_file = st.file_uploader("上传 Mapping 表 CSV / Excel", type=["csv", "xlsx", "xls"])
        selected_today = st.date_input("规则计算日期", value=date.today())

    orders_raw = load_orders(order_file)
    ar_raw = load_ar(ar_file)
    mapping_raw = load_mapping(mapping_file)

    orders_with_rules = apply_order_rules(orders_raw, selected_today)
    ar_with_rules = apply_ar_rules(ar_raw, selected_today)
    orders_merged, ar_merged = merge_risk_data(orders_with_rules, ar_with_rules, mapping_raw)

    with st.sidebar:
        st.divider()
        filter_source = pd.concat(
            [
                orders_merged[["business_line", "product_group", "region", "supervisor_name", "risk_level"]].copy(),
                ar_merged[["business_line", "product_group", "region", "supervisor_name", "risk_level"]].copy(),
            ],
            ignore_index=True,
        )
        filters = {
            "business_line": st.multiselect("business_line", filter_options(filter_source, "business_line")),
            "product_group": st.multiselect("product_group", filter_options(filter_source, "product_group")),
            "region": st.multiselect("region", filter_options(filter_source, "region")),
            "supervisor_name": st.multiselect("supervisor_name", filter_options(filter_source, "supervisor_name")),
            "risk_type": st.multiselect(
                "risk_type",
                ["ORDER_OVERDUE", "ORDER_DUE_SOON", "AR_OVERDUE", "NORMAL"],
            ),
            "risk_level": st.multiselect("risk_level", ["HIGH", "MEDIUM", "LOW"]),
        }

    filtered_orders, filtered_ar = apply_filters(orders_merged, ar_merged, filters)
    risk_orders = filtered_orders[filtered_orders["order_risk_type"].ne("NORMAL")].copy()
    overdue_ar = filtered_ar[filtered_ar["ar_risk_type"].eq("AR_OVERDUE")].copy()
    summary_tables = build_summary_tables(filtered_orders, filtered_ar)
    kpis = calculate_kpis(filtered_orders, filtered_ar)

    st.markdown(
        """
        <div class="hero-note">
        本项目使用模拟数据复现企业商务流程中的订单超期、逾期通报和应收账款风险预警场景，
        用于展示从 Excel 人工筛选、责任人匹配、报表生成到内部通报整理的办公流程产品化能力。
        数据不包含任何真实公司、真实员工或真实邮箱。
        </div>
        """,
        unsafe_allow_html=True,
    )

    kpi_cols = st.columns(5)
    kpi_cols[0].metric("总订单数", f"{kpis['total_orders']:,}")
    kpi_cols[1].metric("即将超期订单数", f"{kpis['due_soon_orders']:,}")
    kpi_cols[2].metric("已超期订单数", f"{kpis['overdue_orders']:,}")
    kpi_cols[3].metric("AR 逾期发票数", f"{kpis['overdue_ar_count']:,}")
    kpi_cols[4].metric("AR 逾期金额", format_currency(kpis["overdue_ar_amount"]))

    st.subheader("风险图表")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        plot_bar(summary_tables["risk_by_business_line"], "business_line", "risk_order_count", "业务线风险订单数量")
        plot_bar(
            summary_tables["ar_station_top10"].sort_values("overdue_ar_amount"),
            "overdue_ar_amount",
            "service_station_name",
            "服务站 AR 逾期金额 TOP10",
            orientation="h",
        )
    with chart_right:
        plot_bar(summary_tables["risk_by_product_group"], "product_group", "risk_order_count", "产品组风险订单数量")
        plot_bar(
            summary_tables["supervisor_top10"].sort_values("abnormal_order_count"),
            "abnormal_order_count",
            "supervisor_name",
            "督导异常订单数量 TOP10",
            orientation="h",
        )

    plot_bar(summary_tables["region_risk_amount"], "region", "risk_amount", "区域风险金额分布")

    st.subheader("明细表")
    tab_orders, tab_ar, tab_station, tab_supervisor = st.tabs(["异常订单明细", "AR 逾期明细", "服务站 TOP10", "督导 TOP10"])
    with tab_orders:
        st.dataframe(risk_orders, width="stretch", hide_index=True)
    with tab_ar:
        st.dataframe(overdue_ar, width="stretch", hide_index=True)
    with tab_station:
        st.dataframe(summary_tables["ar_station_top10"], width="stretch", hide_index=True)
    with tab_supervisor:
        st.dataframe(summary_tables["supervisor_top10"], width="stretch", hide_index=True)

    st.subheader("下载区")
    excel_report = generate_excel_report(risk_orders, overdue_ar, summary_tables)
    html_notice = generate_html_notice(risk_orders, overdue_ar)
    email_list = generate_email_list(risk_orders, overdue_ar)

    download_cols = st.columns(3)
    with download_cols[0]:
        st.download_button(
            "下载 Excel 风险报告",
            data=excel_report,
            file_name="smb_order_ar_risk_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with download_cols[1]:
        st.download_button(
            "下载 HTML 通报文本",
            data=html_notice,
            file_name="risk_notice.html",
            mime="text/html",
        )
    with download_cols[2]:
        st.download_button(
            "下载邮箱名单 txt",
            data=email_list,
            file_name="risk_email_list.txt",
            mime="text/plain",
        )


if __name__ == "__main__":
    main()
