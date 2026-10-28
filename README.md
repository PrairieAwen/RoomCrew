# RoomCrew

## 统一启动入口

所有会话在本项目根目录运行 `./start.ps1`。它只读取 `packaging/active-release.json`，明确选择程序版本和数据目录，不按目录时间或历史文档猜测。

```powershell
# 只查看当前选定的程序与数据目录，不启动窗口。
./start.ps1 -Check
# 启动当前统一版本；同数据目录的重复启动由应用单实例锁阻止。
./start.ps1
```

当前程序以活动发行清单为准，默认数据为 `.cache/asset-v2-showcase`。这是四角色素材验证数据，和用户正式数据、其他历史预览目录分开。需要指定已有数据时显式使用 `./start.ps1 -DataDir '绝对路径'`；脚本不会复制 Key 或迁移数据库。当前包缺失会报错，不改用旧版本。成功执行 `packaging/publish.ps1` 后会更新活动发行清单，并保留原数据目录。

常规发行位于 `dist/RoomCrew`；其他 `dist/RoomCrew-*-preview` 为历史独立快照，不会随源码自动更新。所有会话按活动清单启动，避免打开不同版本。

## 当前实现与设计入口

RoomCrew 是 Windows 本地工作空间原型：多会议室、人物与家具、Agent 定义、会话轨迹、文件产物与人工问答。底层只有 Deep Agents 一套生产循环，桌面单向消费轨迹；安全 VM 尚未接入。

本轮整理见 [ADR-0021](doc/architecture/0021-runtime-refactoring.md)：主子 Agent 统一工厂装配、模型连接生命周期、成员批量读取及废弃资源清理；包含兼容验证和下一步通用 Runtime 升级顺序。完整主题索引见 [开发指导](doc/README.md)，历史设计和验收保留在 doc/。

当前素材为统一投影兼容预览：八类家具八向、四角色配套工作和六帧起坐，见 [ADR-0020](doc/architecture/0020-unified-projection-assets.md)。后续按 [素材规范](doc/assets/asset-production-standard/README.md) 和 [图解版](doc/assets/asset-production-standard/guide.html) 制作；全动作、全部骨点及专业美术仍需验收。

## Windows 用户验证

本仓库验证请使用根 `start.ps1`。常规构建/发布会产生 `dist/RoomCrew/RoomCrew.exe` 与 `dist/RoomCrew-0.1.0-windows-x64.zip`，成功后切换统一启动清单；独立预览有各自的打包快照。对外传递时使用选定发行的完整 ZIP，解压后双击 exe，保留 `_internal` 文件夹，不需要安装 Python 或启动后端。

系统前提：Windows x64、WebView2 Runtime、.NET Framework 4.8。首版尚未签名或提供安装器；先在当前机器做真实模型验收，再验证全新机器分发兼容性。

1. 打开模型配置，手动填 Base URL、模型 ID、API Key、超时和上下文窗口。首版使用 **OpenAI 兼容 Chat Completions**，要求标准工具调用支持。
2. 点击“保存并测试连接”，程序会先保存当前表单，再向对应服务商发起一次真实模型请求；无需先单独保存。也可用“仅保存配置”只在本机保存。
3. 展开“我的团队”添加成员，可调整外观、导入 PNG+JSON 素材，并配置系统提示词、Skills、HTTP MCP、Python 开关和提示泡泡。多个形象可复用 Agent 定义。用户本人就是老板，不显示老板人物；最低保留助手和监管员，默认由助手接待。
4. 通过下方成员选择框或 `@准确名字` 指派任务；未指定时由助手自行使用工具或委派已配置员工。人物动作由真实结构化事件转换，赴约与换座不阻塞后台工作。
5. 完整会话固定在右侧；“会议室”可收起会话。点击人物查看事项与按需轨迹。人物泡泡只提示待答复或完成，点击打开完整内容。
6. 若 Agent 使用 `ask_user` 请求信息、选择或人工确认，人物面向用户并暂停动作；支持选项及可选的“其他 / 补充”。答复后沿用原 Run 继续，可正常关闭应用后再答。这里不是系统权限审批。
7. 可用“让 Agent 写一份日记”验收；按需要提供真实经历及文件要求。程序没有日记模板或专用处理逻辑。

点击人物后再点击沙发、工位或会议座位，可让他换座；“布置会议室”使用统一格网坐标表单添加和移动家具。场景支持拖动、滚轮缩放和人物定位，导航/团队/输入区为悬浮界面。角色素材导入已开放，制作说明见 `doc/assets/crew-avatar-example/README.md`。家具仍使用内置目录，家具拖拽编辑与应用内绘画编辑器尚未提供。

辅助模型旁白默认关闭。如需使用，在模型配置中选择“辅助旁白模型”单独填写，再勾选开关；它只接收活动数量等最小事实，超时回到规则动作，不使用执行模型 Key 兜底，也不能改变任务事实或代替用户答复。

人物属性可设置最多四项空闲活动，默认手机、游戏、散步、同事闲聊；浇花和自绘休闲可作为替换项。首次空闲等待 0—120 秒，选定活动后每 **5–10 分钟随机轮换**。接单、派工或点击人物立即停止；假聊天不调用模型、不写消息。监管员保持值守。委派给已配置成员时，同任务人物集合站会；无形象的已配置 Agent 仅展示轨迹。临时视觉移动不改变持久化座位或执行进度。

顶部“素材总览”提供四套可选形象（阿晨、小禾、小岚、监管员），共 496 个登记姿态，每套覆盖 20 种动作语义和 5 种闲置表情；可切换变体、暂停逐帧并检查真实覆盖矩阵。在人物属性选择角色后“导入完整角色”，保存才绑定，不自动覆盖原人物。另备齐 12 件家具、16 件装饰和 8 组四帧特效，常用家具与灯/咖啡机已接入房间，其余装饰和特效按总览详情标明用途。完整目录、约束与美术缺口见 `desktop/ui/studio/assets/library-v1/README.md`；专业逐帧精修与所有方向/站坐/表情组合仍待完善。

配置与数据默认在 `%LOCALAPPDATA%/RoomCrew`。模型配置由 Windows DPAPI 加密，独立于 Agent 文件视图；原始配置和 Key 不注入消息、普通轨迹或 checkpoint。Python 使用另一个随包解释器，在无网络 AppContainer 与受限 Job 中执行会话文件副本，不继承父进程秘密环境。模型请求仍会将任务内容发往用户配置的服务商。

当前支持文件读写/检索、规划、成员发现与子 Agent 委派、本机时间、人工信息确认、配置 Skills、HTTP MCP 和隔离 Python。未接入 Shell、浏览器、Computer Use、安全 VM 与云端账号同步。当前每个空间同时执行一个会话，最多四个空间并行执行；成功会话可多轮继续，失败或取消会话只保留查看，继续需新建。同一 Agent 定义绑定的不同人物仍使用独立主线程上下文。

Agent 配置与执行流程见 [ADR-0009](doc/architecture/0009-agent-foundation.md)。Skills 表单目前使用 JSON，框架先读名称与描述，再按任务读取完整说明及附带文本；MCP 目前支持无认证的 Streamable HTTP 服务。Python 仅包含标准库，不支持 pip、外网和子进程；用户无需预装 Python。安全审核对应的动作映射已预留，真实安全 VM 尚未实现。

人物属性分为“Agent 配置”和“员工素材配置”。在素材页可为 MCP、普通工具、Python、人工、完成等触发类型选择动作，导入图集后可编辑具体变体、帧号、帧率与循环，预览和场景使用同一播放器。泡泡按当前人物头部跟随，平移/缩放时保持归属。默认文件工具另补 file_info、make_directory、copy_file、move_file、delete_file，主子 Agent 均可使用；二进制复制不转码，文本工具不等于 Office/PDF 解析。详见 [ADR-0010](doc/architecture/0010-member-materials-and-default-tools.md)。

泡泡使用人物局部挂点，与人物共用同一份移动变换，走动、起坐和镜头平移同步跟随，缩放时一起缩放；提示绘制在家具上层，挂点按整套姿态缓存，不随帧裁切抖动或在左右位置间跳换。完成提示只有点击并成功查看对应结果后才消失；人工提示在实际答复或取消相应任务后解除。未读与已读单独保存在各空间 bubbles.sqlite，新任务、切空间和重启不清除未读，也不恢复已经读过的结果。

每个任务由入口主 Agent 统一对用户汇报：子 Agent 完成不单独冒泡，整轮任务完成后由主 Agent 提示；子任务遇到人工问题，也由主 Agent 转达，点击后答复原始问题并恢复原子任务。多个独立入口任务仍各自保留提示；完整委派过程和真实执行者保留在右侧轨迹。升级自动退役旧版子任务完成提示，并保留主结果的已读记录。

## 工作空间与会议室

左侧“我的空间”列出工作空间；选择后，整个主画布切换到该空间唯一对应的会议室。支持新建、重命名，最多 16 个空间。成员、Agent 定义、布局、会话、轨迹、产物与 checkpoint 分别保存；模型连接由本机用户统一配置。切换不停止后台任务，侧栏显示执行和待答复计数，未发送草稿在本次启动中按空间保留。

原数据自动作为“默认工作空间”，继续保存在 `data/`；新空间位于 `workspaces/<空间ID>/data/`。`private/` 仍独立于全部任务目录。修改共享模型配置前需要处理所有空间的运行与待答复任务。当前不提供删除空间或云端同步。详见 [ADR-0007](doc/architecture/0007-workspace-rooms.md)。

## 目录

```text
RoomCrew/
├── AGENTS.md           统一开发规范与个人编码规则
├── changelog/          每天一个日志文件，如 20261025.md
├── desktop/            普通用户桌面应用
│   ├── ui/             会议室、人物、配置、会话及素材
│   ├── src/roomcrew_desktop/ 原生窗口、显式空间桥与生命周期
│   ├── tests/          原生流程、界面脚本与协议验证
│   └── tools/          素材制作与登记工具
├── frontend/           未来管理员 Web 界面，仅预留说明
├── backend/src/roomcrew/ 按 Loop、配置、压缩、中间件、安全、工具等职责分层
├── backend/tests/      真实框架、工具、空间隔离与分层回归
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
│   ├── architecture/0004-studio-interaction.md 人物持久化、表现协议与云端迁移边界
│   ├── architecture/0005-game-animation.md 游戏表现、素材包与轨迹动画映射
│   └── architecture/multi-agent-runtime.html 通用 Agent 与调度设计
├── pyproject.toml      Python 依赖与工具配置
├── uv.lock             完整依赖锁
├── .python-version     Python 版本
└── .env.example        无秘密的开发配置模板
```

规范只维护一份；细分业务目录和共享合同按真实需要建立。
本地 .venv、.tools、.cache 均 Git 忽略。
原有 main.py 为 PyCharm 示例，保持不变，不是正式入口。

后端结构与依赖见 [分层设计](doc/architecture/0003-backend-layers.md) 与 [最新底座](doc/architecture/0009-agent-foundation.md)。`agent_loop/` 只适配 Deep Agents；`application/` 负责会话和调度；配置、模型、压缩、中间件、安全、工具、MCP、Skills、存储分别维护。后端不导入桌面包，不产生动作或泡泡。

后端 `accounts/` 管理执行身份与可复用定义；桌面 `presentation/` 单向消费已提交日志并生成最小显示状态，`assets/` 维护人物素材。账号 SQLite、框架 checkpoint、任务日志、布局与表现缓存分开。迁云设计见 [ADR-0004](doc/architecture/0004-studio-interaction.md)；图集见 [ADR-0005](doc/architecture/0005-game-animation.md)。

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

开发前先读 [开发指导](doc/README.md)；当前后端扩展点与升级顺序见 [ADR-0021](doc/architecture/0021-runtime-refactoring.md)。详细步骤见 [环境说明](doc/development/environment.md)，选型见 [Deep Agents 决定](doc/architecture/0001-deepagents.md)。
每次完成改动后，按 [项目规范](AGENTS.md) 更新 [变更日志](changelog/)，在当天 YYYYMMDD.md 中按 HHmm-标题简短说明改了什么。

## 源码运行、验证和打包

在项目根运行：

```powershell
# 原生桌面应用；原始 main.py 不是入口。
& .\.venv\Scripts\python.exe packaging/desktop_entry.py

# 自动测试只用本机模拟模型，仍真实运行 SDK、Deep Agents 和工具。
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe desktop/tests/desktop_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/capabilities_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/studio_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/workspace_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/collaboration_smoke.py
& .\.venv\Scripts\python.exe -m ruff check backend desktop
& .\.venv\Scripts\python.exe -m mypy backend/src desktop/src
node --check desktop/ui/app.js
node desktop/tests/web/protocol.test.cjs
node desktop/tests/web/workspaces.test.cjs
node desktop/tests/web/model-settings.test.cjs
node desktop/tests/web/material-bindings.test.cjs
node desktop/tests/web/bubble-read.test.cjs
node desktop/tests/web/camera-pointer.test.cjs
node desktop/tests/web/office-behavior.test.cjs
& .\.venv\Scripts\python.exe desktop/tests/office_scene_smoke.py
node desktop/tests/web/markdown.test.cjs
& .\.venv\Scripts\python.exe desktop/tests/markdown_smoke.py

# 独立 exe + 发行目录 + zip。
& .\packaging\build.ps1
```

打包先在 `.cache/` 构建完整候选，成功后再发布。若当前 RoomCrew 正在运行，发布会拒绝替换并保留候选；关闭程序后可用 `packaging/publish.ps1 -Candidate <候选目录>` 发布，无需再次构建。

受限运行环境若阻止 Windows asyncio 的本地套接字初始化，需要在允许本机网络的终端运行测试；不要为了让测试通过修改生产 Loop。此前真实服务验收见 [底座验收](doc/development/agent-foundation-validation.md)。本次整理使用本机合成模型验证，未读取用户真实 Key；兼容与发行检查见 ADR-0021。
