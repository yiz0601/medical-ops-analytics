"""导出服务（阶段四 · 步骤 1-5）。

    export_excel(rows, columns)   指标查询结果 -> xlsx 文件流（openpyxl）
    export_pdf(rows, columns)     报表 -> pdf 文件流（reportlab）

两者均返回 (文件字节流, 文件名, MIME 类型)，由路由层以 StreamingResponse 下发。
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Sequence

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIME = "application/pdf"

DEFAULT_COLUMNS: list[tuple[str, str]] = [
    ("metric_code", "指标编码"),
    ("metric_name", "指标名称"),
    ("dim_value", "维度值"),
    ("granularity", "粒度"),
    ("stat_date", "统计日期"),
    ("metric_value", "指标值"),
    ("unit", "单位"),
    ("data_status", "数据状态"),
]


def _normalize_columns(columns: Sequence[tuple[str, str]] | None) -> list[tuple[str, str]]:
    return list(columns or DEFAULT_COLUMNS)


def _timestamp() -> str:  # 文件名使用 ASCII，中文标题仅保留在文档内容中
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _cell(rows: Sequence[dict[str, Any]], key: str) -> list[Any]:
    return [row.get(key) for row in rows]


def export_excel(
    rows: Sequence[dict[str, Any]],
    columns: Sequence[tuple[str, str]] | None = None,
    *,
    title: str = "指标查询结果",
) -> tuple[bytes, str, str]:
    """生成 xlsx 文件流，返回 (bytes, filename, mime)。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    cols = _normalize_columns(columns)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or "Sheet1"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4F81BD")
    for index, (_, label) in enumerate(cols, start=1):
        cell = sheet.cell(row=1, column=index, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = max(12, min(len(label) * 2 + 6, 32))

    for row_index, row in enumerate(rows, start=2):
        for col_index, (key, _) in enumerate(cols, start=1):
            sheet.cell(row=row_index, column=col_index, value=row.get(key))

    sheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), f"moa_export_{_timestamp()}.xlsx", EXCEL_MIME


def export_pdf(
    rows: Sequence[dict[str, Any]],
    columns: Sequence[tuple[str, str]] | None = None,
    *,
    title: str = "指标查询报表",
) -> tuple[bytes, str, str]:
    """生成 pdf 文件流（A4 横向表格），返回 (bytes, filename, mime)。"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    cols = _normalize_columns(columns)[:8]  # 横向 A4 控制列数
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18,
        title=title,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph(title, styles["Title"]),
        Paragraph(
            f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}　记录数：{len(rows)}", styles["Normal"]
        ),
        Spacer(1, 10),
    ]

    data: list[list[str]] = [[label for _, label in cols]]
    for row in rows:
        data.append([str(row.get(key, "")) if row.get(key) is not None else "" for key, _ in cols])

    table = Table(data, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3FA")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    document.build(story)
    return buffer.getvalue(), f"moa_report_{_timestamp()}.pdf", PDF_MIME


def rows_from_series(series: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """把指标时序结果拍平成导出行（每个数据点一行）。"""
    rows: list[dict[str, Any]] = []
    for item in series:
        for point in item.get("points", []):
            rows.append(
                {
                    "metric_code": point.get("metric_code", item.get("metric_code", "")),
                    "metric_name": point.get("metric_name", item.get("metric_name", "")),
                    "dim_value": point.get("dim_value", ""),
                    "granularity": point.get("granularity", ""),
                    "stat_date": point.get("stat_date", ""),
                    "metric_value": point.get("metric_value"),
                    "unit": point.get("unit", ""),
                    "data_status": point.get("data_status", ""),
                }
            )
    return rows


__all__ = [
    "EXCEL_MIME",
    "PDF_MIME",
    "DEFAULT_COLUMNS",
    "export_excel",
    "export_pdf",
    "rows_from_series",
]
