# ADR-0012：桌面会话 Markdown 渲染

状态：已实现；2026-10-27。覆盖此前消息正文仅按纯文本显示的行为。

## 1. 展示与原始记录分开

用户和 Agent 的公开消息由 desktop/ui/message-markdown.js 统一渲染；实时追加和历史回放共用入口。后端、Deep Agents 消息、SQLite 轨迹、checkpoint 与原始文本不修改。工具输入输出、错误日志和文件预览继续显示纯文本，代码中的星号不会被再次解析。人物泡泡继续使用简短文本提示，不承载长篇 Markdown。

采用 MIT 许可 markdown-it 15.0.3，本地 vendor 随应用分发，不运行时下载 CDN。dependency.json 保存官方 npm 包来源、SHA512 完整性与实际脚本 SHA256，原许可证随文件保留；升级时重新校验官方包并运行回归，不修改第三方源码。

## 2. 渲染方式与边界

解析器负责 CommonMark 语法和表格、删除线扩展；界面把 Token 显式转为有限 DOM，不把解析器生成的 HTML 写入 innerHTML。支持标题、加粗、斜体、嵌套/有序列表、引用、分隔线、表格、行内代码、代码块和链接。代码块显示语言文本标签和复制入口；当前不含语法高亮、数学公式、Mermaid、任务复选框或 HTML 扩展。

关闭原始 HTML；文本使用 TextNode/textContent。DOM 不接收模型提供的事件属性、任意 style 或资源地址；表格对齐仅映射为固定 CSS 类。远程图片只显示替代文字，不自动加载网络资源。超过 200,000 个 UTF-16 代码单元、解析失败或超过 20,000 Token 的消息回退完整纯文本，不截断原文；解析嵌套限制为 24。渲染只发生于消息加载，不加入场景帧循环。

网页链接仅允许 HTTP(S)，拒绝带用户名密码的 URL。用户点击后通过原生 WebView 的外部打开行为交给系统浏览器，使用 noopener/noreferrer，不跳转主应用。javascript/data/file/mailto/系统协议、UNC、盘符路径和上级跳转不启用。链接不是执行授权。

相对或 / 开头的会话文件链接转为按钮，复用 read_artifact 的空间/会话校验与纯文本预览，不直接访问宿主文件。预览返回后再次核对当前会话，避免迟到响应串会话。复制代码仅在明确点击后写剪贴板，失败显示文字反馈；不自动执行代码。

## 3. 验证与后续维护

Node 回归覆盖危险协议、控制字符、编码路径越级、中文文件名、认证 URL、HTML 解析关闭、vendor 内容哈希与本地脚本加载顺序。五组已有界面回归及 Python 注释规范检查通过。

desktop/tests/markdown_smoke.py 使用独立数据目录和本机合成模型，经过真实 Deep Agents、write_file、SQLite 轨迹与原生 WebView2。两次模型请求完成：常用格式实际 DOM、代码原文、HTML 不执行、无远程图片加载、表格对齐、窄栏宽度、实际产物链接、工具日志保持原文及历史重新加载均通过；人工检查了实际窗口的列表、表格和代码块。没有读取真实模型 Key，也没有把测试轨迹写入用户空间。

运行：`node desktop/tests/web/markdown.test.cjs`；原生验收：`.venv/Scripts/python.exe desktop/tests/markdown_smoke.py`。界面静态文件与 vendor 整体随完整 Windows 应用发布，后续完整构建仍由现有资源收集规则处理。

本次复用已验收的原生执行文件，在完整候选目录中同步全部界面资源后原子发布；未修改 Python 生产代码。Windows ZIP 共 421 项，CRC 通过，52 个界面文件与源码及安装目录逐字节一致，无用户数据库/密文。ZIP SHA256：4cf4048ec02690df7fc5cc40ace92c80482e71450bee7facaf952dcd799df698。
