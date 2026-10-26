"""确定性协议测试：替代远端模型响应，但真实运行 SDK、Deep Agents、工具和 SQLite。"""

import asyncio
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from roomcrew.application.options import RunOptions
from roomcrew.application.runtime import Runtime
from roomcrew.config.schema import ConfigurationError
from roomcrew.config.store import ConfigStore
from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.host import RuntimeThread

TEST_KEY = "synthetic-test-key-never-a-real-credential"
TEST_MODEL = "private-test-model-identifier"


def tool_message(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """因为协议测试需要标准函数调用，需要构造与服务商一致的工具请求消息。"""
    # 1、测试消息仅在测试服务中使用，生产运行时没有脚本化答案。
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_" + uuid4().hex,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


@contextmanager
def model_server(
    messages: list[dict[str, Any]],
    *,
    status: int = 200,
    delay: float = 0,
    statuses: list[int] | None = None,
    error_code: str | None = None,
):
    """因为不能用真实 Key 做自动回归，需要启动只监听回环地址的可控模型协议服务。"""
    # 1、记录实际收到的协议数据，以验证真实 SDK 和工具结果往返。
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            """因为测试请求可能包含模拟凭据，需要禁止 HTTP 服务默认打印请求细节。"""
            # 1、测试断言直接使用内存记录，不输出请求头。
            return

        def do_POST(self) -> None:
            """因为真实 SDK 会发起 HTTP 请求，需要按脚本返回标准 Chat Completions JSON。"""
            # 1、保存请求内容用于断言，延迟和错误状态用于失败路径测试。
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            index = len(requests) - 1
            response_status = statuses[min(index, len(statuses) - 1)] if statuses else status
            time.sleep(delay)
            message = messages[min(index, len(messages) - 1)]
            response = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": TEST_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            }
            if response_status != 200:
                response = {
                    "error": {
                        "message": f"provider echoed {TEST_KEY}",
                        "type": "test_error",
                        "code": error_code,
                    }
                }
            # 2、客户端取消后允许连接关闭，不能把预期中断变成测试后台异常。
            try:
                encoded = json.dumps(response).encode()
                self.send_response(response_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        # 2、测试结束后关闭监听，不留下业务服务或模型替身进程。
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


async def configured_runtime(
    root: Path, endpoint: str, options: RunOptions | None = None
) -> Runtime:
    """因为每个测试必须独立存储，需要在临时目录建立真实配置和运行时。"""
    # 1、使用明确标注的模拟 Key，调用与桌面表单相同的配置入口。
    runtime = Runtime(AppPaths.create(root), options)
    await runtime.start()
    await runtime.save_configuration(
        {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
    )
    return runtime


async def wait_finished(runtime: Runtime) -> None:
    """因为提交接口会立即返回，需要等待真实执行协程结束再检查结果。"""
    # 1、限制测试等待时间，避免无限 Loop 把回归测试挂住。
    async with asyncio.timeout(20):
        while runtime.active:
            await asyncio.sleep(0.02)


@pytest.mark.integration
async def test_real_loop_writes_reads_and_preserves_context(tmp_path: Path) -> None:
    """因为框架必须真实完成文件交付，需要验证 SDK、工具、checkpoint 和第二轮上下文。"""
    # 1、测试服务只规定协议响应，所有文件操作都由生产框架的真实工具完成。
    responses = [
        tool_message("write_file", {"file_path": "/result.txt", "content": "普通测试资料"}),
        tool_message("read_file", {"file_path": "/result.txt"}),
        {"role": "assistant", "content": "已写入并读回核对。"},
        {"role": "assistant", "content": "继续处理同一会话。"},
    ]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "保存给定测试资料并核对", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert (runtime.paths.session_files(conversation["id"]) / "result.txt").read_text(
                "utf-8"
            ) == "普通测试资料"
            events = await runtime.events(conversation["id"])
            assert any(e["kind"] == "tool.completed" for e in events)
            assert any(e["kind"] == "assistant.message" for e in events)
            # 2、真实请求中的消息不含 Key、端点或模型配置；原始模型 ID 只在协议 envelope 中。
            for request in requests:
                context = json.dumps(request["messages"], ensure_ascii=False)
                assert (
                    TEST_KEY not in context
                    and TEST_MODEL not in context
                    and endpoint not in context
                )
                names = {item["function"]["name"] for item in request["tools"]}
                assert "execute" not in names and "task" in names
            await runtime.submit(conversation["id"], "接着处理", uuid4().hex)
            await wait_finished(runtime)
            assert any(m.get("role") == "tool" for m in requests[-1]["messages"])
            assert TEST_KEY not in json.dumps(await runtime.events(conversation["id"]))
        finally:
            await runtime.close()
        # 3、checkpoint 字节中不能出现真实密钥和原始模型 ID。
        for database in (tmp_path / "data").glob("*.sqlite*"):
            assert TEST_KEY.encode() not in database.read_bytes()
            assert TEST_MODEL.encode() not in database.read_bytes()


@pytest.mark.integration
async def test_subagent_events_share_one_conversation(tmp_path: Path) -> None:
    """因为委派不能拆散用户会话，需要验证真实 task 工具与子 Agent 轨迹归并。"""
    # 1、要求真实框架进入独立子 Agent，再实际写文件并向父 Agent 汇报。
    responses = [
        tool_message(
            "task",
            {"description": "将给定资料写到 /child.txt。", "subagent_type": "general-purpose"},
        ),
        tool_message("write_file", {"file_path": "/child.txt", "content": "子任务产物"}),
        {"role": "assistant", "content": "子任务完成。"},
        {"role": "assistant", "content": "已收到子任务结果。"},
    ]
    with model_server(responses) as (endpoint, _):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "委派员工保存给定资料", uuid4().hex)
            await wait_finished(runtime)
            events = await runtime.events(conversation["id"])
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert (runtime.paths.session_files(conversation["id"]) / "child.txt").exists()
            assert any(e["scope"] != "main" and e["kind"] == "tool.started" for e in events)
            assert any(
                e["kind"] == "task.assigned" and e["payload"].get("delegation_kind") == "external"
                for e in events
            )
            assert any(e["payload"].get("presentation_external") for e in events)
            assert {e["conversation_id"] for e in events} == {conversation["id"]}
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_key_protection_and_file_boundaries(tmp_path: Path) -> None:
    """因为配置不可进入 Agent 文件视图，需要验证加密、公共响应、路径越界和凭据沿用规则。"""
    # 1、实际调用 Windows DPAPI 保存配置，验证磁盘和公共响应没有 Key。
    paths = AppPaths.create(tmp_path)
    store = ConfigStore(paths.private)
    profile = store.save(
        {"base_url": "https://example.invalid/v1", "model": TEST_MODEL, "api_key": TEST_KEY}
    )
    assert TEST_KEY.encode() not in store.path.read_bytes()
    assert TEST_MODEL.encode() not in store.path.read_bytes()
    assert TEST_KEY not in json.dumps(profile.public())
    assert store.load().api_key == TEST_KEY
    with pytest.raises(ConfigurationError):
        store.save({"base_url": "https://changed.invalid/v1", "model": TEST_MODEL, "api_key": ""})
    # 2、生产文件后端必须拒绝父目录和私有文件真实路径访问。
    from deepagents.backends import FilesystemBackend

    backend = FilesystemBackend(paths.session_files(uuid4().hex), virtual_mode=True)
    for path in ("/../../private/model-config.dpapi", str(store.path)):
        try:
            result = backend.read(path)
        except ValueError:
            continue
        assert result.error is not None


@pytest.mark.integration
@pytest.mark.parametrize(
    "status,code", [(401, "MODEL_AUTH"), (429, "MODEL_RATE_LIMIT"), (500, "MODEL_UNAVAILABLE")]
)
async def test_model_errors_are_redacted_and_not_retried(
    tmp_path: Path, status: int, code: str
) -> None:
    """因为服务商可能在错误中回显凭据，需要验证认证失败分类和禁用隐式重试。"""
    # 1、返回含模拟秘密的认证错误，检查生产轨迹只保留稳定错误码。
    with model_server([{"role": "assistant", "content": "unused"}], status=status) as (
        endpoint,
        requests,
    ):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "普通任务", uuid4().hex)
            await wait_finished(runtime)
            events = await runtime.events(conversation["id"])
            assert len(requests) == 1
            assert events[-1]["payload"]["code"] == code
            assert TEST_KEY not in json.dumps(events)
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_cancel_idempotency_and_restart_history(tmp_path: Path) -> None:
    """因为用户会重复点击或关闭应用，需要验证幂等、取消和重启后的真实历史。"""
    # 1、延迟模型响应，确保取消发生在真实请求期间。
    with model_server([{"role": "assistant", "content": "完成"}], delay=1) as (endpoint, _):
        runtime = await configured_runtime(tmp_path, endpoint)
        conversation = await runtime.new_conversation()
        request = uuid4().hex
        first = await runtime.submit(conversation["id"], "测试取消", request)
        second = await runtime.submit(conversation["id"], "测试取消", request)
        assert first["run_id"] == second["run_id"]
        await asyncio.sleep(0.15)
        await runtime.stop(first["run_id"])
        assert runtime.store.latest_status(conversation["id"]) == "cancelled"
        await runtime.close()
        # 2、重新打开相同数据根后仍可回放，终态不伪装成继续运行。
        runtime = Runtime(AppPaths.create(tmp_path))
        await runtime.start()
        try:
            assert (await runtime.events(conversation["id"]))[-1]["kind"] == "run.cancelled"
            with pytest.raises(ValueError, match="中断或失败"):
                await runtime.submit(conversation["id"], "不能盲目续跑", uuid4().hex)
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_connection_probe_is_real_tool_protocol(tmp_path: Path) -> None:
    """因为连接测试不能是本地假成功，需要验证实际 HTTP 调用和标准工具响应检查。"""
    # 1、正确工具调用返回成功，普通文本返回不能冒充支持工具。
    responses = [
        tool_message("roomcrew_connection_probe", {"value": "ok"}),
        {"role": "assistant", "content": "仅普通文本"},
    ]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            assert "连接成功" in (await runtime.test_connection())["message"]
            with pytest.raises(ValueError, match="未得到标准工具调用"):
                await runtime.test_connection()
            assert len(requests) == 2
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_corrupt_configuration_can_be_replaced(tmp_path: Path) -> None:
    """因为本地文件可能损坏，需要允许用户重新填写配置修复，同时禁止沿用不可读的旧 Key。"""
    # 1、模拟损坏的配置文件，用户界面仍应能进入修复状态。
    runtime = Runtime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        runtime.config.path.write_bytes(b"corrupt-test-data")
        assert (await runtime.configuration())["recovery_required"] is True
        await runtime.save_configuration(
            {"base_url": "https://example.invalid/v1", "model": TEST_MODEL, "api_key": TEST_KEY}
        )
        assert (await runtime.configuration())["configured"] is True
    finally:
        await runtime.close()


@pytest.mark.integration
async def test_provider_echoed_key_does_not_reach_files(tmp_path: Path) -> None:
    """因为异常模型服务可能在工具参数中回显 Key，需要在工具执行和 checkpoint 前脱敏。"""
    # 1、模拟服务把测试凭据塞进写文件参数，真实工具应只收到脱敏后的内容。
    responses = [
        tool_message("write_file", {"file_path": "/echo.txt", "content": TEST_KEY}),
        {"role": "assistant", "content": "完成"},
    ]
    with model_server(responses) as (endpoint, _):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "处理测试资料", uuid4().hex)
            await wait_finished(runtime)
            path = runtime.paths.session_files(conversation["id"]) / "echo.txt"
            assert path.read_text("utf-8") == "[已隐藏凭据]"
            assert TEST_KEY not in json.dumps(await runtime.events(conversation["id"]))
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_conversations_and_model_bindings_are_independent(tmp_path: Path) -> None:
    """因为同一个模型配置会服务多个会话，需要验证上下文隔离和换配置后的旧会话限制。"""
    # 1、连续建立两个会话，第二个真实模型请求不能带上第一个的输入。
    with model_server([{"role": "assistant", "content": "收到"}]) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            first = await runtime.new_conversation()
            await runtime.submit(first["id"], "first-conversation-unique-context", uuid4().hex)
            await wait_finished(runtime)
            second = await runtime.new_conversation()
            await runtime.submit(second["id"], "second-conversation-context", uuid4().hex)
            await wait_finished(runtime)
            assert "first-conversation-unique-context" not in json.dumps(requests[-1]["messages"])
            # 2、实际更换模型才产生新引用，旧历史仍可查看，但不能静默换模型续跑。
            await runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL + "-changed", "api_key": ""}
            )
            with pytest.raises(ValueError, match="模型配置已更新"):
                await runtime.submit(first["id"], "继续", uuid4().hex)
            assert len(await runtime.events(first["id"])) > 0
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_real_request_timeout_is_visible(tmp_path: Path) -> None:
    """因为模型无响应是常见故障，需要验证真实网络超时能结束运行并产生可读终态。"""
    # 1、采用表单允许的最短超时，不缩短生产 SDK 或替换模型适配器。
    with model_server([{"role": "assistant", "content": "迟到输出"}], delay=12) as (
        endpoint,
        requests,
    ):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            await runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": "", "timeout": 10}
            )
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "等待测试响应", uuid4().hex)
            await wait_finished(runtime)
            events = await runtime.events(conversation["id"])
            assert events[-1]["payload"]["code"] == "MODEL_TIMEOUT"
            assert len(requests) == 1
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_unfinished_run_is_marked_interrupted_on_restart(tmp_path: Path) -> None:
    """因为进程可能在记录请求后意外退出，需要在下次启动时标记中断而不自动执行。"""
    # 1、创建尚未交给模型的持久 Run，模拟异常退出留下的 running 状态。
    runtime = Runtime(AppPaths.create(tmp_path))
    await runtime.start()
    conversation = runtime.store.create_conversation("configuration-reference")
    runtime.store.begin(conversation["id"], "尚未执行", uuid4().hex)
    await runtime.close()
    # 2、重建运行时只修正终态，不访问任何模型接口或启动旧工具。
    runtime = Runtime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        assert runtime.store.latest_status(conversation["id"]) == "interrupted"
        assert (await runtime.events(conversation["id"]))[-1]["kind"] == "run.interrupted"
        assert not runtime.active
    finally:
        await runtime.close()


@pytest.mark.integration
def test_desktop_shutdown_cancels_pending_connection_probe(tmp_path: Path) -> None:
    """因为用户可能在模型探测期间关闭窗口，需要保证桥接线程不会继续阻塞数分钟。"""
    # 1、使用真实后台事件循环和慢模型请求，模拟窗口关闭期间仍有桥调用。
    outcome = []
    with model_server([{"role": "assistant", "content": "迟到输出"}], delay=3) as (endpoint, _):
        host = RuntimeThread(AppPaths.create(tmp_path))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )

        def probe() -> None:
            """因为桌面桥调用在工作线程等待，需要在测试中复现同样的等待与取消路径。"""
            # 1、只记录结束事实，不输出模型异常细节。
            try:
                host.call(host.runtime.test_connection())
            except Exception:
                outcome.append("stopped")

        worker = threading.Thread(target=probe)
        worker.start()
        time.sleep(0.15)
        started = time.monotonic()
        host.close()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert time.monotonic() - started < 4
        assert outcome == ["stopped"]


@pytest.mark.integration
async def test_explicit_local_proxy_is_used(tmp_path: Path) -> None:
    """因为部分模型需要经过用户本机代理，需要验证显式代理配置而非继承全局环境。"""
    # 1、模型端口故意不可达，只有走用户指定的本机代理才能得到协议响应。
    responses = [tool_message("roomcrew_connection_probe", {"value": "ok"})]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, "http://127.0.0.1:1/v1")
        try:
            await runtime.save_configuration(
                {
                    "base_url": "http://127.0.0.1:1/v1",
                    "model": TEST_MODEL,
                    "api_key": "",
                    "proxy": endpoint.removesuffix("/v1"),
                }
            )
            assert "连接成功" in (await runtime.test_connection())["message"]
            assert len(requests) == 1
        finally:
            await runtime.close()


def test_unchanged_configuration_preserves_reference_and_ciphertext(tmp_path: Path) -> None:
    """因为反复保存或测试不能让旧会话绑定失效，需要验证无修改保存保留引用且不重写秘密文件。"""
    # 1、只使用临时目录和合成凭据，实际调用校验与 DPAPI 原子保存。
    store = ConfigStore(AppPaths.create(tmp_path).private)
    values = {"base_url": "https://example.invalid/v1", "model": TEST_MODEL, "api_key": TEST_KEY}
    original = store.save(values)
    sealed = store.path.read_bytes()
    stamp = store.path.stat().st_mtime_ns
    for key in ("", TEST_KEY):
        repeated = store.save(
            {**values, "base_url": " https://example.invalid/v1/ ", "api_key": key}
        )
        assert repeated.reference == original.reference
        assert store.path.read_bytes() == sealed and store.path.stat().st_mtime_ns == stamp
    # 2、实际更改模型或 Key 仍产生新绑定；更换端点仍不能沿用旧凭据。
    changed = store.save({**values, "model": "other-test-model"})
    assert changed.reference != original.reference
    with pytest.raises(ConfigurationError):
        store.save({**values, "base_url": "https://other.invalid/v1", "api_key": ""})
    assert store.require_profile().reference == changed.reference
