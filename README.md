# RoomCrew · 一间事务所

一间属于你的事务所，一群陪你做事的伙伴。

当前只做项目初始化，Agent Loop 已选 Deep Agents，尚未进入功能开发。

## 目录

```text
RoomCrew/
├── AGENTS.md           统一开发规范与个人编码规则
├── changelog/          每天一个日志文件，如 20261025.md
├── frontend/src/       前端界面与交互，占位
├── backend/src/        后端逻辑，占位
├── docs/
│   ├── development/environment.md     Python 环境说明
│   └── architecture/0001-deepagents.md 技术选型决定
├── pyproject.toml      Python 依赖与工具配置
├── uv.lock             完整依赖锁
├── .python-version     Python 版本
└── .env.example        无秘密的开发配置模板
```

规范只维护一份；细分业务目录、共享合同和测试目录按真实需要建立。
本地 .venv、.tools、.cache 均 Git 忽略。
原有 main.py 为 PyCharm 示例，保持不变，不是正式入口。

## 开发环境

Python 3.13.17、uv 0.13.5、Deep Agents 0.7.32；使用独立 .venv，只管理依赖，不安装应用入口。
保留模型、MCP 与 SQLite checkpoint 支持；框架已带入的依赖不重复声明。

PyCharm 选择已有解释器：`E:\projects\RoomCrew\.venv\Scripts\python.exe`。

在项目根目录同步依赖：

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.tools/python'
& .\.tools\bootstrap\Scripts\uv.exe sync --locked --all-groups
```

详细步骤见 [环境说明](docs/development/environment.md)，选型见 [Deep Agents 决定](docs/architecture/0001-deepagents.md)。
每次完成改动后，按 [项目规范](AGENTS.md) 更新 [变更日志](changelog/)，在当天 YYYYMMDD.md 中按 HHmm-标题简短说明改了什么。
