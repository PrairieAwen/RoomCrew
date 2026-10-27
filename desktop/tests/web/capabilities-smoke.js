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
        if (__USE_ATLAS__) {
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
        }
        el("member-question-bubble").value = "老板，请帮我选一下。";
        el("member-completed-bubble").value = "验收完成，点击查看产物。";
        el("member-form").requestSubmit();
        await until(saved);
        const member = await api("member", "assistant");
        if (
            !member.python_enabled ||
            member.skills.length !== 1 ||
            member.mcp_servers.length !== 1 ||
            (__USE_ATLAS__ &&
                member.material_profile.bindings.completed.fps !== 7)
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
        for (const [identifier, fact] of studio.renderer.facts)
            if (
                identifier !== "assistant" &&
                (fact.bubble || fact.requires_input)
            )
                throw new Error(
                    "delegated human question leaked to a worker bubble",
                );
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
                .querySelector("small")
                .textContent.startsWith(view.member.name)
        )
            throw new Error(
                "human form presenter did not match the entry agent",
            );
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
        for (const [identifier, fact] of studio.renderer.facts)
            if (identifier !== "assistant" && fact.bubble)
                throw new Error("child completion produced a separate bubble");
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
        if (
            view.bubble.parentNode !== view.bubbleMount ||
            view.bubbleMount.parentNode !== view.bubbleActor ||
            view.bubbleActor.parentNode !== studio.renderer.bubbles ||
            studio.renderer.bubbles.previousSibling !== studio.renderer.depth
        )
            throw new Error(
                "bubble must share actor space above the furniture layer",
            );
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
            __USE_ATLAS__ &&
            (!view.sprite ||
                !member.material_profile.bindings.completed.frames.includes(
                    Number(view.sprite.dataset.frame),
                ))
        )
            throw new Error("configured frame sequence was not rendered");
        studio.renderer.camera(1.1);
        await new Promise(delay);
        const zoomed = view.bubble.getBoundingClientRect();
        if (Math.abs(zoomed.width / bubbleBounds.width - 1.1) > 0.02)
            throw new Error("bubble did not scale together with its actor");
        verifyActualAnchor();
        // 3、通过正式换座入口实际行走，泡泡必须继承人物变换并保持未读。
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
        await verifyWholeWalk();
        // 4、可选人工观察保留真实未读结果，不注入泡泡、不改变回执。
        if (__VISUAL_REVIEW__) {
            window.__capabilityPhase = "visual_review";
            await new Promise(reviewDelay);
        }
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
            customFrames: __USE_ATLAS__,
            material: __USE_ATLAS__ ? "atlas" : "builtin",
            bubbleFollowsActor: true,
            actualWalking: true,
            persistentUntilRead: true,
            wholeWalk: window.__bubbleWalkMetrics,
            mainAgentBubblesOnly: true,
        };
    } catch (error) {
        window.__capabilitiesResult = {
            ok: false,
            error: error.message,
            phase: window.__capabilityPhase,
            walkMetrics: window.__bubbleWalkMetrics,
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
    /** 因为逐帧裁切框会变化，需要以实际人物根节点的位置作为移动参照。 */
    function actualHead() {
        // 1、使用浏览器实际渲染的角色根矩阵，不追逐图集帧留白。
        const current = studio.renderer.views.get("assistant");
        return new DOMPoint(0, 0).matrixTransform(current.group.getScreenCTM());
    }
    /** 因为连线接上不代表泡泡本体稳定，需要检查真实父子关系和本体相对人物的水平中心。 */
    function verifyActualAnchor() {
        // 1、泡泡中心必须在当前人物根中心，走动、转向或镜头变化不能令其横向漂移。
        const current = studio.renderer.views.get("assistant"),
            head = actualHead();
        const box = current.bubble.getBoundingClientRect();
        if (
            current.bubbleMount.parentNode !== current.bubbleActor ||
            Math.abs(box.left + box.width / 2 - head.x) > 2
        )
            throw new Error("bubble body is detached from its actor root");
        if (
            !current.bubbleText ||
            current.bubble.getAttribute("display") === "none"
        )
            throw new Error("unread bubble disappeared");
        // 2、尾巴与实际按钮本体必须相连，不能只检查 foreignObject 的空白容器。
        const body = current.bubbleButton.getBoundingClientRect();
        const pointer = current.bubbleLink.getBoundingClientRect();
        if (body.bottom < pointer.top - 1 || body.bottom > pointer.bottom)
            throw new Error("bubble pointer is detached from the visible body");
        // 3、提示本体必须实际可点击，不能被前景家具盖住但几何检查仍通过。
        if (
            document.elementFromPoint(
                body.left + body.width / 2,
                body.top + body.height / 2,
            ) !== current.bubbleButton
        )
            throw new Error("visible bubble button was covered");
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
    /** 因为抽查几个位置会漏掉行走漂移，需要逐帧检查泡泡相对人物根节点的局部位置。 */
    async function verifyWholeWalk() {
        // 1、完整采样剩余路线，中途通过正式定位入口切换观察人物以覆盖镜头平移。
        const samples = [];
        const started = performance.now();
        let frames = 0;
        while (performance.now() - started < 20000) {
            await new Promise(nextFrame);
            const actor = studio.renderer.motion.actors.get("assistant");
            const current = studio.renderer.views.get("assistant");
            if (actor.phase === "moving") {
                const local = current.group
                    .getScreenCTM()
                    .inverse()
                    .multiply(current.bubble.getScreenCTM());
                samples.push({ x: local.e, y: local.f });
                frames += 1;
                if (frames === 20) studio.renderer.focusMember("guardian");
                if (frames === 40) studio.renderer.focusMember("assistant");
            }
            if (actor.phase === "settled" && frames > 10) break;
        }
        // 2、局部偏移应该稳定；不能用“尾线端点刚好连接”代替泡泡本体的固定挂载。
        let minX = Infinity,
            maxX = -Infinity,
            minY = Infinity,
            maxY = -Infinity;
        for (const point of samples) {
            minX = Math.min(minX, point.x);
            maxX = Math.max(maxX, point.x);
            minY = Math.min(minY, point.y);
            maxY = Math.max(maxY, point.y);
        }
        const drift = Math.hypot(maxX - minX, maxY - minY);
        window.__bubbleWalkMetrics = { frames, localDrift: drift };
        if (frames < 40 || drift > 0.5)
            throw new Error(
                `bubble local attachment drift: ${drift.toFixed(2)}, frames=${frames}`,
            );
    }
    /** 因为漂移发生在帧间，需要把采样安排到实际动画帧。 */
    function nextFrame(resolve) {
        // 1、只观察正式绘制结果，不修改动作时间或伪造人物位置。
        requestAnimationFrame(resolve);
    }
    /** 因为原生截图需要观察真实未读泡泡，需要在可选人工模式短暂延迟点击回执。 */
    function reviewDelay(resolve) {
        // 1、只延迟测试操作，生产渲染和后台刷新照常进行。
        setTimeout(resolve, 20000);
    }
})();
