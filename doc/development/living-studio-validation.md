# 生活、同任务协作与环境验收

日期：2026-10-26。分支：`codex/studio-interaction`。当前规则见 [ADR-0006](../architecture/0006-living-studio.md)。本页覆盖上一轮游戏素材基线的当前验收结论。

## 验证结果

| 项目 | 实际结果 |
| --- | --- |
| 全部后端回归 | **73 passed / 32.28s**；含真实 SDK、两类委派元数据、用户形象隐藏、活动池隔离与持久化、关系清理、地图全部锚点可达 |
| Ruff / 格式 | 通过，95 个 Python 文件 |
| mypy strict | 通过，75 个源码文件 |
| Node 动画协议 | 通过；299999/300000 毫秒轮换边界、同项避免重复、点击/任务打断、假聊天双向解除、旧闲聊路线停止、四格社交间距、会议归还及外援不增人物 |
| 原生会话窗口 | 3 次模型调用、2 次文件工具、1 个真实产物；加配置协议探测共 4 次 HTTP 请求 |
| 原生事务所窗口 | 3 位人物（基础 2 位加招募 1 位）、实际导入三版图集、双页切换、活动池持久化、人工等待/恢复/真实写文件/自动恢复空闲/再次点击停止；3 次 HTTP 请求 |
| 原生协作窗口 | 两轮真实 task 委派；2 名配置成员实际集合讨论，通用外援新增人物数为 0，2 份真实文件，8 次 HTTP 请求，持久化座位未变 |
| 原生素材总览 | 四套原图解码、跨页、暂停逐帧、各分类与覆盖矩阵通过；详情画布 138217 个非透明像素 |

五至十分钟的轮换使用正式导演的注入随机源/时钟做边界测试，没有缩短生产常量。真实窗口验收不修改导演、轨迹或动画时钟；回环模型服务的测试延迟只用于观察真实行走。日常应用没有生成模拟任务、加速轮换或硬编码产物的入口。

原生协作最终输出：`meetingMembers=2`、`externalAvatarCount=0`、`members=3`、`artifacts=2`、`seatsUnchanged=true`、`traceScope=true`、`http_requests=8`。测试使用真实 Deep Agents、任务工具、文件系统后端、SQLite 轨迹和生产页面；只替代远端模型协议响应，不使用真实 Key。

## 当前 Windows 发行包

- 路径：`dist/RoomCrew/RoomCrew.exe`；对外分发完整 `dist/RoomCrew-0.1.0-windows-x64.zip`。
- ZIP：**360 个条目、73070925 字节**，CRC 完整性检查通过。
- **43 个前端资源文件与源码逐字节一致**；归档无凭据、业务数据库、测试缓存和制作工具。
- SHA256：`c085c14e14b53aff33004f9f51caacb179cd989bb557ea7a77c95ce073d4b24c`。

已完整重建 Python 可执行程序与新表现模块；后续站位、低台和闲聊中断的前端修正同步到该发行目录，再压缩并校验。最后的 JS 修正通过 Node 专项检查；相对会议站位另通过原生协作复验。

## 可视检查与数据边界

使用 `.cache/living-studio-preview` 独立账号，导入阿晨、小禾、小岚与监管员四套实际素材。没有 User 形象；示范账号包含两名可配置员工，最低基础配置仍是助手和监管员。空闲随机算法与生产五至十分钟周期一致；假聊天仅有姿势/标签，不请求模型、不写会话。

手绘接待台、桌椅、会议桌、书架、沙发、绿植、落地灯、咖啡角已进入画面；相机适应宽屏，连续地面和边角植物弱化边界。复查后增加闲聊间距、优先相对会议点，并以低台替换遮挡监管员的高柜。原图像素未修改，素材来源仍为上一轮 imagegen 制作记录。

默认正式账号、真实 Key 和历史任务未被预览覆盖。旧 User 记录保留但不作为人物展示；接待台迁移只改场景标识和旧显示占位。人工问题、失败和实际任务进度始终优先；动画结束不提交业务终态，会议也不拖慢实际工具执行。

## 复现

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
node desktop/tests/web/protocol.test.cjs
& .\.venv\Scripts\python.exe desktop/tests/desktop_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/studio_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/collaboration_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/material_gallery_smoke.py
& .\.venv\Scripts\python.exe -m ruff check backend
& .\.venv\Scripts\python.exe -m ruff format --check backend
& .\.venv\Scripts\python.exe -m mypy backend/src
& .\packaging\build.ps1
```

真实模型厂商效果仍需人工填写配置后验收。八向/站坐/表情全组合、专业美术接触分层、多人避让交通、真实电话/通讯、任意代码和安全 VM 尚未完成；当前会议和闲聊均使用现有有限动作与确定性规则。
