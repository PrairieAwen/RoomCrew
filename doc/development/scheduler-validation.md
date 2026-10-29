# 定时任务验收记录

2026-10-29。实现依据 [ADR-0023](../architecture/0023-scheduled-agent-tasks.md)。以下分别记录确定性自动化、真实模型和 Windows 发行检查，不能将合成模型或测试时钟当作真实五分钟验收。

## 1. 自动化与边界

| 检查 | 结果与范围 |
| --- | --- |
| pytest 全量回归 | 156 项通过，含原有 Agent、MCP、Python 隔离、人工恢复、空间、官方轨迹与桌面合同 |
| 新增预检查保护回归 | 全量之后补充 1 项，验证真实验收发现原有活动计划时退出且不取消它；调度专项及规范共 19 项再次通过 |
| 调度目标 | 新建专用员工，实际装配更新后的系统提示词与其 HTTP MCP，真实 MCP 服务返回 42；计划中无提示词、MCP 端点或密钥副本 |
| 调度规则 | 间隔、每天、每周、北京时间、IANA 时区、夏令时缺失/重复时刻；拒绝无偏移时间、过小间隔和未知回调 |
| 持久语义 | CRUD、revision CAS、命令重放、删除不可恢复、重启后删除保留、旧排队项取消、超时不创建空会话 |
| 受理与失败 | 目标停用不回退助手、四空间准入、固定请求对账、模拟回执丢失不重复执行、单条损坏规则不阻断其他正常项 |
| 执行与轨迹 | 正式 Deep Agents Loop、get_local_time、独立会话、原生 v2 run_id/parent_ids、正确 member_id 与 source；自动 Run 无日程写工具 |
| 静态检查 | Ruff 通过；mypy 103 个源码文件通过；新增页面脚本语法检查通过 |
| 原有界面回归 | 9 组 Node 验证通过，涵盖泡泡/镜头/Markdown/模型表单/素材绑定/办公动作/协议/空间隔离 |

单元验证使用合成模型 HTTP 响应和独立临时目录；部分精确边界用 `TestClock` 注入协调器，真实 get_local_time 不被替换。没有修改 SDK、系统时钟或生产图循环。

原生 `desktop/tests/schedules_smoke.py` 使用真实 WebView2、DesktopAPI、SQLite 和正式控件，独立数据且没有真实模型配置。验证新增服务返回的计划在管理面板展示，暂停、恢复、取消、查看空历史和空间切换隔离均成功，结束取消本测试计划。真实窗口截图已目检：白底、深色文字、目标员工、时区时间和直接管理按钮可见。

## 2. 真实五分钟验收

使用原启动清单数据根，通过可信 ConfigStore/ModelFactory 使用用户已经保存的配置；没有复制或读取输出原始 API Key。真实系统时间、正式生产时间检查器与执行器，未缩短五分钟间隔、修改 next_fire 或注入假轨迹。每轮上限十次模型调用、150 秒；检查器等待期间不调用模型。

| 阶段 | 实际结果 |
| --- | --- |
| 目标 | default 工作空间 / assistant 成员（小禾）/ agent_assistant 定义 |
| 创建 | 2026-10-29 02:11:43.391887 +08:00，由真实 Agent 调用 create_schedule，间隔 300 秒 |
| 首次计划时间 | 02:16:43.391887 +08:00，严格创建后五分钟 |
| 实际执行 | occurrence `30a75b661c5c55319db60baef5ae6945`，get_local_time 成功返回 `2026-10-29T02:16:45+08:00`，02:16:47 +08:00 已观察到 completed |
| 取消 | 真实 Agent 调用 get_schedule、delete_schedule、list_schedules；计划 `1aac54ae1e6946abb3b7f2b6031c740f` 为 deleted、next_fire=NULL |
| 收尾 | 确定性服务再次复查，活动计划总数 0；只有一次 completed 触发，取消后无新 pending 或周期执行 |

创建与取消留在同一普通会话 `a17a9c77706b447d8e83c31fbef0a074`；定时执行另开 occurrence 对应会话。最终再次启动新版并超过原下一周期时间后复查，测试计划仍已取消，触发历史仍只有一次。未删除这些普通验收会话，便于追溯。

公开证据保存在本机忽略目录 `.cache/scheduler-live-evidence.json`，包含 ID、时间、工具名、完成/取消状态，没有密钥或模型底层配置。可显式运行 `backend/tests/live_schedule_verification.py --allow-live --data-dir <原数据根> --evidence <报告路径>`；源码运行时须将 backend/src 放入 PYTHONPATH。脚本使用与应用一致的单实例锁，拒绝已有活动计划；finally 只取消本次新增计划，预检查退出也保护原有安排。此脚本会真实消耗模型额度，不由常规 pytest 自动运行。

## 3. Windows 独立发行

- PyInstaller 候选构建成功并经 publish.ps1 发布；活动清单为 `20261029-022130`，根 start.ps1 -Check 与实际启动指向同一个新版和原数据根。
- 冻结包包含 APScheduler 3.11.3 元数据、tzdata 2026.6 时区文件及 tzlocal 5.4.5；已核查 Asia/Shanghai 文件。
- 90 个正式界面文件与源码哈希一致；ZIP CRC 完整，无 private、DPAPI 凭据或用户会话文件。
- 实际发行 exe 启动成功，computer-use 目检会议室、右上角“定时任务”菜单及真实管理弹窗；当前黄金调研空间为空列表，和默认空间的已取消测试记录隔离。

真实五分钟执行验证的是正式源码后端；发行检查验证实际 exe 启动、资源和管理界面，不将两者混称为全新机器安装验证。签名、安装器、干净 Windows 机器兼容性、Windows 服务/开机自启/休眠唤醒仍未验收。
