# 多工作空间与桌面目录验收

日期：2026-10-26。范围见 [ADR-0007](../architecture/0007-workspace-rooms.md)。只使用独立缓存/临时数据和明确标记的模拟 Key；没有读取或发送真实模型凭据。

## 自动验证

| 检查 | 结果 | 核对内容 |
| --- | --- | --- |
| 完整 pytest | 79 passed，37.29 秒 | 既有真实 Deep Agents、SDK、工具、人工恢复、素材协议，加新增空间用例与桌面依赖检查 |
| Ruff | 通过 | backend 与 desktop 共 102 个 Python 文件格式不变，检查无问题 |
| mypy strict | 通过 | 两个源码包 77 个文件 |
| Node 表现协议 | 通过 | 原有动作、导航、生活活动与协作逻辑 |
| Node 空间 RPC | 通过 | 实际 api 函数显式绑定空间、颠倒返回顺序、切换期间拒绝业务调用、旧保存不覆盖新配置表单 |
| 空间目录 | 通过 | 一对一唯一 room_id、名称校验、16 空间边界、重命名保留 ID、跨重启恢复选择 |
| 实际空间执行 | 通过 | 两个 Runtime 同时执行；各自模型消息只含本空间任务；共享配置在忙碌时拒绝修改 |
| 旧数据与读隔离 | 通过 | 默认 data/ 原位保留；成员、会话、同名文件分开；跨空间事件/产物读取拒绝 |
| 未打开的人工待办 | 通过 | 真实 ask_user 暂停后重启，只打开另一空间仍显示待办数量并保护共享模型绑定；目录不含问题正文 |
| 桌面入口约束 | 通过 | 未知方法/空间拒绝，自由宿主素材路径不能通过 invoke 读取 |

测试启动条件现已等待真实会议室快照就绪，避免只看到桥已注入就抢先提交表单。生产执行器未添加测试等待或脚本答案。

## 原生 WebView2 流程

| 入口 | 结果 |
| --- | --- |
| desktop/tests/desktop_smoke.py | 模型表单保存、Key 清空、连接探测、真实 Deep Agents 写入/读回；3 次执行模型调用、2 个工具、1 个实际文件，合计 4 次 HTTP |
| desktop/tests/studio_smoke.py | 3 位实际人物、三版图集/双页、活动池持久化、人工等待与恢复、真实写文件、按需轨迹、全画布；3 次 HTTP |
| desktop/tests/workspace_smoke.py | 通过生产表单创建第二空间，3/2 名成员分开绘制；甲任务在乙房间后台完成，同名 proof.txt 分别存不同内容；草稿返回、重命名与标题同步；4 次 HTTP、2 个文件 |
| desktop/tests/collaboration_smoke.py | 配置成员 2 人站会，外援无形象；原逻辑工位不变、轨迹完整；8 次 HTTP、2 个真实产物 |
| desktop/tests/material_gallery_smoke.py | 4 套角色、12 家具、16 装饰、8 组特效；翻页、逐帧和覆盖矩阵通过 |

## 独立应用与发行检查

PyInstaller 已按两个源码包重新构建。冻结 exe 在独立预览目录启动，原生可访问性树确认标题 RoomCrew、默认空间会议室、四名预览人物及本地同步状态正常。正式用户数据目录未被预览使用。

最终打包的全部 44 个 desktop/ui 文件与源码逐字节核对一致。ZIP 共 361 项（含目录），CRC 检查通过，不含旧 frontend 用户界面、private 配置或 SQLite 数据。最后的界面回调/配色调整以完整资源同步后重新压缩，Python 冻结内容不变。

发行包：dist/RoomCrew-0.1.0-windows-x64.zip；大小 73,086,214 字节。

SHA-256：`28171e589ccb0ccc0ba67cefe5620c52ab556ad0874379b8fc970abae591750d`。

源码入口 packaging/desktop_entry.py；独立入口 dist/RoomCrew/RoomCrew.exe。需保留 _internal；当前环境仍是 Windows x64 + WebView2 / .NET 4.8。

后续墙面优化已同步：连续高墙按镜头补足高度，移除墙外地砖露出，并添加受光渐变、墙角与踢脚线；原生 studio_smoke 和两组 Node 协议检查通过。当前发行哈希已更新。

## 验证边界

上述模型响应来自本机协议服务，真实模型厂商、真实 Key、语义任务效果及全新 Windows 机器分发仍待用户验收。未实现空间删除、云端账号同步、管理员 frontend、任意代码、MCP、浏览器或安全 VM。
