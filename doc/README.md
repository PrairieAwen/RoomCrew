# RoomCrew 开发指导

最新界面与工作区规范见 [ADR-0011](architecture/0011-coherent-studio-and-workspace-roster.md)：统一视觉注册、独立工作区与配置名单。它覆盖旧文档中隐式通用外援和深色界面的描述；档案室仅有规划入口，归档与长期记忆尚未开发。

先读本页，再阅读相关 HTML。三份 HTML 是此前讨论中最后生成的版本，正文原样保留；后续已确定的选型和项目约定按本页与当前规范执行。

## 当前交付：Windows 独立工作空间原型

泡泡真实鼠标点击与同会话多轮结果已读规则见 [ADR-0013](architecture/0013-bubble-pointer-and-read-receipts.md)：成功展示后清除已读完成提示，人工问题仍需实际答复。

消息正文已支持本地 Markdown 排版，历史消息同步生效；工具日志保留原文。格式、链接边界与原生验收见 [ADR-0012](architecture/0012-message-markdown.md)。

最新人物属性和默认工具见 [ADR-0010](architecture/0010-member-materials-and-default-tools.md)：Agent 配置与员工素材页分开，支持触发类型→图集变体/帧序列，泡泡按人物头部跟随；所有 Agent 默认加载补充文件工具，Python 包含子任务及报错修正验收。

最新执行底座以 [ADR-0009](architecture/0009-agent-foundation.md) 为准：后端不包含动作协议，Agent 定义单独持久化；Skills、HTTP MCP、成员发现和隔离 Python 已接入。桌面独立映射动作、短泡泡与右侧人工交互，验收见 [底座验证](development/agent-foundation-validation.md)。该决定覆盖旧文档中“Python/MCP 尚未开放”及后端包含表现模块的描述。

模型配置入口已修复为「保存并测试连接」，支持当前表单先保存、失败短路和绑定稳定，见 [配置测试验收](development/model-settings-validation.md)。

最新空间与目录规则以 [ADR-0007](architecture/0007-workspace-rooms.md) 为准：品牌只保留 RoomCrew；一工作空间对应一会议室，左侧选择后切换主画布，任务继续后台运行。用户桌面界面与原生壳统一位于根 desktop/，frontend/ 仅预留管理员 Web 界面。多空间验证见 [验收记录](development/workspace-validation.md)。

最新人物与空间规则以 [ADR-0006](architecture/0006-living-studio.md) 为准：用户无需老板替身、助手接待、五至十分钟随机生活活动、同任务配置成员会议、无形象外援电话，以及手绘环境接入。此前三人最低配置与单动作逻辑由该决定覆盖。

当前验证结果与发行包见 [生活与协作验收](development/living-studio-validation.md)。

[ADR-0002：V1 范围与运行合同](architecture/0002-conversation-v1.md) 是原会话基线；当前用户进一步授权的事务所空间、人物持久化、单向表现协议与真实人工恢复以 [ADR-0004](architecture/0004-studio-interaction.md) 为准。正交游戏动画、自定义角色图集与全窗口布局以 [ADR-0005](architecture/0005-game-animation.md) 为准；素材样例见 [制作说明](assets/crew-avatar-example/README.md)。安全 VM 仍未接入。运行与构建见根 README；原会话验证保留在 [历史基线](development/v1-validation.md)，新增验证见 [事务所原型验证](development/studio-validation.md)。

[ADR-0003：后端职责分层](architecture/0003-backend-layers.md) 是当前源码结构依据，包含模块目录、依赖方向、运行/压缩时序，以及新增工具、MCP、Skills 和模型适配的接入位置。实际生产 Loop 仍只有 Deep Agents 一套。

最新原生动画与素材验收见 [游戏表现验证](development/game-animation-validation.md)：包括真实图集选帧、跑步与疑问表情叠加、素材绑定及不影响真实 Agent 工具执行。

个人摸鱼偏好、跨上下文空闲判定与自绘生活片段见 [ADR-0005 第 10 节](architecture/0005-game-animation.md#10-没有工作时的人物生活动作)，仍是单向表现，不增加生产 Agent 循环。

最新单角色美术样板与 v2 裁切协议见 ADR-0005 第 11 节。可从人物属性试用手绘角色并连播，正式任务仍由原有轨迹映射驱动。

完整基础素材库与受限双页 v3 协议见 ADR-0005 第 12 节及 `desktop/ui/studio/assets/library-v1/README.md`：四套可导入角色、496 个姿态、每套 20 种动作，另有家具/装饰/状态特效和可播放总览。常用环境美术已接入房间；其余展示素材按总览说明区分。

## 当前多 Agent 执行底座设计

[ADR-0008：官方 Agent 执行记录](architecture/0008-native-agent-tracing.md) 采用官方消息、Runnable v2 事件和 Checkpointer，区分模型工具 ID、SDK 调用 ID、checkpoint 与 MCP 请求 ID。原生事件持久化与 HTTP MCP 已接入，附带模拟样例仍仅用于解释字段。

[通用 Agent 与多 Agent 调度架构 v0.3](architecture/multi-agent-runtime.html)：本次方案包含 25 个章节与 9 张架构图，覆盖通用内核、模型私有配置与可信工厂、同配置多 Run、SQLite 轨迹、能力路由、Skills 加载、中间件压缩和恢复。User、助手与安全 VM 抽象按最新补充修正；具体实现待评审。

## 文档与阅读顺序

| 顺序 | 文档 | 版本与用途 |
| --- | --- | --- |
| 1 | [现行选型决定](architecture/0001-deepagents.md) | 已确定使用 Deep Agents，先了解与历史设计的差异 |
| 2 | [图解架构与实施路线](architecture-roadmap.html) | 路线图 v1.0，基于设计 v1.4；由浅入深理解结构、交互与阶段 |
| 3 | [产品设计文档](product-design.html) | v1.4；用户旅程、角色、画布、人物动作、事项和产品验收 |
| 4 | [技术设计与架构选型](technical-design.html) | v1.4；前后端合同、Agent、上下文、执行、存储、安全与恢复 |
| 5 | [Python 环境说明](development/environment.md) | 本仓库已准备的环境、解释器与依赖维护方式 |

## 当前决定覆盖的历史内容

| 主题 | 当前有效约定 | 阅读历史文档时注意 |
| --- | --- | --- |
| 项目名称 | RoomCrew | “数字工作室”等旧称表达同一产品 |
| Agent Loop | Deep Agents，初始锁定 0.7.32 | 自建小型 Rust Harness / Loop 的推荐已被替代，不再照此实现第二套循环 |
| 角色与并发 | 老板是 User，助手是通用 Agent 配置，监管员是安全 VM；同配置可并发多个独立 Run | 不按旧方案把三者都作为 Agent；首版协程与每空间 SQLite，不强制每 Run 一个进程 / 数据库 |
| Rust 与界面框架 | Rust 可用于必要系统组件；Tauri / React / PixiJS 等仍需相应验证 | 不能把历史候选组合当成已完成或全部冻结的选型 |
| 产品权威 | User、Agent 配置、任务与 Run、共享事实和权限由产品掌握 | 框架 checkpoint、模型声明和动画均不单独决定任务成功或授权 |
| 代码目录 | desktop/ 为用户桌面，backend/ 为底层逻辑，frontend/ 仅预留管理员 Web 界面 | 不直接照搬历史多服务 / 多包目录模板，按实际任务再创建模块 |
| 开发规范 | 根 [AGENTS.md](../AGENTS.md) | 所有方法中文说明“因为……，需要……”，方法体用中文编号步骤，常用能力合理抽象 |
| 变更记录 | 根 [changelog/](../changelog/) 下每天一个 YYYYMMDD.md | 前后端统一记录，每次只简短写实际改动 |
| 依赖版本 | 根 pyproject.toml、uv.lock 和 .python-version | HTML 中的历史版本或工具建议不能覆盖当前锁定环境 |

## 实现边界

当前已进入事务所交互原型开发，保留会话基线。HTML 的完整产品流程、架构图和性能目标仍是长期指导；只有现行 ADR 和验证记录明确列出的能力已经接入，不代表安全 VM、浏览器、认证型 MCP、外部家具/骨骼文件导入或正式商业游戏美术已经完成。

后续实现要先明确当前功能的行为、边界、合同与验收，再按授权任务开发；不能因为完整设计中存在某项能力就提前扩大实现范围。

人物位置与动作、真实任务状态、实际权限分别保持权威来源。任意代码、登录态和 Computer Use 的隔离能力需要独立实现与验证，Deep Agents 不自动提供整套凭据 VM。

发生冲突时，以用户当前明确决定、根 AGENTS.md 和对应已接受 ADR 为准；先同步设计差异，避免同时维护互相矛盾的方案。

## 来源

本目录三个 HTML 复制自此前产出的 architecture-documents，保留原文件名，文档之间的相对链接可直接使用。
为了保留原始内容，当前选型差异集中说明在本页，复制时未直接重写历史 HTML 正文。
