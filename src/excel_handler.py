import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from typing import Tuple
import os
import json

from config import (
    NAME_COLUMN_EXACT,
    PHONE_COLUMN_KEYWORDS,
    ID_CARD_COLUMN_KEYWORDS,
    ADDRESS_COLUMN_KEYWORDS,
    TEXT_COLUMN_KEYWORDS,
    SKIP_COLUMN_PATTERNS,
    TEXT_EXCEPTION_KEYWORDS,
)


def read_excel(file_path: str) -> Tuple:
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    headers = []
    for cell in ws[1]:
        if cell.value is not None:
            headers.append(str(cell.value).strip())
        else:
            headers.append(f"col_{cell.column}")

    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_dict = {}
        for i, val in enumerate(row):
            if i < len(headers):
                row_dict[headers[i]] = str(val) if val is not None else ""
        rows.append(row_dict)

    wb.close()
    return headers, rows


def write_excel(file_path: str, headers: list, rows: list):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "脱敏后数据"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4B3FE3", end_color="4B3FE3", fill_type="solid")
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=i, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for r, row_dict in enumerate(rows, 2):
        for c, h in enumerate(headers, 1):
            ws.cell(row=r, column=c, value=row_dict.get(h, ""))

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        adjusted_width = min(max_length + 4, 50)
        ws.column_dimensions[column].width = max(adjusted_width, 12)

    wb.save(file_path)
    wb.close()


def auto_detect_columns(headers: list) -> dict:
    """自动识别列类型。

    分类优先级（互斥）：姓名 > 电话 > 身份证 > 地址 > 文本 > 跳过
    元数据列（时间/状态/部门/归口/单号等）默认跳过，不做任何脱敏。
    """
    config = {
        "name_columns": [],
        "phone_columns": [],
        "id_card_columns": [],
        "address_columns": [],
        "text_columns": [],
    }

    # 元数据排除模式：列名含这些词的，默认是系统字段，不脱敏
    # 例外：如果同时含"内容/说明/原因/评价内容"等文本关键词，仍按文本列处理
    SKIP_PATTERNS = [
        "是否", "时间", "状态", "批次", "编号", "单号", "归口",
        "部门", "满意度", "工号", "渠道", "类型", "区域", "地市",
        "办结", "归档", "统计", "疑难", "送审", "所属",
    ]
    TEXT_EXCEPTION_KEYWORDS = ["内容", "说明", "原因", "评价内容", "意见", "情况", "结果"]

    # 姓名列精确匹配表（避免"是否联系诉求人"这类列被误判）
    NAME_EXACT = {
        "诉求人", "姓名", "联系人", "反映人", "当事人", "投诉人",
        "举报人", "申请人", "被投诉人", "参保人", "户主",
    }

    for h in headers:
        if not h:
            continue

        # 元数据排除：含跳过模式且不含文本例外关键词 → 不处理
        has_skip = any(p in h for p in SKIP_COLUMN_PATTERNS)
        has_text_exception = any(kw in h for kw in TEXT_EXCEPTION_KEYWORDS)
        if has_skip and not has_text_exception:
            continue

        # 姓名列：精确匹配或以"姓名"结尾
        if h in NAME_COLUMN_EXACT or h.endswith("姓名"):
            config["name_columns"].append(h)
        elif any(kw in h for kw in PHONE_COLUMN_KEYWORDS) or h == "电话":
            config["phone_columns"].append(h)
        elif any(kw in h for kw in ID_CARD_COLUMN_KEYWORDS):
            config["id_card_columns"].append(h)
        elif any(kw in h for kw in ADDRESS_COLUMN_KEYWORDS):
            config["address_columns"].append(h)
        elif any(kw in h for kw in TEXT_COLUMN_KEYWORDS):
            config["text_columns"].append(h)

    return config


def save_job_data(job_id: str, data: dict, output_dir: str):
    path = os.path.join(output_dir, f"{job_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_job_data(job_id: str, output_dir: str) -> dict:
    path = os.path.join(output_dir, f"{job_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
