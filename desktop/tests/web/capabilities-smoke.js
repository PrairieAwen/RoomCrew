/* 原生窗口测试驱动：仅操作当前验证窗口的生产表单与用户入口。 */
(async function verifyCapabilities() {
    let movementOrigin = null;
    /** 因为桥和真实执行结果异步到达，需要限制每个 UI 等待的最长时间。 */
    async function until(check) {
        // 1、轮询只观察状态，不跳过生产执行或伪造结果。
        for (let attempt = 0; attempt < 300; attempt++) {
            if (await check()) return;
            await new Promise(delay);
        }
        throw new Error("capability UI timeout: " + window.__capabilityPhase);
    }
    /** 因为原生窗口需要继续绘制，需要在两次检查之间释放事件循环。 */
    function delay(resolve) {
        // 1、仅控制测试节奏。
        setTimeout(resolve, 100);
    }
    /** 因为首次加载尚未选择空间，需要等待真实桥和人物列表。 */
    function ready() {
        // 1、确认生产对象已初始化，不创建替代服务。
        return Boolean(
            window.pywebview?.api &&
                state.workspace &&
                studio?.data &&
                !state.switching,
        );
    }
    /** 因为表单保存异步返回，需要等待对话框真正关闭。 */
    function saved() {
        // 1、校验闭合状态和页面错误反馈。
        return !el("member-dialog").open;
    }
    /** 因为人工等待必须来自持久化 interrupt，需要查询真实待办。 */
    async function waiting() {
        // 1、同时刷新人物，验证问题泡泡由真实状态产生。
        await studio.refresh();
        return (
            (await api("questions")).length === 1 &&
            studio.renderer.facts.get("assistant")?.requires_input
        );
    }
    /** 因为完成不能依据模型文字猜测，需要观察真实终态和人物泡泡。 */
    async function completed() {
        // 1、会话与场景各读取其正式接口，不能用动画回调决定成功。
        await loadEvents();
        await studio.refresh();
        const overview = await api("overview");
        return (
            !overview.active_run &&
            studio.renderer.facts.get("assistant")?.activity === "reporting"
        );
    }
    try {
        window.__capabilityPhase = "initialization";
        await until(ready);
        window.__capabilityPhase = "configuration";
        studio.selected = "assistant";
        await studio.editMember();
        el("member-skills").value = JSON.stringify(__SKILLS__);
        el("member-mcp").value = JSON.stringify([
            { name: "math", url: __MCP_URL__, enabled: true },
        ]);
        el("member-python").checked = true;
        el("member-tab-material").click();
        if (
            !el("member-panel-agent").hidden ||
            el("member-panel-material").hidden
        )
            throw new Error("agent/material tabs were not separated");
        el("bundle-avatar").click();
        await until(materialReady);
        el("binding-category").value = "completed";
        el("binding-category").dispatchEvent(new Event("change"));
        el("binding-action").value = "report";
        el("binding-action").dispatchEvent(new Event("change"));
        el("binding-clip").selectedIndex = 1;
        el("binding-clip").dispatchEvent(new Event("change"));
        el("binding-fps").value = "7";
        el("binding-loop").checked = false;
        el("binding-apply").click();
        if (!el("binding-summary").textContent.includes("7 fps"))
            throw new Error("custom frame configuration did not apply");
        el("member-question-bubble").value = "老板，请帮我选一下。";
        el("member-completed-bubble").value = "验收完成，点击查看产物。";
        el("member-form").requestSubmit();
        await until(saved);
        const member = await api("member", "assistant");
        if (
            !member.python_enabled ||
            member.skills.length !== 1 ||
            member.mcp_servers.length !== 1 ||
            member.material_profile.bindings.completed.fps !== 7
        )
            throw new Error("capabilities were not persisted");
        await studio.chatMode();
        await newConversation();
        el("prompt").value =
            "按配置技能计算，查询 MCP，运行 Python，经过人工确认再汇总。";
        el("composer").requestSubmit();
        window.__capabilityPhase = "human_interrupt";
        await until(waiting);
        const view = studio.renderer.views.get("assistant");
        if (view.bubbleButton.textContent !== "老板，请帮我选一下。")
            throw new Error("question bubble missing");
        view.bubbleButton.click();
        await until(questionVisible);
        studio.closeQuestions();
        await studio.refresh();
        if (!view.bubbleText || view.bubble.getAttribute("display") === "none")
            throw new Error(
                "closing a question form cleared the unanswered bubble",
            );
        view.bubbleButton.click();
        await until(questionVisible);
        const form = el("questions-list").querySelector("form");
        if (
            !form
                .querySelector(".question-choices")
                .textContent.includes("其他 / 补充")
        )
            throw new Error("free answer option missing");
        form.querySelector(".question-choices button").click();
        form.requestSubmit();
        window.__capabilityPhase = "completion";
        await until(completed);
        studio.closeQuestions();
        const result = await api(
            "read_artifact",
            state.conversation.id,
            "/native-result.json",
        );
        if (!JSON.stringify(result).includes("5050"))
            throw new Error("actual Python artifact missing");
        if (
            studio.renderer.facts.get("assistant").bubble !==
            "验收完成，点击查看产物。"
        )
            throw new Error("completion bubble missing");
        for (const card of el("timeline").querySelectorAll("summary"))
            if (
                card.textContent.includes("ask_user") &&
                card.textContent.includes("未确认完成")
            )
                throw new Error("normal human resume was shown as failed");
        const timeline = el("timeline").getBoundingClientRect();
        if (timeline.left < innerWidth / 2 || timeline.right > innerWidth)
            throw new Error("conversation is not docked on the right");
        if (view.bubble.parentNode !== studio.renderer.bubbles)
            throw new Error("bubble must remain above furniture");
        studio.renderer.focusMember("assistant");
        await new Promise(delay);
        const bubbleBounds = view.bubble.getBoundingClientRect();
        verifyActualAnchor();
        if (
            view.bubble.dataset.speaker !== "assistant" ||
            view.bubbleLink.dataset.speaker !== "assistant"
        )
            throw new Error("bubble is not bound to its actor");
        await new Promise(delay);
        if (
            !view.sprite ||
            !member.material_profile.bindings.completed.frames.includes(
                Number(view.sprite.dataset.frame),
            )
        )
            throw new Error("configured frame sequence was not rendered");
        studio.renderer.camera(1.1);
        await new Promise(delay);
        const zoomed = view.bubble.getBoundingClientRect();
        if (Math.abs(zoomed.width - bubbleBounds.width) > 1)
            throw new Error("bubble changed screen size with camera zoom");
        verifyActualAnchor();
        // 3、通过正式换座入口实际行走，泡泡必须跟随素材并保持未读，不能用固定偏移冒充。
        movementOrigin = actualHead();
        const startBubble = view.bubble.getBoundingClientRect();
        await studio.moveTo("sofa");
        await until(actorMoved);
        verifyActualAnchor();
        const movedBubble = view.bubble.getBoundingClientRect();
        if (
            Math.hypot(
                movedBubble.left - startBubble.left,
                movedBubble.top - startBubble.top,
            ) < 20
        )
            throw new Error("bubble stayed fixed while the material moved");
        const oldConversation =
            studio.renderer.facts.get("assistant").bubble_notice
                .conversation_id;
        await newConversation();
        await studio.refresh();
        if (!view.bubbleText)
            throw new Error("conversation switch cleared unread result");
        view.bubbleButton.click();
        await until(resultRead);
        await studio.refresh();
        if (view.bubbleText || state.conversation.id !== oldConversation)
            throw new Error(
                "read receipt did not persist or opened the wrong conversation",
            );
        window.__capabilitiesResult = {
            ok: true,
            skills: true,
            mcp: true,
            python: true,
            human: true,
            bubbles: true,
            rightDock: true,
            separateConfig: true,
            customFrames: true,
            bubbleFollowsActor: true,
            actualWalking: true,
            persistentUntilRead: true,
        };
    } catch (error) {
        window.__capabilitiesResult = {
            ok: false,
            error: error.message,
            phase: window.__capabilityPhase,
            toast: el("toast")?.textContent,
        };
    }
    /** 因为点击泡泡后表单需要异步加载，需要确认真实问题卡已展示。 */
    function questionVisible() {
        // 1、只观察模态框和正式表单。
        return (
            el("questions-dialog").open &&
            el("questions-list").querySelector("form")
        );
    }
    /** 因为图集导入和编辑器缓存分别异步加载，需要等待真实可选帧清单。 */
    function materialReady() {
        // 1、只读取生产编辑器状态，不补造帧或图集。
        return (
            el("member-avatar").value.startsWith("avatar:") &&
            studio.memberConfiguration.actions.manifest?.clips?.length
        );
    }
    /** 因为图集起坐会改变实际素材边界，需要读取本帧真正显示的裁切区域。 */
    function actualHead() {
        // 1、精确图集取裁切层，内置人物取骨架头部。
        const current = studio.renderer.views.get("assistant");
        const box = (
            current.spriteFrame ||
            current.sprite ||
            current.rig.head
        ).getBoundingClientRect();
        return { x: box.left + box.width / 2, y: box.top };
    }
    /** 因为泡泡连线必须指向对应素材，需要比较实际 SVG 端点与本帧头部边界。 */
    function verifyActualAnchor() {
        // 1、不使用固定身高推算，直接检查正式渲染结果。
        const current = studio.renderer.views.get("assistant"),
            head = actualHead();
        const path = current.bubbleLink;
        const end = path
            .getPointAtLength(path.getTotalLength())
            .matrixTransform(path.getScreenCTM());
        if (Math.hypot(end.x - head.x, end.y - head.y) > 2)
            throw new Error("bubble pointer is detached from actual material");
        if (
            !current.bubbleText ||
            current.bubble.getAttribute("display") === "none"
        )
            throw new Error("unread bubble disappeared");
    }
    /** 因为跟随必须在真正行走中验证，需要等待实际人物移动至少三十屏幕像素。 */
    function actorMoved() {
        // 1、起坐也会改变高度，要求角色处于真实 moving 阶段。
        const actor = studio.renderer.motion.actors.get("assistant"),
            head = actualHead();
        return (
            actor.phase === "moving" &&
            Math.hypot(head.x - movementOrigin.x, head.y - movementOrigin.y) >
                30
        );
    }
    /** 因为查看是异步操作，需要等待正确会话打开且服务端回执令泡泡消失。 */
    function resultRead() {
        // 1、按实际页面和当前人物快照判断，不手动隐藏显示节点。
        return !studio.renderer.views.get("assistant").bubbleText;
    }
})();
