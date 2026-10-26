/* 直接验证生产 RPC 入口的空间绑定和迟到响应处理。 */
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

class ControlledBridge {
    /** 因为迟到顺序必须可控，需要保留每次真实生产入口提交的空间和响应。 */
    constructor() {
        // 1、只替代桌面传输，不替代生产 api 的路由与代次判断。
        this.calls = [];
    }
    /** 因为两个空间的响应可能颠倒，需要将调用信息放进可手动完成的 Promise。 */
    invoke(workspace, method, args) {
        // 1、每个请求保存独立 resolve，模拟正在等待后端的桥调用。
        const record = { workspace, method, args };
        this.calls.push(record);
        /** 因为测试需要按指定顺序完成请求，需要保存当前请求的解析入口。 */
        function defer(resolve) {
            // 1、不修改请求身份。
            record.resolve = resolve;
        }
        return new Promise(defer);
    }
    /** 因为首次启动没有空间身份，需要模拟不携带业务数据的目录接口。 */
    async workspace_state() {
        // 1、目录属于中立请求，可以在切换状态下读取。
        return { ok: true, data: { active: { id: "B" } } };
    }
}

/** 因为仅检查界面代码文本不能发现串空间，需要驱动实际 api 函数并颠倒返回顺序。 */
async function verifyWorkspaceRequests() {
    // 1、装载生产页面逻辑，延迟注入桥，避免启动真实 DOM 与轮询。
    const bridge = new ControlledBridge();
    /** 因为本测试只验证传输逻辑，需要忽略页面自动启动注册。 */
    function ignoreReady() {
        // 1、不调用 boot，生产 api 函数保持原样。
    }
    const page = { addEventListener: ignoreReady };
    const context = vm.createContext({ window: page });
    vm.runInContext(fs.readFileSync("desktop/ui/app.js", "utf8"), context);
    page.pywebview = { api: bridge };
    vm.runInContext('state.workspace={id:"A"};state.switching=false;', context);
    const old = vm.runInContext('api("events","conversation-A",0)', context);
    const rejected = assert.rejects(old, { stale: true });
    vm.runInContext(
        'state.workspaceEpoch++;state.workspace={id:"B"};',
        context,
    );
    const next = vm.runInContext('api("studio_feed",0)', context);
    assert.equal(bridge.calls[0].workspace, "A");
    assert.equal(bridge.calls[1].workspace, "B");
    bridge.calls[1].resolve({ ok: true, data: { room: "B" } });
    assert.equal((await next).room, "B");
    bridge.calls[0].resolve({ ok: true, data: { room: "A", events: ["old"] } });
    await rejected;
    // 2、过渡期间不向任一空间发业务请求，但目录恢复仍可用。
    vm.runInContext("state.switching=true;", context);
    await assert.rejects(
        vm.runInContext('api("submit","id","text","request")', context),
        { stale: true },
    );
    assert.equal(bridge.calls.length, 2);
    assert.equal(
        (await vm.runInContext('api("workspace_state")', context)).active.id,
        "B",
    );
    // 3、迟到保存不得清空新一代配置表单里刚填的内容或解锁新请求。
    const fields = new Map();
    /** 因为配置回调也需要代次隔离，需要给实际保存函数提供最小表单节点。 */
    function field(id) {
        // 1、节点仅保存当前测试值，不访问文件或真实凭据。
        if (!fields.has(id))
            fields.set(id, {
                value: "",
                disabled: false,
                textContent: "",
                open: true,
                reportValidity: validForm,
            });
        return fields.get(id);
    }
    /** 因为生产提交会校验表单，需要让本测试的有效合成输入通过浏览器入口。 */
    function validForm() {
        // 1、表单内容不含真实配置。
        return true;
    }
    context.document = { getElementById: field };
    vm.runInContext("state.switching=false;", context);
    field("api-key").value = "synthetic-old-input";
    context.formEvent = { preventDefault: ignoreReady };
    const saved = vm.runInContext("saveSettings(formEvent)", context);
    vm.runInContext(
        'state.workspaceEpoch++;state.workspace={id:"C"};',
        context,
    );
    field("api-key").value = "synthetic-new-input";
    field("save-model").disabled = true;
    bridge.calls[2].resolve({ ok: true, data: {} });
    await saved;
    assert.equal(field("api-key").value, "synthetic-new-input");
    assert.equal(field("save-model").disabled, true);
    assert.equal(field("settings-result").textContent, "");
    console.log(
        "workspace-scoped RPC + late responses + form isolation: passed",
    );
}

/** 因为异步断言失败应让验证命令失败，需要统一报告并设置退出状态。 */
function failed(error) {
    // 1、只输出测试断言；测试中没有真实秘密。
    console.error(error);
    process.exitCode = 1;
}
verifyWorkspaceRequests().catch(failed);
