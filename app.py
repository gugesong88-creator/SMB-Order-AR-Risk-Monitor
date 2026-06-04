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
    page_icon="⚠️",
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
        .pipeline-shell {
            background: #102A2A;
            border-radius: 8px;
            padding: 1rem;
            margin: 0.8rem 0 1rem;
        }
        .workflow-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.5rem;
            margin: 0;
        }
        .workflow-step {
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
            background: rgba(255,255,255,0.07);
            padding: 0.9rem;
            min-height: 118px;
        }
        .workflow-step strong {
            display: block;
            color: #FFFFFF;
            margin-bottom: 0.35rem;
        }
        .workflow-step span {
            color: #C9D8D5;
            font-size: 0.9rem;
        }
        .queue-panel {
            border: 1px solid #E6E8EC;
            border-left: 4px solid #2A9D8F;
            border-radius: 8px;
            padding: 0.9rem 1rem;
            background: #FFFFFF;
            min-height: 120px;
        }
        .queue-panel.high {border-left-color: #E76F51;}
        .queue-panel.warning {border-left-color: #E9C46A;}
        .queue-panel strong {
            display: block;
            color: #111827;
            font-size: 0.95rem;
            margin-bottom: 0.3rem;
        }
        .queue-panel .queue-value {
            color: #111827;
            font-size: 1.65rem;
            font-weight: 750;
            line-height: 1.1;
        }
        .queue-panel span {
            color: #667085;
            display: block;
            font-size: 0.86rem;
            margin-top: 0.35rem;
        }
        .notice-preview {
            border: 1px solid #D0D5DD;
            border-radius: 8px;
            background: #FCFCFD;
            padding: 1rem 1.1rem;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            white-space: pre-wrap;
            color: #1F2937;
            line-height: 1.55;
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
        @media (max-width: 900px) {
            .workflow-grid {grid-template-columns: 1fr;}
        }
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


def render_workflow() -> None:
    """Render the business automation story before the dashboard sections."""
    st.subheader("Automation Pipeline")
    st.markdown(
        """
        <div class="pipeline-shell">
        <div class="workflow-grid">
            <div class="workflow-step"><strong>Data Input</strong><span>订单、AR 发票和 Mapping 表统一导入。</span></div>
            <div class="workflow-step"><strong>Rule Engine</strong><span>执行订单 deadline、AR 到期日和金额阈值规则。</span></div>
            <div class="workflow-step"><strong>Risk Classification</strong><span>标记已超期、即将超期和高风险 AR。</span></div>
            <div class="workflow-step"><strong>Notification List</strong><span>匹配负责人、服务站邮箱和通报对象。</span></div>
            <div class="workflow-step"><strong>Report Export</strong><span>生成 Excel、HTML 通报和邮箱名单。</span></div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_action_queue(
    risk_orders: pd.DataFrame,
    overdue_ar: pd.DataFrame,
    summary_tables: dict[str, pd.DataFrame],
    email_list: str,
) -> None:
    """Render an operations-first action queue."""
    due_soon = risk_orders[risk_orders["order_risk_type"].eq("ORDER_DUE_SOON")].copy()
    overdue_orders = risk_orders[risk_orders["order_risk_type"].eq("ORDER_OVERDUE")].copy()
    high_risk_dealers = int(
        overdue_ar.loc[overdue_ar["risk_level"].eq("HIGH"), "service_station_name"].nunique()
    ) if not overdue_ar.empty and "service_station_name" in overdue_ar.columns else 0
    notice_recipients = len([line for line in email_list.splitlines() if "@" in line])

    st.subheader("Action Queue")
    queue_cols = st.columns(4)
    queue_cols[0].markdown(
        f'<div class="queue-panel warning"><strong>即将超期订单</strong><div class="queue-value">{len(due_soon):,}</div><span>需要提前提醒，避免转为 overdue。</span></div>',
        unsafe_allow_html=True,
    )
    queue_cols[1].markdown(
        f'<div class="queue-panel high"><strong>已超期订单</strong><div class="queue-value">{len(overdue_orders):,}</div><span>需要优先催办并进入风险报告。</span></div>',
        unsafe_allow_html=True,
    )
    queue_cols[2].markdown(
        f'<div class="queue-panel high"><strong>高风险站点</strong><div class="queue-value">{high_risk_dealers:,}</div><span>按逾期金额和逾期天数识别。</span></div>',
        unsafe_allow_html=True,
    )
    queue_cols[3].markdown(
        f'<div class="queue-panel"><strong>需要通知的负责人</strong><div class="queue-value">{notice_recipients:,}</div><span>由督导和服务站邮箱去重生成。</span></div>',
        unsafe_allow_html=True,
    )

    action_tabs = st.tabs(["即将超期订单", "已超期订单", "高风险站点", "通知负责人"])
    order_columns = [
        "order_id",
        "service_station_name",
        "supervisor_name",
        "order_type",
        "days_to_deadline",
        "order_amount",
        "risk_level",
    ]
    with action_tabs[0]:
        st.dataframe(
            due_soon.sort_values("days_to_deadline").loc[:, [c for c in order_columns if c in due_soon.columns]].head(12),
            width="stretch",
            hide_index=True,
            height=320,
        )
    with action_tabs[1]:
        overdue_view = overdue_orders.assign(overdue_days=(-overdue_orders["days_to_deadline"]).clip(lower=0))
        overdue_columns = [
            "order_id",
            "service_station_name",
            "supervisor_name",
            "order_type",
            "overdue_days",
            "order_amount",
            "risk_level",
        ]
        st.dataframe(
            overdue_view.sort_values("overdue_days", ascending=False)
            .loc[:, [c for c in overdue_columns if c in overdue_view.columns]]
            .head(12),
            width="stretch",
            hide_index=True,
            height=320,
        )
    with action_tabs[2]:
        st.dataframe(summary_tables["ar_station_top10"], width="stretch", hide_index=True, height=320)
    with action_tabs[3]:
        recipients = (
            pd.DataFrame({"notification_recipient": [line for line in email_list.splitlines() if "@" in line]})
            if email_list.strip()
            else pd.DataFrame(columns=["notification_recipient"])
        )
        st.dataframe(recipients.head(30), width="stretch", hide_index=True, height=320)


def render_notification_preview(risk_orders: pd.DataFrame, overdue_ar: pd.DataFrame) -> None:
    """Render a simulated notification preview as a workflow output."""
    top_station = "-"
    top_supervisor = "-"
    if not overdue_ar.empty:
        top_row = (
            overdue_ar.groupby(["service_station_name", "supervisor_name"], dropna=False)["unpaid_amount"]
            .sum()
            .reset_index()
            .sort_values("unpaid_amount", ascending=False)
            .head(1)
        )
        if not top_row.empty:
            top_station = str(top_row.iloc[0]["service_station_name"])
            top_supervisor = str(top_row.iloc[0]["supervisor_name"])

    preview = (
        "Subject: 服务订单与应收账款风险跟进提醒\n\n"
        f"Hi {top_supervisor},\n\n"
        f"系统已识别 {len(risk_orders):,} 条异常订单和 {len(overdue_ar):,} 条逾期 AR 记录。"
        f"当前优先关注站点为 {top_station}。\n\n"
        "请按以下顺序处理：\n"
        "1. 先确认已超期订单是否已完成结算或需要业务升级。\n"
        "2. 对 7 天内即将超期订单提前提醒服务站。\n"
        "3. 对高金额或超 30 天 AR 逾期记录补充回款计划。\n\n"
        "附件：Excel 风险报告、HTML 通报、通知对象名单。"
    )
    st.subheader("Generate Notification Preview")
    st.markdown(f'<div class="notice-preview">{preview}</div>', unsafe_allow_html=True)


def main() -> None:
    """Run the Streamlit dashboard."""
    ensure_sample_data()
    inject_styles()

    st.title("SMB Order & AR Risk Monitor")
    st.caption("商务流程自动化预警 | 运营效率提升 | 规则引擎 | 通知机制")

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
        本项目使用模拟数据复现商务运营中的订单超期、逾期通报和应收账款预警流程，
        重点展示如何把人工统计、人工筛选、人工通知改造成自动化预警和批量通报流程。
        数据不包含任何真实公司、真实员工或真实邮箱。
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_workflow()

    excel_report = generate_excel_report(risk_orders, overdue_ar, summary_tables)
    html_notice = generate_html_notice(risk_orders, overdue_ar)
    email_list = generate_email_list(risk_orders, overdue_ar)

    render_action_queue(risk_orders, overdue_ar, summary_tables, email_list)

    st.subheader("Automation Output Metrics")
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Orders to Notify", f"{len(risk_orders):,}")
    kpi_cols[1].metric("Overdue AR Amount", format_currency(kpis["overdue_ar_amount"]))
    kpi_cols[2].metric("High-risk Dealers", f"{overdue_ar.loc[overdue_ar['risk_level'].eq('HIGH'), 'service_station_name'].nunique():,}")
    kpi_cols[3].metric("Notices Generated", f"{len([line for line in email_list.splitlines() if '@' in line]):,}")

    render_notification_preview(risk_orders, overdue_ar)

    st.subheader("Auxiliary Risk Analytics")
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

    st.subheader("Exception Review Tables")
    tab_orders, tab_ar, tab_station, tab_supervisor = st.tabs(["异常订单明细", "AR 逾期明细", "服务站 TOP10", "督导 TOP10"])
    with tab_orders:
        st.dataframe(risk_orders, width="stretch", hide_index=True)
    with tab_ar:
        st.dataframe(overdue_ar, width="stretch", hide_index=True)
    with tab_station:
        st.dataframe(summary_tables["ar_station_top10"], width="stretch", hide_index=True)
    with tab_supervisor:
        st.dataframe(summary_tables["supervisor_top10"], width="stretch", hide_index=True)

    st.subheader("Notification & Report Export Center")
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
            mime="text/html; charset=utf-8",
        )
    with download_cols[2]:
        st.download_button(
            "下载邮箱名单 txt",
            data=email_list,
            file_name="risk_email_list.txt",
            mime="text/plain; charset=utf-8",
        )


if __name__ == "__main__":
    main()
