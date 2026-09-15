"""统一数据模型层。

所有脱敏相关的数据结构集中在此，避免散落在 rules/engine 中。
engine.py 和 rules.py 从这里导入，不再各自定义 dataclass。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional


@dataclass
class MaskResult:
    """单条规则脱敏结果。"""
    masked_text: str
    hit_count: int
    hit_details: list


@dataclass
class DesensitizationRule:
    """脱敏规则定义。"""
    rule_id: str
    name: str
    pii_type: str
    description: str
    mask_func: Callable[[str], MaskResult]


@dataclass
class AuditEntry:
    """审计日志条目。"""
    row_index: int
    column_name: str
    rule_id: str
    rule_name: str
    pii_type: str
    hit_count: int
    hit_details: list
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DesensitizationResult:
    """批量脱敏结果汇总。"""
    total_rows: int
    total_hits: int
    hits_by_rule: dict
    audit_entries: list
    scan_passed: bool
    scan_warnings: list
    duration_ms: int


@dataclass
class ColumnDetectResult:
    """列自动检测结果。"""
    name_columns: list
    phone_columns: list
    id_card_columns: list
    address_columns: list
    text_columns: list
