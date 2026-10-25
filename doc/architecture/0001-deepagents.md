# ADR-0001：Agent Loop 使用 Deep Agents

状态：已接受。依据：用户明确决定。

使用 Deep Agents 作为 Agent Loop 底座。RoomCrew 自己掌握员工身份、工作空间、任务、共享事实、权限和界面事件。
当前仅准备依赖，不创建生产适配器、不自写另一套 Loop、不 Fork 上游。

正式集成时通过公开扩展点与应用自己的接口隔离框架类型，模型消息和 checkpoint 不直接成为产品协议。
依赖固定到已核实的 Deep Agents 0.7.32；升级需要记录版本变化并验证受影响行为。

此前讨论的自建 Rust Loop 不再作为当前主线。Tauri / React / PixiJS 等界面候选仍需要后续验证。

官方参考：
- https://docs.langchain.com/oss/python/deepagents/overview
- https://docs.langchain.com/oss/python/deepagents/customization
- https://pypi.org/project/deepagents/0.7.32/
