"""真实 Windows WebView2 的会议室交互验收；不进入生产发行包。"""

import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

sys.path[:0] = [
    str(Path(__file__).resolve().parents[2] / "backend/src"),
    str(Path(__file__).resolve().parents[2] / "desktop/src"),
    str(Path(__file__).resolve().parents[2] / "backend/tests"),
]
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import webview
from test_avatar_assets import avatar_fixture
from test_runtime import model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew.storage.accounts import SqliteAccountRepository
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为后端测试不能覆盖人物和表单的连接，需要在原生页面完成招募、换座及人工恢复。"""
    # 1、隔离测试数据与合成模型，不读取真实用户的配置或任务。
    root = Path(__file__).resolve().parents[2]
    test_root = root / ".cache/studio-smoke" / uuid4().hex
    result: dict[str, object] = {}
    source_asset = avatar_fixture(test_root / "source-material")

    def pick_avatar() -> str:
        """因为自动验收不能依赖手工选择文件，需要仅替代文件选择动作而复用真实素材导入。"""
        # 1、返回测试自己生成的路径，不读取用户文件。
        return str(source_asset)

    messages = [
        tool_message(
            "ask_user", {"question": "今天希望记录什么心情？", "choices": ["平静", "开心"]}
        ),
        tool_message("write_file", {"file_path": "/studio.txt", "content": "原生窗口真实工具记录"}),
        {"role": "assistant", "content": "请核对记录文件。"},
    ]
    with model_server(messages) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(test_root))
        window = webview.create_window(
            "RoomCrew studio integration",
            str(host.runtime.paths.resources / "desktop/ui" / "index.html"),
            js_api=DesktopAPI(host, pick_avatar),
            hidden=False,
            width=1100,
            height=650,
        )

        def verify() -> None:
            """因为桥接和动画有异步时序，需要有界观察真实 DOM 并只驱动生产入口。"""
            # 1、脚本仅填表和点击生产元素，不替换执行器或生成生产答案。
            script = (
                (root / "desktop/tests/web/studio-smoke.js")
                .read_text("utf-8")
                .replace("ENDPOINT", json.dumps(endpoint))
            )
            try:
                window.events.loaded.wait(20)
                window.evaluate_js(script)
                # 2、等待当前窗口中的结果，退出时关闭测试窗口不影响用户应用。
                for _ in range(500):
                    snapshot = window.evaluate_js("window.__studioSmoke || null")
                    if snapshot:
                        result.update(snapshot)
                        break
                    threading.Event().wait(0.1)
                else:
                    stage = window.evaluate_js("window.__studioStage || 'not-started'")
                    result.update({"ok": False, "error": "studio test timeout", "stage": stage})
            except Exception as error:
                result.update({"ok": False, "error": type(error).__name__})
            finally:
                window.destroy()

        try:
            # 2、真实 WebView2 主循环；退出后重新打开账号库确认保存不是内存假象。
            webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
        finally:
            host.close()
        repository = SqliteAccountRepository(test_root / "data/account.sqlite")
        result["persisted_members"] = len(repository.members())
        result["custom_materials"] = sum(
            member["avatar_id"].startswith("avatar:") for member in repository.members()
        )
        result["persisted_leisure"] = any(
            member.get("leisure_action") == "water" and member.get("leisure_delay") == 0
            for member in repository.members()
        )
        repository.close()
        result["http_requests"] = len(requests)
    print(json.dumps(result, ensure_ascii=False))
    if (
        not result.get("ok")
        or result["persisted_members"] != 3
        or result["http_requests"] != 3
        or result["custom_materials"] != 1
        or not result.get("leisureLifecycle")
        or not result.get("persisted_leisure")
        or not result.get("handPaintedAtlas")
        or not result.get("completeMaterialBundle")
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
