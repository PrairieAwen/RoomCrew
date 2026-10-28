# 可配置素材与四沙发布景验收

## 2026-10-28：统一投影素材兼容预览

最新设计为 [ADR-0020](../architecture/0020-unified-projection-assets.md)。八类设备八向源帧、默认电脑桌高清单图、四名角色配套工作/六帧起坐已接入；本轮不是规范全部指标均通过的最终美术包。完整提示词、生成身份和未完成项见 `desktop/ui/studio/assets/scene-v2/README.md`。

- 默认电脑桌真实 alpha 硬边拟合约 -26.915°、+27.118°，地轴误差约 0.350°、0.553°。仅该方向做了像素量测。其他方向有统一三维底稿与静态注册，未宣称全部角度、刚性漂移及接触指标合格。
- Python 全量 132 passed；最后替换起坐图集后，素材/办公室专项 18 passed、规范专项通过。8 组 Node、Ruff、mypy 92 文件通过。源端原生流程在 `.cache/office-scene-smoke/4e15868fa2da40aba2e9d06165af8b29/` 通过；后续起坐留白修正已由发行资源完整流程再验。
- 最终发行 UI 原生流程：`.cache/office-scene-smoke/cab2eef0c10e4a1b93703cda5c0fb77f/`。真实 Deep Agents、隔离 Python、文件产物、人工恢复共 4 次本机合成模型请求；全起身/移动/转向/落座、八向白板保存、总览通过。单步最大约 0.2040 格，脚点侵入 0，最多 2 人物精灵；已目检工作近景、全景、起身/落座关键帧。
- 最终素材总览原生检查：`.cache/scene-gallery-smoke/fe53bcfe8de546b5bf4a1c026cd09a39/`，实际等待 14 类设备和四套配套/起坐 Canvas 出图。曾发现独立测试宿主的静态根目录设在子目录导致全图 404，已改为从 UI 根进入素材页；这是验收宿主修正，不能冒称修复了生产场景的全部图片。实际修复了跨目录人物图片路径，并为新版配套/起坐新增选择器。
- 目检发现第一次起坐原图的鞋底/椅轮跨越等分行列、出现相邻行黑碎片，已用内置 image_gen 重做留白。最终四角色画面再目检确认没有该碎片；不以修改原图 alpha 或隐藏角色方式绕过。

Windows 独立程序已发布并启动：

```text
dist/RoomCrew-material-preview/RoomCrew.exe
dist/RoomCrew-material-preview-windows-x64.zip
```

使用独立 `.cache/asset-v2-showcase` 数据，含四角色，不复制用户 Key 或会话。已通过桌面工具查看实际 exe 并切到完整会议室；未声称该 exe 已调用用户真实模型完成任务。完整工具流程使用发行 UI 与测试宿主验证。

ZIP 共 468 项、CRC 通过；100 个运行 UI 文件在源码、发行目录、ZIP 中逐字节一致。SHA256：

```text
f9dea2f073201053d9c459be3aede547296cf38dbf1e561b1dc5304e9487dc35
```

制作源网格与参考画布不打入包。新图仍为旧角色 seat22 兼容规格；全部动作八向、逐帧双手双脚、0.44 米新骨架、八人物负载和多 DPI / p95 性能验收尚未完成。原目录和用户数据保持可追溯，旧记录如下。

## 2026-10-28：配套椅交互与独立发行预览

现行实现为 [ADR-0019](../architecture/0019-paired-chair-interactions.md)。本轮纠正此前只靠独立人物贴椅子和静态数值验收的不足；并不据此声称已达最终商业游戏美术标准。

- 四套内置人物都有配套椅子和伸手工作片段，另有每角色六帧起坐。原椅/目标椅分开，拉椅与推回可见，起身后空椅保留，键盘从桌面图中分离；鞋底与椅脚使用各自原图登记值，按正确的 24/12 投影交接。
- 最终 Python **130 passed**；8 组 Node、Ruff、mypy（92 文件）通过。包含五页实际加载、原清单不变、起身期间再次换目标、原座归属、自定义素材回退、透明帧边界、默认拉椅区与自定义布局保护。
- 源码原生验证 `.cache/office-scene-smoke/42cbc822ae264f5ca2f01b8ec285fa15/`，真实经过六张离座、六张入座帧；已目检末端站立、落座与工作近景。之前错误的座点复用、根节点切换与透明双椅重影均经历失败/修正，失败轮次不算验收通过。
- 最终发行 UI 原生验证 `.cache/office-scene-smoke/b547a517db2742d593f1628a5af67e7b/`，使用发行目录实际 HTML/JS/PNG。已目检 working、working-close、离座/落座近景、resting；默认盆栽已避开第四工位拉椅区。模型请求 4 次，实际 Deep Agents、隔离 Python 文件产物及人工恢复通过；未调用用户真实 Key。
- 连续脚点侵入 0，单步最大约 0.1433 格，人物精灵最多 2。六帧片段采用逐帧动画，取消逐帧透明交叉，避免整张椅子重影；这些指标不代替画面检查。

本轮 Windows 独立预览为：

```text
dist/RoomCrew-interaction-preview/RoomCrew.exe
dist/RoomCrew-interaction-preview-windows-x64.zip
```

ZIP 452 项，CRC 通过；83 个 UI 文件在源码、发行目录、ZIP 中逐字节一致。SHA256：

```text
9dc530c7d93e80972d8cd0a10ef19460c069c540017bcd2cdc486cc230120c83
```

旧正式窗口处于空闲，但两次正常激活/关闭返回失败，未强制终止，也未覆盖原发行目录。新 exe 已以 `.cache/paired-chair-showcase` 独立数据启动并查看实际窗口，四套图集和新桌椅确实显示；受系统窗口激活失败影响，未替用户切到全会议室模式。顶部“会议室”按钮可切换。预览数据未复制模型配置和用户会话。发行目录的完整工作流验收由独立测试宿主完成，不能混称新 exe 已连接真实模型完成任务。

新增原图与生成来源在 `desktop/ui/studio/assets/scene-v1/generation-v3.json`，使用内置 image_gen，原图保存于项目；记录明确区分可恢复的设计描述与逐字原提示。配套交互限定标准椅与匹配人物，任意自制家具、全向全部动作、骨骼 IK 尚未完成。

## 2026-10-27 历史视觉修正与正式发行（2340）

本次按用户第二张目标图校准，现行设计为 [ADR-0018](../architecture/0018-coherent-office-art.md)。下文 scene-preview 为上一轮历史记录，不能据此判断当前正式版未更新。

- 统一桌椅、沙发、茶几比例；新增西北/东北伸手工作双帧、手绘窗景，修正椅背与会议桌遮挡、接触阴影、织物地毯与空输入区。
- Python 完整回归 **128 passed**，8 组 Node 全通过，包含正式 ensure/load 的四个显示页与原清单/数组不变；Ruff 与 mypy（92 源文件）通过。
- 最终源码原生验收为 `.cache/office-scene-smoke/46db3bb442c44c839df32c75bea6fa54/`；已逐张目检 working-close、working、resting，明确检查键盘、椅背、坐席和脚线。此前加载失败及比例试验不计为成功结果。
- 用独立宿主加载**正式发行目录的实际 UI 文件**再次跑通：`.cache/office-scene-smoke/61f3bf87869849d4be3634bf67d21728/`。真实 SDK、隔离 Python、人工恢复共四次合成模型请求；经过完整起身/移动/转向/落座，连续脚点侵入 0，同时人物精灵最多 2，最大单步约 0.094 格；八方向白板编辑与受限总览通过。该轮 working-close / resting 也已目检。
- 正式 exe 已启动并通过桌面工具查看实际用户窗口，切到完整会议室。旧 scene-preview 窗口已正常关闭；未强制终止进程。用户原会话计数前后均为 completed 7、cancelled 1，用户布局为 32×25、四沙发与一茶几；升级前布局备份到 `.cache/scene-layout-backups/before-cohesion.sqlite`，未复制或输出真实 Key。

当前发行位置为 `dist/RoomCrew/RoomCrew.exe` 及 `dist/RoomCrew-0.1.0-windows-x64.zip`。ZIP 共 447 项，CRC 通过；78 个 UI 文件在源码、发行目录和 ZIP 中逐字节一致。SHA256：

```text
2743bc9d75b49f3b9c76f31a1a431b1bb65a5c567fd6d49b539138e5f2490984
```

补充图像由内置 image_gen 生成，原图与完整提示词集位于 `desktop/ui/studio/assets/scene-v1/working-v2.png`、`window-garden-v2.png`、`generation-v2.json`。这不是全八方向完整工作动画或手部 IK；视觉检查通过也不等于最终商业美术验收。

## 上一轮素材合同与独立预览记录

日期：2026-10-27。设计与当前能力边界见 [ADR-0017](../architecture/0017-configurable-scene-assets.md)。

## 已执行检查

| 检查 | 结果与范围 |
| --- | --- |
| Python 完整回归 | 127 passed；后续逐向操作面元数据调整后，素材专项 10 passed |
| Node | 8 组全部通过；覆盖协议、动作、素材、泡泡、工作区、Markdown、相机、模型表单 |
| 静态 | Ruff 通过；mypy 92 个源文件通过；修改的场景脚本语法通过 |
| 统一目录 | JSON / JS 内容一致；14 类设备；原图矩形有界；逐向操作侧挂点存在 |
| 方向编辑 | 桌、椅、沙发、会议桌、白板、茶几各八向几何、可达与持久化通过 |
| 人物接触 | 四角色各八向坐姿选择及臀部、脚底支撑方程通过；自制非法坐标拒绝 |
| 房间升级 | 已知旧标准模板升级；移动过家具的自定义模板保留；四沙发入口均可达 |
| 原生 WebView | 真实 Deep Agents / 隔离 Python / 人工恢复；完整换座；真实表单八向保存；素材总览打开 |

最新原生报告：`.cache/scene-native.log`。截图在 `.cache/office-scene-smoke/8565bf9be855420a853a9a8d5656e410/`；已目检前一轮相同场景的 working / resting / rotation / assets 图像，确认实际使用新图集和四沙发布景。最后细调为非默认方向操作面挂点、预览脚底标记及初始镜头，不改变默认坐姿注册。

原生任务使用本机合成模型服务，模型请求 4 次，实际工具生成文件并在 ask_user 后恢复。并非真实模型质量评估，未使用用户 Key。连续移动最大单步约 0.13 格，脚点侵入计数 0，人物同时精灵最多 2；观察到 settled、stand_up、moving、turn_to_seat、sit_down 五种阶段。

## Windows 发行预览

本次保留原 `dist/RoomCrew`：正常关闭时窗口控制连续返回 `failed to activate captured window`，未强制结束原进程，未覆盖其目录。

新版单独发布并启动：

```text
dist/RoomCrew-scene-preview/RoomCrew.exe
dist/RoomCrew-scene-preview-windows-x64.zip
```

启动使用独立 `.cache/scene-showcase` 数据目录，没有复制真实模型配置或用户会话。已核对该程序创建的房间为 32×25、四张沙发、一张茶几，会话 Run 数为 0。原用户数据不迁移，原窗口保留。

ZIP 共 444 项，CRC 通过。75 个界面文件在源码、发行目录和 ZIP 中逐字节一致，office-v1 历史资源不打入新包。SHA256：

```text
5830bc04db352d763a7aef7f0a4fa101f6759817d4e54a2ebd7ed23615efbbf2
```

预览进程及目标窗口存在，但桌面捕获未返回目标应用画面，因此没有宣称发行窗口已完成截图验收；视觉检查依据本机原生 WebView 测试窗口和逐文件发行一致性。

## 明确没有完成的部分

- 新增八方向坐姿为接触关键帧，尚非所有动作的八向逐帧循环；部分手部动作复用兼容坐姿。
- 内置接触标记仍需美术逐帧精修；没有自动骨骼 IK、手部贴合或精确双脚物理。
- 已开放内置家具表单编辑与人物 PNG / JSON 导入；外部家具导入、拖拽布置、应用内骨骼/绘画编辑器未开放。
- 未在本次验证中替换原用户正在运行的发行目录，也未宣称该旧窗口已显示新版。
