/** 因为定时任务必须随时可人工取消，需要通过正式桥和按钮验证真实状态。 */
(async function verifySchedules() {
    // 1、只创建独立测试数据，时间不加速，运行时与页面均为正式实现。
    let stage = "initializing";
    /** 因为异步按钮不能靠固定等待判断成功，需要有界观察真实数据。 */
    async function until(check) {
        // 1、轮询只用于验收，不修改生产时钟或调度规则。
        for (let index = 0; index < 250; index++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("Schedule UI timed out: " + stage);
    }
    /** 因为等待不能阻塞 WebView，需要用短延迟释放事件循环。 */
    function pause(resolve) { /* 1、只控制采样频率。 */ setTimeout(resolve, 80); }
    /** 因为桥就绪之前不能调用业务，需要等待当前空间确定。 */
    function ready() { /* 1、正式状态必须稳定。 */ return state.workspace && !state.switching; }
    /** 因为刷新会替换卡片，需要每次查找当前按钮。 */
    function button(text) {
        // 1、只匹配当前管理窗口的纯文本按钮。
        return [...el("schedules-list").querySelectorAll("button")].find(hasText, text);
    }
    /** 因为查找可复用，需要通过 thisArg 传递期待标签。 */
    function hasText(item) { /* 1、精确文本匹配。 */ return item.textContent === String(this); }
    /** 因为创建完成后要目检真实面板，需要等待 Python 自身渲染导出。 */
    function captured() { /* 1、不会抓其他应用画面。 */ return window.__schedulesCaptured; }
    try {
        await until(ready);
        const first = state.workspace.id;
        const plan = await api("create_schedule", {
            title: "每小时查看时间（界面验收）", instruction: "调用 get_local_time 查看时间。",
            target_member_id: "assistant", trigger: { type: "interval", seconds: 3600 },
        }, crypto.randomUUID());
        el("workspace-options").open = true;
        el("open-schedules").click();
        /** 因为列表加载异步完成，需要观察标题和操作按钮都出现。 */
        function listed() {
            // 1、实际卡片与按钮必须同时可用。
            return el("schedules-dialog").open && button("暂停");
        }
        await until(listed);
        stage = "capture"; window.__schedulesStage = stage;
        await until(captured);
        button("暂停").click();
        /** 因为暂停需要真实持久化，需要通过后端查询回执。 */
        async function paused() { /* 1、状态与控件必须一致。 */ return (await api("get_schedule", plan.id)).state === "paused" && button("恢复"); }
        await until(paused);
        button("恢复").click();
        /** 因为恢复不能只改按钮，需要再次验证数据库状态。 */
        async function resumed() { /* 1、恢复后必须再次有下一次触发时间。 */ const value = await api("get_schedule", plan.id); return value.state === "active" && value.next_run_at && button("暂停"); }
        await until(resumed);
        button("取消后续安排").click();
        /** 因为取消必须彻底移除未来触发，需要验证状态和时间同时清除。 */
        async function cancelled() { /* 1、完成后不留下周期计划。 */ const value = await api("get_schedule", plan.id); return value.state === "deleted" && value.next_fire === null && !button("取消后续安排"); }
        await until(cancelled);
        button("执行记录").click();
        /** 因为未触发的安排没有会话，需要避免查看记录创建空任务。 */
        function emptyHistory() { /* 1、检查实际查询提示。 */ return el("schedules-list").textContent.includes("尚未触发"); }
        await until(emptyHistory);
        await workspacePanel.apply(await api("create_workspace", "定时任务隔离空间"));
        await schedulePanel.open();
        if ((await api("list_schedules", "", true)).length) throw new Error("Cross-workspace schedule leak");
        await workspacePanel.apply(await api("select_workspace", first));
        const persisted = await api("get_schedule", plan.id);
        if (persisted.state !== "deleted") throw new Error("Cancellation not persisted");
        window.__schedulesResult = { ok: true, pause: true, resume: true, cancelled: true, workspaceIsolation: true };
    } catch (error) {
        window.__schedulesResult = { ok: false, stage, error: error.message };
    }
})();
