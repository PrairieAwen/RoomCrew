# RoomCrew · 一间事务所

一间属于你的事务所，一群陪你做事的伙伴。

当前已实现 Windows V1 会话应用：本地模型配置、真实 Deep Agents 执行、主子 Agent 同会话轨迹、SQLite 历史与实际文件产物。房间渲染与安全 VM 留待后续。

## Windows 用户验证

构建结果位于 `dist/RoomCrew/RoomCrew.exe`；对外传递使用完整的 `dist/RoomCrew-0.1.0-windows-x64.zip`。解压后双击 exe，保留 `_internal` 文件夹，不需要安装 Python 或启动后端。

系统前提：Windows x64、WebView2 Runtime、.NET Framework 4.8。首版尚未签名或提供安装器；先在当前机器做真实模型验收，再验证全新机器分发兼容性。

1. 打开模型配置，手动填 Base URL、模型 ID、API Key、超时和上下文窗口。首版使用 **OpenAI 兼容 Chat Completions**，要求标准工具调用支持。
2. 保存配置，点击“测试已保存配置”。它会向指定服务商发起真实模型请求。
3. 提交任务，观察公开回复、工具输入输出、子 Agent 和状态；点击右侧文件核对真实交付。
4. 可用“让 Agent 写一份日记”验收；按需要提供真实经历及文件要求。程序没有日记模板或专用处理逻辑。

配置与数据默认在 `%LOCALAPPDATA%/RoomCrew`。配置由 Windows DPAPI 加密，独立于 Agent 文件视图；原始配置和 Key 不注入消息、普通轨迹或 checkpoint。该边界不是 OS 沙箱，所以 V1 不开放任意代码工具。模型请求仍会将任务内容发往用户配置的服务商。

当前支持文件读写/检索、规划、子 Agent 委派、本机时间。未接入 Shell、MCP、浏览器、Computer Use、用户 Skills 管理、员工配置和房间渲染。首版全局同时运行一个会话；成功会话可多轮继续，失败或取消会话只保留查看，继续需新建。

## 目录

```text
RoomCrew/
├── AGENTS.md           统一开发规范与个人编码规则
├── changelog/          每天一个日志文件，如 20261025.md
├── frontend/src/       原生窗口中的会话界面
├── backend/src/roomcrew/ 按 Loop、配置、压缩、中间件、安全、工具等职责分层
├── backend/tests/      真实框架/工具回归与原生窗口集成测试
├── packaging/          PyInstaller 方案、构建脚本和用户说明
├── doc/                开发指导文档
│   ├── README.md                    现行基线与阅读导引
│   ├── product-design.html          产品设计 v1.4
│   ├── technical-design.html        技术设计 v1.4
│   ├── architecture-roadmap.html    图解架构与路线图
│   ├── development/environment.md   Python 环境说明
│   ├── architecture/0001-deepagents.md 现行选型决定
│   ├── architecture/0002-conversation-v1.md 首版范围与运行合同
│   ├── architecture/0003-backend-layers.md 模块职责、依赖方向与扩展方式
│   └── architecture/multi-agent-runtime.html 通用 Agent 与调度设计
├── pyproject.toml      Python 依赖与工具配置
├── uv.lock             完整依赖锁
├── .python-version     Python 版本
└── .env.example        无秘密的开发配置模板
```

规范只维护一份；细分业务目录和共享合同按真实需要建立。
本地 .venv、.tools、.cache 均 Git 忽略。
原有 main.py 为 PyCharm 示例，保持不变，不是正式入口。

后端结构与依赖见 [分层设计](doc/architecture/0003-backend-layers.md)。`agent_loop/` 只适配 Deep Agents；`application/` 负责会话和调度；配置、模型、压缩、中间件、安全、工具、MCP、Skills、存储和桌面分别维护。MCP 仍关闭，Skills 已有显式来源和渐进加载接入，尚无用户技能管理界面。

## 开发环境

Python 3.13.17、uv 0.13.5、Deep Agents 0.7.32、pywebview 6.2.1、PyInstaller 6.22.3；使用独立 .venv，打包入口不依赖用户全局 Python。
保留模型、MCP 与 SQLite checkpoint 支持；框架已带入的依赖不重复声明。

PyCharm 选择已有解释器：`E:\projects\RoomCrew\.venv\Scripts\python.exe`。

在项目根目录同步依赖：

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.tools/python'
& .\.tools\bootstrap\Scripts\uv.exe sync --locked --all-groups
```

开发前先读 [开发指导](doc/README.md)；当前后端方案见 [通用 Agent 与调度设计](doc/architecture/multi-agent-runtime.html)。详细步骤见 [环境说明](doc/development/environment.md)，选型见 [Deep Agents 决定](doc/architecture/0001-deepagents.md)。
每次完成改动后，按 [项目规范](AGENTS.md) 更新 [变更日志](changelog/)，在当天 YYYYMMDD.md 中按 HHmm-标题简短说明改了什么。

## 源码运行、验证和打包

在项目根运行：

```powershell
# 原生桌面应用；原始 main.py 不是入口。
& .\.venv\Scripts\python.exe packaging/desktop_entry.py

# 自动测试只用本机模拟模型，仍真实运行 SDK、Deep Agents 和工具。
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe backend/tests/desktop_smoke.py
& .\.venv\Scripts\python.exe -m ruff check backend
& .\.venv\Scripts\python.exe -m mypy backend/src
node --check frontend/src/app.js

# 独立 exe + 发行目录 + zip。
& .\packaging\build.ps1
```

受限运行环境若阻止 Windows asyncio 的本地套接字初始化，需要在允许本机网络的终端运行测试；不要为了让测试通过修改生产 Loop。真实模型效果和厂商差异需要用户在应用中填写配置后验证，自动测试不代替该验收。
