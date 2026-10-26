"""用户界面的具名业务入口，不注册为 Agent 工具。"""

from typing import Any

from roomcrew.desktop.host import RuntimeThread
from roomcrew.desktop.responses import public_reply


class DesktopAPI:
    def __init__(self, host: RuntimeThread) -> None:
        """因为前端只能调用明确业务接口，需要用桌面桥封装后端而不暴露存储对象。"""
        # 1、私有成员不会作为前端公共桥方法发布。
        self._host = host

    @public_reply
    def overview(self) -> dict[str, Any]:
        """因为窗口启动需要恢复本地状态，需要提供会话和能力概况。"""
        # 1、通过所属线程读取状态。
        return self._host.call(self._host.runtime.overview())

    @public_reply
    def configuration(self) -> dict[str, Any]:
        """因为用户需要编辑已保存配置，需要提供不含 Key 的人工配置视图。"""
        # 1、该入口属于用户界面，不注册成 Agent 工具。
        return self._host.call(self._host.runtime.configuration())

    @public_reply
    def save_configuration(self, values: dict[str, Any]) -> dict[str, Any]:
        """因为用户手动输入模型信息需要持久化，需要将表单交给本机可信配置服务。"""
        # 1、不在桌面桥打印或缓存密钥。
        return self._host.call(self._host.runtime.save_configuration(values))

    @public_reply
    def test_connection(self) -> dict[str, Any]:
        """因为用户需要确认配置能用于工具调用，需要启动真实模型协议探测。"""
        # 1、把结果返回配置界面，不把探测提示注入普通会话。
        return self._host.call(self._host.runtime.test_connection())

    @public_reply
    def new_conversation(self) -> dict[str, Any]:
        """因为用户需要独立会话，需要建立新的线程和产物目录绑定。"""
        # 1、由后端生成会话 ID。
        return self._host.call(self._host.runtime.new_conversation())

    @public_reply
    def submit(self, conversation_id: str, text: str, request_id: str) -> dict[str, Any]:
        """因为用户提交后界面应继续响应，需要只等待任务受理而不是等待模型全部执行。"""
        # 1、由 Runtime 创建真正的异步执行任务。
        return self._host.call(self._host.runtime.submit(conversation_id, text, request_id))

    @public_reply
    def events(self, conversation_id: str, after: int) -> list[dict[str, Any]]:
        """因为会话轨迹需要跨重启回放，需要按游标读取落盘后的事件。"""
        # 1、传输普通产品事件，不返回 LangChain 私有类型。
        return self._host.call(self._host.runtime.events(conversation_id, after))

    @public_reply
    def stop(self, run_id: str) -> dict[str, Any]:
        """因为用户需要中止执行，需要把明确的停止请求转给任务管理器。"""
        # 1、停止的是指定运行，不操作用户其他程序。
        return self._host.call(self._host.runtime.stop(run_id))

    @public_reply
    def artifacts(self, conversation_id: str) -> list[dict[str, Any]]:
        """因为用户需要核对交付，需要列出当前会话真实存在的产物文件。"""
        # 1、不从模型回答中猜测文件清单。
        return self._host.call(self._host.runtime.artifacts(conversation_id))

    @public_reply
    def read_artifact(self, conversation_id: str, path: str) -> dict[str, Any]:
        """因为查看产物不能获得任意系统文件读取权限，需要通过后端验证虚拟路径。"""
        # 1、返回纯文本预览，不执行产物内容。
        return self._host.call(self._host.runtime.read_artifact(conversation_id, path))
