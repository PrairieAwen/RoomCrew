/** 因为直接调用 click 不经过真实按下/抬起，需要等待 computer-use 点击实际人物泡泡。 */
(async function verifyBubblePointer() {
    // 1、只观察生产对象与可信指针，不改写相机、按钮处理器或回执。
    const clicks = [];
    document.addEventListener("pointerdown", observePointer, true);
    /** 因为要确认测试覆盖真实输入，需要记录泡泡收到的可信 pointerdown。 */
    function observePointer(event) {
        // 1、其他测试表单操作不算泡泡鼠标验收。
        if (event.target.closest(".crew-speech-bubble"))
            clicks.push(event.isTrusted);
    }
    /** 因为模型和用户点击都异步，需要等待实际条件并有界失败。 */
    async function until(check) {
        // 1、每阶段最多六十秒，不伪造点击或状态来绕过失败。
        for (let i = 0; i < 600; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error(
            "pointer verification timeout: " + window.__pointerStage,
        );
    }
    /** 因为 WebView 需要继续响应鼠标，需要异步让出测试执行。 */
    function pause(resolve) {
        // 1、等待只控制测试节奏。
        setTimeout(resolve, 100);
    }
    /** 因为启动先于空间准备，需要等待正式场景与成员初始化。 */
    function ready() {
        // 1、不创建假场景替代实际表现服务。
        return state.workspace && !state.switching && studio?.data;
    }
    /** 因为完成必须由正式 Run 确认，需要加载会话与场景并检查权威终态。 */
    async function completed() {
        // 1、不根据模型回答中的完成二字推定结束。
        await loadEvents();
        await studio.refresh();
        const overview = await api("overview");
        renderOverview(overview);
        return (
            !overview.active_run &&
            studio.renderer.facts.get("assistant")?.bubble_notice?.kind ===
                "result"
        );
    }
    /** 因为每轮任务应经过生产发送器，需要只设置人工输入并等待真实提交完成。 */
    async function send(text) {
        // 1、不会直接向 SQLite 注入产品事件。
        el("prompt").value = text;
        await sendTask({ preventDefault: preventSubmit });
    }
    /** 因为测试直接调用发送器，需要提供阻止浏览器导航的事件接口。 */
    function preventSubmit() {
        // 1、测试本身没有原生表单默认导航。
    }
    /** 因为相机刷新与回执可能不同步，需要等正式快照和显示节点都已清除。 */
    async function resultRead() {
        // 1、同时确认人物提示文字与 DOM，不只检查按钮焦点变化。
        await studio.refresh();
        const view = studio.renderer.views.get("assistant");
        return (
            !view.bubbleText &&
            view.bubble.getAttribute("display") === "none" &&
            !studio.renderer.facts.get("assistant").bubble_pending_count
        );
    }
    /** 因为人工问题由生产待办生成，需要确认原生表单真正打开。 */
    function questionOpened() {
        // 1、不能把会话面板展开等同于人工问题表单。
        return (
            el("questions-dialog").open &&
            Boolean(el("questions-list").querySelector("form"))
        );
    }
    /** 因为模型提出人工问题会中断执行，需要等正式待办和人物提示同时就绪。 */
    async function waiting() {
        // 1、读取后端问题而非根据动画猜测。
        await studio.refresh();
        return (
            (await api("questions")).length === 1 &&
            studio.renderer.facts.get("assistant").requires_input
        );
    }
    /** 因为鼠标验收需要可见对象，需要只调整相机并告知外部当前可点击阶段。 */
    function requestClick(stage) {
        // 1、画面定位不替代真正点击。
        studio.renderer.focusMember("assistant");
        window.__pointerStage = stage;
    }
    try {
        await until(ready);
        await newConversation();
        await studio.chatMode();
        const conversation = state.conversation.id;
        await send("第一轮简单回复");
        await until(completed);
        await send("第二轮简单回复");
        await until(completed);
        if (studio.renderer.facts.get("assistant").bubble_pending_count !== 2)
            throw new Error("same-conversation results were not accumulated");
        // 2、等待真实鼠标一次点击，必须消除同会话两条已展示完成提示。
        requestClick("click_two_results");
        await until(resultRead);
        if (
            state.conversation.id !== conversation ||
            studio.renderer.cameraRig.drag
        )
            throw new Error("wrong conversation or pointer left captured");
        studio.roomMode();
        await studio.refresh();
        if (studio.renderer.views.get("assistant").bubbleText)
            throw new Error("read result reappeared");
        await studio.chatMode();
        await send("需要人工选择后才能继续");
        await until(waiting);
        // 3、真实鼠标打开人工表单后直接关闭，问题应继续跟随；实际提交后才解除。
        requestClick("click_question");
        await until(questionOpened);
        studio.closeQuestions();
        await studio.refresh();
        if (!studio.renderer.views.get("assistant").bubbleText)
            throw new Error("unanswered question disappeared");
        requestClick("click_question_again");
        await until(questionOpened);
        const form = el("questions-list").querySelector("form");
        form.querySelector(".question-choices button").click();
        form.requestSubmit();
        await until(completed);
        studio.closeQuestions();
        requestClick("click_final_result");
        await until(resultRead);
        if (clicks.length < 4 || clicks.some(isUntrusted))
            throw new Error("physical pointer path was not exercised");
        window.__pointerResult = {
            ok: true,
            trustedPointerDowns: clicks.length,
            sameConversationResults: 2,
            humanKeptUntilAnswered: true,
        };
    } catch (error) {
        window.__pointerResult = {
            ok: false,
            error: error.message,
            stack: error.stack,
            clicks,
        };
    } finally {
        // 4、验证结束移除测试观察器，保持生产事件处理器不变。
        document.removeEventListener("pointerdown", observePointer, true);
    }
    /** 因为不可信合成事件不能代替真实鼠标验收，需要拒绝任何非可信指针记录。 */
    function isUntrusted(value) {
        // 1、浏览器只有实际输入事件才标记 isTrusted。
        return !value;
    }
})();
