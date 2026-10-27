/** 因为纯字符串测试不能证明桌面兼容，需要检查真实消息的 DOM、链接和原始轨迹。 */
(async function verifyMarkdown() {
    // 1、等待正式桥与会话入口，不直接给时间线注入测试消息。
    /** 因为模型执行与界面刷新异步，需要有界轮询实际完成条件。 */
    async function until(check) {
        // 1、超时即失败，不强行改写执行状态。
        for (let attempt = 0; attempt < 300; attempt++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("Markdown verification timed out");
    }
    /** 因为动画与桥需要继续处理，需要异步等待下一次检查。 */
    function pause(resolve) {
        // 1、测试节奏与生产超时相互独立。
        setTimeout(resolve, 100);
    }
    /** 因为页面加载事件早于工作区初始化，需要同时确认真实空间和场景可用。 */
    function ready() {
        // 1、不创建替代生产对象。
        return state.workspace && !state.switching && studio?.data;
    }
    /** 因为回答需要经过生产执行与轨迹存储，需要同时确认终态和最终正文。 */
    async function completed() {
        // 1、正文出现不代表任务完成，读取权威运行状态。
        await loadEvents();
        return (
            !(await api("overview")).active_run &&
            Boolean(
                el("timeline").querySelector(".assistant .markdown-content h1"),
            )
        );
    }
    /** 因为任务文件读取异步，需要等实际产物预览打开后才能判断内容。 */
    function artifactOpened() {
        // 1、不能用链接存在替代真实文件读取。
        return el("file-dialog").open;
    }
    /** 因为每次回放应保持同样语义，需要复用 DOM 结构检查而不复制实现。 */
    function inspect() {
        // 1、正文支持常用格式，但代码和 HTML 仍是原文。
        const body = el("timeline").querySelector(
            ".assistant .markdown-content",
        );
        if (
            !body ||
            body.querySelector("strong")?.textContent !== "加粗" ||
            body.querySelector("em")?.textContent !== "斜体" ||
            !body.querySelector("s") ||
            !body.querySelector("ul ul li") ||
            body.querySelector("ol")?.start !== 3 ||
            !body.querySelector("blockquote") ||
            body.querySelector("table tbody td")?.textContent !== "Markdown"
        )
            throw new Error("missing Markdown structure");
        const code = body.querySelector("pre code");
        if (
            !code?.textContent.includes('print("**literal**")') ||
            code.querySelector("script") ||
            body.querySelector("p > code")?.textContent !== "a*b"
        )
            throw new Error("code was interpreted or changed");
        if (
            body.querySelector("script,img,iframe,style,object") ||
            window.__markdownAttack ||
            !body.textContent.includes(
                '<img src=x onerror="window.__markdownAttack=true">',
            )
        )
            throw new Error("HTML was not kept inert");
        const link = body.querySelector("a");
        if (
            link?.href !== "https://example.com/docs" ||
            link.target !== "_blank" ||
            link.rel !== "noopener noreferrer" ||
            body.querySelectorAll("a").length !== 1 ||
            !body.querySelector(".markdown-code-header button") ||
            !body.querySelector(".md-align-right") ||
            body.scrollWidth > body.clientWidth + 1
        )
            throw new Error("link or layout contract failed");
        return body;
    }
    try {
        await until(ready);
        await newConversation();
        await studio.chatMode();
        el("prompt").value = "生成一份 Markdown 排版和工具产物验收报告";
        await sendTask({ preventDefault: preventSubmit });
        await until(completed);
        inspect().querySelector(".markdown-artifact-link").click();
        await until(artifactOpened);
        if (el("file-content").textContent !== "**产物原文**")
            throw new Error("artifact preview did not preserve raw content");
        closeArtifact();
        // 2、通过生产接口确认原始 Markdown 未改写，重读历史仍得到相同格式。
        const events = await api("events", state.conversation.id, 0);
        const answer = events.find(isAnswer);
        if (
            !answer?.payload.text.includes("**加粗**") ||
            !el("timeline")
                .querySelector(".tool-event pre")
                ?.textContent.includes("**产物原文**")
        )
            throw new Error("trace or tool log was modified");
        const conversation = state.conversation;
        resetConversation(conversation);
        await loadEvents();
        inspect();
        window.__markdownResult = {
            ok: true,
            history: true,
            artifact: true,
            inertHtml: true,
            formats: [
                "heading",
                "strong",
                "emphasis",
                "strike",
                "nested-list",
                "ordered-list",
                "quote",
                "table",
                "code",
                "link",
            ],
        };
    } catch (error) {
        window.__markdownResult = {
            ok: false,
            error: error.message,
            stack: error.stack,
        };
    }
    /** 因为直接调用生产发送器也应阻止导航，需要提供测试事件的最小接口。 */
    function preventSubmit() {
        // 1、测试本身不产生浏览器默认提交。
    }
    /** 因为轨迹含有模型和工具事件，需要精确选择最终公开 AI 消息。 */
    function isAnswer(event) {
        // 1、检查产品事件，不根据屏幕文字猜测存储内容。
        return event.kind === "assistant.message";
    }
})();
