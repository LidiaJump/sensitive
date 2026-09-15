# 发布用例中的姓名、地区与证件地区码已替换为虚构示例。
"""脱敏规则单元测试。

基于原有 test_fix.py / test_row41.py 的用例整理为 pytest 格式。
"""
import pytest
from src.core.rules import (
    mask_id_card, mask_phone, mask_address,
    mask_names_by_keyword, mask_salutation,
    mask_names_after_address,
    mask_structured_name, mask_structured_phone, mask_structured_id_card,
    mask_certificate,
    NameDictRule,
)


class TestMaskPhone:
    def test_basic_phone(self):
        result = mask_phone("联系电话13800138000")
        assert result.hit_count == 1
        assert "13800138000" not in result.masked_text
        assert "138****8000" in result.masked_text

    def test_phone_with_spaces(self):
        result = mask_phone("电话：139 1234 5678")
        assert result.hit_count == 1
        assert "139****5678" in result.masked_text

    def test_phone_with_dash(self):
        result = mask_phone("电话：138-1234-5678")
        assert result.hit_count == 1

    def test_no_false_positive(self):
        """订单号等长数字不应被误判为手机号。"""
        result = mask_phone("订单号12345678901已发货")
        assert result.hit_count == 0


class TestMaskIdCard:
    def test_basic_id_card(self):
        result = mask_id_card("身份证号999999199001011234")
        assert result.hit_count == 1
        assert "999999********1234" in result.masked_text

    def test_invalid_id_card_not_masked(self):
        """非法身份证号不应被脱敏。"""
        result = mask_id_card("编号999999999999999999")
        assert result.hit_count == 0

    def test_15_digit_old_id_card(self):
        """15位旧身份证号应脱敏（前6后3，中间6星）。"""
        result = mask_id_card("身份证号：999999900113602")
        assert result.hit_count == 1
        assert "999999******602" in result.masked_text

    def test_17_digit_space_separated_id_card(self):
        """17位空格分隔身份证（疑似缺校验位）应脱敏。"""
        result = mask_id_card("身份证号码：999999 1990 0113 602。")
        assert result.hit_count == 1
        assert "999999*******3602" in result.masked_text

    def test_id_card_with_fullwidth_dash(self):
        """全角横线分隔的身份证号应脱敏。"""
        result = mask_id_card("999999－19900113－602X")
        assert result.hit_count == 1


class TestMaskAddress:
    def test_building_number(self):
        result = mask_address("示例区示例景苑B区2栋2单元501室")
        assert result.hit_count > 0
        assert "*栋" in result.masked_text

    def test_road_number(self):
        result = mask_address("示例区示例路123号")
        assert result.hit_count > 0

    def test_public_district_not_masked(self):
        """公共行政区名不应被脱敏。"""
        result = mask_address("示例区")
        assert result.hit_count == 0
        assert result.masked_text == "示例区"

    def test_building_with_lou(self):
        """'X号楼'格式应脱敏（用户反馈 shot4）。"""
        result = mask_address("示例花园2号楼2单元803号02室")
        assert result.hit_count >= 1
        assert "*号楼" in result.masked_text
        assert "*单元" in result.masked_text

    def test_street_with_direction(self):
        """'路+方位词+号'格式应脱敏。"""
        result = mask_address("示例区示例路西277号")
        assert result.hit_count >= 1
        assert "***号" in result.masked_text

    def test_room_after_floor(self):
        """'X楼X房间'格式应脱敏。"""
        result = mask_address("示例二巷8号3楼502房间")
        assert result.hit_count >= 1
        assert "3楼502" not in result.masked_text

    def test_full_complex_address(self):
        """完整复杂地址（用户反馈的示例路示例花园）。"""
        result = mask_address("关于示例区示例路西277号示例花园2号楼2单元803号02室消费纠纷")
        assert result.hit_count >= 2
        assert "277" not in result.masked_text
        assert "803" not in result.masked_text
        assert "02室" not in result.masked_text

    def test_address_chinese_numerals(self):
        """中文数字门牌号（用户反馈：二栋二区一单元602号）应脱敏。"""
        result = mask_address("其是示例区东二路与东南一路交叉口示例国际小区二栋二区一单元602号的业主")
        assert result.hit_count >= 1
        assert "二栋二区一单元602号" not in result.masked_text
        assert "*栋" in result.masked_text
        # 公共道路名"东二路"不应被脱敏
        assert "东二路" in result.masked_text

    def test_address_arabic_mixed_qu(self):
        """阿拉伯数字+区组分（2栋2区1单元602号）应完整脱敏。"""
        result = mask_address("其是示例国际小区2栋2区1单元602号的业主")
        assert result.hit_count >= 1
        assert "2栋2区1单元602号" not in result.masked_text
        assert "*栋*区*单元***号" in result.masked_text


class TestMaskNamesByKeyword:
    @pytest.mark.parametrize("text,expected_name", [
        ("母亲姓名：张小华，身份证号", "张小华"),
        ("父亲姓名：张小平；市民未告知", "张小平"),
        ("女儿姓名：张小安；女儿身份证", "张小安"),
        ("被投诉人：张小红;身份证号", "张小红"),
        ("负责人：张小芳，联系电话", "张小芳"),
        ("厂长：张梅，联系方式", "张梅"),
        ("曾用名：张兰。已建议", "张兰"),
        ("父亲：张小竹，身份证号码", "张小竹"),
        ("参保人姓名：张小菊，参保人身份证", "张小菊"),
        ("爱人姓名：张小杰，身份证", "张小杰"),
    ])
    def test_name_detected(self, text, expected_name):
        result = mask_names_by_keyword(text)
        found = any(d["original"] == expected_name for d in result.hit_details)
        assert found, f"应识别出姓名 '{expected_name}'"

    @pytest.mark.parametrize("text,should_not_match", [
        ("母亲属于二级残疾人", "属于"),
        ("母亲已中风生活无法", "已中风"),
        ("父亲无工作，在家照顾", "无工作"),
        ("参保人信息已于2026年", "信息已"),
        ("参保人本人", "本人"),
        ("负责人表示已支付", "表示已"),
        ("已经提供身份证", "已经提"),
    ])
    def test_no_false_positive(self, text, should_not_match):
        result = mask_names_by_keyword(text)
        found = any(d["original"] == should_not_match for d in result.hit_details)
        assert not found, f"'{should_not_match}' 不应被误判为姓名"

    def test_p3_requires_separator(self):
        """p3规则：关系词后必须有分隔符，避免'负责人区城管局'误判。"""
        result = mask_names_by_keyword("负责人区城管局环卫科")
        # "区城管"不应被当姓名
        assert not any("区城管" in d["original"] for d in result.hit_details)

    @pytest.mark.parametrize("text", [
        "2025年12月为女儿缴纳了2026年的医保",
        "为儿子办理了入学手续",
        "给爱人报销了医疗费",
        "带父亲就医",
    ])
    def test_verb_after_relationship_not_name(self, text):
        """上下文感知：关系词后面紧跟动词时，不应把动词当姓名。"""
        result = mask_names_by_keyword(text)
        # "缴纳""办理""报销""就医"等动词不应被脱敏
        assert not any(d["original"] in ("缴纳", "办理", "报销", "就医")
                       for d in result.hit_details)

    def test_field_name_before_idcard_not_masked(self):
        """p4：'母亲姓名、身份证'中的'母亲姓名'是字段名不是人名，不应被脱敏。"""
        result = mask_names_by_keyword("母亲姓名、身份证：张小娜，999999197710127228。")
        # '母亲姓名'不应被脱敏
        assert not any("母亲姓名" == d["original"] for d in result.hit_details)
        # '张小娜'应被脱敏
        assert any("张小娜" == d["original"] for d in result.hit_details)


class TestMaskSalutation:
    def test_respected_surname(self):
        result = mask_salutation("尊敬的覃先生：您好！")
        assert result.hit_count == 1
        assert "覃*先生" in result.masked_text or "覃**" in result.masked_text

    def test_doctor_title(self):
        result = mask_salutation("随后联系了韦医生")
        assert result.hit_count >= 1

    def test_org_suffix_not_surname(self):
        """上下文感知：'局局长''处处长'是机构名+职位，不应被误判为姓+职位。"""
        result = mask_salutation("示例区移民局局长张勇说")
        assert "移民局局长" in result.masked_text
        assert "移民*局长" not in result.masked_text

    @pytest.mark.parametrize("text", [
        "区城管局科长",
        "镇派出所所长",
        "县教育局局长",
    ])
    def test_various_org_suffix_not_surname(self, text):
        result = mask_salutation(text)
        # 机构后缀字不应被当姓氏替换
        assert result.hit_count == 0


class TestStructuredMask:
    def test_structured_name(self):
        assert mask_structured_name("张三") == "张*"
        assert mask_structured_name("张三丰") == "张**"
        assert mask_structured_name("张") == "张"  # 单字不脱敏

    def test_structured_phone(self):
        assert mask_structured_phone("13800138000") == "138****8000"

    def test_structured_id_card(self):
        assert mask_structured_id_card("999999199001011234") == "999999********1234"


class TestNameDictRule:
    def test_basic_replacement(self):
        rule = NameDictRule(["张三", "李四"])
        result = rule.mask("张三和李四一起去了")
        assert result.hit_count == 2
        assert "张*" in result.masked_text
        assert "李*" in result.masked_text

    def test_single_char_ignored(self):
        """单字姓名不处理。"""
        rule = NameDictRule(["张"])
        result = rule.mask("张去了")
        assert result.hit_count == 0


class TestMaskCertificate:
    def test_land_contract_certificate(self):
        """土地承包经营权证号应脱敏，保留前4后4。"""
        result = mask_certificate("旧版土地承包经营权证（证号：999998213204100049）")
        assert result.hit_count == 1
        assert "9999**********0049" in result.masked_text

    def test_certificate_colon_preserved(self):
        """证件号脱敏时冒号等分隔符应保留。"""
        result = mask_certificate("证号：9999982132041000518")
        assert "证号：" in result.masked_text
        assert "9999982132041000518" not in result.masked_text

    def test_bank_card_number(self):
        """银行卡号应脱敏。"""
        result = mask_certificate("卡号：6222021234567890123")
        assert result.hit_count == 1
        assert "6222" in result.masked_text
        assert "0123" in result.masked_text

    def test_no_keyword_no_match(self):
        """无关键词前缀的长数字不应被证件号规则匹配（由身份证/手机号规则处理）。"""
        result = mask_certificate("编号是123456789012345678")
        assert result.hit_count == 0


class TestMaskNamesAfterAddress:
    """地址后名单姓名脱敏测试。"""

    def test_owner_list_all_masked(self):
        """业主/组织者名单中的姓名（含不在字典里的张霞/张小冬）应全部脱敏。"""
        result = mask_names_after_address(
            "自管小区主要组织者：2栋3号张小强、2栋4号张小云、2栋张霞（不清楚房号）、2栋张小冬（不清楚房号）")
        names = [d['original'] for d in result.hit_details]
        assert '张小强' in names and '张小云' in names
        assert '张霞' in names and '张小冬' in names

    def test_owner_not_masked(self):
        """地址后描述词'业主'不应被误判为姓名。"""
        result = mask_names_after_address("其是示例国际小区2栋2区1单元602号的业主")
        assert not any('业主' == d['original'] for d in result.hit_details)

    @pytest.mark.parametrize('text,word', [
        ("3号楼旁边有棵大树", '旁边'),
        ("2栋对面开了家店", '对面'),
        ("1单元楼上漏水", '楼上'),
        ("5栋楼下很吵", '楼下'),
    ])
    def test_description_word_not_masked(self, text, word):
        """地址后的方位/现象描述词不应被误判为姓名。"""
        result = mask_names_after_address(text)
        assert not any(word == d['original'] for d in result.hit_details)

    def test_normal_list_masked(self):
        """正常名单（5栋2单元302室王小明、6栋李大海）应命中。"""
        result = mask_names_after_address("5栋2单元302室王小明、6栋李大海")
        names = [d['original'] for d in result.hit_details]
        assert '王小明' in names and '李大海' in names
