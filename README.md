# 政务工单脱敏工具

面向政务工单 Excel 的本地脱敏工具，使用 Python、FastAPI 与 openpyxl 实现。通过浏览器完成文件导入、列映射、批量脱敏、前后对比、疑似残留复核和结果下载。

当前源码与本地安装包的内部版本为 **1.2.0**。仓库首次发布标签按要求使用 **v1.0.0**；该标签不代表安装包内部版本已更改。

## 项目背景与目标

工单的姓名、联系方式、证件号码和住址可能同时出现在独立字段与诉求、备注、答复等长文本中。人工逐项处理容易遗漏，也容易破坏业务描述。

本项目的目标是：批量遮盖可识别的个人信息，尽量保留问题描述与办理过程；让操作者能够调整列分类、检查规则命中和疑似残留，并导出供后续复核的表格。

项目按单机本地工具设计，默认监听 `127.0.0.1`，前端请求本机 API，核心规则不调用外部模型服务。脱敏依赖规则，不能保证完全匿名化，结果仍需人工审核。

## 项目特性

- 自动识别姓名、电话、身份证、地址和文本列；时间、状态、部门、单号等元数据默认跳过。
- 支持姓名字典、关系词/职位词姓名识别、称谓、手机号、身份证、车牌、证件号、社保编号及门牌号掩码。
- 对同一行文本列执行姓名二次扫描，处理跨列出现的姓名。
- 姓名列平均文本过长时自动降级为文本列；过度脱敏时回退低置信度处理，保留此前的高置信度号码掩码。
- 提供逐项审计、原文与结果对比、疑似号码残留扫描和人工选择修复。
- 保存列映射模板；任务文件按保留时间在后续上传时清理。
- 支持 Windows 源码启动、PyInstaller 打包与 Inno Setup 安装包。

## 目录结构

```text
.
├── run.py                    # 启动、端口探测、日志、浏览器入口
├── config.py                 # 公共默认配置与环境变量
├── requirements.txt          # 运行及测试依赖
├── src/
│   ├── app.py                # FastAPI 路由与任务管理
│   ├── models.py             # 结果、规则与审计对象
│   ├── excel_handler.py      # Excel 读写、列分类、任务持久化
│   └── core/
│       ├── rules.py          # 文本与结构化字段掩码规则
│       ├── engine.py         # 行/批处理、二次扫描与完整性检查
│       └── cleaner.py        # 过期上传及输出文件清理
├── static/index.html         # 浏览器操作页面
├── tests/                    # 已替换为虚构样例的单元/回归测试
├── GovDataProcessor.spec     # PyInstaller 构建配置
├── installer.iss             # Inno Setup 安装脚本
├── build_exe.bat             # Windows 打包入口
└── 启动.bat                  # Windows 快捷启动
```

仓库根目录对应本地项目中的 `代码库/gov-data-processor`。原始工单、输出表格、任务 JSON、历史调试脚本、备份页面和已有二进制均未纳入源码。

## 环境准备与运行方式

需要 Python **3.9 或更高版本**。建议使用独立虚拟环境；下列命令在仓库根目录执行，示例为 Windows PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

查看控制台中的实际端口，默认访问 `http://127.0.0.1:8080`。端口被占用时启动器最多尝试从默认端口起的 10 个端口。直接执行 `run.py` 的源码模式需手动打开浏览器；打包模式会自动打开。也可双击 `启动.bat`，但它的浏览器地址固定为 8080，如服务改用其他端口需手动调整地址。

启动后访问 `/docs` 可查看由 FastAPI 生成的交互式 API 文档。运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

### 配置与数据目录

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `DESENSITIZE_HOST` | `127.0.0.1` | 监听地址，保持本机访问 |
| `DESENSITIZE_PORT` | `8080` | 端口探测起点 |
| `FILE_EXPIRE_SECONDS` | `86400` | 上传/输出文件保留秒数 |
| `APPDATA` | Windows 用户配置目录 | 数据根目录的父目录 |

开发模式与打包模式均将用户数据写入 `%APPDATA%\GovDataProcessor` 下的 `uploads/`、`output/`、`templates/`，日志为 `app.log`。没有独立定时清理进程；过期清理由后续上传触发，模板不在该清理范围。`config.py` 是可公开的默认配置，不含访问密钥；本地私有配置和 `.env` 文件不得提交。

## 实现方案

### 处理流程

1. **上传与解析**：接收 Excel，读取活动工作表，以第一行为表头，将单元格转换为文本。
2. **列分类**：依据表头关键词和排除规则产生默认列映射，用户可在页面复核和调整。
3. **批量处理**：独立字段使用结构化掩码，地址列与文本列采用不同规则组合。
4. **保真保护**：进行姓名列防呆判断、过度掩码熔断及同一行跨文本列的姓名二次扫描。
5. **审计与复核**：汇总命中数量及耗时，在参与处理的列中扫描疑似身份证、手机号残留。
6. **导出**：生成新的 `.xlsx`，下载文件名包含“脱敏后”。

### 核心 API 简介

| 方法与路径 | 参数/说明 |
| --- | --- |
| `POST /api/upload` | multipart 表单 `file`；返回 `job_id`、表头、样例行及默认列映射 |
| `POST /api/desensitize/{job_id}` | 表单传入各类 `*_columns`（逗号分隔）及 `enable_*` 开关，执行批处理 |
| `GET /api/preview/{job_id}?limit=10` | 返回原始行、结果行及发生变化的列 |
| `GET /api/audit/{job_id}` | 支持 `rule_id`、`limit`；返回命中明细、汇总及扫描警告 |
| `POST /api/fix/{job_id}` | JSON `items` 指定行、列、规则类型，对疑似项执行定向修复 |
| `GET /api/download/{job_id}` | 导出当前处理结果为 `.xlsx` |
| `GET /api/jobs` | 列出当前进程内的任务 |
| `GET /api/templates` | 列出已保存的列映射模板 |
| `POST /api/templates` | 表单 `name` 与各类 `*_columns` 保存模板 |
| `DELETE /api/templates/{template_id}` | 删除指定模板 |
| `POST /api/shutdown` | 退出本地服务 |

`/api/fix` 的 `row` 为从 0 开始的数据行索引（不含表头）。请求示例：

```json
{"items": [{"row": 0, "column": "备注", "type": "phone"}]}
```

支持修复类型为 `id_card`、`phone`、`certificate`、`social_security`、`address`。请在页面确认疑似项后使用。

### 核心对象与注解说明

| 对象 | 定义与用途 |
| --- | --- |
| `MaskResult` | 一条规则的输出文本、命中数量、命中明细 |
| `DesensitizationRule` | 规则标识、名称、信息类型、说明和 `mask_func` 函数 |
| `AuditEntry` | 数据行、列、规则、命中细节和生成时间 |
| `DesensitizationResult` | 批量处理行数、总命中、规则汇总、审计、扫描警告与耗时 |
| `ColumnDetectResult` | 五类列映射的数据结构；当前 Excel/API 流程实际使用字典 |
| `DesensitizationEngine` | 根据列配置执行 `process_row`、`process_batch`、`scan_completeness` |
| `NameDictRule` | 用已知姓名字典匹配并掩码文本中的姓名 |

数据结构使用 Python `@dataclass` 自动生成初始化等方法，`field(default_factory=...)` 为审计对象生成时间。`str`、`list`、`dict`、`Optional[str]` 等类型注解表达参数和返回值意图；普通 Python 类型注解本身不执行所有运行时校验。`@app.get`、`@app.post` 等装饰器将函数注册为 HTTP 路由；`File(...)`、`Form(...)` 定义上传/表单字段，FastAPI 据此进行请求解析并生成接口文档。

## 脱敏演示与效果

以下是为文档构造的虚构样例，证件地区码 `999999` 为测试占位，不来自原始工单：

| 字段 | 处理前 | 处理后 |
| --- | --- | --- |
| 姓名 | 张三 | 张* |
| 联系电话 | 13800138000 | 138****8000 |
| 身份证 | 999999199001011234 | 999999********1234 |
| 具体地址 | 示例路123号 | 示例路***号 |
| 诉求内容 | 路灯损坏，电话13800138000，请安排维修。 | 路灯损坏，电话138****8000，请安排维修。 |

姓名保留首字；手机号保留前三后四位；18 位身份证保留前六后四位，15 位保留前六后三位，17 位保留前六后四位；门牌号使用星号替换，公共地名通常保留。实际输出受列映射、开关、上下文及熔断保护影响。

也可直接调用规则进行最小演示：

```python
from src.core.rules import mask_phone

result = mask_phone("路灯损坏，电话13800138000，请安排维修。")
print(result.masked_text)
# 路灯损坏，电话138****8000，请安排维修。
```

### 页面操作

1. 上传 `.xlsx` 文件。
2. 逐列检查分类，尤其是诉求、备注、答复等长文本列。
3. 按需要选择规则或套用列映射模板，执行脱敏。
4. 查看前后对比、审计详情和疑似残留；必要时选中疑似项修复。
5. 下载后继续人工复核，再用于预定业务场景。

## 当前实现边界

- 上传接口虽接受 `.xls` 扩展名，但底层只使用 openpyxl；旧二进制 `.xls` 应先转换为 `.xlsx`。
- 只读取活动工作表；重新生成结果表，不保留多工作表、原始公式、格式、图表或宏。重复表头可能造成同名字段覆盖，应先整理表头。
- 任务 JSON、预览与审计明细可含原始个人信息；“脱敏结果”和“审计记录”不能视为同等可公开内容。仓库只发布源码与虚构样例。
- 疑似残留扫描只覆盖已配置列中的部分身份证/手机号模式。`scan_passed=true` 不代表所有个人信息均已消除。
- 过度脱敏保护会回退部分姓名/地址处理，相关输出仍应人工复核；部分附加规则未提供独立开关。
- 接口未实现用户认证或权限隔离，面向可信本机使用；不要直接将监听地址改为公网服务。
- 任务列表保存在内存中；虽然任务文件落盘，当前启动流程不会自动恢复历史任务。
- 安装脚本的卸载动作会删除用户数据目录；卸载前应自行保存仍需保留的数据。

## 打包与发布

源码环境安装 PyInstaller 后，可用仓库中的配置文件构建：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller GovDataProcessor.spec
```

再用 Inno Setup 编译 `installer.iss`，产物位于 `installer_output/`。`build_exe.bat` 是原项目的便捷脚本，会先清理旧的 `build/`、`dist/` 和 spec 文件，使用前应确认这些目录仅存放可重建产物。

安装包请从本仓库 [GitHub Releases](https://github.com/LidiaJump/sensitive/releases) 获取。`.exe`、其他构建产物与压缩包不进入 Git 历史。首次 Release 使用标签 `v1.0.0`、标题“工单脱敏工具 v1.0.0”，本地现有资产文件名仍保留内部版本 `v1.2.0`。

## 提交内容约束

`.gitignore` 排除 `.env`、`node_modules/`、`*.tmp`、`*.log`、安装包、构建目录、缓存、原始/输出表格、任务数据、证书密钥及机器私有配置。忽略规则不会自动清除已跟踪文件；每次提交前仍需检查暂存文件列表。测试中的姓名、地区及证件地区码已经替换，生产程序的执行逻辑保持原样。
