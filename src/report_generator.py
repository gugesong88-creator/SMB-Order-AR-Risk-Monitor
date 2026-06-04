"""Downloadable report generation for Excel, HTML notice, and email lists."""

from __future__ import annotations

from io import BytesIO
from html import escape

import pandas as pd


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
    overdue_ar_amount = float(overdue_ar["unpaid_amount"].sum()) if not overdue_ar.empty else 0

    top10 = (
        overdue_ar.groupby(["service_station_name", "supervisor_name"], dropna=False)["unpaid_amount"]
        .sum()
        .reset_index()
        .sort_values("unpaid_amount", ascending=False)
        .head(10)
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(row.service_station_name))}</td>"
        f"<td>{escape(str(row.supervisor_name))}</td>"
        f"<td>¥{row.unpaid_amount:,.2f}</td>"
        "</tr>"
        for row in top10.itertuples(index=False)
    )
    if not rows:
        rows = "<tr><td colspan='3'>当前筛选范围内暂无逾期 AR 记录。</td></tr>"

    return f"""
<html>
<body>
  <h2>服务订单与应收账款风险通报</h2>
  <p>各位同事好，以下为当前筛选范围内的订单超期与应收账款风险摘要，请相关责任人尽快跟进处理。</p>
  <ul>
    <li>已超期订单数量：<strong>{overdue_orders_count}</strong></li>
    <li>即将超期订单数量：<strong>{due_soon_orders_count}</strong></li>
    <li>AR 逾期金额：<strong>¥{overdue_ar_amount:,.2f}</strong></li>
  </ul>
  <h3>逾期 AR TOP10</h3>
  <table border="1" cellspacing="0" cellpadding="6">
    <thead>
      <tr>
        <th>服务站</th>
        <th>责任督导</th>
        <th>逾期未收金额</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  <p>请各服务站及督导根据明细清单核对订单状态、结算状态与客户回款进度，并及时反馈处理结果。</p>
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

