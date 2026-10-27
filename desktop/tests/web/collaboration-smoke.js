/** 因为委派元数据正确不代表角色真的交互，需要在正式页面通过真实 Agent 连续验证会议与外援。 */
(async function verifyCollaboration() {
    /** 因为模型请求和人物走动是独立异步过程，需要有界等待实际页面状态。 */
    async function until(check) {
        // 1、不替换轨迹、时钟、导演或播放器；最多等待三十秒。
        for (let i = 0; i < 300; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("collaboration condition timed out");
    }
    /** 因为测试不能占用渲染线程，需要在观察之间释放事件循环。 */
    function pause(resolve) {
        // 1、仅控制测试采样频率。
        setTimeout(resolve, 100);
    }
    /** 因为测试必须使用实际注册人物，需要等真实空间快照和绘图就绪。 */
    function ready() {
        // 1、不创建或注入替代人物。
        return (
            typeof studio !== "undefined" &&
            studio?.data &&
            studio.renderer.views.size === 3
        );
    }
    /** 因为开会必须实际到达，需要同时观察两名配置成员的站会与讨论动作。 */
    function discussing() {
        // 1、只读取正式帧循环输出的观测标签。
        for (const id of ["assistant", EMPLOYEE_ID]) {
            const group = studio.renderer.views.get(id)?.group;
            if (
                group?.dataset.meeting !== "true" ||
                group.dataset.phase !== "settled" ||
                !["talk", "listen"].includes(group.dataset.clip) ||
                group.dataset.leisure !== "false"
            )
                return false;
        }
        return true;
    }
    /** 因为完成只能以实际运行终态为准，需要查询后端和本次会话的提交事件。 */
    async function finished() {
        // 1、动画播放完不算任务完成。
        if ((await api("overview")).active_run) return false;
        const events = await api("events", state.conversation.id, 0);
        return events.some(completedEvent);
    }
    /** 因为模型文本可能声称完成，需要只判断产品终态事件。 */
    function completedEvent(event) {
        // 1、使用有限事件类型。
        return event.kind === "run.completed";
    }
    /** 因为外援没有对应人物，需要观察主 Agent 电话状态并保持团队数量不变。 */
    function calling() {
        // 1、电话不是生活手机动作，真实工作不能被摸鱼标签掩盖。
        const group = studio.renderer.views.get("assistant")?.group;
        return (
            group?.dataset.externalCall === "true" &&
            group.dataset.leisure === "false" &&
            studio.renderer.views.size === 3 &&
            group.dataset.meeting !== "true"
        );
    }
    try {
        // 1、用户通过正常输入表单提交任务，由真实 Loop 自行发起配置成员委派。
        window.__collaborationStage = "boot";
        await until(ready);
        if (document.querySelector('[data-member="boss"]'))
            throw new Error("user avatar still rendered");
        const before = JSON.stringify(studio.data.scene.placements);
        await newConversation();
        el("task-member").value = "assistant";
        el("prompt").value = "把给定记录交给已配置的原生同事处理";
        el("composer").requestSubmit();
        window.__collaborationStage = "meeting";
        await until(discussing);
        const first = state.conversation.id;
        const membership = studio.data.interactions[0]?.members || [];
        if (membership.length !== 2)
            throw new Error("wrong meeting membership");
        await until(finished);
        const meetingFile = await api("read_artifact", first, "/meeting.txt");
        if (meetingFile.text !== "真实会议委派产物")
            throw new Error("missing real configured-worker artifact");
        await studio.refresh();
        if (JSON.stringify(studio.data.scene.placements) !== before)
            throw new Error("visual meeting changed persisted seats");
        // 2、第二项任务调用通用外援，只显示主 Agent 电话与完整子作用域轨迹。
        await newConversation();
        el("prompt").value = "调用通用外援保存第二份记录";
        el("composer").requestSubmit();
        window.__collaborationStage = "external";
        await until(calling);
        await until(finished);
        const second = state.conversation.id;
        const externalFile = await api(
            "read_artifact",
            second,
            "/external.txt",
        );
        const events = await api("events", second, 0);
        if (
            externalFile.text !== "真实外援工具产物" ||
            !events.some(externalTrace)
        )
            throw new Error("external trace or artifact missing");
        if (studio.renderer.views.size !== 3)
            throw new Error("external worker spawned a scene avatar");
        window.__collaborationSmoke = {
            ok: true,
            meetingMembers: membership.length,
            externalAvatarCount: 0,
            members: studio.data.members.length,
            artifacts: 2,
            seatsUnchanged: true,
            traceScope: true,
        };
    } catch (error) {
        window.__collaborationSmoke = {
            ok: false,
            error: error.message,
            stage: window.__collaborationStage,
            actors: studio?.data?.actors?.map(actorSummary),
            interactions: studio?.data?.interactions,
        };
    }
    /** 因为无形象协作者必须来自显式配置，需要检查真实子作用域身份而非旧版通用外援标记。 */
    function externalTrace(event) {
        // 1、完整会话中存在子作用域模型或工具事件。
        return (
            event.scope !== "main" &&
            event.member_id?.startsWith("definition_")
        );
    }
    /** 因为失败诊断不应打印任务正文，需要只输出有限活动元数据。 */
    function actorSummary(actor) {
        // 1、不输出模型配置、提示或工具内容。
        return {
            member: actor.member_id,
            activity: actor.activity,
            external_calls: actor.external_calls,
        };
    }
})();
