# 统一投影素材 · 第一批兼容预览

本批按 `doc/assets/asset-production-standard/README.md` 开始重制，当前状态为 **兼容预览**。不能将本目录全部标为通过规范所有指标的 verified 包。

## 已接入

2026-10-28 代码整理后，登记器直接选择本目录几何源帧；无运行引用的旧 scene-v1 图和 office-v1 已删除。运行合同仍为 scene-assets v1，当前人物帧、112 个设备方向槽和键盘附件保持一致。旧来源记录的历史文件通过 Git 追溯。

- 电脑桌、办公椅、双人沙发、会议桌、茶几、白板、档案柜、书架，共八类八向源帧。监管台复用电脑桌。默认东南电脑桌另用更清晰的单件原图。
- 四名角色各四张配套椅姿势：背向待命、打字 A、打字 B、正面待命；各六张起坐关键帧，反序用于落座。东北/西南交互仍明确镜像复用，不计作独立原绘。
- 总览保留旧八向坐姿参考，新增“新版人物与椅子”“新版六帧起坐”和动作帧选择器。
- 显示仍使用既有 scene-assets v1 合同，由 `packaging/register_scene_assets.py` 写入 scene-v1/catalog.json 与同内容 JS。导入器没有新增对制作端 profile JSON 的支持。

## 制作与校准

1. `packaging/generate_geometry_guides.py` 用固定相机生成实体、八向旋转、投影角点、深度绘制网格；`source/` 中 PNG 是带深度遮挡的制作参考，SVG 是便于读坐标的简化底稿。成品 PNG 由内置 image_gen 绘制，没有用 Python 修图。
2. 地面投影为 x=24(gx-gy)、y=12(gx+gy)，高度项为 -12√6·gz。地轴倾角 26.565°，相机仰角 30°。旋转 45° 的家具不能强套地砖的两组边线。
3. 成品图集未严格保持底稿的源像素密度，作者注册按固定实体投影作一次等比校准，保留 `outline_width_ratio` 审计。运行时不按当前帧透明框缩放或追踪挂点；这一步兼容处理仍不等于完成了严格的整包同密度导出。
4. 本批坐具沿用旧角色兼容规格 `legacy-character-seat22`，座高 22 视图单位。它不是规范中的 0.44 米新骨架样板。配套椅原点与鞋底交接继续使用 ADR-0019 的显式换算。
5. 默认桌子的两条无遮挡硬边从真实 alpha 轮廓拟合，约 -26.915°、+27.118°，相对地轴偏差约 0.350°、0.553°。仅该方向完成该项像素量测，不能推为所有方向都已通过一度目标。

## 来源

`generation.json`、`furniture-generation.json`、`character-generation.json`、`workstation-generation.json`、`packing-repair.json` 保存完整提示词、引用和生成身份。选用图像：

| 文件 | 内置 image_gen 生成身份 |
| --- | --- |
| workstation-se.png | exec-621e7532-d2f0-4b7a-b8a0-0a797fa900e1 |
| workstation.png | exec-3d9f91de-9934-487f-b927-b9c1ae08cabc |
| chair.png | exec-f92ebac6-8638-4099-a80e-bdaa3d8416f7 |
| sofa.png | exec-bca468f0-9de3-43a5-ad54-d00b0d26bba3 |
| meeting.png | exec-11d789e4-da6f-4862-82f4-4b3abf0ff09b |
| tea_table.png | exec-5a32b250-2824-464b-8b76-55c97fcac9bd |
| screen.png | exec-a6d929ec-a7de-40d5-be8f-95f803f2b767 |
| archive.png | exec-073db6fb-d727-483c-a2e5-fb5e0a6a6654 |
| bookcase.png | exec-e9a75562-3200-4359-9c6e-04cc4b2df946 |
| paired-chair-v2.png | exec-8b914b2a-7109-41f5-9cc7-774645905ca0 |
| chair-rise-v3.png | exec-d28318ed-b8cb-4294-9375-80097439e9a7 |

## 尚未完成

2026-10-30 增补：`telephone-calls.png` 为五套角色各两张贴耳通话关键帧，生成身份 `exec-9d1f40d2-076d-4acb-809c-f30c7fe7c126`，完整提示见 `telephone-generation.json`。它只在 MCP 一次性演出期间使用，不替代闲置玩手机。原绘五行不是等高网格，`packaging/register_action_assets.py` 按实测透明间隙登记；主场景登记重建后须最后运行该脚本恢复通话补页。额外单份 RGBA 解码约 6 MiB，仍未完成整应用帧耗时与内存峰值验收。

全动作八向动画、逐帧双手/双脚/注视骨点、IK、0.44 米新骨架、所有视角像素级轴线和刚性部件漂移验收尚未完成。沙发仍一个主坐席。键盘沿用旧独立附件的四向覆盖，部分摸鱼动作仍用旧图。冰箱、咖啡机、植物和落地灯本轮未重绘。

十一张 PNG 的单份 RGBA 解码理论体积约 66 MiB，不等于实际进程或显存测量。未完成八人物负载、所有 DPI、p95/p99 帧耗时的性能验收。制作底稿不打入运行发行包；成品和来源记录保留在项目。
