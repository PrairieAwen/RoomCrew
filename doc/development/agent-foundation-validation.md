# Agent 底座验收记录

本页保留 ADR-0009 初版验收；最新人物配置分层、动作帧、泡泡跟随、默认文件工具、107 项回归与新版发行验证见 [ADR-0010](../architecture/0010-member-materials-and-default-tools.md)。下文 100 项测试和旧 ZIP 指纹属于初版底座记录。

日期：2026-10-27；源码分支：codex/studio-interaction。范围见 [ADR-0009](../architecture/0009-agent-foundation.md)。

## 已验证能力

- 后端完全不导入桌面包；通用 Runtime 不需要动作协议、人物素材或 WebView。
- 专用 Agent 定义表持久化提示词、Skills、MCP、Python 配置；人物保存引用，支持多个形象共用定义及无形象工作者。
- 官方 Skills 渐进加载和配置目录只读；实际 Streamable HTTP MCP 发现与调用；成员列表工具及真实 task 委派。
- Agent 自写 Python 后由随包标准库解释器在 AppContainer/Job 内运行，产生真实文件；用户不需要安装 Python。
- 实际隔离 Token、外部私有 canary 拒绝、秘密环境未继承、网络与子进程拒绝、超时清理。
- 官方 Runnable v2 事件写入 native_events；模型工具 ID 与 SDK ID 分开，人工恢复合并正常工具卡片。
- 人工问题类型、选项及自由补充；同 Run 中断/恢复；桌面正面停顿、自定义短泡泡和右侧完整消息。

## 自动回归

最终完整 pytest：**100 passed，47.37 秒**。包含既有会话、压缩、失败/取消、存储与重启回归，以及新增能力和桌面映射验证。Ruff 通过；mypy 检查 86 个源码文件通过。

Node 三组验证通过：动作/协议/摸鱼；空间显式路由/迟到响应/表单隔离；模型表单保存探测/重试/过期回调。

原生 basic smoke 已通过：3 次模型请求、2 个工具、1 个文件，覆盖保存后测试和稳定配置绑定。新增 capabilities smoke 使用本机合成模型、真实 Deep Agents、真实 HTTP MCP 和真正 AppContainer，结果为 skills/mcp/python/human/bubbles/rightDock 全部通过；8 次模型请求、1 次 MCP 业务调用。实际表单保存配置、点泡泡打开人工问题并提交，返回产物求和 5050。

气泡经过原生截图复核，移到独立显示层避免家具遮挡，并限制在顶栏与会话边界之内。源码测试与发行程序验证分别记录，不能把源码运行当成新机器分发验证。

原生历史回归也通过：studio（3 次模型请求，素材导入/图集动画/人工停顿/读后恢复空闲）、workspace（4 次，两个会议室与产物/草稿隔离）、collaboration（8 次，配置成员会议/外援电话/真实产物/持久座位不变）。旧测试按新需求改为主动收起右侧会话后检查按需订阅，文件工具动作由 write 更新为 work，外援元数据更新为 external_worker。

## 已保存配置的真实模型验收

用户本次明确授权使用已配置 Key。可信 ConfigStore/ModelFactory 加载配置；没有在测试代码或 Agent 中读取明文 Key，没有修改用户会话和成员。测试使用独立数据根和合成任务输入。

实际模型自行选择和执行：发现成员 → 委派配置工作者 → 读取指定 Skill → 调用真实本机 MCP → 生成并运行 Python → 核对随机数据 → 写模拟日记 → ask_user 暂停 → 答复后继续。生产程序没有日记专用分支或预置模型回答。自动答复只用于本测试明确标注的合成人工问题。

| 项目 | 结果 |
| --- | --- |
| 最终状态 | completed |
| 逻辑模型调用 | 17 次 |
| 耗时 | 56.81 秒 |
| 原生执行事件 | 183 条 |
| MCP 业务调用 | 1 次 |
| 人工中断/答复 | 1 次 |
| 随机输入计算 | count、sum、sum_squares 与独立验证端完全一致 |
| 日记 | 模型依据合成事实自行创建，真实文件存在 |
| Python | Windows AppContainer |
| 隐私扫描 | 本轮数据库未出现保存的 Key、端点或原始模型 ID |

机器可读记录为 [agent-foundation-live-validation.json](agent-foundation-live-validation.json)，保留会话 ID、实际工具序列与产物 SHA256。日志中的 ask_user 两次调用对应中断与恢复，不是替用户作出两次决定。

此结果说明当前配置的一次端到端执行通过，不代表所有模型、MCP 服务或恶意脚本都已穷尽验证。外部厂商效果、复杂任务成功率、新机器依赖与正式商业美术仍需持续验收。

## 发行与限制

使用 packaging/build.ps1 先构建缓存候选，再整体发布；用户配置和历史不进入发行目录。包内另带标准库 Python，不包含开发环境 site-packages。

发行 exe 在独立合成配置下通过实际窗口发送任务，完成 4 次模型请求、1 次真实本机 MCP 调用，以及真正包内 Python 执行，生成 frozen-result.json，求和为 5050。验证脚本为 desktop/tests/frozen_smoke.py：先启动本机测试服务和独立 exe，再在该窗口发送任务；只观察程序自己生成的结果。没有用源码 Runtime 代替发行进程执行任务。

ZIP 共 412 个条目，CRC 全部通过，发行 UI 与源码逐字节一致；包含 python-runtime/python.exe 与标准库，不含 .sqlite、.dpapi、.env、private 或 tests。SHA256：`10e4c81a01a1c211b7c44ff56f2d2bd63b14ff0e4f1fdaa77931ed6201ca5e18`。产物：dist/RoomCrew/RoomCrew.exe 和 dist/RoomCrew-0.1.0-windows-x64.zip；未签名，尚未在干净的新 Windows 机器验收。

当前 MCP 仅无认证 HTTP；Python 仅标准库、无网络/子进程；Shell、浏览器、Computer Use、凭据安全 VM、第三方包安装和账号云同步尚未实现。监管员仍标明安全 VM 未接入；任务层 approval 不构成系统授权。
