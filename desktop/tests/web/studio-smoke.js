/** 因为会议室验收需要覆盖可见控件，需要通过真实表单和人物点击完成工作流。 */
(async function verifyStudio() {
    /** 因为后端与页面异步更新，需要有界等待可观察的状态。 */
    async function until(check) {
        // 1、失败在二十秒内报告，不改变生产超时。
        for (let i = 0; i < 200; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("studio condition timed out");
    }
    /** 因为测试不能忙等，需要在检查之间释放前端事件循环。 */
    function pause(resolve) {
        // 1、只控制测试采样间隔。
        setTimeout(resolve, 100);
    }
    /** 因为页面尚未初始化时不能填表，需要先观察实际场景快照。 */
    function ready() {
        // 1、真实 bridge 和绘制器同时就绪。
        return (
            typeof studio !== "undefined" &&
            studio?.data &&
            studio.renderer.views.size === 2
        );
    }
    /** 因为配置保存异步返回，需要观察用户可见的加密保存结果。 */
    function saved() {
        // 1、不从点击成功推定配置已保存。
        return el("settings-result").textContent.includes("已加密保存");
    }
    /** 因为招募会刷新账号快照，需要等待真实第四位成员出现。 */
    function recruited() {
        // 1、名字与人物数量同时符合。
        return (
            studio.data.members.length === 3 && studio.data.members.some(named)
        );
    }
    /** 因为测试人物名字只在测试里出现，需要按纯显示文本确认表单生效。 */
    function named(member) {
        // 1、身份随后仍使用后端生成的 ID。
        return member.name === "窗口资料员";
    }
    /** 因为人工等待只能由后端确定，需要读取真实待办和运行状态。 */
    async function waiting() {
        // 1、正文问号不是判定依据。
        return (
            (await api("questions")).length === 1 &&
            !(await api("overview")).active_run
        );
    }
    /** 因为完成必须依据真实运行，需要同时确认已无待办和任务终态。 */
    async function completed() {
        // 1、先观察全局空闲，再查询完整会话真实终态。
        if (
            (await api("overview")).active_run ||
            (await api("questions")).length
        )
            return false;
        const events = await api("events", state.conversation.id, 0);
        return events.some(isCompleted);
    }
    /** 因为模型回复不能代表完成，需要只识别产品终态事件。 */
    function isCompleted(event) {
        // 1、依据确定性事件类型。
        return event.kind === "run.completed";
    }
    try {
        // 1、默认场景不得加载全日志；通过实际招募表单保存新人物。
        window.__studioStage = "boot";
        await until(ready);
        const canvasBox = el("room-canvas").getBoundingClientRect();
        if (
            Math.abs(canvasBox.left) > 1 ||
            Math.abs(canvasBox.top) > 1 ||
            Math.abs(canvasBox.width - window.innerWidth) > 1 ||
            Math.abs(canvasBox.height - window.innerHeight) > 1
        )
            throw new Error("workspace does not cover client area");
        if (
            state.cursor !== 0 ||
            !document.body.classList.contains("studio-mode")
        )
            throw new Error("raw trace loaded without selection");
        window.__studioStage = "form";
        el("toggle-team").click();
        el("add-member").click();
        el("member-name").value = "窗口资料员";
        el("member-description").value = "整理用户资料";
        el("member-glasses").checked = true;
        el("member-leisure-action").value = "random";
        for (const box of el("member-leisure-pool").querySelectorAll("input"))
            box.checked = box.value === "water";
        el("member-leisure-delay").value = "0";
        el("import-avatar").click();
        /** 因为导入只在校验后才可绑定，需要等待生产接口的真实结果。 */
        function imported() {
            // 1、只替代原生文件选择，PNG 解码、清单校验和复制均由真实实现完成。
            return el("avatar-feedback").textContent.includes("已校验并复制");
        }
        await until(imported);
        window.__studioStage = "imported";
        el("preview-action").value = "run";
        el("preview-expression").value = "curious";
        el("preview-direction").value = "e";
        el("preview-action").dispatchEvent(new Event("change"));
        /** 因为静态占位图不代表动画可用，需要检查真实图集与表情变体进入预览。 */
        function atlasReady() {
            // 1、正式播放器应选中导入包的精确动作、朝向、姿态和表情组合。
            return document.querySelector(
                '#avatar-preview svg[data-variant="run.e.standing.curious"]',
            );
        }
        await until(atlasReady);
        window.__studioStage = "atlas-ready";
        const initialFrame = atlasReady().dataset.frame;
        /** 因为图集动画需要实际选帧，需要等待当前帧随播放时间改变。 */
        function atlasAdvanced() {
            // 1、没有修改测试时间或伪造帧值。
            return atlasReady()?.dataset.frame !== initialFrame;
        }
        await until(atlasAdvanced);
        // 2、真实手绘图集通过相同入口导入，矩形裁切与背面镜像进入正式播放器。
        el("portrait-avatar").click();
        /** 因为旧图集反馈可能暂留，需要同时确认新素材名字和 v2 裁切容器。 */
        function portraitReady() {
            // 1、只观察正式导入及正式图集播放器，不替换图片或时间。
            return (
                el("member-avatar").selectedOptions[0]?.textContent.includes(
                    "手绘",
                ) &&
                document.querySelector(
                    '#avatar-preview svg[viewBox="0 0 192 168"] svg',
                )
            );
        }
        await until(portraitReady);
        el("preview-action").value = "walk";
        el("preview-posture").value = "standing";
        el("preview-direction").value = "nw";
        el("preview-action").dispatchEvent(new Event("change"));
        /** 因为真实背面美术应能镜像为西北，需要观察实际 SVG 的变体与翻转。 */
        function paintedBack() {
            // 1、检查实际渲染节点而非期望中的清单字符串。
            return document.querySelector(
                '#avatar-preview svg[data-variant="walk.ne.standing.neutral"][data-mirrored="true"]',
            );
        }
        await until(paintedBack);
        const cropFrame = paintedBack().dataset.frame;
        /** 因为 v2 裁切也需要真正播放，需要确认背面步态帧发生变化。 */
        function paintedAdvanced() {
            // 1、不修改帧号或播放器时钟。
            return paintedBack()?.dataset.frame !== cropFrame;
        }
        await until(paintedAdvanced);
        el("preview-sequence").click();
        /** 因为连播只是素材预览，需要观察它按真实时间进入走路且没有启动任务。 */
        function previewAdvanced() {
            // 1、检查生产预览控件及实际输出，不调用模型。
            return (
                el("avatar-preview").dataset.action === "walk" &&
                el("preview-mode").textContent.includes("不提交任务")
            );
        }
        await until(previewAdvanced);
        el("preview-sequence").click();
        // 3、完整两页角色通过真实按钮导入，工作页与基础页切换不得重设纹理 URL。
        el("bundle-character").value = "employee";
        el("bundle-avatar").click();
        /** 因为旧预览会暂时保留，需要等待新角色的两张实际 SVG 纹理。 */
        function bundleReady() {
            // 1、同时验证正式导入的名称与页数。
            return (
                el("member-avatar").selectedOptions[0]?.textContent.includes(
                    "小岚",
                ) &&
                document.querySelectorAll("#avatar-preview svg image")
                    .length === 2
            );
        }
        await until(bundleReady);
        el("preview-action").value = "read";
        el("preview-posture").value = "seated";
        el("preview-direction").value = "se";
        el("preview-expression").value = "neutral";
        el("preview-action").dispatchEvent(new Event("change"));
        /** 因为读写帧位于第二页，需要核对正式播放器实际显示的页与姿态。 */
        function workPage() {
            // 1、源图页号和精确片段必须一致。
            return document.querySelector(
                '#avatar-preview svg[data-page="1"][data-variant="read.se.seated.neutral"]',
            );
        }
        await until(workPage);
        const pageSources = Array.from(
            document.querySelectorAll("#avatar-preview image"),
            imageSource,
        );
        /** 因为选帧不应重复写入大图 URL，需要记录已创建纹理供切换后比较。 */
        function imageSource(image) {
            // 1、只检查测试页面已加载图像，不输出图片内容。
            return image.getAttribute("href");
        }
        el("preview-action").value = "run";
        el("preview-action").dispatchEvent(new Event("change"));
        /** 因为走跑位于第一页，需要等待真实跨页切换完成。 */
        function corePage() {
            // 1、不是仅修改清单中的期望值。
            return document.querySelector(
                '#avatar-preview svg[data-page="0"][data-variant="run.se.standing.neutral"]',
            );
        }
        await until(corePage);
        const afterSources = Array.from(
            document.querySelectorAll("#avatar-preview image"),
            imageSource,
        );
        if (JSON.stringify(pageSources) !== JSON.stringify(afterSources))
            throw new Error("texture URL changed during page selection");
        el("member-form").requestSubmit();
        await until(recruited);
        window.__studioStage = "recruited";
        const member = studio.data.members.find(named);
        if (!member.avatar_id.startsWith("avatar:"))
            throw new Error("material binding not persisted");
        /** 因为空闲动画必须由真实无任务快照触发，需要检查站姿手绘浇花与坐姿缺帧骨架回退。 */
        function memberRelaxing() {
            // 1、不修改轨迹或帧时钟，观察生产渲染器实际输出。
            const view = studio.renderer.views.get(member.id);
            return (
                view?.group.dataset.leisure === "true" &&
                view.group.dataset.clip === "water" &&
                (view.group.dataset.posture === "standing"
                    ? view.sprite?.dataset.page === "1"
                    : view.rig.props.water.getAttribute("visibility") ===
                      "visible")
            );
        }
        await until(memberRelaxing);
        if (member.leisure_action !== "water" || member.leisure_delay !== 0)
            throw new Error("leisure profile not persisted");
        document
            .querySelector('[data-member="assistant"].crew-avatar')
            .dispatchEvent(new MouseEvent("click", { bubbles: true }));
        el("anchor-target").value = "sofa";
        await studio.moveSelected();
        if (studio.renderer.motion.actors.get("assistant").route.length === 0)
            throw new Error("move plan not applied");
        // 2、真实模型配置入口只存合成凭据，并通过 @成员路由到员工主线程。
        await openSettings();
        el("base-url").value = ENDPOINT;
        el("model-id").value = "private-test-model-identifier";
        el("api-key").value = "synthetic-test-key-never-a-real-credential";
        el("settings-form").requestSubmit();
        await until(saved);
        closeSettings();
        await newConversation();
        el("prompt").value = "@窗口资料员 先询问我的心情，再保存给定记录";
        el("composer").requestSubmit();
        await until(waiting);
        window.__studioStage = "waiting";
        await studio.refresh();
        if (state.cursor !== 0) throw new Error("room polled full messages");
        const fact = studio.renderer.facts.get(member.id);
        if (!fact?.requires_input || fact.activity !== "question")
            throw new Error("human state not projected");
        /** 因为真实提问和赴约应能同时展示，需要检查跑步没有抹去人工表情。 */
        function runningQuestion() {
            // 1、读取生产帧循环写入的实际角色状态。
            const group = studio.renderer.views.get(member.id).group;
            return (
                group.dataset.expression === "curious" &&
                group.dataset.leisure === "false"
            );
        }
        await until(runningQuestion);
        window.__studioStage = "animated-question";
        el("show-questions").click();
        /** 因为待办表单来自按需查询，需要等待它实际出现。 */
        function questionShown() {
            // 1、检查生产表单而非模拟状态。
            return (
                el("questions-dialog").open &&
                document.querySelector(".question-card textarea")
            );
        }
        await until(questionShown);
        const form = document.querySelector(".question-card");
        form.querySelector("textarea").value = "平静";
        form.requestSubmit();
        await until(completed);
        el("close-questions").click();
        // 3、完成后先观察自动恢复生活，再点击员工中止摸鱼并展开真实轨迹。
        window.__studioStage = "resume-leisure";
        await until(memberRelaxing);
        await studio.refresh();
        document
            .querySelector('[data-member="' + member.id + '"].crew-avatar')
            .dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await studio.traceTab();
        await new Promise(pause);
        if (!el("member-trace").textContent.includes("human.requested"))
            throw new Error("missing selected trace");
        const file = await api(
            "read_artifact",
            state.conversation.id,
            "/studio.txt",
        );
        if (file.text !== "原生窗口真实工具记录")
            throw new Error("wrong artifact");
        const replay = await api("studio_feed", 0);
        /** 因为快速工具状态可能被轮询合并，需要验证源轨迹留下了可丢弃的书写线索。 */
        function writeCue(value) {
            // 1、线索只有动作语义，不包含工具输入或输出正文。
            return value.action === "write" && value.visual_only;
        }
        if (!replay.cues.some(writeCue))
            throw new Error("missing real tool animation cue");
        if (
            studio.renderer.views.get(member.id).group.dataset.leisure ===
            "true"
        )
            throw new Error("click did not interrupt idle activity");
        if (document.body.scrollWidth > window.innerWidth + 1)
            throw new Error("horizontal layout overflow");
        const sendBox = el("send").getBoundingClientRect();
        if (sendBox.bottom > window.innerHeight + 1)
            throw new Error(
                `composer overflow: ${sendBox.bottom}/${window.innerHeight}`,
            );
        window.__studioSmoke = {
            ok: true,
            members: studio.data.members.length,
            selected: studio.selected,
            sceneRevision: studio.data.scene.room.revision,
            rawCursor: state.cursor,
            atlasAnimated: true,
            traceExpression: true,
            fullCanvas: true,
            leisureLifecycle: true,
            handPaintedAtlas: true,
            completeMaterialBundle: true,
        };
    } catch (error) {
        window.__studioSmoke = {
            ok: false,
            error: error.message,
            stage: window.__studioStage,
        };
    }
})();
