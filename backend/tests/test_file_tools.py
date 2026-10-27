"""默认文件工具与主子 Agent Python 产物的集成验证。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_runtime import configured_runtime, model_server, tool_message, wait_finished

from roomcrew.tools.files import file_tools


def test_file_tools_preserve_binary_data_and_directory_lifecycle(tmp_path: Path) -> None:
    """因为不同格式都需要真实增删改查，需要验证二进制不转码、目录管理和已存在目标行为。"""
    # 1、创建包含零字节与非 UTF8 字节的合成内容，不依赖模型重新生成二进制。
    tools = {tool.name: tool for tool in file_tools(tmp_path)}
    source = bytes(range(256))
    (tmp_path / "source.bin").write_bytes(source)
    tools["make_directory"].invoke({"path": "/archive"})
    tools["copy_file"].invoke({"source": "/source.bin", "destination": "/archive/copy.bin"})
    tools["move_file"].invoke({"source": "/archive/copy.bin", "destination": "/archive/final.bin"})
    assert (tmp_path / "archive/final.bin").read_bytes() == source
    assert not (tmp_path / "archive/copy.bin").exists()
    info = json.loads(tools["file_info"].invoke({"path": "/archive/final.bin"}))
    assert info["bytes"] == 256 and info["kind"] == "file"
    # 2、拒绝静默覆盖和清空非空目录，删除返回值反映真实状态。
    with pytest.raises(ValueError, match="存在"):
        tools["copy_file"].invoke({"source": "/source.bin", "destination": "/archive/final.bin"})
    with pytest.raises(OSError):
        tools["delete_file"].invoke({"path": "/archive"})
    assert json.loads(tools["delete_file"].invoke({"path": "/archive/final.bin"}))["deleted"]
    tools["delete_file"].invoke({"path": "/archive"})
    assert not json.loads(tools["file_info"].invoke({"path": "/archive"}))["exists"]
    assert not json.loads(tools["delete_file"].invoke({"path": "/missing"}))["deleted"]


@pytest.mark.integration
async def test_worker_generates_python_and_manages_actual_outputs(tmp_path: Path) -> None:
    """因为所有 Agent 都应默认具备文件工具和 Python，需要验证子 Agent 真正生成并管理产物。"""
    # 1、输入与预期只在验证端生成；脚本必须读取文件并计算，不能靠最终回复冒充执行。
    script = (
        "import json\nfrom pathlib import Path\n"
        "numbers=json.loads(Path('input.json').read_text())\n"
        "Path('answer.json').write_text(json.dumps({'total':sum(x*x for x in numbers)}))\n"
        "Path('result.bin').write_bytes(bytes(range(256)))\n"
        "print('actual-python-output')\n"
    )
    responses = [
        tool_message(
            "task", {"description": "计算后归档真实文件", "subagent_type": "general-purpose"}
        ),
        tool_message("write_file", {"file_path": "/calculate.py", "content": script}),
        tool_message("execute_python", {"script_path": "/calculate.py"}),
        tool_message("make_directory", {"path": "/archive"}),
        tool_message("copy_file", {"source": "/result.bin", "destination": "/archive/copy.bin"}),
        tool_message(
            "move_file", {"source": "/archive/copy.bin", "destination": "/archive/final.bin"}
        ),
        tool_message("file_info", {"path": "/archive/final.bin"}),
        tool_message("delete_file", {"path": "/result.bin"}),
        tool_message("read_file", {"file_path": "/answer.json"}),
        {"role": "assistant", "content": "子任务已完成，产物已归档。"},
        {"role": "assistant", "content": "已汇总实际计算与归档结果。"},
    ]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            root = runtime.paths.session_files(conversation["id"])
            numbers = [19, 71, 5, 303]
            (root / "input.json").write_text(json.dumps(numbers), "utf-8")
            await runtime.submit(conversation["id"], "委派通用员工计算与归档", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert json.loads((root / "answer.json").read_text())["total"] == sum(
                x * x for x in numbers
            )
            assert (root / "archive/final.bin").read_bytes() == bytes(range(256))
            assert not (root / "result.bin").exists()
            # 2、从主 Agent 与子 Agent 实际模型请求确认同一组默认工具确实注册。
            for request in requests:
                names = {tool["function"]["name"] for tool in request["tools"]}
                assert {
                    "file_info",
                    "copy_file",
                    "move_file",
                    "delete_file",
                    "make_directory",
                    "execute_python",
                    "read_file",
                    "write_file",
                    "edit_file",
                } <= names
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_python_failure_can_be_corrected_in_the_same_loop(tmp_path: Path) -> None:
    """因为生成脚本可能有错误，需要验证失败日志返回模型后可以修正并真实重新执行。"""
    # 1、首次脚本实际失败，不能被执行器标成成功或伪造产物。
    responses = [
        tool_message(
            "write_file",
            {"file_path": "/retry.py", "content": "raise ValueError('test-failure')\n"},
        ),
        tool_message("execute_python", {"script_path": "/retry.py"}),
        tool_message(
            "edit_file",
            {
                "file_path": "/retry.py",
                "old_string": "raise ValueError('test-failure')",
                "new_string": (
                    "from pathlib import Path; Path('recovered.txt').write_text('actual recovery')"
                ),
            },
        ),
        tool_message("execute_python", {"script_path": "/retry.py"}),
        {"role": "assistant", "content": "修正后实际执行成功。"},
    ]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "执行并修正 Python", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert (
                runtime.paths.session_files(conversation["id"]) / "recovered.txt"
            ).read_text() == "actual recovery"
            assert "test-failure" in json.dumps(requests[2]["messages"])
            assert '"exit_code": 0' in json.dumps(requests[-1]["messages"]).replace('\\"', '"')
        finally:
            await runtime.close()
