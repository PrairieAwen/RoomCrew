/** 因为归档和续聊必须在实际界面可操作，需要验证原文、语义、共享与两个并行会话。 */
(async function verifyArchive() {
    // 1、只驱动正式页面和 API，不改时钟、不补写数据库或替换轨迹。
    let stage = "initializing";
    /** 因为查询和模型异步返回，需要有界观察真实状态。 */
    async function until(check) {
        // 1、等待只控制采样，最多约二十秒。
        for (let index = 0; index < 250; index++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("Archive UI condition timed out: " + stage);
    }
    /** 因为等待不应阻塞原生帧，需要短暂释放测试执行片段。 */
    function pause(resolve) { /* 1、只影响测试采样频率。 */ setTimeout(resolve, 80); }
    /** 因为桥存在不代表人物数据就绪，需要等待正式空间与场景初始化。 */
    function ready() { /* 1、不预建空会话。 */ return !state.switching && studio?.data?.members.length >= 2; }
    /** 因为截图由原生窗口自身导出，需要等待控制端确认。 */
    function captured() { /* 1、不抓取其他应用。 */ return window.__archiveCaptured === window.__archiveStage; }
    /** 因为页面按钮异步执行，需要按可观察目录状态判断。 */
    function listed() { /* 1、读取实际摘要内容。 */ return el("archive-results").textContent.includes("金毛犬"); }
    /** 因为原文必须来自查询回执，需要等待完整消息出现。 */
    function original() { /* 1、不是检索片段。 */ return el("archive-detail").textContent.includes("我家里养了一只金毛犬"); }
    /** 因为结果按钮结构相同，需要按实际标签查找。 */
    function button(text, root = "archive-results") {
        // 1、只操作当前弹窗内的正式控件。
        return [...el(root).querySelectorAll("button")].find(textMatches, text);
    }
    /** 因为复用查找需要具名回调，需要精确比较标签。 */
    function textMatches(item) { /* 1、不使用部分匹配误点其他按钮。 */ return item.textContent === String(this); }
    /** 因为两条会话同时完成前要观察隔离，需要读取后端真实活动列表。 */
    async function twoRunning() { /* 1、不能用人物动作推测执行。 */ return (await api("overview")).active_runs.length === 2; }
    /** 因为关闭测试前必须等待全部真实执行结束，需要查询后端运行状态。 */
    async function allFinished() { /* 1、不以输出文字代替终态。 */ return (await api("overview")).active_runs.length === 0; }
    try {
        await until(ready);
        workspacePanel.openArchive();
        await until(listed);
        button("查看完整消息").click();
        await until(original);
        stage = "capture-history"; window.__archiveStage = stage;
        await until(captured);
        // 2、没有相同关键词的查询必须由真实语义模型检索到原文证据。
        el("archive-query").value = "家里的宠物是什么品种的狗？";
        el("archive-mode").value = "vector";
        await archivePanel.search();
        await until(listed);
        stage = "capture-semantic"; window.__archiveStage = stage;
        await until(captured);
        const sharing = el("archive-shares").querySelector("input");
        sharing.checked = true;
        el("archive-save-sharing").click();
        /** 因为保存需要真实白名单回执，需要等待新的来源选项出现。 */
        function shared() { /* 1、正式查询选项来自已保存权限。 */ return [...el("archive-space").options].some(sourceMatches); }
        /** 因为来源 ID 是测试生成，需要只检查该空间。 */
        function sourceMatches(option) { /* 1、不把其他来源误认为本次共享成功。 */ return option.value === window.__archiveInputs.other_workspace; }
        await until(shared);
        stage = "capture-sharing"; window.__archiveStage = stage;
        el("archive-shares").parentElement.open = true;
        await until(captured);
        el("archive-shares").querySelector("input").checked = false;
        await archivePanel.saveSharing();
        if ((await api("archive_settings")).allowed_sources.includes(window.__archiveInputs.other_workspace)) throw new Error("Sharing revoke failed");
        workspacePanel.closeArchive();
        // 3、点击人物恢复封存旧会话，发送时透明换线程，再显式新建第二个独立并行会话。
        stage = "continuation";
        await studio.talkToMember("assistant");
        if (state.conversation.id !== window.__archiveInputs.old_conversation) throw new Error("Persistent person chat not restored");
        el("prompt").value = "继续任务甲，请使用之前的背景。";
        await sendTask(new Event("submit"));
        const resumed = state.conversation.id;
        if (resumed === window.__archiveInputs.old_conversation) throw new Error("Archived checkpoint was reused");
        await newConversation();
        if (state.run || el("send").disabled) throw new Error("Other conversation blocks fresh input");
        el("prompt").value = "另一个独立任务乙。";
        await sendTask(new Event("submit"));
        await until(twoRunning);
        if (state.conversation.id === resumed) throw new Error("Parallel conversations share thread");
        await until(allFinished);
        window.__archiveResult = { ok: true, fullHistory: true, realSemanticSearch: true,
            sharingRevoked: true, seamlessContinuation: true, parallelConversations: true };
    } catch (error) {
        window.__archiveResult = { ok: false, stage, error: error.message };
    }
})();
