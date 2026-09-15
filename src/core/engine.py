import re
import json
from datetime import datetime
from dataclasses import asdict
from typing import Optional

from config import (
    NAME_FALSE_POSITIVES,
    NAME_COL_MAX_AVG_LEN,
    MASK_RATIO_FUSE_THRESHOLD,
    ANON_NAME_SUFFIXES,
    ANON_NAME_MARKERS,
)

from ..models import AuditEntry, DesensitizationResult

from .rules import (
    mask_id_card,
    mask_phone,
    mask_plate,
    mask_certificate,
    mask_social_security,
    mask_names_by_keyword,
    mask_salutation,
    mask_address,
    mask_names_after_address,
    mask_structured_name,
    mask_structured_phone,
    mask_structured_id_card,
    NameDictRule,
    ALL_RULES,
)


class DesensitizationEngine:
    def __init__(self, config: dict):
        self.name_columns = config.get("name_columns", [])
        self.phone_columns = config.get("phone_columns", [])
        self.id_card_columns = config.get("id_card_columns", [])
        self.address_columns = config.get("address_columns", [])
        self.text_columns = config.get("text_columns", [])
        self.enable_rules = config.get("enable_rules", {
            "id_card": True,
            "phone": True,
            "name": True,
            "salutation": True,
            "address": True,
        })
        self._config_warnings = []

    def process_row(self, row_index: int, row_data: dict) -> tuple:
        audit_entries = []
        processed = dict(row_data)

        for col in self.name_columns:
            if col in processed and processed[col]:
                original = str(processed[col])
                masked = mask_structured_name(original)
                if masked != original:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="structured_name",
                        rule_name="姓名字段脱敏",
                        pii_type="name",
                        hit_count=1,
                        hit_details=[{"original": original, "masked": masked}],
                    ))
                processed[col] = masked

        for col in self.phone_columns:
            if col in processed and processed[col]:
                original = str(processed[col])
                masked = mask_structured_phone(original)
                if masked != original:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="structured_phone",
                        rule_name="电话字段脱敏",
                        pii_type="phone",
                        hit_count=1,
                        hit_details=[{"original": original, "masked": masked}],
                    ))
                processed[col] = masked

        for col in self.id_card_columns:
            if col in processed and processed[col]:
                original = str(processed[col])
                masked = mask_structured_id_card(original)
                if masked != original:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="structured_id_card",
                        rule_name="身份证字段脱敏",
                        pii_type="id_card",
                        hit_count=1,
                        hit_details=[{"original": original, "masked": masked}],
                    ))
                processed[col] = masked

        # 地址列：只跑地址脱敏（门牌号）+ 高置信度身份证/手机号（地址列也可能混入），
        # 不跑姓名/称谓字典，避免地名被误脱敏
        for col in self.address_columns:
            if col in processed and processed[col]:
                original = str(processed[col])
                text = original
                if self.enable_rules.get("id_card", True):
                    result = mask_id_card(text)
                    if result.hit_count > 0:
                        audit_entries.append(AuditEntry(
                            row_index=row_index,
                            column_name=col,
                            rule_id="id_card",
                            rule_name="身份证号脱敏",
                            pii_type="id_card",
                            hit_count=result.hit_count,
                            hit_details=result.hit_details,
                        ))
                        text = result.masked_text
                if self.enable_rules.get("phone", True):
                    result = mask_phone(text)
                    if result.hit_count > 0:
                        audit_entries.append(AuditEntry(
                            row_index=row_index,
                            column_name=col,
                            rule_id="phone",
                            rule_name="手机号脱敏",
                            pii_type="phone",
                            hit_count=result.hit_count,
                            hit_details=result.hit_details,
                        ))
                        text = result.masked_text
                # 车牌号脱敏
                result = mask_plate(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="plate",
                        rule_name="车牌号脱敏",
                        pii_type="plate",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    text = result.masked_text
                if self.enable_rules.get("address", True):
                    result = mask_address(text)
                    if result.hit_count > 0:
                        audit_entries.append(AuditEntry(
                            row_index=row_index,
                            column_name=col,
                            rule_id="address",
                            rule_name="地址脱敏",
                            pii_type="address",
                            hit_count=result.hit_count,
                            hit_details=result.hit_details,
                        ))
                    text = result.masked_text
                processed[col] = text

        names = []
        for col in self.name_columns:
            if col in row_data and row_data[col]:
                val = str(row_data[col]).strip()
                # 过滤非人名值（保密/先生/女士等）、匿名称谓（韦先生/某女士等）和过短值
                if (
                    val and len(val) >= 2
                    and val not in NAME_FALSE_POSITIVES
                    and not any(m in val for m in ANON_NAME_MARKERS)
                ):
                    names.append(val)
        name_rule = NameDictRule(names) if self.enable_rules.get("name", True) else None

        for col in self.text_columns:
            if col not in processed or not processed[col]:
                continue
            text = str(processed[col])

            if self.enable_rules.get("id_card", True):
                result = mask_id_card(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="id_card",
                        rule_name="身份证号脱敏",
                        pii_type="id_card",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    text = result.masked_text

            if self.enable_rules.get("phone", True):
                result = mask_phone(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="phone",
                        rule_name="手机号脱敏",
                        pii_type="phone",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    text = result.masked_text

            # 车牌号脱敏
            result = mask_plate(text)
            if result.hit_count > 0:
                audit_entries.append(AuditEntry(
                    row_index=row_index,
                    column_name=col,
                    rule_id="plate",
                    rule_name="车牌号脱敏",
                    pii_type="plate",
                    hit_count=result.hit_count,
                    hit_details=result.hit_details,
                ))
                text = result.masked_text

            # 其他证件号：土地承包经营权证、不动产权证、银行卡等
            result = mask_certificate(text)
            if result.hit_count > 0:
                audit_entries.append(AuditEntry(
                    row_index=row_index,
                    column_name=col,
                    rule_id="certificate",
                    rule_name="其他证件号脱敏",
                    pii_type="certificate",
                    hit_count=result.hit_count,
                    hit_details=result.hit_details,
                ))
                text = result.masked_text

            result = mask_social_security(text)
            if result.hit_count > 0:
                audit_entries.append(AuditEntry(
                    row_index=row_index,
                    column_name=col,
                    rule_id="social_security",
                    rule_name="社保编号脱敏",
                    pii_type="social_security",
                    hit_count=result.hit_count,
                    hit_details=result.hit_details,
                ))
                text = result.masked_text

            # 高置信度脱敏中间态：身份证/手机号/证件号/社保号已脱敏，
            # 姓名/称谓/地址等低置信度规则尚未执行。
            # 熔断时回退到这里（而非原文），避免连累已确认的脱敏结果。
            text_safe = text

            if name_rule:
                result = name_rule.mask(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="name_dict",
                        rule_name="姓名字典查找脱敏",
                        pii_type="name",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    text = result.masked_text

            result = mask_names_by_keyword(text)
            if result.hit_count > 0:
                audit_entries.append(AuditEntry(
                    row_index=row_index,
                    column_name=col,
                    rule_id="name_keyword",
                    rule_name="关键词姓名脱敏",
                    pii_type="name",
                    hit_count=result.hit_count,
                    hit_details=result.hit_details,
                ))
                text = result.masked_text

            if self.enable_rules.get("salutation", True):
                result = mask_salutation(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="salutation",
                        rule_name="称谓脱敏",
                        pii_type="salutation",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    text = result.masked_text

            if self.enable_rules.get("address", True):
                result = mask_address(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="address",
                        rule_name="地址脱敏",
                        pii_type="address",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    text = result.masked_text

            # 地址后名单姓名：识别"2栋3号张小强、2栋张霞"中的姓名
            if self.enable_rules.get("address", True):
                result = mask_names_after_address(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="addr_name",
                        rule_name="地址后名单姓名脱敏",
                        pii_type="name",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    text = result.masked_text

            # 熔断保护：如果脱敏后星号占比过高，说明低置信度规则大概率误判，
            # 回退到"高置信度脱敏中间态"（保留身份证/手机号等确认脱敏）
            if text and text_safe:
                masked_ratio = text.count('*') / max(len(text), 1)
                if masked_ratio > MASK_RATIO_FUSE_THRESHOLD:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="over_mask_fuse",
                        rule_name="过度脱敏熔断",
                        pii_type="system",
                        hit_count=1,
                        hit_details=[{"warning": f"脱敏比例{masked_ratio:.0%}，已回退低置信度脱敏"}],
                    ))
                    text = text_safe

            processed[col] = text

        found_names = set()
        for entry in audit_entries:
            if entry.rule_id in ("name_keyword", "name_dict", "name_second_pass"):
                for detail in entry.hit_details:
                    original = detail.get("original", "")
                    if (
                        original and len(original) >= 2 and '*' not in original
                        and original not in NAME_FALSE_POSITIVES
                        and not any(m in original for m in ANON_NAME_MARKERS)
                    ):
                        found_names.add(original)

        if found_names:
            second_name_rule = NameDictRule(list(found_names))
            for col in self.text_columns:
                if col not in processed or not processed[col]:
                    continue
                text = str(processed[col])
                result = second_name_rule.mask(text)
                if result.hit_count > 0:
                    audit_entries.append(AuditEntry(
                        row_index=row_index,
                        column_name=col,
                        rule_id="name_second_pass",
                        rule_name="姓名二次扫描脱敏",
                        pii_type="name",
                        hit_count=result.hit_count,
                        hit_details=result.hit_details,
                    ))
                    processed[col] = result.masked_text

        return processed, audit_entries

    def _safeguard_name_columns(self, rows: list):
        """防呆：姓名列平均内容过长 → 判定分类错误，降级为文本列。

        真实姓名通常 2-4 字。如果某列被标记为姓名列，但平均长度 > 15，
        大概率是前端误选（如把诉求内容选成了姓名列），自动降级避免整段打星。
        """
        downgraded = []
        for col in list(self.name_columns):
            lengths = []
            for row in rows[:100]:  # 采样前100行
                val = str(row.get(col, "")).strip()
                if val:
                    lengths.append(len(val))
            if not lengths:
                continue
            avg_len = sum(lengths) / len(lengths)
            if avg_len > NAME_COL_MAX_AVG_LEN:
                self.name_columns.remove(col)
                if col not in self.text_columns:
                    self.text_columns.append(col)
                downgraded.append(col)
        if downgraded:
            self._config_warnings.append(
                f"防呆触发：列 {downgraded} 平均内容过长，已从姓名列降级为文本列"
            )

    def process_batch(self, rows: list) -> tuple:
        start_time = datetime.now()

        # 防呆校验：姓名列平均内容过长 → 判定分类错误，降级为文本列
        self._safeguard_name_columns(rows)

        all_audit = []
        processed_rows = []
        hits_by_rule = {}
        total_hits = 0

        for i, row in enumerate(rows):
            processed, audit_entries = self.process_row(i, row)
            processed_rows.append(processed)
            for entry in audit_entries:
                all_audit.append(entry)
                total_hits += entry.hit_count
                if entry.rule_id not in hits_by_rule:
                    hits_by_rule[entry.rule_id] = 0
                hits_by_rule[entry.rule_id] += entry.hit_count

        warnings = self.scan_completeness(processed_rows)
        # 合并防呆配置警告
        for w in self._config_warnings:
            warnings.append({"type": "config", "message": w})

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        result = DesensitizationResult(
            total_rows=len(rows),
            total_hits=total_hits,
            hits_by_rule=hits_by_rule,
            audit_entries=[asdict(e) for e in all_audit],
            scan_passed=len(warnings) == 0,
            scan_warnings=warnings,
            duration_ms=duration,
        )

        return processed_rows, result

    def scan_completeness(self, rows: list) -> list:
        warnings = []
        # 只扫描参与脱敏的列（跳过未配置列，避免工单号/编号等被误报）
        scanned_cols = set()
        for group in (self.name_columns, self.phone_columns,
                      self.id_card_columns, self.address_columns,
                      self.text_columns):
            scanned_cols.update(group)
        # 身份证：支持15/17/18位，含空格分隔（与 mask_id_card 一致）
        id_card_pattern = re.compile(
            r'(?<!\d)([1-9](?:\d|\s){13,27}[\dXx])(?!\d)'
        )
        # 手机号：前后必须有非数字边界，避免身份证内部子串误报
        phone_pattern = re.compile(r'(?<!\d)(1[3-9]\d{9})(?!\d)')
        # 编号类上下文：这些词后面的数字可能是工单号/编号，不是手机号/身份证
        num_context_pattern = re.compile(
            r'(?:编号|单号|证号|证码|回执|工单号|订单|随手拍|流水号|业务号|受理号|号码)'
        )

        def _is_id_card(clean: str) -> bool:
            if len(clean) not in (15, 17, 18):
                return False
            if len(clean) == 18:
                year = clean[6:10]
                month = clean[10:12]
                day = clean[12:14]
            elif len(clean) == 15:
                year = '19' + clean[6:8]
                month = clean[8:10]
                day = clean[10:12]
            else:  # 17
                year = clean[6:10]
                month = clean[10:12]
                day = clean[12:14]
            if not (year.startswith('19') or year.startswith('20')):
                return False
            try:
                return (1 <= int(month) <= 12) and (1 <= int(day) <= 31)
            except ValueError:
                return False

        for i, row in enumerate(rows):
            for col, val in row.items():
                if not val:
                    continue
                if col not in scanned_cols:
                    continue
                text = str(val)
                for m in id_card_pattern.finditer(text):
                    raw = m.group(1)
                    clean = re.sub(r'[\s\t\-－]', '', raw)
                    if not _is_id_card(clean):
                        continue
                    ctx_before = text[max(0, m.start()-15):m.start()]
                    if num_context_pattern.search(ctx_before):
                        continue
                    warnings.append({
                        "row": i,
                        "row_no": i + 1,
                        "column": col,
                        "type": "id_card",
                        "fragment": clean,
                        "context": text[max(0, m.start()-20):m.end()+20],
                        "message": f"第{i+1}行 '{col}' 列可能残留身份证号",
                    })
                for m in phone_pattern.finditer(text):
                    ctx_before = text[max(0, m.start()-15):m.start()]
                    if num_context_pattern.search(ctx_before):
                        continue
                    warnings.append({
                        "row": i,
                        "row_no": i + 1,
                        "column": col,
                        "type": "phone",
                        "fragment": m.group(1),
                        "context": text[max(0, m.start()-20):m.end()+20],
                        "message": f"第{i+1}行 '{col}' 列可能残留手机号",
                    })
        return warnings
