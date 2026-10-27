/* 工作空间目录、显式房间切换和迟到响应隔离；不停止后台执行。 */
"use strict";

class CrewWorkspaces {
    /** 因为一个空间只显示一间会议室，需要集中管理用户选择和临时输入草稿。 */
    constructor() {
        // 1、草稿只驻留内存，模型 Key 不进入此缓存。
        this.drafts = new Map();
        this.busy = false;
        this.editing = false;
        el("create-workspace").addEventListener(
            "click",
            this.create.bind(this),
        );
        el("quick-create-workspace").addEventListener(
            "click",
            this.create.bind(this),
        );
        el("open-archive").addEventListener(
            "click",
            this.openArchive.bind(this),
        );
        el("close-archive").addEventListener(
            "click",
            this.closeArchive.bind(this),
        );
        el("rename-workspace").addEventListener(
            "click",
            this.rename.bind(this),
        );
        el("workspace-form").addEventListener("submit", this.save.bind(this));
        el("close-workspace").addEventListener("click", this.close.bind(this));
    }

    /** 因为首次请求必须有确定的空间身份，需要先恢复目录选择再读取场景。 */
    async initialize() {
        // 1、目录接口不读取模型秘密或其他房间的任务正文。
        await this.apply(await api("workspace_state"));
    }

    /** 因为侧栏只需显示房间状态，需要用安全文本和最小计数绘制目录。 */
    render(rooms) {
        // 1、名称不能变成 HTML；只有稳定 ID 能作为切换依据。
        const panel = el("workspaces");
        const signature = JSON.stringify([state.workspace?.id, rooms]);
        if (this.signature === signature) return;
        this.signature = signature;
        panel.replaceChildren();
        el("workspace-count").textContent = rooms.length;
        for (const room of rooms) {
            const button = node(
                "button",
                `workspace-card ${room.id === state.workspace?.id ? "selected" : ""}`,
            );
            button.dataset.workspace = room.id;
            button.setAttribute(
                "aria-current",
                room.id === state.workspace?.id ? "true" : "false",
            );
            const text = node("div", "workspace-title", room.name);
            const status = room.active_runs
                ? `执行中 · ${room.active_runs}`
                : room.pending_count
                  ? `待答复 · ${room.pending_count}`
                  : room.status;
            text.append(node("small", "", `会议室 · ${status}`));
            button.append(node("span", "", "◈"), text);
            button.addEventListener("click", this.choose.bind(this));
            panel.append(button);
        }
        el("workspace-name").textContent =
            state.workspace?.name || "我的工作空间";
        el("room-name").textContent =
            `${state.workspace?.name || "工作空间"} · 会议室`;
    }

    /** 因为用户切换房间时旧任务仍在执行，需要只请求改变活动空间并隔离迟到界面响应。 */
    async choose(event) {
        // 1、同一空间不重建画布，连续点击在切换期间被合并。
        const id = event.currentTarget.dataset.workspace;
        if (this.busy || id === state.workspace?.id) return;
        this.begin();
        try {
            await this.apply(await api("select_workspace", id));
        } catch (error) {
            showError(error);
            await this.recover();
        } finally {
            this.finish();
        }
    }

    /** 因为切换不能串用草稿、人物和任务按钮，需要在目录操作前冻结旧视图。 */
    begin() {
        // 1、代次先递增，让所有已经发出的业务请求失效；执行仍绑定旧空间。
        this.busy = true;
        state.switching = true;
        state.workspaceEpoch++;
        if (state.workspace)
            this.drafts.set(state.workspace.id, el("prompt").value);
        el("send").disabled = true;
        // 2、关闭含空间身份的浮层，避免用户在新房间保存旧成员或回复旧问题。
        for (const dialog of document.querySelectorAll("dialog[open]"))
            dialog.close();
        el("asset-library-frame").removeAttribute("src");
        clearKey();
    }

    /** 因为新会议室可能有相同成员 ID 和布局版本，需要清空全部表现游标后恢复它自己的状态。 */
    async apply(directory) {
        // 1、业务身份只来自后端目录，不使用房间名称作为路径或授权。
        state.workspace = directory.active;
        state.switching = false;
        state.run = null;
        state.sending = false;
        resetConversation(null);
        studio.resetWorkspace();
        el("prompt").value = this.drafts.get(state.workspace.id) || "";
        el("stop").disabled = false;
        this.render(directory.workspaces);
        // 2、只恢复本空间会话；房间视图仍按需展开原始轨迹。
        const data = await api("overview");
        if (data.conversations.length) resetConversation(data.conversations[0]);
        renderOverview(data);
        await studio.refresh();
        await loadEvents();
        await refreshArtifacts();
    }

    /** 因为目录请求失败不能把界面永久锁住，需要重新读取后端确认的活动会议室。 */
    async recover() {
        // 1、不盲目重试创建，避免一次点击产生多个空间。
        try {
            await this.apply(await api("workspace_state"));
        } catch (error) {
            state.switching = true;
            showError(error);
        }
    }

    /** 因为切换后的按钮需要恢复可操作状态，需要释放界面锁而不改写后台运行状态。 */
    finish() {
        // 1、发送是否可用仍取决于当前会议室的权威 Run 状态。
        this.busy = false;
        el("save-workspace").disabled = false;
        el("send").disabled =
            state.switching || Boolean(state.run) || state.sending;
    }

    /** 因为新空间应由用户命名，需要打开有明确说明的本地表单。 */
    create() {
        // 1、切换未结束前不接受新的目录操作。
        if (this.busy) return;
        this.editing = false;
        this.open("新建工作空间", "创建并进入", "");
    }

    /** 因为改名不能重置数据，需要复用同一表单并保留稳定空间身份。 */
    rename() {
        // 1、空目录或正在切换时不执行改名。
        if (this.busy || !state.workspace) return;
        this.editing = true;
        this.open("重命名工作空间", "保存名称", state.workspace.name);
    }

    /** 因为两类目录编辑共享输入要求，需要统一设置标题并聚焦名称。 */
    open(title, button, value) {
        // 1、所有展示值以文本赋值，输入不涉及模型配置。
        el("workspace-dialog-title").textContent = title;
        el("save-workspace").textContent = button;
        el("workspace-title").value = value;
        el("workspace-result").textContent = "";
        el("workspace-dialog").showModal();
        el("workspace-title").focus();
    }

    /** 因为取消命名不应产生空间，需要只关闭表单。 */
    close() {
        // 1、没有提交则不写目录或创建会议室。
        el("workspace-dialog").close();
    }

    /** 因为档案室尚无归档执行能力，需要只打开说明，不触发模型、读取或迁移资料。 */
    openArchive() {
        // 1、基础设施入口独立于员工名单，也不改变当前会议室。
        el("archive-dialog").showModal();
    }

    /** 因为查看规划入口不应保留模态状态，需要提供明确的关闭操作。 */
    closeArchive() {
        // 1、关闭说明没有数据副作用。
        el("archive-dialog").close();
    }

    /** 因为创建和重命名都要落盘，需要通过用户入口提交并恢复对应房间。 */
    async save(event) {
        // 1、表单验证名称边界，后端仍会再次校验；不把名称变成文件路径。
        event.preventDefault();
        if (this.busy) return;
        const name = el("workspace-title").value.trim();
        if (!name) return;
        const editing = this.editing;
        const id = state.workspace.id;
        this.begin();
        el("save-workspace").disabled = true;
        try {
            const directory = editing
                ? await api("rename_workspace", id, name)
                : await api("create_workspace", name);
            await this.apply(directory);
        } catch (error) {
            showError(error);
            await this.recover();
        } finally {
            this.finish();
        }
    }
}
