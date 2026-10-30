/** 因为动作要反映实际 MCP 与人工状态，需要在原生页面按正式入口执行完整会话。 */
(async function verifyExecutionVisuals() {
    // 1、等待真实界面和资源，所有状态来自正式桥接接口。
    /** 因为执行和图集解码均异步，需要有界等待真实状态。 */
    async function until(check) {
        // 1、超时显式失败，不覆盖状态让断言成立。
        for (let i = 0; i < 500; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("visual condition timed out: " + window.__executionVisualStage);
    }
    /** 因为测试不能阻塞动画，需要把采样让回浏览器帧循环。 */
    function pause(resolve) {
        // 1、仅用于验证节奏。
        setTimeout(resolve, 100);
    }
    /** 因为截图应包含稳定姿势，需要在原生宿主确认导出后继续流程。 */
    async function capture(name) {
        // 1、宿主只导出自己的测试 WebView。
        window.__executionVisualStage = name;
        await until(captured);
    }
    /** 因为宿主与页面异步，需要核对实际截图阶段回执。 */
    function captured() {
        // 1、只观察宿主导出回执。
        return window.__executionVisualCaptured === window.__executionVisualStage;
    }
    /** 因为任务必须从用户入口启动，需要先选接单人再调用正常发送流程。 */
    async function send(member, text) {
        // 1、显式独立会话保留旧结果，验证通知与活动状态解耦。
        await studio.talkToMember(member);
        await newConversation();
        el("prompt").value = text;
        await sendTask({preventDefault: preventSubmit});
        studio.roomMode();
    }
    /** 因为原生表单不应刷新页面，需要复用发送入口的阻止默认行为回调。 */
    function preventSubmit() {
        // 1、不会改变后台执行结果。
    }
    /** 因为框架结束才可产生提示，需要检查权威 Run 与人物通知同时一致。 */
    async function completed() {
        // 1、刷新正常页面数据，不能只看模型输出文字。
        const overview = await api("overview");
        renderOverview(overview);
        await studio.refresh();
        return !overview.active_run && !overview.active_runs?.length;
    }
    /** 因为只转身不等于操作电脑，需要检查真实工具类别与背向打字图集。 */
    async function typing(member) {
        // 1、工作持续期间必须没有当前任务完成提示。
        await studio.refresh();
        const fact = studio.renderer.facts.get(member), view = studio.renderer.views.get(member);
        return fact?.tool_kind === "mcp" && fact.activity === "executing" && view?.sprite?.dataset.variant.startsWith("type.nw.seated.");
    }
    const counts = {};
    try {
        await until(ready);
        await send("assistant", "先给出一轮合成回复，用于保留未读通知");
        await until(completed);
        await send("assistant", "调用数学 MCP 后先询问我是否继续");
        await until(calling.bind(null, "assistant"));
        await capture("mcp-telephone");
        await until(typing.bind(null, "assistant"));
        const fact = studio.renderer.facts.get("assistant");
        if (!fact.bubble_is_history || fact.bubble.includes("干完")) throw new Error("旧结果冒充当前任务完成");
        studio.renderer.cameraRig.focus(studio.renderer.motion.actors.get("assistant").position);
        studio.renderer.cameraRig.zoom = 1.5;
        studio.renderer.cameraRig.resize();
        await capture("mcp-working-history");
        await until(hasQuestion);
        await studio.showQuestions();
        await capture("human-question");
        const form = el("questions-list").querySelector("form");
        form.querySelector(".question-choices button").click();
        form.requestSubmit();
        await until(completed);
        studio.closeQuestions();
        await capture("main-reply-ready");
        // 2、同样的 MCP 通过新素材真实执行，采样确认手臂工作帧发生切换。
        await send("hippo_visual_worker", "请用数学 MCP 计算18加24");
        await until(calling.bind(null, "hippo_visual_worker"));
        await capture("mascot-telephone");
        await until(typing.bind(null, "hippo_visual_worker"));
        studio.renderer.cameraRig.focus(studio.renderer.motion.actors.get("hippo_visual_worker").position);
        studio.renderer.cameraRig.zoom = 1.6;
        studio.renderer.cameraRig.resize();
        const frames = new Set();
        for (let i = 0; i < 12; i++) {
            const view = studio.renderer.views.get("hippo_visual_worker");
            frames.add(view.sprite.dataset.frame);
            await new Promise(pause);
        }
        if (frames.size < 2) throw new Error("新素材没有切换打字帧");
        counts.typing_frames = [...frames];
        await capture("mascot-mcp-working");
        await until(completed);
        await until(frontFacing);
        await capture("mascot-reply-ready");
        // 3、新形象还需通过正式换座路径，检查实际起身、行走和再次落座。
        studio.selected = "hippo_visual_worker";
        await studio.moveTo("desk-4");
        await until(rising);
        await capture("mascot-rise");
        await until(reseated);
        await capture("mascot-reseated");
        window.__executionVisualResult = {ok: true, ...counts};
    } catch (error) {
        window.__executionVisualResult = {ok: false, error: String(error), stack: error.stack};
    }
    /** 因为初始化未完成不能发任务，需要检查实际素材与工作空间已就绪。 */
    function ready() {
        // 1、固定验证人物来自测试数据库。
        return state.workspace && !state.switching && studio?.renderer?.views?.has("hippo_visual_worker");
    }
    /** 因为人工问题必须来自真实工具中断，需要读取正式待办列表。 */
    async function hasQuestion() {
        // 1、等待期间不把任务标记完成。
        await studio.refresh();
        return (await api("questions")).length === 1;
    }
    /** 因为完成之后也应经过转身，需要等新素材稳定面向用户。 */
    function frontFacing() {
        // 1、不直接写入动作或朝向。
        return studio.renderer.views.get("hippo_visual_worker")?.sprite?.dataset.variant.includes(".se.seated.");
    }
    /** 因为 MCP 通话不能与摸鱼玩手机混淆，需要确认独立补页的贴耳电话动作。 */
    async function calling(member) {
        // 1、正式持久队列触发，仅原地通话一段时间，再恢复电脑工作。
        await studio.refresh();
        const view=studio.renderer.views.get(member), active=studio.renderer.collaboration.active;
        return active?.item.kind==="mcp" && active?.item.member_id===member && active.stage==="perform" && active.elapsed>0.4 &&
            view?.group?.dataset.clip==="phone" && view.sprite?.dataset.variant.startsWith("phone.se.seated.") &&
            view.sprite.dataset.page===(member==="assistant"?"5":"3");
    }
    /** 因为坐姿不能直接瞬移成站姿，需要观察正式运动层的起身阶段。 */
    function rising() {
        // 1、用户移动计划正常驱动，不直接设置运动状态。
        return studio.renderer.motion.actors.get("hippo_visual_worker")?.phase === "stand_up";
    }
    /** 因为素材动作结束不代表移动到达，需要检查目标位置和真实稳定姿态。 */
    function reseated() {
        // 1、确认完整走到新工位再落座。
        const actor = studio.renderer.motion.actors.get("hippo_visual_worker");
        return actor?.phase === "settled" && actor?.target?.id === "desk-4";
    }
})();
