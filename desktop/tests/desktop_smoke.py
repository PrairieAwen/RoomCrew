"""独立运行的原生 WebView 集成测试，不进入发行包，也不使用真实模型凭据。"""

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
from test_runtime import model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为仅验证后端不能证明桌面表单可用，需要通过真实 WebView DOM 和桌面桥走完整流程。"""
    # 1、测试资源始终位于缓存目录，真实发行入口不会加载这个文件。
    root = Path(__file__).resolve().parents[2]
    test_root = root / ".cache/desktop-smoke" / uuid4().hex
    responses = [
        tool_message("roomcrew_connection_probe", {"value": "ok"}),
        tool_message("roomcrew_connection_probe", {"value": "ok"}),
        tool_message("write_file", {"file_path": "/smoke.txt", "content": "桌面桥真实工具产物"}),
        tool_message("read_file", {"file_path": "/smoke.txt"}),
        {"role": "assistant", "content": "已写入并核对。"},
    ]
    result: dict[str, object] = {}
    with model_server(responses) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(test_root))
        # 2、预先存入旧端点；测试必须保存新表单，不能悄悄探测旧值。
        host.call(
            host.runtime.save_configuration(
                {
                    "base_url": "http://127.0.0.1:1/v1",
                    "model": "obsolete-test-model",
                    "api_key": "synthetic-obsolete-key",
                }
            )
        )
        window = webview.create_window(
            "RoomCrew desktop integration",
            str(host.runtime.paths.resources / "desktop/ui" / "index.html"),
            js_api=DesktopAPI(host),
            hidden=False,
            width=1380,
            height=900,
        )

        def verify() -> None:
            """因为页面和桥注入有异步时序，需要在页面就绪后驱动生产表单并核对实际结果。"""
            # 1、向测试页面注入仅存在于回归测试的驱动，不替换任何业务接口。
            script = r"""
            /** 因为需要验证完整窗口工作流，需要操作生产表单并观察真实桥接结果。 */
            (async function verifyDesktop() {
              /** 因为桥和表单反馈异步到达，需要有界等待可观察状态。 */
              async function until(check) {
                // 1、测试等待最长二十秒，不改变生产任务超时。
                for (let i=0; i<200; i++) {
                  if (await check()) return;
                  await new Promise(waitStep);
                }
                throw new Error('desktop condition timed out');
              }
              /** 因为测试不能忙等，需要在两次观察之间释放事件循环。 */
              function waitStep(resolve) {
                // 1、仅控制测试节奏。
                setTimeout(resolve, 100);
              }
              /** 因为桌面桥尚未注入时不能调用配置，需要先确认桥存在。 */
              function bridgeReady() {
                // 1、检查真实桥，不创建替代接口。
                return Boolean(window.pywebview?.api && state.workspace
                  && !state.switching && studio?.data);
              }
              /** 因为连接探测必须真实往返，需要等待界面收到工具协议成功响应。 */
              function tested() {
                // 1、不根据按钮点击推定成功。
                return document.getElementById('settings-result').textContent.includes('连接成功');
              }
              /** 因为任务受理和完成分开，需要先观察真实 Run 已创建。 */
              function submitted() {
                // 1、从持久事件或当前状态观察本次任务。
                return state.cursor > 0;
              }
              /** 因为完成必须由运行时确认，需要同时检查终态和真实工具展示。 */
              async function completed() {
                // 1、查询生产桥并核对当前会话的完整轨迹。
                await loadEvents();
                const data=await api('overview');
                return !data.active_run && document.getElementById('timeline')
                  .textContent.includes('本轮执行结束');
              }
              try {
                // 1、通过真实设置表单保存模拟凭据并测试实际协议连接。
                await until(bridgeReady);
                window.__smokePhase='bridge';
                await studio.chatMode();
                window.__smokePhase="chat";
                await openSettings();
                window.__smokePhase="settings";
                document.getElementById('base-url').value=ENDPOINT;
                document.getElementById('model-id').value='private-test-model-identifier';
                document.getElementById('api-key').value='synthetic-test-key-never-a-real-credential';
                // 2、直接点击测试而不单独保存，复现用户修改后仍探测旧配置的场景。
                document.getElementById('test-model').click();
                document.getElementById('test-model').click();
                await until(tested);
                if(document.getElementById('api-key').value)
                  throw new Error('key remained in form');
                const before=await api('configuration');
                if(before.base_url!==ENDPOINT || before.model!=='private-test-model-identifier')
                  throw new Error('current form was not saved');
                // 3、无修改重复测试应只探测，不改变配置引用或会话绑定。
                await testSettings(); await until(tested);
                const after=await api('configuration');
                if(before.reference!==after.reference)
                  throw new Error('test changed model binding');
                closeSettings();
                // 2、通过生产输入框和提交事件执行真实 Deep Agents 文件操作。
                await newConversation();
                document.getElementById('prompt').value='保存给定测试资料并读回核对';
                document.getElementById('composer').requestSubmit();
                await until(submitted); await until(completed); await refreshArtifacts();
                const files=await api('artifacts',state.conversation.id);
                const file=await api('read_artifact',state.conversation.id,'/smoke.txt');
                if(file.text!=='桌面桥真实工具产物' || !files.length || state.tools!==2)
                  throw new Error('wrong actual artifact');
                if(state.actors.size!==1) throw new Error('wrong distinct member count');
                window.__smoke={ok:true,modelCalls:state.models,tools:state.tools,files:files.length,saveBeforeTest:true,stableBinding:true};
              } catch(error) { window.__smoke={ok:false,error:error.message}; }
            })();
            """.replace("ENDPOINT", json.dumps(endpoint))
            try:
                window.events.loaded.wait(20)
                window.evaluate_js(script)
                # 2、测试线程有界观察结果，测试完成或失败后都关闭窗口。
                for _ in range(400):
                    snapshot = window.evaluate_js("window.__smoke || null")
                    if snapshot:
                        result.update(snapshot)
                        break
                    threading.Event().wait(0.1)
                else:
                    result.update(
                        {
                            "ok": False,
                            "error": "desktop test timeout",
                            "diagnostic": window.evaluate_js(
                                "({phase:window.__smokePhase,workspace:state.workspace?.id,"
                                'switching:state.switching,toast:el("toast").textContent,'
                                'settings:el("settings-result").textContent})'
                            ),
                        }
                    )
            except Exception as error:
                result.update({"ok": False, "error": type(error).__name__})
            finally:
                window.destroy()

        try:
            # 3、真实 WebView2 主循环，后台验证线程只操作本测试创建的页面。
            webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
        finally:
            host.close()
        result["http_requests"] = len(requests)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
