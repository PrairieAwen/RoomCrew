# RoomCrew Desktop

- `ui/`：用户桌面界面、会议室画布、人物、素材与会话。
- `src/roomcrew_desktop/`：WebView2 窗口、桌面桥与本机生命周期。
- `tests/`：Windows 原生流程验证；`tests/web/` 是界面脚本与协议检查。
- `tools/`：素材登记和导出工具，不进入正式 Agent 工具目录。

本目录属于普通用户的本地应用；根 `frontend/` 只预留未来管理员 Web 界面。统一规范仍在根 `AGENTS.md`。

源码启动：`python packaging/desktop_entry.py`（使用根 `.venv`）。构建：`packaging/build.ps1`。
