/** 因为 MCP 配置必须能被用户实际操作，需要通过正式表单和桥验证保存、测试与执行。 */
(async function verifyMCPSettings() {
    /** 因为界面和网络异步更新，需要等待有限时间内的可观察状态。 */
    async function until(check) {
        // 1、只观察正式页面，不替换执行器、配置接口或时钟。
        for (let i = 0; i < 250; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("MCP settings condition timed out");
    }
    /** 因为忙等会阻塞原生渲染，需要释放事件循环。 */
    function pause(resolve) {
        /* 1、只控制测试采样。 */ setTimeout(resolve, 80);
    }
    /** 因为表单输入会清除旧测试结论，需要派发真实输入事件。 */
    function input(field, value) {
        // 1、驱动生产监听器，不能直接修改编辑器缓存。
        field.value = value;
        field.dispatchEvent(new Event("input", { bubbles: true }));
    }
    /** 因为表单按钮异步执行，需要观察连接状态和按钮解锁。 */
    function tested() {
        /* 1、读取真实状态文字。 */ return (
            !row.test.disabled && row.status.textContent.length > 0
        );
    }
    /** 因为截图应覆盖真实配置界面，需要等原生导出完成再保存。 */
    function captured() {
        /* 1、截图由测试窗口自身导出。 */ return (
            window.__mcpCaptured === window.__mcpStage
        );
    }
    /** 因为初始化会拉取人物，需要在场景和桥就绪后开始操作。 */
    function ready() {
        /* 1、不提前创建测试会话。 */ return (
            !state.switching && studio?.data?.members.length >= 2
        );
    }
    /** 因为保存会关闭弹窗，需要等待真实保存结束。 */
    function closed() {
        /* 1、不能仅根据提示文字判断持久化成功。 */ return !el("member-dialog")
            .open;
    }
    /** 因为任务完成状态来自后端，需要通过正式事件查询确定终态。 */
    async function completed() {
        // 1、保留真实 Deep Agents 执行及 MCP 调用。
        return (
            state.conversation &&
            (await api("events", state.conversation.id)).some(isComplete)
        );
    }
    /** 因为事件流包含工具和模型消息，需要只识别产品完成事件。 */
    function isComplete(event) {
        /* 1、匹配真实终态。 */ return event.kind === "run.completed";
    }
    let row;
    try {
        await until(ready);
        studio.roomMode();
        el("toggle-team").click();
        studio.selectMember("assistant");
        await studio.editMember();
        el("mcp-bailian").click();
        row = studio.memberConfiguration.mcp.rows[0];
        if (
            row.url.value !==
                "https://dashscope.aliyuncs.com/api/v1/mcps/EnhancedSearch/mcp" ||
            row.mode.value !== "bearer"
        )
            throw new Error("Bailian preset missing");
        input(row.name, "math");
        input(row.url, window.__mcpInputs.url);
        input(row.key, "wrong-key");
        row.test.click();
        await until(tested);
        if (row.status.textContent.includes("连接成功"))
            throw new Error("invalid Key accepted");
        input(row.key, window.__mcpInputs.key);
        row.test.click();
        await until(tested);
        if (!row.status.textContent.includes("math_add_numbers"))
            throw new Error(row.status.textContent);
        row.card.scrollIntoView({ block: "center" });
        window.__mcpStage = "mcp-config";
        await until(captured);
        el("member-form").requestSubmit();
        await until(closed);
        const saved = await api("member", "assistant");
        if (
            !saved.mcp_servers[0].auth_ref ||
            JSON.stringify(saved).includes(window.__mcpInputs.key)
        )
            throw new Error(
                "protected reference missing or public secret exposure",
            );
        await studio.editMember();
        row = studio.memberConfiguration.mcp.rows[0];
        if (row.key.value !== "" || !row.key.placeholder.includes("已保存"))
            throw new Error("saved Key echoed");
        row.test.click();
        await until(tested);
        if (!row.status.textContent.includes("连接成功"))
            throw new Error("blank Key reuse failed");
        input(row.key, window.__mcpInputs.key);
        el("close-member").click();
        await until(closed);
        if (row.key.value !== "") throw new Error("Key remained after close");
        // 2、新增共享形象不能覆盖已有定义；取消编辑不改变已经保存的 MCP。
        studio.addMember();
        input(el("member-agent"), saved.agent_id);
        el("member-agent").dispatchEvent(
            new Event("change", { bubbles: true }),
        );
        if (
            !el("member-mcp").disabled ||
            Object.keys(studio.memberConfiguration.readAgent()).length
        )
            throw new Error("shared Agent configuration is editable");
        el("close-member").click();
        await until(closed);
        studio.talkToMember("assistant");
        input(el("prompt"), "请通过数学 MCP 计算 20 加 22。");
        el("composer").requestSubmit();
        await until(completed);
        window.__mcpResult = {
            ok: true,
            conversation: state.conversation.id,
            preset: true,
            unsavedProbe: true,
            invalidKeyRejected: true,
            protectedReference: true,
            blankKeyReuse: true,
            clearOnClose: true,
            sharedReadOnly: true,
        };
    } catch (error) {
        window.__mcpResult = { ok: false, error: error.message };
    }
})();
