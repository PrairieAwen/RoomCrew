"""原生能力配置、MCP、脚本、人工介入与泡泡的完整桌面验收。"""

import argparse
import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

project = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(project / folder) for folder in ("backend/src", "desktop/src", "backend/tests")]
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import webview
from mcp_fixture import mcp_server
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.accounts.configuration import agent_configuration
from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为后端通过不代表窗口可操作，需要驱动生产配置表单并检查真实人物状态和文件产物。"""
    # 1、全部服务和 Key 都是合成验证数据，代码不读取真实用户配置。
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-open", action="store_true")
    options = parser.parse_args()
    root = project / ".cache/capabilities-smoke" / uuid4().hex
    skills = agent_configuration(
        {
            "skills": [
                {
                    "name": "arithmetic-review",
                    "description": "算术验收技能",
                    "instructions": "先执行数值计算，再读取文件验证。NATIVE_SKILL_BODY_MARKER",
                }
            ]
        }
    )["skills"]
    digest = hashlib.sha256(
        json.dumps(skills, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    script = (
        "import json\nfrom pathlib import Path\n"
        "Path('native-result.json').write_text(json.dumps({'sum':sum(range(101))}), "
        "encoding='utf-8')\nprint('executed')\n"
    )
    responses = [
        tool_message(
            "read_file",
            {"file_path": "/skills/configured/" + digest + "/arithmetic-review/SKILL.md"},
        ),
        tool_message("list_agents", {}),
        tool_message("math_add_numbers", {"left": 17, "right": 25}),
        tool_message("write_file", {"file_path": "/calculate.py", "content": script}),
        tool_message("execute_python", {"script_path": "/calculate.py", "timeout_seconds": 15}),
        tool_message(
            "ask_user",
            {
                "question": "这是自动验收的合成人工问题，请选择是否继续",
                "choices": ["继续", "取消"],
                "interaction_type": "choice",
                "allow_other": True,
            },
        ),
        tool_message("read_file", {"file_path": "/native-result.json"}),
        {
            "role": "assistant",
            "content": (
                "MCP 计算得到 42，Python 已执行并生成 native-result.json，文件中的求和结果是 5050。"
            ),
        },
    ]
    result: dict[str, object] = {}
    with mcp_server() as (url, calls), model_server(responses) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        window = webview.create_window(
            "RoomCrew capability verification",
            str(host.runtime.paths.resources / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1440,
            height=960,
        )

        def verify() -> None:
            """因为原生窗口与桥注入异步完成，需要在生产页面就绪后运行有界 UI 验证。"""
            # 1、脚本只操作本测试创建的窗口，不注入假的 Agent 轨迹或动作状态。
            source = (project / "desktop/tests/web/capabilities-smoke.js").read_text("utf-8")
            source = source.replace("__SKILLS__", json.dumps(skills, ensure_ascii=False)).replace(
                "__MCP_URL__", json.dumps(url)
            )
            window.evaluate_js(source)
            try:
                for _ in range(600):
                    status = window.evaluate_js("window.__capabilitiesResult || null")
                    if status:
                        result.update(status)
                        break
                    threading.Event().wait(0.1)
                if not result:
                    result.update({"ok": False, "error": "native verification timeout"})
            finally:
                # 2、保留窗口只用于人工截图，默认回归完成即释放原生资源。
                if not options.keep_open or not result.get("ok"):
                    window.destroy()

        try:
            webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
        finally:
            host.close()
        result.update({"model_requests": len(requests), "mcp_calls": len(calls)})
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
