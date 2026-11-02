/** 因为角色点击需改变真实对话入口，需要在正式页面验证接单身份、草稿及配置分离。 */
(async function verifyRoleChat() {
    /** 因为界面刷新是异步的，需要有界等待实际可观察状态。 */
    async function until(check) {
        // 1、不改执行器和页面时钟，仅等待生产状态更新。
        for (let i = 0; i < 200; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("role chat condition timed out");
    }
    /** 因为忙等会阻塞动画，需要在检查之间释放事件循环。 */
    function pause(resolve) { /* 1、只控制测试采样间隔。 */ setTimeout(resolve, 100); }
    /** 因为实际 DOM 点击不能绕过渲染器，需要通过人物根节点触发正式入口。 */
    async function clickMember(id) {
        // 1、稳定成员身份来自本测试的配置，不根据显示名字猜测。
        const expected = id === "guardian" ? null : await api("member_chat",id);
        studio.renderer.views.get(id).group.dispatchEvent(new MouseEvent("click", {bubbles: true}));
        // 2、人物入口需异步查询持久聊天，不能在桥响应前断言会话已展开。
        if(id === "guardian") await new Promise(pause);
        else await until(recipientReady.bind(null,id,expected?.id || null));
    }
    /** 因为角色接单包含异步恢复，需要等待实际对话与选中身份一致。 */
    function recipientReady(id, conversation) {
        // 1、不直接调用控制器来绕过正式人物事件。
        return document.body.classList.contains("conversation-open") && el("task-member").value===id &&
            (state.conversation?.id || null)===conversation;
    }
    /** 因为桥与人物异步初始化，需要确认真实空间已经可用。 */
    function ready() { /* 1、只检查实际就绪状态。 */ return !state.switching && studio?.data?.members.length === 3; }
    /** 因为发送后需要观察后端终态，需要查询真实会话事件。 */
    async function completed() {
        // 1、任务结果不能只根据模型正文判断。
        return state.conversation && (await api("events", state.conversation.id, 0)).some(isCompleted);
    }
    /** 因为轨迹包含多类事件，需要只识别真实产品终态。 */
    function isCompleted(event) { /* 1、只检查确定性状态类型。 */ return event.kind === "run.completed"; }
    /** 因为截图应覆盖当前真实状态，需要等待原生导出完成再继续下一步。 */
    function captured() { /* 1、不注入图片，只确认本窗口画面已保存。 */ return window.__roleCaptured === window.__roleStage; }
    try {
        await until(ready);
        studio.roomMode();
        const before = (await api("overview")).conversations.length;
        await clickMember("role_worker");
        if (!document.body.classList.contains("conversation-open") || document.body.classList.contains("team-open") || el("task-member").value !== "role_worker")
            throw new Error("role click opened configuration or wrong recipient");
        if ((await api("overview")).conversations.length !== before)
            throw new Error("role click created an empty conversation");
        if (el("room-name") || [...el("room-canvas").querySelectorAll("text")].some(isWallBrand))
            throw new Error("redundant canvas labels remain");
        window.__roleStage = "direct-chat";
        await until(captured);
        el("prompt").value = "请写入角色接单验证文件。";
        el("composer").requestSubmit();
        await until(completed);
        const conversation = state.conversation.id;
        await until(notSending);
        await clickMember("assistant");
        if (state.conversation || el("task-member").value !== "assistant")
            throw new Error("different agent reused another agent conversation");
        await clickMember("role_worker");
        if (state.conversation?.id !== conversation)
            throw new Error("return to existing member conversation failed");
        await clickMember("guardian");
        if (state.conversation?.id !== conversation || el("task-member").value !== "role_worker")
            throw new Error("infrastructure stole conversation recipient");
        el("room-options").open = true;
        if (!el("toggle-team").getBoundingClientRect().width)
            throw new Error("team configuration menu is not visible");
        window.__roleStage = "options";
        await until(captured);
        el("toggle-team").click();
        if (!document.body.classList.contains("team-open") || document.body.classList.contains("conversation-open") || el("room-options").open)
            throw new Error("explicit team configuration did not open independently");
        window.__roleResult = {ok: true, conversation, roleClick: true, recipient: "role_worker", noEmptyConversation: true, separateAgentChats: true, optionsMenu: true, labelsRemoved: true};
    } catch (error) {
        window.__roleResult = {ok: false, error: error.message};
    }
    /** 因为普通会话正文可能包含品牌词，需要只检查墙上的 SVG 文本。 */
    function isWallBrand(node) { /* 1、匹配删除前的完整墙面标签。 */ return node.textContent === "RoomCrew"; }
    /** 因为请求响应后会继续刷新日志，需要等发送锁真正释放再切换角色。 */
    function notSending() { /* 1、不修改真实发送状态。 */ return !state.sending; }
})();
