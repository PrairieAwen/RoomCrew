/* 使用实际表单逻辑验证保存—测试顺序，所有凭据均为合成测试文本。 */
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

class ModelSettingsHarness {
    /** 因为需要观察真实表单发出的请求，需要仅替代 DOM 与桌面传输。 */
    constructor() {
        // 1、每个场景有独立状态，不替换生产保存、比较或探测函数。
        this.fields = new Map();
        this.calls = [];
        this.context = vm.createContext({
            window: { addEventListener: this.ignoreReady },
        });
        vm.runInContext(
            fs.readFileSync("desktop/ui/app.js", "utf8"),
            this.context,
        );
        this.context.document = { getElementById: this.field.bind(this) };
        this.context.window.pywebview = {
            api: { invoke: this.invoke.bind(this) },
        };
        vm.runInContext(
            'state.workspace={id:"test"};state.switching=false;',
            this.context,
        );
        this.field("settings-dialog").open = true;
        this.field("settings-target").value = "execution";
        this.field("model-label").value = "测试配置";
        this.field("model-id").value = "test-model";
        this.field("base-url").value = "https://current.invalid/v1";
        this.field("api-key").value = "synthetic-new-key";
        this.field("model-timeout").value = "90";
        this.field("context-window").value = "32768";
    }
    /** 因为本测试不启动轮询，需要忽略自动 boot 的事件注册。 */
    ignoreReady() {
        // 1、生产函数保持原样等待测试驱动。
    }
    /** 因为生产逻辑通过 ID 操作表单，需要提供最小可观察字段。 */
    field(id) {
        // 1、只保留值、锁与反馈，浏览器校验由单独场景控制。
        if (!this.fields.has(id))
            this.fields.set(id, {
                value: "",
                disabled: false,
                textContent: "",
                valid: true,
                reportValidity: this.reportValidity,
            });
        return this.fields.get(id);
    }
    /** 因为无效表单不应发请求，需要模拟原生 reportValidity 的布尔结果。 */
    reportValidity() {
        // 1、只返回当前节点的校验结果。
        return this.valid;
    }
    /** 因为要控制迟到响应顺序，需要记录当前请求并让场景决定何时完成。 */
    invoke(workspace, method, args) {
        // 1、复制传输快照，避免生产清理临时 Key 改写已发出的测试记录。
        const record = { workspace, method, args: structuredClone(args) };
        this.calls.push(record);
        /** 因为请求应持续等待实际场景回复，需要保存独立 resolve。 */
        function defer(resolve) {
            // 1、不自动生成业务成功结果。
            record.resolve = resolve;
        }
        return new Promise(defer);
    }
    /** 因为保存响应不能回传 Key，需要按公开配置合同构造测试响应。 */
    saved(index = 0) {
        // 1、只复制已发送的非秘密参数，省略 api_key。
        const { api_key, ...values } = this.calls[index].args[0];
        this.calls[index].resolve({
            ok: true,
            data: {
                ...values,
                configured: true,
                has_key: true,
                reference: "stable-reference",
            },
        });
    }
    /** 因为要直接运行实际事件处理器，需要在独立页面状态内求值。 */
    run(code) {
        // 1、不修改生产函数体。
        return vm.runInContext(code, this.context);
    }
}

/** 因为链式 await 会跨多个微任务，需要在可观察步骤间让出一次事件循环。 */
async function settle() {
    // 1、不改变生产超时或异步逻辑。
    await new Promise(nextTurn);
}
/** 因为不能忙等，需要通过 Node 的下一轮事件通知完成测试等待。 */
function nextTurn(resolve) {
    // 1、只供测试调度。
    setImmediate(resolve);
}

/** 因为原问题是表单改了却仍测旧配置，需要验证发送顺序、失败短路和重入保护。 */
async function verifyCurrentForm() {
    // 1、首次直接测试必须先保存新地址和新 Key，保存未完成不能发送探测。
    const h = new ModelSettingsHarness();
    const pending = h.run("testSettings()");
    await h.run("testSettings()");
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].method, "save_configuration");
    assert.equal(h.calls[0].args[0].base_url, "https://current.invalid/v1");
    assert.equal(h.calls[0].args[0].api_key, "synthetic-new-key");
    assert.equal(h.field("settings-target").disabled, true);
    h.saved();
    await settle();
    assert.equal(h.field("api-key").value, "");
    assert.equal(h.calls[1].method, "test_connection");
    h.calls[1].resolve({ ok: true, data: { message: "连接成功" } });
    await pending;
    assert.equal(h.field("settings-result").textContent, "连接成功");
    assert(!h.run("JSON.stringify(state)").includes("synthetic-new-key"));
    // 2、重复测试复用保存绑定，只再发一次探测，不重复写配置。
    const again = h.run("testSettings()");
    await settle();
    assert.equal(h.calls.length, 3);
    assert.equal(h.calls[2].method, "test_connection");
    h.calls[2].resolve({ ok: true, data: { message: "连接成功" } });
    await again;
    h.run("modelSettingsEdited()");
    assert(!h.field("settings-result").textContent.includes("连接成功"));
}

/** 因为保存失败时不能测试磁盘旧值，需要验证保存错误后没有任何模型请求。 */
async function verifySaveFailure() {
    // 1、后端拒绝新配置时显示保存失败，Key 清除，按钮恢复。
    const h = new ModelSettingsHarness();
    const pending = h.run("testSettings()");
    h.calls[0].resolve({ ok: false, error: "请填写有效 Key" });
    await pending;
    assert.equal(h.calls.length, 1);
    assert(h.field("settings-result").textContent.includes("未发起连接测试"));
    assert.equal(h.field("api-key").value, "");
    assert.equal(h.field("test-model").disabled, false);
    // 2、浏览器校验失败甚至不能触发保存。
    const invalid = new ModelSettingsHarness();
    invalid.field("settings-form").valid = false;
    await invalid.run("testSettings()");
    assert.equal(invalid.calls.length, 0);
}

/** 因为用途切换或关闭后旧反馈不能覆盖新表单，需要验证同空间内的版本隔离。 */
async function verifyLateForm() {
    // 1、保存尚未返回时切到旁白表单，旧请求不得继续探测或清空新输入。
    const h = new ModelSettingsHarness();
    const pending = h.run("testSettings()");
    h.run("state.settingsVersion++;");
    h.field("settings-target").value = "presentation";
    h.field("api-key").value = "synthetic-other-input";
    h.field("settings-result").textContent = "新表单反馈";
    h.saved();
    await pending;
    assert.equal(h.calls.length, 1);
    assert.equal(h.field("api-key").value, "synthetic-other-input");
    assert.equal(h.field("settings-result").textContent, "新表单反馈");
}

/** 因为探测失败不应伪装成保存失败，需要验证两个阶段的反馈和失败后重试。 */
async function verifyProbeFailure() {
    // 1、首次保存成功后模拟认证失败，重试应沿用已保存配置再探测。
    const h = new ModelSettingsHarness();
    const pending = h.run("testSettings()");
    h.saved();
    await settle();
    h.calls[1].resolve({ ok: false, error: "模型认证失败" });
    await pending;
    assert(
        h
            .field("settings-result")
            .textContent.startsWith("配置已保存，但连接测试失败"),
    );
    const retry = h.run("testSettings()");
    await settle();
    assert.equal(h.calls[2].method, "test_connection");
    h.calls[2].resolve({ ok: true, data: { message: "连接成功" } });
    await retry;
}

/** 因为回归命令需要可靠退出状态，需要依次完成所有失败路径检查。 */
async function main() {
    // 1、场景互不共享页面或模拟请求。
    await verifyCurrentForm();
    await verifySaveFailure();
    await verifyLateForm();
    await verifyProbeFailure();
    console.log("current form save + probe + retries + stale replies: passed");
}
/** 因为异步断言不能静默失败，需要让命令返回失败状态。 */
function failed(error) {
    // 1、测试仅含合成凭据，不涉及用户 Key。
    console.error(error);
    process.exitCode = 1;
}
main().catch(failed);
