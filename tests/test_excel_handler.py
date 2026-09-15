# 发布用例中的姓名、地区与证件地区码已替换为虚构示例。
"""列自动检测测试。

重点验证：机构名/时间/状态列不被误归入文本列，地址列独立分类。
"""
from src.excel_handler import auto_detect_columns


class TestAutoDetectColumns:
    """政务工单典型列名的分类测试。"""

    def test_name_column_exact_match(self):
        """诉求人等精确匹配姓名列。"""
        headers = ["诉求人", "姓名", "联系人", "反映人"]
        config = auto_detect_columns(headers)
        assert set(config["name_columns"]) == {"诉求人", "姓名", "联系人", "反映人"}

    def test_yes_no_column_not_name(self):
        """'部门反馈是否联系诉求人' 含'诉求人'但是否字段，不应归为姓名列。"""
        headers = ["部门反馈是否联系诉求人"]
        config = auto_detect_columns(headers)
        assert "部门反馈是否联系诉求人" not in config["name_columns"]
        assert "部门反馈是否联系诉求人" not in config["text_columns"]

    def test_department_not_text(self):
        """答复部门/主办部门/经办部门是机构名，不应归入文本列。"""
        headers = ["答复部门", "主办部门", "经办部门"]
        config = auto_detect_columns(headers)
        for col in ["答复部门", "主办部门", "经办部门"]:
            assert col not in config["text_columns"], f"{col} 不应是文本列"
            assert col not in config["name_columns"], f"{col} 不应是姓名列"

    def test_address_column_independent(self):
        """具体地址/事件发生地应归为地址列，不是文本列。"""
        headers = ["具体地址", "事件发生地"]
        config = auto_detect_columns(headers)
        assert "具体地址" in config["address_columns"]
        assert "事件发生地" in config["address_columns"]
        assert "具体地址" not in config["text_columns"]

    def test_text_columns_detected(self):
        """诉求内容/答复内容/备注等应归为文本列。"""
        headers = ["诉求内容", "答复内容", "备注", "经办部门答复内容", "标题/目的"]
        config = auto_detect_columns(headers)
        for col in headers:
            assert col in config["text_columns"], f"{col} 应是文本列"

    def test_time_columns_skipped(self):
        """各种时间列应跳过不处理。"""
        headers = ["诉求时间", "答复时间", "经办部门答复时间", "归档时间", "办结截止时间"]
        config = auto_detect_columns(headers)
        all_cols = (config["name_columns"] + config["phone_columns"] +
                    config["id_card_columns"] + config["address_columns"] +
                    config["text_columns"])
        for col in headers:
            assert col not in all_cols, f"{col} 应被跳过"

    def test_metadata_columns_skipped(self):
        """归口/状态/批次/工号等元数据列应跳过。"""
        headers = ["一级归口", "二级归口", "工单状态", "处理批次", "话务员工号", "来源渠道"]
        config = auto_detect_columns(headers)
        all_cols = (config["name_columns"] + config["phone_columns"] +
                    config["id_card_columns"] + config["address_columns"] +
                    config["text_columns"])
        for col in headers:
            assert col not in all_cols, f"{col} 应被跳过"

    def test_full_workorder_headers(self):
        """完整工单表头的集成测试：关键列分类正确。"""
        headers = [
            "区域", "服务单号", "诉求类型", "诉求时间", "诉求人", "来电号码",
            "话务员工号", "处理人", "工单状态", "标题/目的", "诉求内容", "备注",
            "一级归口", "具体地址", "事件发生地", "答复部门", "主办部门",
            "答复内容", "经办部门", "经办部门答复内容", "经办部门答复时间",
            "答复时间", "是否按时办结", "部门反馈是否联系诉求人",
            "未解决原因", "其他原因说明", "评价内容", "处理批次",
        ]
        config = auto_detect_columns(headers)

        assert config["name_columns"] == ["诉求人"]
        assert config["phone_columns"] == ["来电号码"]
        assert set(config["address_columns"]) == {"具体地址", "事件发生地"}
        assert set(config["text_columns"]) == {
            "标题/目的", "诉求内容", "备注", "答复内容",
            "经办部门答复内容", "未解决原因", "其他原因说明", "评价内容",
        }
        # 机构名/时间/状态列不应被处理
        for col in ["答复部门", "主办部门", "经办部门", "经办部门答复时间",
                    "答复时间", "部门反馈是否联系诉求人", "处理批次", "工单状态"]:
            assert col not in config["text_columns"]
            assert col not in config["name_columns"]
