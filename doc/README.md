# RoomCrew 开发指导

先读根 `AGENTS.md` 和 `README.md`。日常启动统一运行根 `start.ps1`；`-Check` 查看活动发行和数据目录。历史文档中的 exe 路径仅指当时快照。当前数据目录为 `.cache/asset-v2-showcase`，发布保留它，不自动复制用户配置。

## 当前实现基线

从图开始了解 Agent 后端：[当前架构图解](architecture/agent-runtime-map.html)。包含整体分层、定义与 Run、主子协作、上下文、能力接入、人工恢复、轨迹/checkpoint 及生命周期八张离线矢量图，并标明对应源码和当前边界。

| 主题 | 当前依据 | 适用范围 |
| --- | --- | --- |
| 执行底座与扩展点 | [ADR-0021：底座整理](architecture/0021-runtime-refactoring.md)、[ADR-0009：Agent 能力](architecture/0009-agent-foundation.md) | 唯一 Deep Agents 循环、能力装配、模型资源与后续升级顺序 |
| 包与依赖方向 | [ADR-0003](architecture/0003-backend-layers.md)、[ADR-0021](architecture/0021-runtime-refactoring.md) | 配置、模型、压缩、中间件、安全、工具、MCP、Skills、存储分层；最新说明修正历史目录 |
| 官方执行记录 | [ADR-0008](architecture/0008-native-agent-tracing.md) | 消息、Runnable v2 事件、checkpoint 与产品 Run 分开 |
| 成员配置与默认工具 | [ADR-0010](architecture/0010-member-materials-and-default-tools.md) | Agent 定义与素材分离，文件工具、Python、主子能力装配 |
| MCP 可视化与鉴权 | [ADR-0022](architecture/0022-authenticated-mcp.md) | Bearer 保护引用、百炼搜索预设、当前表单连接测试与模型前脱敏 |
| 持久定时任务 | [ADR-0023](architecture/0023-scheduled-agent-tasks.md) | 空间与 Agent 绑定、通用时间检查器、专用 CRUD 工具、取消和独立会话 |
| 档案库与无感续聊 | [ADR-0024](architecture/0024-archive-memory.md) | 完整历史、异步摘要、文本/本地语义/日期检索、用户共享来源和独立并行线程 |
| 空间与协作名单 | [ADR-0007](architecture/0007-workspace-rooms.md)、[ADR-0011](architecture/0011-coherent-studio-and-workspace-roster.md) | 一空间一会议室，上下文隔离，仅委派本空间显式配置名单 |
| 泡泡与人工交互 | [ADR-0013](architecture/0013-bubble-pointer-and-read-receipts.md) | 主 Agent 转达、局部挂点、真实点击及持久已读 |
| Markdown | [ADR-0012](architecture/0012-message-markdown.md) | 展示层安全解析，原轨迹保留原文 |
| 素材与人物接触 | [ADR-0020](architecture/0020-unified-projection-assets.md)、[ADR-0019](architecture/0019-paired-chair-interactions.md) | 固定投影兼容预览，四角色配套工作/起坐；完整动作及骨点仍待验收 |
| 素材制作规范 | [规范 v1.0](assets/asset-production-standard/README.md)、[图解版](assets/asset-production-standard/guide.html) | 相机、尺寸、八向、接触、导出及验收；制作端 JSON 尚非导入合同 |
| 环境 | [Python 环境](development/environment.md) | 版本以 uv.lock 为准，不改第三方源码，不依赖用户预装 Python |

后端不包含人物动作或泡泡协议，桌面单向消费已提交轨迹。主子 Agent 的消息、产物和 checkpoint 按任务隔离，不能用共享 agent_id 作为可变上下文。

## 验证入口

- 档案完整性、静默封存、语义、共享撤销、真实模型回查与原生并行交互：[档案验收](development/archive-validation.md)。

- 定时任务 CRUD、目标 MCP、空间隔离、原生管理和真实五分钟创建/执行/取消：[定时任务验收](development/scheduler-validation.md)。

- 当前整理与兼容检查：[ADR-0021 验证记录](architecture/0021-runtime-refactoring.md#5-验证记录)。
- Agent / Skills / MCP / Python / 人工恢复：[底座验收](development/agent-foundation-validation.md)。
- 模型表单：[配置验收](development/model-settings-validation.md)；空间隔离：[工作区验收](development/workspace-validation.md)。
- 角色点击开启对话、右上角团队配置及简化画布入口：[当前交互验收](development/studio-validation.md#2026-10-28角色对话与简化画布入口)。
- 场景、素材与原生截图：[素材验收](development/scene-assets-validation.md)；其他历史记录保留在 development/。
- 常用检查、源码运行和打包命令统一见根 README.md，不在每篇文档复制一套。

## 产品与长期设计

| 顺序 | 文档 | 阅读方式 |
| --- | --- | --- |
| 1 | [Deep Agents 决定](architecture/0001-deepagents.md) | 已替代旧自建 Rust Loop 方案 |
| 2 | [图解路线图](architecture-roadmap.html) | 从产品和宏观结构理解实施阶段 |
| 3 | [产品设计](product-design.html) | v1.4 完整历史需求，不能把所有条目当成已交付 |
| 4 | [技术设计](technical-design.html) | v1.4 长期指导，与现行 ADR 冲突时以最新决定为准 |
| 5 | [通用 Agent 与调度设计](architecture/multi-agent-runtime.html) | v0.3 方案背景，落地边界见 ADR-0009 和 ADR-0021 |

三份根 HTML 保留此前讨论的完整版本；通过现行决定说明差异，避免维护多份相近方案。下一阶段先升级通用 Runtime，再接入编码和日常工作能力，具体顺序见 ADR-0021。

## 历史设计索引

| 阶段 | 文档 |
| --- | --- |
| V1 与会话 | [0002 会话合同](architecture/0002-conversation-v1.md) |
| 桌面表现与素材 | [0004 只读投影](architecture/0004-studio-interaction.md)、[0005 游戏动画](architecture/0005-game-animation.md)、[0006 生活协作](architecture/0006-living-studio.md) |
| 办公物理校准 | [0014 办公行为](architecture/0014-physical-office-interactions.md)、[0015 接触修正](architecture/0015-office-contact-correction.md)、[0016 美术对齐](architecture/0016-office-art-alignment.md) |
| 可配置素材演进 | [0017 八向合同](architecture/0017-configurable-scene-assets.md)、[0018 视觉校准](architecture/0018-coherent-office-art.md)、[0019 配套桌椅](architecture/0019-paired-chair-interactions.md) |

历史 ADR 保留当时的动机和验证事实。被替代的图像与脚本已从当前源码删除，需要追溯时查看 Git，不重新保留备用执行路径。

## 当前边界

Windows 本地原型已支持用户模型配置、真实 Deep Agents、同会话主子轨迹、Skills、无认证/Bearer HTTP MCP、标准库隔离 Python、文件产物、人工恢复、多个工作空间和应用运行期间的持久定时任务。SQLite 产品状态与官方 checkpoint 分开，配置由可信入口保护和加载。

安全 VM、浏览器、Shell、Computer Use、MCP OAuth/stdio/自定义 Header、云账号、自动长期偏好提取、空间删除和外部家具/骨骼导入尚未实现。档案室已支持完整历史归档、摘要、检索和有授权的跨空间读取。Python AppContainer 不是凭据 VM；人物动画不能授予权限。当前素材仍为兼容预览，功能测试通过不等于专业美术或全部动作验收。

变更统一记录在根 changelog/YYYYMMDD.md。冲突时以当前用户决定、根规范和最新相关 ADR 为准，不照搬已被替代的版本、目录或实现。
