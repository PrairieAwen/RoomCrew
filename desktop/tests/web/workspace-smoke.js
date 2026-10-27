/** 因为同 ID 人物跨房间容易残留，需要用真实表单验证画面、草稿与任务各自归属。 */
(async function verifyWorkspaces() {
    // 1、所有条件观察正式状态，不替换后端或表现协议。
    let second;
    /** 因为窗口和后端异步刷新，需要有界轮询真实页面状态。 */
    async function until(check) {
        // 1、最多观察三十秒，超时不修改生产任务。
        for (let i = 0; i < 300; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error(
            "workspace condition timed out: " + window.__workspaceStage,
        );
    }
    /** 因为等待不能阻塞帧循环，需要让出当前测试执行片段。 */
    function pause(resolve) {
        // 1、只控制测试采样频率。
        setTimeout(resolve, 100);
    }
    /** 因为桥存在不代表会议室已就绪，需要同时确认数据和渲染器。 */
    function ready() {
        // 1、等待旧默认空间的三名实际人物。
        return (
            typeof studio !== "undefined" &&
            state.workspace &&
            !state.switching &&
            studio?.data &&
            studio.renderer.views.size === 3
        );
    }
    /** 因为切换过程可能有旧轮询，需要等新空间与人物快照共同稳定。 */
    function secondReady() {
        // 1、不根据点击发生推断完成。
        return (
            state.workspace?.id !== "default" &&
            !workspacePanel.busy &&
            studio.data?.members.length === 2 &&
            studio.renderer.views.size === 2
        );
    }
    /** 因为切回默认空间要恢复原来的独立人物，需要等待三名人物真正绘制。 */
    function firstReady() {
        // 1、确认代次重置后得到原空间快照。
        return (
            state.workspace?.id === "default" &&
            !workspacePanel.busy &&
            studio.data?.members.length === 3 &&
            studio.renderer.views.size === 3
        );
    }
    /** 因为任务完成应由后端确认，需要读取当前空间权威运行状态。 */
    async function finished() {
        // 1、不会根据动画停止推定成功。
        return !(await api("overview")).active_run;
    }
    /** 因为任务启动异步，需要等待真正登记的 Run。 */
    function started() {
        // 1、使用生产状态而非按钮禁用状态。
        return Boolean(state.run) && !state.sending;
    }
    /** 因为目录包含后台最小计数，需要在不切回时检查甲空间已完成。 */
    async function backgroundFinished() {
        // 1、目录不包含其他房间任务正文。
        const value = await api("workspace_state");
        return !value.workspaces.find(isFirst).active_runs;
    }
    /** 因为目录按稳定 ID 关联，需要精确匹配默认空间。 */
    function isFirst(room) {
        // 1、名称变化不影响身份。
        return room.id === "default";
    }
    /** 因为改名要持久化且不换房间，需要观察保存后的目录状态。 */
    function renamed() {
        // 1、当前空间身份保留。
        return (
            state.workspace?.id === second &&
            state.workspace.name === "乙会议室" &&
            !workspacePanel.busy
        );
    }
    try {
        window.__workspaceStage = "ready";
        await until(ready);
        studio.roomMode();
        if (document.title !== "RoomCrew") throw new Error("wrong brand");
        await newConversation();
        const firstConversation = state.conversation.id;
        el("prompt").value = "写入甲空间测试文件";
        el("composer").requestSubmit();
        await until(started);
        el("prompt").value = "甲空间未发送草稿";
        // 2、通过用户创建表单进入乙空间，甲任务在后台继续。
        window.__workspaceStage = "create";
        workspacePanel.create();
        el("workspace-title").value = "乙空间";
        el("workspace-form").requestSubmit();
        await until(secondReady);
        second = state.workspace.id;
        if (state.conversation || state.cursor || el("prompt").value)
            throw new Error("old conversation or draft leaked");
        const directory = await api("workspace_state");
        if (
            directory.workspaces.length !== 2 ||
            new Set(directory.workspaces.map(roomIdentity)).size !== 2
        )
            throw new Error("wrong room mapping");
        if (!directory.workspaces.find(isFirst).active_runs)
            throw new Error("background task unexpectedly stopped");
        await until(backgroundFinished);
        window.__workspaceStage = "second-task";
        await newConversation();
        el("prompt").value = "写入乙空间测试文件";
        el("composer").requestSubmit();
        await until(started);
        await until(finished);
        const secondFile = await api(
            "read_artifact",
            state.conversation.id,
            "/proof.txt",
        );
        if (secondFile.text !== "乙空间产物") throw new Error("wrong B file");
        // 3、切回原房间核对任务、草稿与真实文件，原始轨迹仍按需加载。
        window.__workspaceStage = "return";
        document.querySelector('[data-workspace="default"]').click();
        await until(firstReady);
        if (
            state.conversation.id !== firstConversation ||
            el("prompt").value !== "甲空间未发送草稿" ||
            state.cursor !== 0
        )
            throw new Error("wrong A restoration");
        const firstFile = await api(
            "read_artifact",
            firstConversation,
            "/proof.txt",
        );
        if (firstFile.text !== "甲空间产物") throw new Error("wrong A file");
        document.querySelector(`[data-workspace="${second}"]`).click();
        await until(secondReady);
        workspacePanel.rename();
        el("workspace-title").value = "乙会议室";
        el("workspace-form").requestSubmit();
        await until(renamed);
        if (el("room-name").textContent !== "乙会议室 · 会议室")
            throw new Error("room title did not update");
        window.__workspaceSmoke = {
            ok: true,
            workspaces: 2,
            rooms: 2,
            firstMembers: 3,
            secondMembers: 2,
            files: 2,
            backgroundContinued: true,
            draftRestored: true,
        };
    } catch (error) {
        window.__workspaceSmoke = {
            ok: false,
            error: error.message,
            stage: window.__workspaceStage,
        };
    }
    /** 因为会议室不能按显示名去重，需要读取目录持久标识。 */
    function roomIdentity(room) {
        // 1、只返回房间 ID。
        return room.room_id;
    }
})();
