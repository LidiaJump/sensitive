# 发布用例中的姓名、地区与证件地区码已替换为虚构示例。
"""pytest 共享配置：确保项目根目录在 sys.path 中。"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
