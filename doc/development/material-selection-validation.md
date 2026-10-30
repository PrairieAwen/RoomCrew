# 人物素材选择与保存验收

2026-10-30，修复“随附角色选了小橘，但预览与保存仍是小岚”的操作断层。

## 行为与实现

原界面两个选择框分工不明确：下方只选择待导入角色，需要额外点击“导入完整角色”；上方才是实际保存的素材引用。现在下方 change 事件直接复用 importSource，导入、刷新目录、解码完成后更新预览。上方标明“当前人物素材（已导入）”，下方有选择即预览的可见说明。

- 导入中禁用保存，实际 submit 处理也校验状态，不能靠快捷键绕过并写入旧引用。
- 注册与目录读取之后分别检查代次；新选择胜出，关闭或重开表单不应用旧响应。
- 解码失败显示错误并阻止保存；可重试随附角色、重新加载或选择已有素材恢复。
- 明确保存后才绑定成员；取消编辑只保留已导入库文件，不创建成员或改变已有绑定。
- 后端、Agent 定义和素材格式不变，没有修改实际模型配置或权限。

## 验证

- `desktop/tests/web/material-selection.test.cjs`：颠倒注册/目录返回，校验最新选择；加载中绕过 disabled 提交仍被阻止；解码失败重试、关闭后的迟到响应。
- `desktop/tests/material_selection_smoke.py`：正式 WebView2、DesktopAPI、图像解码和 SQLite，选择 hippo 后仅触发 change，不额外点击导入；保存、重新编辑、实际场景和快速改选/取消均通过。
- 源码原生记录 `.cache/material-selection-smoke/94b5ae3eb2bd4c40892f22afd846f772/result.json`：automaticPreview、saveGuard、reopened、latestWins、cancelPreservesBinding 均为 true；仓库重读为 `avatar:27c5734b3cc039323c9fda743e22e089`，截图已目检。
- 24 项素材/规范/分层相关 Python 验证及 12 组 Node 检查通过；ruff 与 mypy 通过。本次不调用真实模型，不消费用户 Token。
- 候选包 `.cache/material-selection-20261030/RoomCrew` 已构建。直接加载其中 `_internal/desktop/ui` 复验，上述条件全部通过，记录在 `.cache/material-selection-smoke/7ccc22dc4c0941c7aafc3fa51c4bd3c8/result.json`。materials.js、controller.js 与 index.html 的 SHA256 均与当前源码一致。

用户确认保存后更新并重启；更新前已核对“新成员”保存为小橘内容 ID，且没有活动 Run。2026-10-30 发布并通过 `start.ps1` 切换至 `20261030-101308`，仍使用 `.cache/asset-v2-showcase`，未复制或迁移模型配置和会话。发行 ZIP SHA256：`736012415EE1D76A1C9456B320A045DD03F0E0605FF9CCDF0DE8EB934B5BA147`。
