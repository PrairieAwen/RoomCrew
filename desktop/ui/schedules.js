/* 定时任务人工管理：直接暂停、取消与查看历史，不需要模型调用。 */
"use strict";

class CrewSchedules {
    /** 因为后台安排必须随时可取消，需要提供独立于 Agent 对话的人工入口。 */
    constructor() {
        // 1、页面只通过具名产品接口操作当前空间，不读取调度数据库。
        this.generation = 0;
        el("open-schedules").addEventListener("click", this.open.bind(this));
        el("close-schedules").addEventListener("click", this.close.bind(this));
        el("refresh-schedules").addEventListener("click", this.load.bind(this));
        el("schedules-dialog").addEventListener("close", this.closed.bind(this));
    }

    /** 因为计划与空间绑定，需要显示当前会议室名称并读取其实际目录。 */
    async open() {
        // 1、打开列表不会创建任务、启动 Agent 或消耗模型额度。
        el("workspace-options").open = false;
        el("schedules-space").textContent =
            state.workspace?.name || "当前工作空间";
        el("schedules-dialog").showModal();
        await this.load();
    }

    /** 因为关闭或切换后迟到响应不能覆盖新空间，需要递增显示代次。 */
    clear() {
        // 1、只丢弃显示缓存，不修改计划和执行状态。
        this.generation++;
        el("schedules-list").replaceChildren();
    }

    /** 因为原生关闭事件可能迟到，需要避免清除用户刚重新打开的列表。 */
    closed() {
        // 1、窗口仍关闭时才丢弃缓存，重新打开后的请求保持自己的代次。
        if (!el("schedules-dialog").open) this.clear();
    }

    /** 因为关闭管理窗口不代表取消安排，需要仅退出表单。 */
    close() {
        // 1、真正取消需点击对应任务的取消按钮。
        this.clear();
        el("schedules-dialog").close();
    }

    /** 因为状态由真实后台运行变化，需要在打开和人工刷新时查询当前结果。 */
    async load() {
        // 1、请求绑定工作空间和显示代次，源数据只作为文本创建节点。
        const token = ++this.generation;
        const epoch = state.workspaceEpoch;
        el("schedules-result").textContent = "正在读取…";
        try {
            const plans = await api("list_schedules", "", true);
            if (
                token !== this.generation ||
                epoch !== state.workspaceEpoch ||
                !el("schedules-dialog").open
            )
                return;
            el("schedules-list").replaceChildren();
            for (const plan of plans) this.render(plan);
            el("schedules-result").textContent = plans.length
                ? `共 ${plans.length} 项安排`
                : "当前空间没有定时任务。";
        } catch (error) {
            if (token === this.generation && epoch === state.workspaceEpoch)
                el("schedules-result").textContent =
                    error.message || "读取失败";
        }
    }

    /** 因为计划有明确目标、规则和状态，需要把可读信息与人工操作放在同一张卡片。 */
    render(plan) {
        // 1、只展示当前空间的公开计划，用户文本不进入 innerHTML。
        const card = node("article", "schedule-card");
        card.dataset.schedule = plan.id;
        const labels = {
            active: "已启用",
            paused: "已暂停",
            deleted: "已取消",
            finished: "已触发，无后续安排",
        };
        card.append(
            node("h3", "", plan.title),
            node(
                "p",
                "muted",
                `${plan.target_name} · ${labels[plan.state] || plan.state} · ${this.rule(plan.trigger)}`,
            ),
            node("p", "", plan.instruction),
            node(
                "p",
                "muted",
                plan.next_run_local
                    ? `下一次：${this.time(plan.next_run_local, plan.trigger.timezone)}`
                    : "没有下一次执行时间",
            ),
        );
        const actions = node("div", "schedule-actions");
        if (plan.state === "active")
            this.button(
                actions,
                "暂停",
                this.change.bind(this, plan, "paused"),
            );
        if (plan.state === "paused")
            this.button(
                actions,
                "恢复",
                this.change.bind(this, plan, "active"),
            );
        if (plan.state !== "deleted")
            this.button(
                actions,
                "取消后续安排",
                this.change.bind(this, plan, "deleted"),
            );
        const history = node("div", "schedule-history");
        this.button(
            actions,
            "执行记录",
            this.history.bind(this, plan, history),
        );
        card.append(actions, history);
        el("schedules-list").append(card);
    }

    /** 因为按钮结构相同但操作不同，需要复用节点创建而保留具名处理器。 */
    button(parent, text, callback) {
        // 1、所有按钮为非提交控件，不触发其他表单。
        const button = node("button", "secondary-button", text);
        button.type = "button";
        button.addEventListener("click", callback);
        parent.append(button);
    }

    /** 因为原始 ISO 时间含机器精度，需要按计划时区展示用户可读的日期时间。 */
    time(value, timezone) {
        // 1、显示格式不会改变后端触发时间，明确保留计划时区以免跨地区误解。
        return `${new Date(value).toLocaleString("zh-CN", { timeZone: timezone, hour12: false })}（${timezone}）`;
    }

    /** 因为用户不应换算规则字段，需要按已实现类型展示时间安排。 */
    rule(trigger) {
        // 1、复杂时间计算属于后端，此处只格式化已经校验的公开信息。
        if (trigger.type === "interval")
            return `每 ${trigger.seconds / 60} 分钟`;
        if (trigger.type === "once") return `一次性：${this.time(trigger.at, trigger.timezone)}`;
        const days = ["一", "二", "三", "四", "五", "六", "日"];
        return (
            (trigger.type === "daily"
                ? "每天"
                : `每周${trigger.weekdays.map(crewScheduleDay, days).join("、")}`) +
            ` ${trigger.time}（${trigger.timezone}）`
        );
    }

    /** 因为取消必须以数据库回执为准，需要提交当前版本并在成功后重新读取。 */
    async change(plan, target, event) {
        // 1、用户直接操作不调用模型；取消未来安排不擅自停止已受理的 Run。
        const epoch = state.workspaceEpoch;
        const button = event.currentTarget;
        button.disabled = true;
        try {
            await api(
                "set_schedule_state",
                plan.id,
                target,
                plan.revision,
                crypto.randomUUID(),
            );
            if (epoch === state.workspaceEpoch) await this.load();
        } catch (error) {
            showError(error);
        } finally {
            button.disabled = false;
        }
    }

    /** 因为任务结果保存在独立会话，需要展示真实触发状态和可打开的会话引用。 */
    async history(plan, container) {
        // 1、异步返回时同时验证空间、窗口和节点连接，避免切换串入其他会议室。
        const epoch = state.workspaceEpoch;
        const token = this.generation;
        try {
            const current = await api("get_schedule", plan.id);
            if (
                epoch !== state.workspaceEpoch ||
                token !== this.generation ||
                !container.isConnected
            )
                return;
            container.replaceChildren();
            const labels = {
                pending: "排队中",
                running: "执行中",
                waiting_user: "等待答复",
                completed: "已完成",
                failed: "失败",
                interrupted: "已中断",
                cancelled: "已取消",
                expired: "错过执行窗口",
                skipped_overlap: "上次未结束，已跳过",
                blocked: "目标或配置不可用",
            };
            for (const item of current.history) {
                const row = node("div", "schedule-history-row");
                row.append(
                    node(
                        "span",
                        "",
                        `${new Date(item.scheduled_for * 1000).toLocaleString("zh-CN")} · ${labels[item.state] || item.state}`,
                    ),
                );
                if (item.run_id)
                    this.button(
                        row,
                        "查看会话",
                        this.view.bind(this, plan, item),
                    );
                container.append(row);
            }
            if (!current.history.length)
                container.append(node("p", "muted", "尚未触发。"));
        } catch (error) {
            showError(error);
        }
    }

    /** 因为查看记录不能误发新任务，需要只打开已存在的会话和正式轨迹。 */
    async view(plan, occurrence) {
        // 1、复用桌面会话入口，不改变定时任务或确认其他未读泡泡。
        this.close();
        await studio.openConversation(plan.target_member_id, {
            conversation_id: occurrence.conversation_id,
            kind: "history",
        });
    }
}

/** 因为每周规则用整数表示日期，需要仅映射到本地固定中文标签。 */
function crewScheduleDay(day) {
    // 1、此函数只格式化已校验值，不决定实际调度时间。
    return this[day];
}
