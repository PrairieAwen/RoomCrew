/* 独立档案室：文本/本地语义检索、完整历史分页与用户控制的共享来源。 */
"use strict";

class CrewArchive {
    /** 因为查档与共享属于人工独立入口，需要集中维护表单代次和原文分页状态。 */
    constructor() {
        // 1、所有业务经正式空间桥，界面不访问 SQLite、模型文件或凭据。
        this.generation = 0;
        this.selected = null;
        this.offset = 0;
        this.detailGeneration = 0;
        el("archive-form").addEventListener("submit", this.search.bind(this));
        el("archive-save-sharing").addEventListener("click", this.saveSharing.bind(this));
        el("archive-current").addEventListener("click", this.archiveCurrent.bind(this));
        el("archive-dialog").addEventListener("close", this.closed.bind(this));
    }

    /** 因为工作空间可能切换，需要在打开时重新读取当前空间权限和检索目录。 */
    async open() {
        // 1、打开不创建摘要、不加载完整消息，不调用远程模型。
        const token = ++this.generation;
        const epoch = state.workspaceEpoch;
        el("archive-dialog").showModal();
        el("archive-status").textContent = "正在读取档案…";
        el("archive-detail").replaceChildren();
        this.selected = null;
        try {
            const settings = await api("archive_settings");
            if (!this.current(token, epoch)) return;
            this.settings(settings);
            await this.search();
        } catch (error) { showError(error); }
    }

    /** 因为迟到请求不能把旧房间资料放入新房间，需要统一检查窗口、空间和请求代次。 */
    current(token, epoch) {
        // 1、代次是显示隔离，不代替后端每次读取的真实授权校验。
        return token === this.generation && epoch === state.workspaceEpoch && el("archive-dialog").open;
    }

    /** 因为关闭后完整原文不应留在隐藏视图，需要清空页面缓存并使旧回调失效。 */
    closed() {
        // 1、迟到 close 事件不能清除刚重新打开的窗口。
        if (el("archive-dialog").open) return;
        this.generation++;
        this.detailGeneration++;
        this.selected = null;
        el("archive-results").replaceChildren();
        el("archive-detail").replaceChildren();
    }

    /** 因为用户需明确知道可查哪些空间，需要展示有方向的来源授权和本地检索状态。 */
    settings(value) {
        // 1、名字只作为纯文本创建节点，共享写权限不提供给 Agent。
        el("archive-space").replaceChildren();
        el("archive-shares").replaceChildren();
        for (const space of value.spaces) {
            if (value.allowed_sources.includes(space.id)) {
                const option = node("option", "", space.name);
                option.value = space.id;
                el("archive-space").append(option);
            }
            if (space.id === value.workspace_id) continue;
            const label = node("label", "archive-share-option");
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.value = space.id;
            checkbox.checked = value.allowed_sources.includes(space.id);
            label.append(checkbox, node("span", "", space.name));
            el("archive-shares").append(label);
        }
        el("archive-space").value = value.workspace_id;
        el("archive-member").replaceChildren(node("option", "", "所有成员"));
        el("archive-member").firstElementChild.value = "";
        for (const member of studio.data?.members || []) {
            if (!member.agent_id) continue;
            const option = node("option", "", member.name);
            option.value = member.id;
            el("archive-member").append(option);
        }
        el("archive-health").textContent = value.vector_available
            ? "本地语义模型已就绪 · 首次查询按需加载"
            : "本地语义模型缺失 · 文本与原文查询仍可用";
    }

    /** 因为文本、成员和日期应同时生效，需要一次读取表单并转换为产品过滤合同。 */
    values() {
        // 1、日期按用户本机日界转换为 UTC，后台仍会严格验证时区与范围。
        const from = el("archive-from").value, to = el("archive-to").value;
        return {
            query: el("archive-query").value.trim(), mode: el("archive-mode").value,
            workspace_id: el("archive-space").value,
            member_id: el("archive-member").value, all_members: true,
            from_time: from ? new Date(from + "T00:00:00").toISOString() : "",
            to_time: to ? new Date(to + "T23:59:59.999").toISOString() : "",
            kind: el("archive-kind").value, limit: 20,
        };
    }

    /** 因为查询是按需读取，需要在点击或提交后拉取有限片段，不预加载全部历史。 */
    async search(event) {
        // 1、表单不导航，刷新会使先前检索和原文请求全部失效。
        event?.preventDefault();
        const token = ++this.generation, epoch = state.workspaceEpoch;
        this.detailGeneration++;
        el("archive-status").textContent = "正在检索…";
        el("archive-search").disabled = true;
        el("archive-detail").replaceChildren();
        try {
            const data = await api("archive_search", this.values());
            if (!this.current(token, epoch)) return;
            el("archive-results").replaceChildren();
            for (const record of data.archives || []) this.record(record);
            for (const result of data.results || []) this.result(result);
            const count = (data.archives || data.results || []).length;
            el("archive-status").textContent = (data.warning ? data.warning + "。" : "") +
                (count ? `找到 ${count} 项资料` : "没有找到匹配资料。未归档会话仍保存在原历史中。");
        } catch (error) {
            if (this.current(token, epoch)) el("archive-status").textContent = error.message;
        } finally {
            if (this.current(token, epoch)) el("archive-search").disabled = false;
        }
    }

    /** 因为目录条目必须说明时间、状态和摘要，需要在同一张卡片展示归档进度与证据入口。 */
    record(record) {
        // 1、摘要不可用时明确标记，不显示伪造的默认总结。
        const card = node("article", "archive-card");
        const states = { snapshot: "保存完整历史中", indexing_raw: "索引原文中", summarizing: "整理摘要中",
            indexing: "索引笔记中", ready: "归档完成", ready_text: "文本可用，向量未就绪" };
        const status = record.attempts >= 3 ? "处理失败，原文保留，可重试" : states[record.state] || record.state;
        card.append(node("h3", "", record.title), node("p", "muted", `${this.date(record.ended_at)} · ${status}`),
            node("p", "muted", `${record.member_id} · ${record.messages || 0} 条完整公开消息`),
            node("p", "archive-excerpt", record.summary || "摘要尚未生成。已保存的完整历史仍可查看。"));
        this.button(card, "查看完整消息", this.read.bind(this, record.id, 0, false));
        if (record.error) this.button(card, "重试处理", this.retry.bind(this, record.id));
        if (record.workspace_id === state.workspace.id && ["ready", "ready_text"].includes(record.state))
            this.button(card, "重建检索索引", this.reindex.bind(this, record.id));
        el("archive-results").append(card);
    }

    /** 因为语义匹配不代表事实已经核实，需要展示原始片段与准确消息定位入口。 */
    result(value) {
        // 1、用户和模型文本不进入 innerHTML，避免历史内容成为页面代码。
        const card = node("article", "archive-card");
        card.append(node("h3", "", value.kind === "note" ? "摘要 / 笔记" : "原始消息片段"),
            node("p", "muted", `${this.date(value.at)} · ${value.member_id}`),
            node("p", "archive-excerpt", value.excerpt));
        this.button(card, "查看来源消息", this.read.bind(this, value.archive_id, value.first_position, false));
        el("archive-results").append(card);
    }

    /** 因为完整消息可能很长，需要按来源稳定位置分批读取，并在每次请求后重新校验权限。 */
    async read(identifier, offset = 0, append = false) {
        // 1、当前选中的来源和读取代次共同保护分页，不串入其他档案或会议室。
        const token = this.generation, epoch = state.workspaceEpoch, detail = ++this.detailGeneration;
        this.selected = identifier;
        try {
            const data = await api("archive_read", identifier, offset, 10);
            if (!this.current(token, epoch) || detail !== this.detailGeneration) return;
            const area = el("archive-detail");
            if (!append) area.replaceChildren(node("h3", "", data.archive.title));
            area.querySelector(".archive-more")?.remove();
            for (const message of data.messages) {
                const block = node("article", "archive-message");
                block.append(node("p", "muted", `#${message.position} · ${this.date(message.at)} · ${message.actor} · ${message.role}`),
                    node("pre", "archive-original", message.text));
                area.append(block);
            }
            if (!data.messages.length) area.append(node("p", "muted", "完整历史尚在保存，请稍后刷新。"));
            if (data.has_more) this.button(area, "读取下一页", this.read.bind(this, identifier, data.next_offset, true), "archive-more");
        } catch (error) {
            if (this.current(token, epoch)) el("archive-status").textContent = error.message;
        }
    }

    /** 因为权限写入只能由用户明确操作，需要保存勾选来源并重新查询，清除旧详情。 */
    async saveSharing() {
        // 1、当前请求仍绑定原工作空间；撤销后不会继续复用缓存原文。
        const token = this.generation, epoch = state.workspaceEpoch;
        const sources = [...el("archive-shares").querySelectorAll("input:checked")].map(archiveInputValue);
        try {
            const settings = await api("archive_share", sources);
            if (!this.current(token, epoch)) return;
            this.settings(settings);
            await this.search();
            toast("档案共享来源已保存");
        } catch (error) { showError(error); }
    }

    /** 因为用户可主动结束一段工作，需要归档当前已完成会话，同时保留下一次无感续聊。 */
    async archiveCurrent() {
        // 1、活动或人工等待状态由后端拒绝，不修改自动归档的一小时阈值。
        if (!state.conversation) { toast("先选择一个已完成的会话"); return; }
        const epoch = state.workspaceEpoch;
        try {
            await api("archive_now", state.conversation.id);
            if (epoch !== state.workspaceEpoch) return;
            toast("已安排归档，完整原文会保留；你可以继续对话。");
            await this.search();
        } catch (error) { showError(error); }
    }

    /** 因为模型暂时不可用可能留下分块作业，需要让用户显式恢复而不重做原任务。 */
    async retry(identifier) {
        // 1、后台会继续未完成部分，人工操作本身不调用模型。
        try { await api("archive_retry", identifier); await this.search(); }
        catch (error) { showError(error); }
    }

    /** 因为索引可从原资料恢复，需要提供不会删除原文或再次摘要的本地重建操作。 */
    async reindex(identifier) {
        // 1、只对当前空间的完成档案开放，向量会在后台恢复。
        try { await api("archive_reindex", identifier); await this.search(); }
        catch (error) { showError(error); }
    }

    /** 因为多处展示时间，需要使用同一可读格式并保留真实日期。 */
    date(value) { /* 1、仅格式化，不更改归档时间。 */ return new Date(value).toLocaleString("zh-CN", { hour12: false }); }

    /** 因为证据入口共用结构，需要复用按钮创建并保持具名事件处理器。 */
    button(parent, text, callback, extra = "") {
        // 1、不触发表单提交，也不把数据拼接为执行脚本。
        const button = node("button", "secondary-button " + extra, text);
        button.type = "button";
        button.addEventListener("click", callback);
        parent.append(button);
    }
}

/** 因为复选值提取有独立职责，需要给共享保存使用一个明确的纯函数。 */
function archiveInputValue(input) { /* 1、只读取用户勾选的空间 ID。 */ return input.value; }
