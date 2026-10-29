# Python 开发环境

## 已准备

- Python 3.13.17，项目 .venv。
- uv 0.13.5，项目 .tools/bootstrap/Scripts/uv.exe。
- 项目托管解释器位于 .tools/python/，缓存位于 .cache/uv/。
- Deep Agents 0.7.32；其他依赖以根 uv.lock 为准。
- OpenAI / Anthropic / Google 模型适配器、MCP 和 SQLite checkpoint 支持已安装。
- pywebview 6.2.1、pythonnet 3.2.1；原生窗口使用系统 WebView2 与 .NET Framework 4.8。
- 构建组 PyInstaller 6.22.3；Ruff、mypy、pytest 已用于 V1 会话版验证。
- APScheduler 3.11.3 公开触发器用于日历和间隔计算；tzdata 2026.6、tzlocal 5.4.5 按 uv.lock 同步，Windows 发行携带 IANA 时区数据。业务计划不序列化为 Python JobStore。
- 档案本地语义使用 FastEmbed 0.9.1、ONNX Runtime 1.31.1，CPU 两线程按需加载 BGE small 中文模型；无 PyTorch/GPU 要求。构建步骤 packaging/prepare_archive_model.py 下载公开权重到忽略缓存，打包后只读随包 archive-model，不在运行时下载或请求远程 embedding 服务。

所有项目工具 / 缓存 / 环境目录均 Git 忽略，不替换系统 Python，不改全局 PATH / 注册表。
pyproject 的 package=false 表示使用源码和明确的冻结入口，不安装全局 RoomCrew 包。源码入口为 packaging/desktop_entry.py；项目日常启动统一使用根 start.ps1，以 packaging/active-release.json 选择实际发行程序及数据目录，不直接按历史记录打开 dist/RoomCrew/RoomCrew.exe。

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

.env.example 只提供不含秘密的开发变量模板，程序不加载它。用户在原生窗口手动配置模型，DPAPI 文件位于本地应用 private/ 目录；不在 .env 填写 API Key，不从系统环境兜底。V1 由可信工厂创建模型，安全 VM 后续迭代。具体边界见 [ADR-0002](../architecture/0002-conversation-v1.md)。

测试使用真实 Deep Agents / SDK / 工具，但远程响应由本机协议服务替代；原生窗口测试验证实际表单与桌面桥。真实服务验证由用户在应用内填写 Key 后执行。详见根 README 与验证记录。

前端为普通 HTML/CSS/JavaScript，运行和打包不需要 Node / Rust；node --check 仅用于开发期语法检查。Windows 用户只需要完整发行目录和 WebView2 / .NET 系统前提。
