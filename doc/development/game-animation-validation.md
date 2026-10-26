# 游戏表现与自定义素材验证

本页保留上一轮素材库基线；最新生活、协作、身份和环境验证见 [生活与协作验收](living-studio-validation.md)。最新规则由 ADR-0006 覆盖。

日期：2026-10-26。代码分支 `codex/studio-interaction`。功能合同见 [ADR-0005](../architecture/0005-game-animation.md)，完整素材样例见 [制作说明](../assets/crew-avatar-example/README.md)。

## 验证结果

| 项目 | 结果 | 实际范围 |
| --- | --- | --- |
| 全部后端回归 | 68 passed / 32.09s | 原有执行、配置与空闲回归，加四套真实素材、双页/缩放/路径边界、第二页篡改与 36 项物件裁切检查 |
| Ruff 与格式检查 | 通过，92 个 Python 文件 | 源码、测试及开发登记工具 |
| mypy strict | 通过，74 个源码文件 | 新素材文件名边界仍不依赖 Agent SDK |
| Node 协议与动画检查 | 通过 | 走跑、起坐、独立表情、事实优先、线索去重、历史终态、空闲计时/打断、人物独立时钟、姿态和图集回退 |
| 原生会话窗口 | 通过 | 3 次真实 SDK 模型请求、2 次真实文件工具、1 个产物，另有 1 次配置协议探测 |
| 原生游戏窗口 | 通过 | v1/v2/v3 图集、背面镜像、跨页裁切且 URL 不变，加空闲/真实任务/人工恢复的完整生命周期 |
| 原生素材展厅 | 通过 | 4 套真实角色解码、工作/基础跨页、暂停逐帧、非空画布、12/16/8 分类和 20×4 覆盖矩阵 |
| 真实素材样例 | 通过生产导入器 | 184 帧、37 变体、2048×1920 RGBA PNG + JSON，可直接试用和编辑 |

原生游戏验收最终返回：`atlasAnimated=true`、`traceExpression=true`、`fullCanvas=true`、`leisureLifecycle=true`、`persisted_leisure=true`、`handPaintedAtlas=true`；保存后重新打开账号库仍有 4 位人物，其中 1 位绑定手绘素材并保存浇花偏好。全会话原始日志游标仍为 0，只有明确展开人物轨迹后才读取该成员事件。仍仅发生 3 次合成模型 HTTP 请求，生活动作及素材连播不新增模型调用。

## 当前 Windows 发行包（四角色基础素材库）

发行包共 356 个条目、73,048,372 字节；CRC 检查通过，39 个前端文件与源码逐字节一致。包含四套角色 PNG/JSON、家具/装饰/特效原图、裁切登记与本地展厅，没有带入凭据、业务数据库、测试或制作工具。

SHA256：`a6ccebaa138089b0b06965794a31c05da511554f6073afc4b114ccee473a5475`。

完整库为老板 120 帧、小禾 128 帧、小岚 128 帧、监管员 120 帧，共 496 个登记姿态、每套 34 个片段变体/20 种动作语义。五种表情仅覆盖闲置姿态；西向镜像、工作复用打字，未虚报全部方向/姿态/表情组合。原始 PNG 像素保留，元数据分析修正了误选坐姿的员工默认站姿，并剔除独立相邻行残片。

最终视觉修正后另通过 7 项素材专项复验（3.92s）和原生展厅复验：采用主体连通区域分析与三张游戏帧的人工核查边界，剔除邻行鞋尖；家具/装饰按整页独立区域登记，修正茶几带入白板边角及不等高物件的网格裁切。只修改元数据，保留原图。全量执行回归与真实任务流程结果不变。

素材 iframe 新增有限 Esc 关闭消息；Node 检查拒绝非对应窗口来源和非关闭类型，不允许借消息调用桌面桥。最终 JS/元数据作为资源更新到已构建发行目录后重新打包，原有 Python 可执行内容未变，避免覆盖正在浏览的程序。当前预览重启后加载最终前端资源。

原生任务验收新增 `completeMaterialBundle=true`：实际导入小岚双页角色，读坐姿切第二页、跑步切第一页，两张 SVG 纹理 URL 保持不变；随后真实模型发起人工询问，用户答复恢复，真实工具写出文件。坐姿浇花缺帧仍正确回退内置骨架，不能冒充已绘制；只有 3 次合成模型 HTTP 请求。

展厅验收在真实 WebView2 中通过正式按钮切换，画布具有 138,682 个非透明像素；可暂停在跑步第 3/8 帧，分类数量与 21 行（含标题）动作覆盖矩阵一致，无水平溢出。测试从与应用相同的资源根导航，避免独立 HTTP 根遗漏共享脚本。发行版另用 `.cache/material-library-preview` 独立账号导入四套素材供可视验收，没有读取或改变正式账号配置。

素材说明位于 `desktop/ui/studio/assets/library-v1/README.md`；生成模式为 imagegen 内置工具，提示分别记录于 `doc/assets/library-v1-generation.json` 与 `doc/assets/library-v1-environment-generation.json`。12 件家具、16 件装饰及 8 组四帧特效已制作并可总览预览，房间渲染尚未替换；部分体型/边缘/接触和方向站坐组合仍待美术精修。

## 上一轮 Windows 发行包（含单角色手绘样板）

发行包共 334 个条目、52,308,621 字节；CRC 完整性检查通过。18 个前端资源文件与源码完全一致，包含 PNG、JSON 和样板说明，没有带入凭据、业务数据库、测试及制作工具。

SHA256：`79d83cf9ff137c718921dee24be88b324e6a77e287c8e14011f3645847a9ee30`。

实际 exe 使用 `.cache/portrait-preview` 的独立账号库显示最终比例的小禾手绘角色；默认账号与真实模型配置未改变。样板含 64 个姿态、14 个动作变体，正式注册 ID 为 `avatar:49fb7da01d70657017a4c2b23d1acdd3`。冻结程序已确认图片解码、裁切与坐姿手机表现可用；制作提示保存在 `doc/assets/atelier-v1-generation.txt`。

## 上一轮 Windows 发行包（含个人摸鱼动作）

已重建 `dist/RoomCrew/RoomCrew.exe` 与 `dist/RoomCrew-0.1.0-windows-x64.zip`，共 330 个条目、50,681,407 字节；ZIP CRC 检查通过，15 个界面文件与随附样例均与当前源码一致，没有带入测试数据、业务数据库或凭据文件。

SHA256：`fe901771dff35d856678ec2569aa2fd3628b3668b8a975849095f29828aa27ba`。

以实际 exe 和隔离的 `.cache/leisure-preview` 账号库验收，窗口同时显示老板玩手机、助手打游戏、员工浇花及各自的“摸鱼”标注，监管员保持值守。使用真实人物配置和正式播放器，没有创建业务任务、伪造轨迹或填写真实 Key。源代码的原生流程另外验证了接单/人工等待打断、完成后恢复及数据库重开持久化。

## 上一轮 Windows 发行包（摸鱼功能接入前）

已重新构建 `dist/RoomCrew/RoomCrew.exe` 与 `dist/RoomCrew-0.1.0-windows-x64.zip`。压缩包共 330 个条目、50,675,964 字节，CRC 完整性检查通过；15 个界面源文件和随附素材样例与当前源码一致，归档中没有私有凭据、业务数据库、测试或素材导出工具。

SHA256：`ba200998aa7e8086862d59eed426e506f22c7e384a28763dfe0395260778270b`。

通过实际冻结后的 exe，在独立的 `.cache/frozen-animation` 数据目录中打开全窗口事务所、进入添加成员、点击“试用示例素材”，确认 Pillow PNG 解码、清单校验、本地复制与角色预览均正常。素材注册为 `avatar:af3daf570d780631bfdd552f708d6297`，原图颜色的预览可见；该验证未填真实 Key、未修改用户正式数据。

## 自动验收怎样运行

- 模型服务仅监听回环地址并返回协议响应；执行器、Deep Agents、文件工具、人工 interrupt/checkpoint、SQLite 和动画播放器均为生产实现。
- 原生文件选择回调只返回测试自己的 PNG+JSON 路径，后续图片解码、清单校验、元数据清理、复制、选帧和绑定走真实代码。
- 游戏动画测试使用可见 WebView2 窗口。隐藏/完全遮挡窗口时 Chromium 可以暂停动画帧；不能将隐藏窗口没有帧回调误判成素材导入失败，也不能为了测试而在生产中伪造动画时间。
- 图集制作样例由正式矢量骨架在真实浏览器 Canvas 上逐帧导出，随后用生产导入器复验，不是空白占位 PNG。

## 重要边界

1. 图集清单中的脚本、URL、目录跳转和 Windows 设备名在访问前被拒绝；非法帧号、布尔帧号、重复变体、错误文件类型和超出尺寸均失败。
2. 导入后的源路径不进入账号配置；规范化 PNG 不保留原始元数据。图集若被手工修改，旧内容 hash 读取失败。
3. 人物素材绑定持久化，但不进入 Agent prompt、Run 定义或模型请求消息。所有素材操作都属于人工界面，不注册为 Agent 工具。
4. 跑步和疑问表情可以并行；起坐和行走阶段互斥，旧计划被拒绝。重规划观察点仍需后端验证格网与家具阻塞。
5. 片段线索与动画结束不能决定任务状态，快速回顾不表示任务仍在执行。保留真实待答复、失败、取消和结束标签。
6. 当前美术是骨架与可替换手绘 PNG 图集，支持有界双页；专业商业美术、全组合变体、绘画编辑器、外部骨骼动画、无限多页与道路避让未完成。

## 复现命令

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
node desktop/tests/web/protocol.test.cjs
& .\.venv\Scripts\python.exe desktop/tests/desktop_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/studio_smoke.py
& .\.venv\Scripts\python.exe desktop/tests/material_gallery_smoke.py
& .\.venv\Scripts\python.exe -m ruff check backend
& .\.venv\Scripts\python.exe -m ruff format --check backend
& .\.venv\Scripts\python.exe -m mypy backend/src
& .\packaging\build.ps1
```

真实服务商与用户 Key 的兼容性仍未验收；自动回归不替代实际模型质量测试。安全 VM、任意代码、MCP 和 Computer Use 仍未开放。
