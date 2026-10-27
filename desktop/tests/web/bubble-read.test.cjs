const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const calls = [];
const context = vm.createContext({
    state: { workspaceEpoch: 1, conversation: { id: "old" } },
    calls,
});
vm.runInContext(
    fs.readFileSync("desktop/ui/studio/controller.js", "utf8") +
        `
/** 因为单元验证不能调用真实桌面桥，需要只记录被测控制器发起的已读操作。 */
async function api(...args) { /* 1、只记录调用顺序，不修改生产数据。 */ calls.push(args); }
/** 因为切换会话是被测流程的一部分，需要保留控制器选择的目标。 */
function resetConversation(value) { /* 1、仅用于模拟页面选择状态。 */ state.conversation=value; }
/** 因为加载失败应保留未读，需要收集错误而不抛出到测试外部。 */
function showError(error) { /* 1、记录错误被正常处理。 */ calls.push(["error",error.message]); }
globalThis.CrewStudio=CrewStudio;
`,
    context,
);

/** 因为查看失败不能清除泡泡，需要验证确认回执只在正确会话成功加载之后发送。 */
async function verifyReadLifecycle() {
    // 1、加载失败保留待处理状态，不调用已读 API。
    const studio = Object.create(context.CrewStudio.prototype);
    studio.renderer = { facts: new Map() };
    studio.chatMode = failedView;
    studio.refresh = refreshView;
    studio.showQuestions = questionView;
    const notice = {
        id: "result:one",
        kind: "result",
        conversation_id: "original",
    };
    assert.equal(await studio.openConversation("member", notice), false);
    assert.equal(calls.some(isReceipt), false);
    // 2、成功打开对应会话后先记录已读，再刷新服务端结果。
    calls.length = 0;
    studio.chatMode = loadedView;
    assert.equal(await studio.openConversation("member", notice), true);
    assert.equal(context.state.conversation.id, "original");
    assert.deepEqual(calls.map(firstItem), [
        "loaded",
        "acknowledge_bubble",
        "refreshed",
    ]);
    assert.deepEqual(Array.from(calls[1]), [
        "acknowledge_bubble",
        "member",
        "result:one",
    ]);
    // 3、打开问题表单不算答复，不能调用完成已读入口。
    calls.length = 0;
    await studio.openConversation("member", {
        ...notice,
        kind: "question",
        request_id: "child-question",
    });
    assert.deepEqual(calls.map(firstItem), ["loaded", "question"]);
    assert.equal(calls[1][1], "child-question");
    // 4、等待期间切到其他工作空间，不能把回执写入错误空间。
    calls.length = 0;
    studio.chatMode = switchedWorkspace;
    assert.equal(await studio.openConversation("member", notice), false);
    assert.equal(calls.some(isReceipt), false);
}
/** 因为失败路径需要真实异常，需要模拟读取内容失败。 */
async function failedView() {
    /* 1、只模拟 I/O 失败，不主动隐藏泡泡。 */ throw new Error("read failed");
}
/** 因为成功顺序需要可观察，需要记录内容已加载。 */
async function loadedView() {
    /* 1、记录成功加载。 */ calls.push(["loaded"]);
}
/** 因为已读后应重新获取泡泡，需要观察刷新步骤。 */
async function refreshView() {
    /* 1、记录刷新。 */ calls.push(["refreshed"]);
}
/** 因为人工表单打开不代表提交，需要单独记录打开步骤。 */
async function questionView(requestId) {
    /* 1、记录显示表单及原始人工请求身份。 */ calls.push([
        "question",
        requestId,
    ]);
}
/** 因为异步查看可能遇到空间切换，需要模拟页面代次变化。 */
async function switchedWorkspace() {
    /* 1、改变测试代次，不调用回执。 */ context.state.workspaceEpoch += 1;
}
/** 因为不同调用要比较顺序，需要取记录的操作名。 */
function firstItem(value) {
    /* 1、返回已记录的名称。 */ return value[0];
}
/** 因为失败不能发已读，需要筛选回执操作。 */
function isReceipt(value) {
    /* 1、只匹配正式已读方法。 */ return value[0] === "acknowledge_bubble";
}
/** 因为异步断言失败需要正确退出，需要把异常报告为测试失败。 */
function failed(error) {
    /* 1、保留断言原因并返回失败退出码。 */ console.error(error);
    process.exitCode = 1;
}
/** 因为测试完成需要明确结果，需要输出经过全部断言的成功信息。 */
function passed() {
    /* 1、只输出验证结论。 */ console.log(
        "bubble view success + failure + question + workspace: passed",
    );
}
verifyReadLifecycle().then(passed, failed);
