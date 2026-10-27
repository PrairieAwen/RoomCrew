"""发行 exe 的真实跨进程验收；需要在独立窗口发送合成任务。"""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path[:0] = [
    str(Path(__file__).resolve().parents[2] / "backend/src"),
    str(Path(__file__).resolve().parents[2] / "backend/tests"),
    str(Path(__file__).resolve().parents[2] / "desktop/src"),
]
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from mcp_fixture import mcp_server
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.application.runtime import Runtime
from roomcrew.platform.paths import AppPaths


async def configure(root: Path, endpoint: str, mcp_url: str) -> None:
    """因为发行进程不能注入测试桥，需要先通过真实配置用例创建独立的合成验证配置。"""
    # 1、仅写本测试随机根，不读取用户 Key 或任务。
    runtime = Runtime(AppPaths.create(root))
    await runtime.start()
    try:
        await runtime.save_configuration(
            {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
        )
        member = await runtime.member("assistant")
        await runtime.save_member(
            {**member, "mcp_servers": [{"name": "frozen", "url": mcp_url}]}, member["revision"]
        )
    finally:
        await runtime.close()


def main() -> None:
    """因为源码通过不能证明打包完整，需要让发行 exe 自己运行 MCP 和随包隔离 Python。"""
    # 1、真实本机协议服务只返回合成响应，执行器与产物由发行程序自身生成。
    logging.disable(logging.CRITICAL)
    project = Path(__file__).resolve().parents[2]
    root = project / ".cache/frozen-smoke" / uuid4().hex
    script = (
        "import json\nfrom pathlib import Path\n"
        "Path('frozen-result.json').write_text(json.dumps({'sum':sum(range(1,101))}),"
        "encoding='utf-8')\nprint('frozen-executed')\n"
    )
    responses = [
        tool_message("frozen_add_numbers", {"left": 23, "right": 19}),
        tool_message("write_file", {"file_path": "/frozen.py", "content": script}),
        tool_message("execute_python", {"script_path": "/frozen.py", "timeout_seconds": 15}),
        tool_message("make_directory", {"path": "/archive"}),
        tool_message(
            "copy_file", {"source": "/frozen-result.json", "destination": "/archive/copy.json"}
        ),
        tool_message(
            "move_file", {"source": "/archive/copy.json", "destination": "/archive/final.json"}
        ),
        tool_message("file_info", {"path": "/archive/final.json"}),
        tool_message("delete_file", {"path": "/archive/final.json"}),
        {"role": "assistant", "content": "发行包验收完成，请核对 frozen-result.json。"},
    ]
    with mcp_server() as (url, calls), model_server(responses) as (endpoint, requests):
        asyncio.run(configure(root, endpoint, url))
        process = subprocess.Popen(
            [str(project / "dist/RoomCrew/RoomCrew.exe"), "--data-dir", str(root)],
            creationflags=0x08000000,
        )
        print(json.dumps({"stage": "ready_for_native_input", "pid": process.pid}), flush=True)
        # 2、只观察发行程序自己写入的终态与文件，不能补写缺失结果。
        result: dict = {"ok": False}
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and process.poll() is None:
            database = root / "data/sessions.sqlite"
            if database.exists():
                with sqlite3.connect(database) as connection:
                    row = connection.execute(
                        "SELECT seq FROM events WHERE kind='run.completed' "
                        "ORDER BY seq DESC LIMIT 1"
                    ).fetchone()
                if row:
                    artifacts = list((root / "data").rglob("frozen-result.json"))
                    result = {
                        "ok": bool(artifacts)
                        and json.loads(artifacts[0].read_text("utf-8"))["sum"] == 5050
                        and len(calls) == 1
                        and len(requests) == 9,
                        "model_requests": len(requests),
                        "mcp_calls": len(calls),
                        "frozen_executable": True,
                        "root": str(root),
                    }
                    break
            time.sleep(0.25)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        # 3、留出时间由原生界面关闭本测试窗口；超时不终止其他用户进程。
        process.wait(timeout=120)
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
