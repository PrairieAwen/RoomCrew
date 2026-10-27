"""通过真实 Deep Agents、文件工具和 WebView2 验证会话 Markdown。"""

import argparse
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
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread

MARKDOWN = """# 排版验收

这是**加粗**、*斜体*、~~删除线~~和 `a*b`，星号应按语义展示。

- 一级项目
  - 嵌套项目
- 第二项目

3. 第三项
4. 第四项

> 引用内容

| 项目 | 状态 |
| :--- | ---: |
| Markdown | 正常 |

```python
print("**literal**")
<script>window.__markdownAttack = true</script>
```

[文档](https://example.com/docs) [查看产物](/notes.md)

<img src=x onerror="window.__markdownAttack=true">
<script>window.__markdownAttack=true</script>
[危险脚本](javascript:alert(1))
![远程图片](https://example.com/pixel.png)
"""


def main() -> None:
    """因为解析通过不代表原生消息正确，需要从实际会话执行到历史重载完整验证。"""
    # 1、独立数据与合成模型只替代远端响应，执行仍经过生产 SDK、文件工具和持久化。
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-open", action="store_true")
    options = parser.parse_args()
    root = project / ".cache/markdown-smoke" / uuid4().hex
    responses = [
        tool_message("write_file", {"file_path": "/notes.md", "content": "**产物原文**"}),
        {"role": "assistant", "content": MARKDOWN},
    ]
    result: dict[str, object] = {}
    with model_server(responses) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        window = webview.create_window(
            "RoomCrew Markdown verification",
            str(host.runtime.paths.resources / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1440,
            height=960,
        )

        def verify() -> None:
            """因为原生桥异步注入，需要等待生产页面并观察受限时间内的实际验证结果。"""
            # 1、脚本操作自己创建的窗口，不修改生产 DOM 渲染方法或虚构产品事件。
            source = (project / "desktop/tests/web/markdown-smoke.js").read_text("utf-8")
            window.evaluate_js(source)
            try:
                for _ in range(600):
                    status = window.evaluate_js("window.__markdownResult || null")
                    if status:
                        result.update(status)
                        break
                    threading.Event().wait(0.1)
                if not result:
                    result.update({"ok": False, "error": "native Markdown verification timeout"})
            finally:
                # 2、默认释放测试窗口；显式保留只用于截图，不使用用户历史或 Key。
                if not options.keep_open or not result.get("ok"):
                    window.destroy()

        try:
            webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
        finally:
            host.close()
        result["model_requests"] = len(requests)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
