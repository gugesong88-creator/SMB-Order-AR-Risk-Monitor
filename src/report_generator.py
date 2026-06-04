"""Downloadable report generation for Excel, HTML notice, and email lists."""

from __future__ import annotations

from io import BytesIO
from html import escape

import pandas as pd


def _safe_text(value) -> str:
    """Return escaped display text for HTML cells."""
    if pd.isna(value):
        return "-"
    return escape(str(value))


def _money(value: float) -> str:
    """Format money values for notice output."""
    return f"¥{float(value or 0):,.2f}"


def generate_excel_report(risk_orders: pd.DataFrame, overdue_ar: pd.DataFrame, summary_tables: dict[str, pd.DataFrame]) -> BytesIO:
    """Generate a formatted Excel report and return it as a BytesIO object."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        risk_orders.to_excel(writer, sheet_name="Risk Orders", index=False)
        overdue_ar.to_excel(writer, sheet_name="Overdue AR", index=False)
        summary_tables["ar_station_top10"].to_excel(writer, sheet_name="Service Station TOP10", index=False)
        summary_tables["supervisor_top10"].to_excel(writer, sheet_name="Supervisor TOP10", index=False)

        workbook = writer.book
        header_format = workbook.add_format(
            {"bold": True, "font_color": "white", "bg_color": "#1F4E79", "border": 1}
        )
        money_format = workbook.add_format({"num_format": "¥#,##0.00"})

        for sheet_name, worksheet in writer.sheets.items():
            df = {
                "Risk Orders": risk_orders,
                "Overdue AR": overdue_ar,
                "Service Station TOP10": summary_tables["ar_station_top10"],
                "Supervisor TOP10": summary_tables["supervisor_top10"],
            }[sheet_name]
            for col_num, value in enumerate(df.columns):
                worksheet.write(0, col_num, value, header_format)
                width = min(max(len(str(value)) + 4, 14), 34)
                worksheet.set_column(col_num, col_num, width)
            for idx, col in enumerate(df.columns):
                if "amount" in col.lower():
                    worksheet.set_column(idx, idx, 16, money_format)
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))

    output.seek(0)
    return output


def generate_html_notice(risk_orders: pd.DataFrame, overdue_ar: pd.DataFrame) -> str:
    """Generate a business-style HTML notice for internal risk follow-up."""
    overdue_orders_count = int(risk_orders["order_risk_type"].eq("ORDER_OVERDUE").sum()) if not risk_orders.empty else 0
    due_soon_orders_count = int(risk_orders["order_risk_type"].eq("ORDER_DUE_SOON").sum()) if not risk_orders.empty else 0
    overdue_ar_count = int(len(overdue_ar)) if not overdue_ar.empty else 0
    overdue_ar_amount = float(overdue_ar["unpaid_amount"].sum()) if not overdue_ar.empty else 0
    max_overdue_days = int(overdue_ar["overdue_days"].max()) if not overdue_ar.empty else 0

    ar_top10 = (
        overdue_ar.groupby(["service_station_name", "supervisor_name"], dropna=False)["unpaid_amount"]
        .agg(["sum", "count"])
        .reset_index()
        .rename(columns={"sum": "overdue_ar_amount", "count": "invoice_count"})
        .sort_values("overdue_ar_amount", ascending=False)
        .head(10)
    )

    order_top10 = (
        risk_orders.groupby(["service_station_name", "supervisor_name"], dropna=False)
        .agg(
            risk_order_count=("order_id", "count"),
            overdue_order_count=("order_risk_type", lambda s: int(s.eq("ORDER_OVERDUE").sum())),
            due_soon_order_count=("order_risk_type", lambda s: int(s.eq("ORDER_DUE_SOON").sum())),
            risk_order_amount=("order_amount", "sum"),
        )
        .reset_index()
        .sort_values(["overdue_order_count", "risk_order_count", "risk_order_amount"], ascending=False)
        .head(10)
        if not risk_orders.empty
        else pd.DataFrame()
    )

    ar_rows = "\n".join(
        "<tr>"
        f"<td>{idx}</td>"
        f"<td>{_safe_text(row.service_station_name)}</td>"
        f"<td>{_safe_text(row.supervisor_name)}</td>"
        f"<td class=\"number\">{int(row.invoice_count)}</td>"
        f"<td class=\"number strong-red\">{_money(row.overdue_ar_amount)}</td>"
        "</tr>"
        for idx, row in enumerate(ar_top10.itertuples(index=False), start=1)
    )
    if not ar_rows:
        ar_rows = "<tr><td colspan=\"5\" class=\"empty\">当前筛选范围内暂无逾期 AR 记录。</td></tr>"

    order_rows = "\n".join(
        "<tr>"
        f"<td>{idx}</td>"
        f"<td>{_safe_text(row.service_station_name)}</td>"
        f"<td>{_safe_text(row.supervisor_name)}</td>"
        f"<td class=\"number strong-red\">{int(row.overdue_order_count)}</td>"
        f"<td class=\"number warning\">{int(row.due_soon_order_count)}</td>"
        f"<td class=\"number\">{int(row.risk_order_count)}</td>"
        f"<td class=\"number\">{_money(row.risk_order_amount)}</td>"
        "</tr>"
        for idx, row in enumerate(order_top10.itertuples(index=False), start=1)
    )
    if not order_rows:
        order_rows = "<tr><td colspan=\"7\" class=\"empty\">当前筛选范围内暂无异常订单记录。</td></tr>"

    return f"""\ufeff<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>服务订单与应收账款风险通报</title>
<style>
    body {{
        margin: 0;
        padding: 24px;
        background: #f5f7fb;
        color: #1f2937;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
            "Microsoft YaHei", Arial, sans-serif;
        font-size: 14px;
        line-height: 1.6;
    }}
    .container {{
        max-width: 980px;
        margin: 0 auto;
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }}
    .header {{
        padding: 24px 28px;
        background: #17324d;
        color: #ffffff;
    }}
    .header h1 {{
        margin: 0 0 8px;
        font-size: 24px;
        letter-spacing: 0;
    }}
    .header p {{
        margin: 0;
        color: #d8e6f3;
    }}
    .content {{
        padding: 24px 28px 30px;
    }}
    .intro {{
        margin: 0 0 18px;
    }}
    .summary-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 18px 0 22px;
    }}
    .summary-card {{
        border: 1px solid #e5e7eb;
        border-left: 4px solid #2a9d8f;
        border-radius: 8px;
        padding: 12px 14px;
        background: #fbfdff;
    }}
    .summary-card.high {{
        border-left-color: #e76f51;
    }}
    .summary-card.warning-card {{
        border-left-color: #f4a261;
    }}
    .label {{
        color: #6b7280;
        font-size: 12px;
        margin-bottom: 4px;
    }}
    .value {{
        font-size: 20px;
        font-weight: 700;
        color: #111827;
    }}
    .section-title {{
        margin: 24px 0 10px;
        font-size: 17px;
        color: #17324d;
        border-bottom: 2px solid #d8e6f3;
        padding-bottom: 6px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        margin: 10px 0 18px;
        border: 1px solid #d1d5db;
        font-size: 13px;
    }}
    th {{
        background: #d8e6f3;
        color: #17324d;
        font-weight: 700;
        text-align: left;
        border: 1px solid #cbd5e1;
        padding: 8px 10px;
    }}
    td {{
        border: 1px solid #e5e7eb;
        padding: 8px 10px;
        word-break: break-word;
        vertical-align: top;
    }}
    tr:nth-child(even) td {{
        background: #f8fbff;
    }}
    .number {{
        text-align: right;
        white-space: nowrap;
    }}
    .strong-red {{
        color: #d92d20;
        font-weight: 700;
    }}
    .warning {{
        color: #b7791f;
        font-weight: 700;
    }}
    .note {{
        margin: 18px 0;
        padding: 12px 14px;
        border-left: 4px solid #f4a261;
        background: #fff8eb;
        border-radius: 6px;
    }}
    .footer {{
        margin-top: 20px;
        padding-top: 14px;
        border-top: 1px solid #e5e7eb;
        color: #6b7280;
        font-size: 12px;
    }}
    .empty {{
        text-align: center;
        color: #6b7280;
        padding: 14px;
    }}
    @media (max-width: 760px) {{
        body {{
            padding: 12px;
        }}
        .summary-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .content,
        .header {{
            padding-left: 16px;
            padding-right: 16px;
        }}
        table {{
            table-layout: auto;
        }}
    }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>服务订单与应收账款风险通报</h1>
        <p>SMB Order & AR Risk Monitor | 内部经营风险跟进摘要</p>
    </div>
    <div class="content">
        <p class="intro">
            各位同事好，以下为当前筛选范围内的订单超期、即将超期与应收账款逾期风险摘要。
            请相关服务站和责任督导结合明细表核对订单结算状态、客户回款进度和后续处理计划。
        </p>

        <div class="summary-grid">
            <div class="summary-card high">
                <div class="label">已超期订单</div>
                <div class="value">{overdue_orders_count}</div>
            </div>
            <div class="summary-card warning-card">
                <div class="label">即将超期订单</div>
                <div class="value">{due_soon_orders_count}</div>
            </div>
            <div class="summary-card high">
                <div class="label">AR 逾期发票</div>
                <div class="value">{overdue_ar_count}</div>
            </div>
            <div class="summary-card high">
                <div class="label">AR 逾期金额</div>
                <div class="value">{_money(overdue_ar_amount)}</div>
            </div>
        </div>

        <div class="note">
            <strong>风险提示：</strong>当前筛选范围内 AR 最长逾期天数为
            <strong>{max_overdue_days}</strong> 天。请优先跟进高金额、长账龄以及已超期订单集中的服务站。
        </div>

        <h2 class="section-title">逾期 AR TOP10</h2>
        <table>
            <thead>
                <tr>
                    <th style="width:52px;">排名</th>
                    <th>服务站</th>
                    <th>责任督导</th>
                    <th style="width:90px;">发票数</th>
                    <th style="width:150px;">逾期未收金额</th>
                </tr>
            </thead>
            <tbody>
                {ar_rows}
            </tbody>
        </table>

        <h2 class="section-title">异常订单服务站 TOP10</h2>
        <table>
            <thead>
                <tr>
                    <th style="width:52px;">排名</th>
                    <th>服务站</th>
                    <th>责任督导</th>
                    <th style="width:90px;">已超期</th>
                    <th style="width:90px;">即将超期</th>
                    <th style="width:90px;">异常订单</th>
                    <th style="width:150px;">风险订单金额</th>
                </tr>
            </thead>
            <tbody>
                {order_rows}
            </tbody>
        </table>

        <div class="note">
            <strong>建议动作：</strong>
            1. 督导优先核对 TOP10 服务站的订单结算状态和客户付款计划；
            2. 服务站补充预计处理时间和责任人；
            3. 对逾期金额较高或逾期天数较长的客户，建议在下一轮例会中单独跟进。
        </div>

        <div class="footer">
            本通报由 SMB Order & AR Risk Monitor 基于模拟数据自动生成，仅用于项目展示和流程演示，不包含真实公司、真实人员或真实邮箱信息。
        </div>
    </div>
</div>
</body>
</html>
""".strip()


def generate_email_list(risk_orders: pd.DataFrame, overdue_ar: pd.DataFrame) -> str:
    """Extract unique supervisor and service-station emails as a plain-text list."""
    emails = []
    for df in [risk_orders, overdue_ar]:
        for col in ["supervisor_email", "station_email"]:
            if col in df.columns:
                emails.extend(df[col].dropna().astype(str).str.strip().tolist())
    unique_emails = sorted({email for email in emails if email and email.lower() != "nan"})
    return "\n".join(unique_emails)
