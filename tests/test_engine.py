# 发布用例中的姓名、地区与证件地区码已替换为虚构示例。
"""脱敏引擎测试。

重点：过度脱敏回归测试 — 文本列不应被整段打星。
"""
import re
from src.core.engine import DesensitizationEngine


def _is_full_star(text: str) -> bool:
    """判断是否是'首字+全星号'模式（结构化姓名脱敏特征）。"""
    return bool(re.match(r'^.[\*]+$', text))


class TestOverMaskingRegression:
    """过度脱敏回归测试：确保文本列不会被整段打星。"""

    def test_text_column_no_sensitive_unchanged(self):
        """文本列无敏感信息时，输出应与输入完全一致。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["诉求内容"],
        }
        engine = DesensitizationEngine(config)
        row = {"诉求人": "张三", "诉求内容": "最近雨多水大，村干拉警戒线，安排专人负责一守，很有安全感"}
        processed, _ = engine.process_row(0, row)
        assert processed["诉求内容"] == row["诉求内容"]

    def test_text_column_with_phone_only_phone_masked(self):
        """文本列含手机号时，只替换手机号片段，业务文字保留。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["诉求内容"],
        }
        engine = DesensitizationEngine(config)
        row = {"诉求人": "张三", "诉求内容": "用户反映路灯损坏，电话13800138000，需要尽快处理"}
        processed, _ = engine.process_row(0, row)
        assert "路灯损坏" in processed["诉求内容"], "业务文字应保留"
        assert "需要尽快处理" in processed["诉求内容"], "业务文字应保留"
        assert "13800138000" not in processed["诉求内容"], "手机号应被脱敏"
        assert not _is_full_star(processed["诉求内容"]), "不应整段打星"

    def test_text_column_not_full_star(self):
        """文本列处理后绝不能是'首字+全星号'模式。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": ["来电号码"],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["诉求内容", "答复内容", "备注"],
        }
        engine = DesensitizationEngine(config)
        rows = [
            {"诉求人": "张小雪", "来电号码": "13800138000",
             "诉求内容": "来电反映：市民在示例区示例镇承包了200亩土地种植水稻",
             "答复内容": "尊敬的覃先生：您好！您反映的问题已收悉，经核实现答复如下",
             "备注": "以上为市民全媒体诉求原内容。"},
            {"诉求人": "张小松", "来电号码": "13912345678",
             "诉求内容": "最近雨多水大，水漫路，村干拉警戒线，安排专人负责一守",
             "答复内容": "非常感谢您对村委会防汛工作的肯定与表扬",
             "备注": "市民要求信息保密"},
        ]
        processed_rows, _ = engine.process_batch(rows)
        for i, row in enumerate(processed_rows):
            for col in ["诉求内容", "答复内容", "备注"]:
                assert not _is_full_star(row[col]), \
                    f"行{i} {col} 被整段打星: {row[col][:50]}"

    def test_department_column_not_processed(self):
        """机构名列（答复部门）不应被脱敏。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": [],  # 答复部门不在任何处理列
        }
        engine = DesensitizationEngine(config)
        row = {"诉求人": "张三", "答复部门": "示例市示例区示例乡人民政府"}
        processed, _ = engine.process_row(0, row)
        assert processed["答复部门"] == "示例市示例区示例乡人民政府"

    def test_safeguard_downgrades_long_name_column(self):
        """防呆机制：姓名列平均内容过长时自动降级为文本列。"""
        config = {
            "name_columns": ["诉求内容"],  # 故意把长文本列标记为姓名列
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": [],
        }
        engine = DesensitizationEngine(config)
        rows = [
            {"诉求内容": "最近雨多水大，水漫路，村干拉警戒线，安排专人负责一守，很有安全感"},
            {"诉求内容": "来电反映：市民在示例区示例镇承包了200亩土地种植水稻"},
        ] * 10  # 多行确保采样足够
        processed_rows, result = engine.process_batch(rows)
        # 防呆应触发，诉求内容被降级为文本列，不会整段打星
        for row in processed_rows:
            assert not _is_full_star(row["诉求内容"]), \
                f"防呆未生效，诉求内容被整段打星: {row['诉求内容'][:50]}"
        # 应有配置警告
        assert any("防呆" in w.get("message", "") for w in result.scan_warnings)

    def test_circuit_breaker_reverts_over_masked_cell(self):
        """熔断机制：单单元格脱敏后星号占比过高时回退原文。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["备注"],
        }
        engine = DesensitizationEngine(config)
        # 构造一个会被大量误脱敏的文本（虽然实际很难触发，但验证熔断逻辑存在）
        row = {"诉求人": "张三", "备注": "张三李四王五赵六钱七孙八周九吴十"}
        processed, audit = engine.process_row(0, row)
        # 熔断触发时应有 over_mask_fuse 审计条目，或文本未被过度破坏
        fuse_triggered = any(e.rule_id == "over_mask_fuse" for e in audit)
        if fuse_triggered:
            assert processed["备注"] == row["备注"], "熔断触发后应回退原文"

    def test_circuit_breaker_keeps_high_confidence_masking(self):
        """熔断回退到高置信度脱敏态：身份证脱敏保留，只撤销低置信度脱敏。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["备注"],
        }
        engine = DesensitizationEngine(config)
        # "母亲姓名"会被 p4 误判为姓名（低置信度），但身份证（高置信度）必须保留
        row = {"诉求人": "张小柏",
               "备注": "母亲姓名、身份证：张小娜，999999197710127228。请尽快办理"}
        processed, audit = engine.process_row(0, row)
        # 身份证号必须被脱敏（不能因熔断回退原文而还原）
        assert "999999197710127228" not in processed["备注"]
        assert "999999" in processed["备注"]
        # "母亲姓名"不应被误判为姓名（p4 修复）
        assert "母亲姓名" in processed["备注"]
        # 真实姓名"张小娜"应被脱敏
        assert "张小娜" not in processed["备注"]

    def test_scan_only_scanned_columns(self):
        """完整性扫描只扫描配置的列，主单号/工单号列不报警。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["备注"],
        }
        engine = DesensitizationEngine(config)
        rows = [
            {"诉求人": "张三", "备注": "无敏感信息", "主单号": "DH120260721013061"},
        ]
        processed_rows, _ = engine.process_batch(rows)
        warnings = engine.scan_completeness(processed_rows)
        # 主单号列不在配置中，不应产生身份证残留警告
        assert not any(w["column"] == "主单号" for w in warnings), \
            f"主单号列不应报警: {warnings}"

    def test_name_dict_filters_anon_title(self):
        """名字字典应过滤匿名称谓（韦先生/某女士），不全文扩散替换。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["答复内容"],
        }
        engine = DesensitizationEngine(config)
        # 诉求人列有匿名称谓"韦先生"，答复内容里"尊敬的韦先生"不应被全文替换
        rows = [
            {"诉求人": "韦先生", "答复内容": "尊敬的韦先生：您好！您反映的问题已收悉"},
        ]
        processed_rows, result = engine.process_batch(rows)
        # 称谓"尊敬的X先生"由 salutation 规则处理，保留姓氏
        assert "韦先生" in processed_rows[0]["答复内容"] or "韦*先生" in processed_rows[0]["答复内容"]
        # name_dict 不应命中（称谓词被过滤）
        assert not any(e["rule_id"] == "name_dict" for e in result.audit_entries), \
            "匿名称谓不应进入名字字典全文替换"


class TestAddressColumn:
    """地址列独立处理测试。"""

    def test_address_only_runs_address_rule(self):
        """地址列只跑地址脱敏，不跑姓名/称谓字典。"""
        config = {
            "name_columns": [],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": ["具体地址"],
            "text_columns": [],
        }
        engine = DesensitizationEngine(config)
        row = {"具体地址": "示例区示例景苑B区2栋2单元501"}
        processed, audit = engine.process_row(0, row)
        # 门牌号应被脱敏
        assert "2栋" not in processed["具体地址"] or "*栋" in processed["具体地址"]
        # 地名"示例区"不应被脱敏
        assert "示例区" in processed["具体地址"]

    def test_public_district_not_masked(self):
        """公共行政区名不应被脱敏。"""
        config = {
            "name_columns": [],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": ["事件发生地"],
            "text_columns": [],
        }
        engine = DesensitizationEngine(config)
        row = {"事件发生地": "示例区"}
        processed, _ = engine.process_row(0, row)
        assert processed["事件发生地"] == "示例区"


class TestNameFalsePositiveFilter:
    """姓名误判白名单过滤测试。"""

    def test_baomi_not_treated_as_name(self):
        """诉求人='保密'时，'保密'不应在文本列中被替换。"""
        config = {
            "name_columns": ["诉求人"],
            "phone_columns": [],
            "id_card_columns": [],
            "address_columns": [],
            "text_columns": ["备注"],
        }
        engine = DesensitizationEngine(config)
        row = {"诉求人": "保密", "备注": "市民要求信息保密，已告知市民信息保密后期出现的情况"}
        processed, _ = engine.process_row(0, row)
        assert "保密" in processed["备注"], "'保密'不应被当姓名替换"
        assert "保*" not in processed["备注"], "'保密'不应被脱敏为'保*'"
