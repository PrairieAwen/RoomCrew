# RoomCrew 角色素材制作与导入

本目录是完整可导入样例：`avatar.json` + `atlas.png`，包含 184 帧、37 个动作变体。由正式矢量骨架导出，可复制到自己的文件夹后修改 PNG 中的角色和 JSON 中的动作安排。应用中“人物属性 → 试用示例素材”也可以直接使用。

## 导入步骤

1. 在“我的团队”新增成员，或选中人物后打开“属性”。
2. 点击“导入本地素材”，选择 `avatar.json`；PNG 放在同一目录。
3. 用动作、表情、朝向、姿态菜单预览。它们只是素材预览，不创建 Agent 任务。
4. 点击“保存到本地”绑定该人物；不同人物可以绑定不同素材，也可共享同一 Agent 定义。
5. 重新打开应用后绑定仍有效。PNG/JSON 已复制到应用数据目录，不依赖原文件夹。

## 文件结构与清单

```text
我的角色/
  avatar.json
  atlas.png
```

下面是最小清单示例；本目录真实 avatar.json 提供完整动作安排。

```json
{
  "format": "roomcrew.avatar",
  "version": 1,
  "name": "我的角色",
  "image": "atlas.png",
  "frame_size": [128, 160],
  "pivot": [64, 151],
  "pixel_art": false,
  "clips": [
    {
      "action": "idle",
      "direction": "se",
      "posture": "standing",
      "expression": "neutral",
      "frames": [0, 1, 2, 3],
      "fps": 12,
      "loop": true
    }
  ]
}
```

每一格都使用 frame_size。帧号从 0 开始，从左到右、从上到下排列：`帧号 = 行号 × 每行格数 + 列号`。PNG 宽高必须是帧宽和帧高的整数倍。空白帧不会自动补图，需由作者提供有效内容。

脚底锚点 pivot 是该格内的像素坐标，所有帧的角色脚底必须对齐。整帧在世界中归一为 128 个显示单位，建议人物主体约占帧高的 85%～90%，保持脚底和头顶少量透明边距。这样换素材后不会忽大忽小或浮空。

## 可用词表

本目录继续使用 v1 等格格式。新增手绘样板位于 `desktop/ui/studio/assets/atelier-v1/`，使用 v2 非等格裁切：额外提供 `frame_rects`（每项 `rect:[x,y,w,h]` 与 `offset:[x,y]`），源矩形须在 PNG 内、目标矩形须在统一 `frame_size` 内。最多 512 个裁切帧；片段 `frames` 引用这些矩形的下标。v2 必须提供裁切表，v1 不接受裁切表；其余动作与安全边界一致。可选布尔 `mirror_west` 允许播放器镜像西向，不允许任意脚本或远程资源。

| 字段 | 值 |
| --- | --- |
| action | idle、think、read、type、write、work、talk、ask、report、alert、listen、walk、run、sit_down、stand_up、sit、phone、game、water、relax |
| expression | neutral 中性、focused 专注、curious 疑问、concerned 担忧/提醒、smile 微笑 |
| direction | e 右、se 右下、s 下、sw 左下、w 左、nw 左上、n 上、ne 右上；按屏幕方向定义 |
| posture | standing 站立、seated 坐姿 |
| loop | true 循环播放；false 到最后一帧保持 |

同一 action 可以提供多种表情、朝向和姿态组合。组合不能重复。至少提供一个 standing 的 idle；建议优先制作 idle、walk、run、read、write、ask、alert，以及 seated idle。

本样例含四个方向的行走/小跑、站立与坐姿工作动作、起坐过渡及 idle 的五种表情。词表支持八向；未制作的朝向会选择最近变体。可以让 `write` 画成写字、敲键盘或其他符合自己角色风格的动作，无须改 Agent Loop。

## 清晰度与动作质量

- 当前支持帧宽 32～512、帧高 48～512。需要更多细节时增加单帧尺寸，并在图集容量内安排状态；不是把同一张小图放大。
- PNG 单边不超过 2048 像素，源文件不超过 4 MiB；不接受 APNG、GIF、JPEG 或脚本素材。透明背景推荐 RGBA。
- 推荐行走 8～16 帧、小跑 8～16 帧，工作与表情按需要制作；支持每动作 1～120 帧、1～60fps。帧越多不自动代表动作自然，脚底稳定与关键姿态更重要。
- pixel_art=true 使用像素风缩放；false 使用平滑缩放。PNG 原图配色不会被内置角色的颜色表单重染。
- 缺少工作动作时回退同姿态 idle；缺少摸鱼动作或坐姿等整个姿态时使用内置骨架。问题和报错徽记仍会显示。
- 当前是单 PNG 图集格式；多图集、骨骼动画文件导入和应用内绘画编辑器尚未提供。

素材会被校验、去除元数据并复制到本地库。描述文件不能包含 URL、脚本、目录跳转或权限字段；它不能改变 Agent 能做什么。

## 自制摸鱼动作

在人物属性里选择“没有工作时”的动作与等待秒数。先在 PNG 里绘制实际片段，再在 `clips` 中添加 `phone`（手机）、`game`（游戏）、`water`（浇花）或 `relax`（任意自绘休闲）。例如给 `relax` 画成喝茶，无须改 Agent Loop。配置按人物独立保存，不改变共享 Agent 定义。

待添加片段示例（帧号 4—11 必须真的画有对应内容，不能只复制清单而不补图）：

```json
{
  "action": "phone", "direction": "se", "posture": "standing",
  "expression": "smile", "frames": [4, 5, 6, 7, 8, 9, 10, 11],
  "fps": 8, "loop": true
}
```

需要坐着休闲时提供 `posture: "seated"` 变体。当前 184 帧样例仍是工作/移动基线，没有新增摸鱼片段，缺帧回退内置手机、游戏、盆栽或伸懒腰动作。动作菜单可以预览；真实场景只有所有工作、人工问题和提醒都清空后才播放，接单立即停止，不消耗模型额度。

## 开发者重新生成

`desktop/tools/python/export_avatar_template.py` 调用正式骨架，在真实 WebView2 中导出本目录样例；已有文件时拒绝覆盖。导出工具不随应用运行，样例 PNG 和 JSON 随发行包提供。
