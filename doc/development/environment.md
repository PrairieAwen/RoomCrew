# Python 开发环境

## 已准备

- Python 3.13.17，项目 .venv。
- uv 0.13.5，项目 .tools/bootstrap/Scripts/uv.exe。
- 项目托管解释器位于 .tools/python/，缓存位于 .cache/uv/。
- Deep Agents 0.7.32；其他依赖以根 uv.lock 为准。
- OpenAI / Anthropic / Google 模型适配器、MCP 和 SQLite checkpoint 支持已安装。
- Ruff、mypy、pytest 仅预装和配置，没有业务代码或测试用例。

所有项目工具 / 缓存 / 环境目录均 Git 忽略，不替换系统 Python，不改全局 PATH / 注册表。
pyproject 的 package=false 表示只管理依赖；当前不安装 RoomCrew 包或入口。

## PyCharm

设置 → 项目 → Python 解释器 → 添加已有本地解释器，选择：

E:\projects\RoomCrew\.venv\Scripts\python.exe

系统默认 python 可能仍为 3.9；不要把它当业务解释器。

## 同步当前依赖

在根目录执行：

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.tools/python'
& .\.tools\bootstrap\Scripts\uv.exe sync --locked --all-groups
```

新机器使用官方 uv，匹配仓库要求的版本，再按 .python-version 准备解释器并同步锁文件。
依赖升级通过 uv 生成新锁文件；不能手工修改 lock 或强行忽略依赖冲突。

## 配置与验证边界

.env.example 只提供不含秘密的开发变量模板，当前没有程序读取它。不要提交真实 API Key。
当前仅检查解释器、依赖一致性、配置可解析与目录；不调用模型、不启动 VM / 浏览器、不运行 Agent Demo。
前端 Node / Rust / 构建链在对应界面开发任务中准备，不在本轮安装系统组件。
