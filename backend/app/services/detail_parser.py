"""经营明细文件解析与逐行校验。

约定的明细文件为带表头的 CSV（UTF-8，逗号分隔），表头必须包含：
业务编号、所属周期、金额、币种。解析时保留每一行的原始文本与原始行号，
校验失败的行不丢弃、不当零值，全部带定位信息返回，由 service 层决定如何归档。

只用标准库实现，避免为文件解析引入额外依赖。
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any

REQUIRED_HEADERS = ["业务编号", "所属周期", "金额", "币种"]
# 允许的表头别名，降低来源方表头差异带来的手工成本
HEADER_ALIASES = {
    "业务编号": ["业务编号", "业务id", "业务ID", "业务编码", "编号"],
    "所属周期": ["所属周期", "业务周期", "周期", "账期"],
    "金额": ["金额", "业务金额", "发生额"],
    "币种": ["币种", "货币", "币别"],
}


class FileParseError(ValueError):
    """文件本身无法解析（空文件、表头缺失等），区别于行级数据错误。"""


def _normalize_header(name: str) -> str:
    return (name or "").strip().lstrip("﻿")


def _map_headers(fieldnames: list[str]) -> dict[str, int]:
    """把来源表头映射到标准四列，返回 标准列 -> 列下标。"""
    normalized = [_normalize_header(name) for name in fieldnames]
    mapping: dict[str, int] = {}
    for standard, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[standard] = normalized.index(alias)
                break
    missing = [name for name in REQUIRED_HEADERS if name not in mapping]
    if missing:
        raise FileParseError(f"明细文件缺少必需表头：{'、'.join(missing)}")
    return mapping


def parse_amount(raw: str) -> Decimal:
    """严格金额校验：空值、非数字、NaN/Infinity 都算无效，绝不按零处理。"""
    text = (raw or "").strip().replace(",", "")
    if not text:
        raise ValueError("金额为空")
    value = Decimal(text)
    if not value.is_finite():
        raise ValueError("金额不是有限数值")
    return value


def parse_detail_file(content: str) -> dict[str, Any]:
    """解析明细文件内容，返回结构化的有效行与无效行。

    - 有效行：含业务编号、所属周期、币种，且金额可解析为有限十进制数；
    - 无效行：保留原始行号、原始文本与错误原因，可定位回原始文件；
    - 行号从 1 开始且按物理行计数（表头是第 1 行，第一条数据是第 2 行）。
    """
    if content is None or not content.strip():
        raise FileParseError("明细文件为空，没有可导入的内容")

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        raise FileParseError("明细文件为空，没有可导入的内容")

    header_row = rows[0]
    mapping = _map_headers(header_row)

    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    # 物理行号：表头占第 1 行
    for line_no, raw_cells in enumerate(rows[1:], start=2):
        original_line = ",".join(raw_cells)
        # 跳过完全空白的物理行，但行号仍然连续，不影响定位
        if not any(cell.strip() for cell in raw_cells):
            continue

        def cell(column: str) -> str:
            index = mapping[column]
            return raw_cells[index].strip() if index < len(raw_cells) else ""

        biz_no = cell("业务编号")
        period = cell("所属周期")
        currency = cell("币种")
        amount_raw = cell("金额")

        missing: list[str] = []
        if not biz_no:
            missing.append("业务编号")
        if not period:
            missing.append("所属周期")
        if not currency:
            missing.append("币种")

        amount_value: Decimal | None = None
        amount_error = ""
        try:
            amount_value = parse_amount(amount_raw)
        except (ValueError, InvalidOperation, ArithmeticError):
            amount_error = f"无效金额「{amount_raw}」：不是合法的十进制数值"

        if missing or amount_error:
            reasons = []
            if missing:
                reasons.append(f"缺少必填字段：{'、'.join(missing)}")
            if amount_error:
                reasons.append(amount_error)
            invalid_rows.append({
                "line_no": line_no,
                "original_line": original_line,
                "raw_cells": list(raw_cells),
                "reasons": reasons,
            })
            continue

        valid_rows.append({
            "line_no": line_no,
            "original_line": original_line,
            "biz_no": biz_no,
            "period": period,
            "currency": currency.upper(),
            "amount": amount_value,
        })

    return {
        "header": [_normalize_header(name) for name in header_row],
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "data_row_count": len(rows) - 1,
    }
