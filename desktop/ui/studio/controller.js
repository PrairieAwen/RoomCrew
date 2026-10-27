/* 人工空间操作与按需轨迹；渲染器不能访问本模块的业务入口。 */
"use strict";

class CrewStudio {
    /** 因为场景需要独立于会话日志刷新，需要维护最小投影游标和明确的用户选择。 */
    constructor() {
        // 1、未点击人物前，不加载任何人物原始轨迹。
        this.cursor = 0;
        this.refreshGeneration = 0;
        this.data = null;
        this.selected = null;
        this.tab = "tasks";
        this.editing = false;
        this.traceCursor = 0;
        this.traceConversation = null;
        this.traceMember = null;
        this.memberRevision = 0;
        this.initialized = false;
        this.renderer = new CrewRenderer(
            el("room-canvas"),
            this.selectMember.bind(this),
            this.objectClick.bind(this),
            crewLoadAvatar,
            this.openConversation.bind(this),
        );
        this.materials = new CrewMaterialPanel(this.renderer.skins);
        this.memberConfiguration = new CrewMemberConfiguration(this.materials);
        el("asset-library-open").addEventListener(
            "click",
            this.showAssetLibrary.bind(this),
        );
        el("asset-library-close").addEventListener(
            "click",
            this.closeAssetLibrary.bind(this),
        );
        el("asset-library-dialog").addEventListener(
            "close",
            this.closeAssetLibrary.bind(this),
        );
        window.addEventListener("message", this.galleryMessage.bind(this));
        el("toggle-workspace").addEventListener(
            "click",
            this.toggleWorkspace.bind(this),
        );
        el("toggle-team").addEventListener("click", this.toggleTeam.bind(this));
        el("focus-member").addEventListener(
            "click",
            this.focusMember.bind(this),
        );
        document.addEventListener("keydown", this.panelKey.bind(this));
        el("view-room").addEventListener("click", this.roomMode.bind(this));
        el("view-chat").addEventListener("click", this.chatMode.bind(this));
        el("add-member").addEventListener("click", this.addMember.bind(this));
        el("member-edit").addEventListener("click", this.editMember.bind(this));
        el("member-form").addEventListener(
            "submit",
            this.saveMember.bind(this),
        );
        el("member-leisure-pool").addEventListener(
            "change",
            this.changeIdlePool.bind(this),
        );
        el("member-leisure-action").addEventListener(
            "change",
            this.changeIdleMode.bind(this),
        );
        el("close-member").addEventListener(
            "click",
            this.closeMember.bind(this),
        );
        el("member-agent").addEventListener(
            "change",
            this.sharedDefinition.bind(this),
        );
        el("show-questions").addEventListener(
            "click",
            this.showQuestions.bind(this),
        );
        el("close-questions").addEventListener(
            "click",
            this.closeQuestions.bind(this),
        );
        el("member-tasks-tab").addEventListener(
            "click",
            this.tasksTab.bind(this),
        );
        el("member-trace-tab").addEventListener(
            "click",
            this.traceTab.bind(this),
        );
        el("layout-toggle").addEventListener(
            "click",
            this.toggleLayout.bind(this),
        );
        el("furniture-add").addEventListener(
            "click",
            this.addFurniture.bind(this),
        );
        el("furniture-form").addEventListener(
            "submit",
            this.saveFurniture.bind(this),
        );
        el("close-furniture").addEventListener(
            "click",
            this.closeFurniture.bind(this),
        );
        el("move-member").addEventListener(
            "click",
            this.moveSelected.bind(this),
        );
        el("zoom-in").addEventListener("click", this.zoomIn.bind(this));
        el("zoom-out").addEventListener("click", this.zoomOut.bind(this));
        el("narration-enabled").addEventListener(
            "change",
            this.toggleNarration.bind(this),
        );
        el("settings-target").addEventListener(
            "change",
            this.changeModelTarget.bind(this),
        );
    }

    /** 因为空间之间可能复用成员 ID，需要清除选择、轨迹游标与动画缓存再加载新房间。 */
    resetWorkspace() {
        // 1、界面只丢弃显示状态，不取消旧空间的真实任务。
        this.cursor = 0;
        this.refreshGeneration += 1;
        this.data = null;
        this.selected = null;
        this.tab = "tasks";
        this.editing = false;
        this.traceCursor = 0;
        this.traceConversation = null;
        this.traceMember = null;
        this.memberRevision = 0;
        this.initialized = false;
        this.teamSignature = null;
        this.definitionSignature = null;
        this.anchorRevision = null;
        el("member-trace").replaceChildren();
        el("team-list").replaceChildren();
        el("task-member").replaceChildren();
        document.body.classList.remove("team-open", "layout-edit");
        this.renderer.resetWorkspace();
        this.materials.skins = this.renderer.skins;
        this.materials.token++;
        // 2、新空间不继承旧表单的提交锁；旧回调按代次或素材令牌丢弃。
        for (const id of [
            "save-model",
            "test-model",
            "save-member",
            "import-avatar",
            "example-avatar",
            "portrait-avatar",
            "bundle-avatar",
        ])
            el(id).disabled = false;
    }

    /** 因为完整素材需要脱离任务单独核查，需要按需打开不持有桌面桥的本地展厅。 */
    showAssetLibrary() {
        // 1、固定资源地址只在首次访问时加载，不读取账号、轨迹或模型配置。
        const frame = el("asset-library-frame");
        if (!frame.getAttribute("src"))
            frame.src = "studio/assets/library-v1/index.html";
        el("asset-library-dialog").showModal();
    }

    /** 因为关闭展厅不应改变人物绑定，需要只关闭可随时再次打开的素材窗口。 */
    closeAssetLibrary() {
        // 1、暂停隐藏 iframe，释放纹理并避免关闭后继续绘制；下次打开重新加载。
        el("asset-library-dialog").close();
        el("asset-library-frame").removeAttribute("src");
    }

    /** 因为受限 iframe 内的 Esc 不会冒泡到主页面，需要只接受该窗口发送的固定关闭请求。 */
    galleryMessage(event) {
        // 1、严格匹配来源窗口和消息类型；消息不能调用桌面桥或传入业务参数。
        if (
            event.source === el("asset-library-frame").contentWindow &&
            event.data?.type === "roomcrew.material.close"
        )
            this.closeAssetLibrary();
    }

    /** 因为后台执行不能等待页面，需要只轮询已经落盘的投影并合并当前快照。 */
    async refresh() {
        // 1、缓存故障保持上一次画面，并明确显示降级提示。
        let data;
        const generation = (this.refreshGeneration || 0) + 1;
        this.refreshGeneration = generation;
        try {
            data = await api("studio_feed", this.cursor);
        } catch (error) {
            if (!error.stale) this.renderer.factsHealthy = false;
            throw error;
        }
        if (generation !== this.refreshGeneration) return;
        if (data.protocol_version !== 1)
            throw new Error("表现协议版本不兼容，请更新应用。");
        if (data.cursor < this.cursor) {
            this.renderer.facts.clear();
            this.renderer.animator.clear();
            this.initialized = false;
        }
        this.data = data;
        this.cursor = data.cursor;
        this.renderer.update(data);
        this.renderTeam();
        this.renderSelection();
        el("projection-status").textContent = data.degraded
            ? "表现暂不可用 · 执行继续"
            : data.catching_up
              ? "正在恢复状态…"
              : "本地状态同步";
        el("narration-enabled").checked = data.preferences.narration_enabled;
        if (
            this.initialized &&
            !data.catching_up &&
            !document.hidden &&
            this.renderer.active
        )
            this.renderer.animator.offer(data.cues);
        this.initialized = true;
        // 2、用户明确选择人物且展开轨迹后才读取原始事件。
        if (
            this.selected &&
            this.tab === "trace" &&
            document.body.classList.contains("team-open")
        )
            await this.loadTrace();
    }

    /** 因为团队列表只需要显示活动和提醒，需要用纯文本与配色生成身份条目。 */
    renderTeam() {
        // 1、不同人物使用 member ID 关联，即使共享 Agent 定义也分别显示。
        const signature = JSON.stringify([
            this.selected,
            this.data.members,
            this.data.actors.map(crewTeamFact),
        ]);
        if (this.teamSignature === signature) return;
        this.teamSignature = signature;
        const definitions = JSON.stringify(this.data.members);
        const menuChanged = this.definitionSignature !== definitions;
        this.definitionSignature = definitions;
        const panel = el("team-list");
        panel.replaceChildren();
        const previous = el("task-member").value;
        if (menuChanged) el("task-member").replaceChildren();
        for (const member of this.data.members) {
            const fact = this.renderer.facts.get(member.id);
            const row = node(
                "button",
                `team-card ${this.selected === member.id ? "selected" : ""}`,
            );
            row.dataset.member = member.id;
            const avatar = node("span", "team-avatar", member.name.slice(0, 1));
            avatar.style.backgroundColor = member.color;
            const text = node("span", "team-name", member.name);
            const description =
                member.role === "guardian"
                    ? "安全 VM · 未接入"
                    : member.role === "user"
                      ? "你 · 老板"
                      : `${member.enabled ? fact?.rule_summary || fact?.summary || "待命" : "已停用"}${fact?.active_contexts > 1 ? ` · ${fact.active_contexts} 个上下文` : ""}`;
            text.append(node("small", "", description));
            row.append(
                avatar,
                text,
                node(
                    "span",
                    fact?.question_count ? "team-question" : "team-presence",
                    fact?.question_count ? String(fact.question_count) : "",
                ),
            );
            row.addEventListener("click", this.teamClick.bind(this));
            panel.append(row);
            if (menuChanged && member.agent_id && member.enabled) {
                const option = node(
                    "option",
                    "",
                    `@${member.name}${member.role === "assistant" ? " · 自动分工" : ""}`,
                );
                option.value = member.id;
                el("task-member").append(option);
            }
        }
        el("team-count").textContent = this.data.members.length;
        if (menuChanged)
            el("task-member").value = this.data.members.some(
                crewIdMatches,
                previous,
            )
                ? previous
                : "assistant";
    }

    /** 因为团队按钮不能按显示名称路由，需要读取绑定的稳定人物身份。 */
    teamClick(event) {
        // 1、点击只展开人物面板，不自动提交任务。
        this.renderer.engage(event.currentTarget.dataset.member);
        this.selectMember(event.currentTarget.dataset.member);
        this.renderer.focusMember(this.selected);
    }

    /** 因为轨迹需要用户主动点击人物，需要记录观察对象并默认展开事项页。 */
    selectMember(identifier) {
        // 1、换人时清空旧游标，迟到的查询不能混入新人物。
        document.body.classList.add("team-open");
        el("toggle-team").setAttribute("aria-expanded", "true");
        this.selected = identifier;
        this.renderer.selected = identifier;
        this.tab = "tasks";
        this.traceCursor = 0;
        this.traceMember = null;
        el("member-trace").replaceChildren();
        this.renderTeam();
        this.renderSelection();
    }

    /** 因为人物事项和执行轨迹不同，需要分别展示状态摘要和显式展开的事件列表。 */
    renderSelection() {
        // 1、未选择人物时只展示提示，不默默读取老板或助手的原始记录。
        const member = this.data?.members.find(crewIdMatches, this.selected);
        el("member-empty").hidden = Boolean(member);
        el("member-inspector").hidden = !member;
        if (!member) return;
        const fact = this.renderer.facts.get(member.id);
        el("selected-name").textContent = member.name;
        el("selected-role").textContent = {
            user: "User · 本人",
            assistant: "Agent · 助手",
            guardian: "基础设施 · 非 Agent",
            employee: "Agent · 团队成员",
        }[member.role];
        el("member-state").textContent =
            member.role === "guardian"
                ? "安全 VM 尚未接入"
                : fact?.rule_summary || fact?.summary || "待命";
        el("member-caption").textContent =
            fact?.origin === "model"
                ? `辅助旁白：${fact.summary}`
                : "动作由已落盘的执行状态驱动";
        el("member-contexts").textContent =
            member.role === "user"
                ? "老板的待办在顶部「待答复」中处理。"
                : `${fact?.active_contexts || 0} 个活动上下文 · ${fact?.question_count || 0} 项待答复 · ${fact?.warning_count || 0} 条提醒`;
        el("member-tasks").hidden = this.tab !== "tasks";
        el("member-trace").hidden = this.tab !== "trace";
        el("member-tasks-tab").classList.toggle("active", this.tab === "tasks");
        el("member-trace-tab").classList.toggle("active", this.tab === "trace");
        // 2、换座菜单来自真实锚点；动作帧和像素坐标由本地素材驱动选择。
        if (this.anchorRevision === this.data.scene.room.revision) return;
        this.anchorRevision = this.data.scene.room.revision;
        const previous = el("anchor-target").value;
        el("anchor-target").replaceChildren();
        for (const anchor of this.data.scene.anchors) {
            const option = node("option", "", anchor.id);
            option.value = anchor.id;
            el("anchor-target").append(option);
        }
        if (previous) el("anchor-target").value = previous;
        if (!el("anchor-target").value) el("anchor-target").value = "sofa";
    }

    /** 因为事项页只需要最小状态，需要切换标签而不读取历史消息。 */
    tasksTab() {
        // 1、保持当前人物身份。
        this.tab = "tasks";
        this.renderSelection();
    }

    /** 因为原始轨迹只能由用户主动展开，需要在明确点击后启动增量查询。 */
    async traceTab() {
        // 1、异步失败只影响面板，不能让执行器停止。
        this.tab = "trace";
        this.renderSelection();
        try {
            await this.loadTrace();
        } catch (error) {
            showError(error);
        }
    }

    /** 因为同一人物可参与多个子任务，需要按成员和会话显示全部作用域轨迹。 */
    async loadTrace() {
        // 1、会话或人物变化后重置游标，旧查询结果按三元组检查丢弃。
        if (!this.selected || !state.conversation || this.tab !== "trace")
            return;
        const member = this.selected,
            conversation = state.conversation.id;
        if (
            this.traceMember !== member ||
            this.traceConversation !== conversation
        ) {
            this.traceMember = member;
            this.traceConversation = conversation;
            this.traceCursor = 0;
            el("member-trace").replaceChildren();
        }
        const events = await api(
            "member_events",
            member,
            conversation,
            this.traceCursor,
        );
        if (
            this.selected !== member ||
            state.conversation?.id !== conversation ||
            this.tab !== "trace"
        )
            return;
        // 2、正文与工具输入只在此处按需展示，全部使用纯文本。
        for (const event of events) {
            if (event.seq <= this.traceCursor) continue;
            const item = node("details", "member-event");
            item.append(
                node(
                    "summary",
                    "",
                    `#${event.seq} · ${event.kind} · ${event.scope === "main" ? "主任务" : "子任务"}`,
                ),
                node("pre", "", JSON.stringify(event.payload, null, 2)),
            );
            el("member-trace").append(item);
            this.traceCursor = event.seq;
        }
    }

    /** 因为泡泡已读必须确认内容加载成功，需要允许查看入口严格等待会话和产物读取结果。 */
    async chatMode(strict = false) {
        // 1、主动切换后才开始订阅全会话原始日志。
        document.body.classList.add("conversation-open");
        document.body.classList.remove("team-open");
        try {
            await loadEvents();
            await refreshArtifacts();
            return true;
        } catch (error) {
            if (strict === true) throw error;
            showError(error);
            return false;
        }
    }

    /** 因为空间模式只需要人物状态，需要退出全日志订阅但保持任务继续。 */
    roomMode() {
        // 1、视图切换不取消 Run。
        this.renderer.active = true;
        this.renderer.motion.settle();
        this.renderer.animator.clear();
        document.body.classList.add("studio-mode");
        document.body.classList.remove("chat-mode");
        document.body.classList.remove("conversation-open");
    }

    /** 因为未读泡泡可能积累同会话多轮结果，需要成功展示后按实际加载上界一起确认该人物的结果。 */
    async openConversation(identifier, notice = null) {
        // 1、固定点击时的通知身份，不能被新任务的会话或并行轮询替换。
        const fact = this.renderer.facts.get(identifier);
        const epoch = state.workspaceEpoch;
        const conversation = notice?.conversation_id || fact?.conversation_id;
        try {
            if (conversation && state.conversation?.id !== conversation)
                resetConversation({ id: conversation, title: "成员会话" });
            await this.chatMode(true);
            if (
                epoch !== state.workspaceEpoch ||
                state.conversation?.id !== conversation
            )
                return false;
            // 2、打开人工表单不等于答复；只确认已加载的同会话结果，不吞掉其他会话和后来新结果。
            if (
                notice?.kind === "question" ||
                (!notice && fact?.requires_input)
            )
                await this.showQuestions(notice?.request_id);
            else if (notice?.kind === "result") {
                await api(
                    "acknowledge_bubble",
                    identifier,
                    notice.id,
                    state.cursor,
                );
                if (epoch === state.workspaceEpoch) {
                    await this.refresh();
                    const remaining =
                        this.renderer.facts.get(identifier)?.bubble_notice;
                    if (
                        remaining?.kind === "result" &&
                        remaining.conversation_id !== conversation
                    )
                        toast(
                            "本会话结果已查看；该成员还有其他会话的未读结果。",
                        );
                }
            }
            return true;
        } catch (error) {
            showError(error);
            return false;
        }
    }

    /** 因为用户可以在任务执行中让老板休息，需要只提交独立的显示移动计划。 */
    async moveTo(identifier) {
        // 1、未选人物时给出清楚反馈，不隐式移动助手或老板。
        if (!this.selected) {
            toast("先点击一个人物，再选择他的目的地。");
            return;
        }
        this.renderer.engage(this.selected, true);
        try {
            const plan = await api(
                "scene_move",
                this.selected,
                identifier,
                this.data.scene.room.revision,
                this.movementStart(this.selected),
            );
            this.renderer.motion.accept({ ...plan, manual: true });
        } catch (error) {
            showError(error);
        }
    }

    /** 因为目的地菜单是用户指令，需要把注册锚点交给布局服务。 */
    async moveSelected() {
        // 1、坐姿由目标锚点决定，不向 Agent 注入移动提示。
        await this.moveTo(el("anchor-target").value);
    }

    /** 因为家具点击在两种模式中有不同含义，需要明确区分布置和人物换座。 */
    objectClick(identifier) {
        // 1、布置模式打开坐标表单；普通模式只能移动到真实锚点。
        if (this.editing) {
            this.openFurniture(identifier);
            return;
        }
        if (this.data.scene.room.objects.find(crewArchiveObject, identifier)) {
            el("archive-dialog").showModal();
            return;
        }
        const anchor = this.data.scene.anchors.find(
            crewObjectAnchor,
            identifier,
        );
        if (anchor) this.moveTo(anchor.id);
        else toast("这件家具没有人物交互锚点，可在布置模式修改。");
    }

    /** 因为新增员工要持久化配置，需要打开与运行定义分离的人物编辑表单。 */
    addMember() {
        // 1、新人物默认独立 Agent，也可选择引用现有定义。
        this.fillMember({
            name: "新成员",
            avatar_id: this.data.default_avatars?.employee || "builtin:crew-v1",
            color: "#759c8c",
            skin: "#edc39b",
            hair: "#51443e",
            role: "employee",
            enabled: true,
        });
    }

    /** 因为完整提示配置不应出现在场景订阅，需要在人工点击后单独读取。 */
    async editMember() {
        // 1、编辑入口不注册为 Agent 工具。
        if (!this.selected) return;
        try {
            this.fillMember(await api("member", this.selected));
        } catch (error) {
            showError(error);
        }
    }

    /** 因为新建与编辑共享字段，需要在一个表单中维护版本和已注册的外观参数。 */
    fillMember(member) {
        // 1、隐藏字段仅保存稳定 ID 与版本，不包含 Key 或模型 URL。
        this.editMemberValue = member;
        this.memberRevision = member.revision || 0;
        el("member-name").value = member.name;
        this.memberConfiguration.loadAgent(member);
        for (const key of ["color", "skin", "hair"])
            el("member-" + key).value = member[key];
        el("member-glasses").checked = Boolean(member.glasses);
        el("member-enabled").checked = member.enabled;
        el("member-enabled").disabled = member.role !== "employee";
        const idle = crewIdleProfile(member);
        el("member-leisure-action").value = idle ? "random" : "none";
        for (const box of el("member-leisure-pool").querySelectorAll("input"))
            box.checked = Boolean(idle?.actions.includes(box.value));
        el("member-leisure-delay").value = member.leisure_delay ?? 5;
        el("member-leisure-action").disabled = member.role === "guardian";
        el("member-leisure-delay").disabled = member.role === "guardian";
        this.changeIdleMode();
        el("member-agent").replaceChildren(
            node("option", "", "独立 Agent 定义"),
        );
        el("member-agent").firstChild.value = "";
        for (const item of this.data.members)
            if (item.agent_id) {
                const option = node(
                    "option",
                    "",
                    `${item.name} · ${item.agent_id}`,
                );
                option.value = item.agent_id;
                el("member-agent").append(option);
            }
        el("member-agent").value = member.agent_id || "";
        el("member-agent").disabled = Boolean(member.id);
        this.sharedDefinition();
        el("member-dialog").showModal();
        this.materials.open(member);
        this.memberConfiguration.loadMaterial(member);
    }

    /** 因为复用定义不应意外覆盖原人物的能力，需要在新建共享形象时锁定定义字段。 */
    sharedDefinition() {
        // 1、已有共享定义的修改仍通过版本校验；新增共享形象不提交空提示覆盖。
        const shared =
            !this.editMemberValue?.id && Boolean(el("member-agent").value);
        el("member-description").disabled = shared;
        el("member-prompt").disabled = shared;
        for (const key of ["member-skills", "member-mcp", "member-python"])
            el(key).disabled =
                shared || this.editMemberValue?.role === "guardian";
    }

    /** 因为人物属性需要跨重启保存，需要使用显式版本提交并处理冲突。 */
    async saveMember(event) {
        // 1、只收集白名单普通属性，拒绝任意素材路径或脚本。
        event.preventDefault();
        const epoch = state.workspaceEpoch;
        el("save-member").disabled = true;
        const original = this.editMemberValue;
        const values = {
            name: el("member-name").value,
            role: original.role,
            enabled: el("member-enabled").checked,
            color: el("member-color").value,
            skin: el("member-skin").value,
            hair: el("member-hair").value,
            glasses: el("member-glasses").checked,
            avatar_id: el("member-avatar").value || "builtin:crew-v1",
            leisure_action: this.idleActivities()[0] || "none",
            leisure_actions: this.idleActivities(),
            leisure_delay: Number(el("member-leisure-delay").value),
        };
        if (original.id) {
            values.id = original.id;
            values.agent_revision = original.agent_revision || 0;
        }
        if (el("member-agent").value)
            values.agent_id = el("member-agent").value;
        try {
            Object.assign(
                values,
                this.memberConfiguration.readAgent(),
                this.memberConfiguration.readMaterial(),
            );
            const member = await api(
                "save_member",
                values,
                this.memberRevision,
            );
            this.closeMember();
            await this.refresh();
            this.selectMember(member.id);
            toast("成员属性已保存到本地账号库。");
        } catch (error) {
            showError(error);
        } finally {
            if (epoch === state.workspaceEpoch)
                el("save-member").disabled = false;
        }
    }

    /** 因为关闭编辑不应修改人物，需要直接结束本地表单。 */
    closeMember() {
        // 1、未保存值不进入执行定义。
        el("member-dialog").close();
    }

    /** 因为每个人物最多使用四项活动，需要从人工表单收集有限勾选值。 */
    idleActivities() {
        // 1、禁用时返回空池，不把 UI 模式名称传成素材动作。
        if (el("member-leisure-action").value !== "random") return [];
        const result = [];
        for (const box of el("member-leisure-pool").querySelectorAll("input"))
            if (box.checked) result.push(box.value);
        return result;
    }

    /** 因为活动过多会降低可读性，需要在勾选第五项时立即解释并撤销该项。 */
    changeIdlePool(event) {
        // 1、后端仍会独立验证上限，页面反馈不承担权限或安全权威。
        if (this.idleActivities().length > 4) {
            event.target.checked = false;
            toast("每个人物最多选择四项空闲活动。");
        }
    }

    /** 因为保持待命和基础设施不应随机行动，需要同步禁用活动池与等待控件。 */
    changeIdleMode() {
        // 1、不清空已勾选值，用户切回随机模式可继续原选择。
        const off =
            el("member-leisure-action").value !== "random" ||
            this.editMemberValue?.role === "guardian";
        el("member-leisure-pool").disabled = off;
        el("member-leisure-delay").disabled = off;
    }

    /** 因为人工问题应由任务入口人物转达，需要按请求定位原问题并保留真实恢复身份。 */
    async showQuestions(requestId = null) {
        // 1、问题正文只在用户打开待办时读取，不广播到场景。
        try {
            const questions = await api("questions");
            await this.refresh();
            el("questions-list").replaceChildren();
            for (const question of questions) {
                if (typeof requestId === "string" && question.id !== requestId)
                    continue;
                const presenterId =
                    this.data?.question_presenters?.[question.id];
                const presenter = this.data?.members.find(
                    crewQuestionPresenter,
                    presenterId,
                );
                const form = node("form", "question-card");
                form.dataset.request = question.id;
                form.dataset.command = crypto.randomUUID();
                form.append(
                    node(
                        "small",
                        "",
                        `${presenter?.name || question.actor} · ${question.conversation_id.slice(0, 8)} · ${{ question: "信息补充", choice: "请选择", approval: "人工审批" }[question.interaction_type] || "信息确认"}`,
                    ),
                    node("h3", "", question.question),
                );
                const choices = node("div", "question-choices");
                for (const value of question.choices) {
                    const choice = node("button", "secondary-button", value);
                    choice.type = "button";
                    choice.addEventListener(
                        "click",
                        this.chooseAnswer.bind(this),
                    );
                    choices.append(choice);
                }
                const answer = node("textarea", "");
                answer.maxLength = 4000;
                answer.required = true;
                answer.placeholder = "填写你的答复…";
                answer.readOnly = question.allow_other === false;
                if (question.allow_other !== false && question.choices.length) {
                    const other = node(
                        "button",
                        "secondary-button",
                        "其他 / 补充",
                    );
                    other.type = "button";
                    other.addEventListener(
                        "click",
                        this.supplementAnswer.bind(this),
                    );
                    choices.append(other);
                }
                const send = node(
                    "button",
                    "primary-button",
                    "答复并继续原任务",
                );
                send.type = "submit";
                const cancel = node("button", "text-button", "取消该任务");
                cancel.type = "button";
                cancel.dataset.run = question.run_id;
                cancel.addEventListener(
                    "click",
                    this.cancelQuestion.bind(this),
                );
                form.append(choices, answer, send, cancel);
                form.addEventListener("submit", this.answerQuestion.bind(this));
                el("questions-list").append(form);
            }
            if (!el("questions-list").childElementCount)
                el("questions-list").append(
                    node("p", "muted", "目前没有待答复事项。"),
                );
            if (!el("questions-dialog").open)
                el("questions-dialog").showModal();
        } catch (error) {
            showError(error);
        }
    }

    /** 因为建议选项只是填表便利，需要仍由用户明确提交后才恢复任务。 */
    chooseAnswer(event) {
        // 1、点击建议不自动授权或提交。
        event.currentTarget.closest("form").querySelector("textarea").value =
            event.currentTarget.textContent;
    }

    /** 因为建议选项可能无法完整表达用户意图，需要提供清空并聚焦自由补充的入口。 */
    supplementAnswer(event) {
        // 1、只调整表单内容，不自动提交或恢复任务。
        const input = event.currentTarget
            .closest("form")
            .querySelector("textarea");
        input.value = "";
        input.focus();
    }

    /** 因为用户可能重复点击答复，需要锁定按钮并使用同一幂等命令标识。 */
    async answerQuestion(event) {
        // 1、只提交人工输入，不让旁白模型代答。
        event.preventDefault();
        const form = event.currentTarget,
            button = form.querySelector("button[type=submit]");
        button.disabled = true;
        try {
            await api(
                "respond",
                form.dataset.request,
                form.querySelector("textarea").value,
                form.dataset.command,
            );
            await this.refresh();
            await this.showQuestions();
        } catch (error) {
            showError(error);
            button.disabled = false;
        }
    }

    /** 因为旧问题不能在取消后继续，需要调用真实停止入口并刷新待办。 */
    async cancelQuestion(event) {
        // 1、保留原历史，只取消该 Run 的等待。
        try {
            await api("stop", event.currentTarget.dataset.run);
            await this.refresh();
            await this.showQuestions();
        } catch (error) {
            showError(error);
        }
    }

    /** 因为关闭待办不等于取消任务，需要只隐藏面板。 */
    closeQuestions() {
        // 1、后端继续保持 waiting_user。
        el("questions-dialog").close();
    }

    /** 因为家具操作需要明确模式，需要让用户主动进入布置状态。 */
    toggleLayout() {
        // 1、布置模式不暂停模型或工具调用。
        this.editing = !this.editing;
        el("layout-toggle").classList.toggle("active", this.editing);
        el("layout-hint").textContent = this.editing
            ? "布置中：点击家具修改格网位置；占用中的家具需先让人物离开。"
            : "点击人物查看事项，再点击沙发或工位让他换座。";
        el("furniture-add").hidden = !this.editing;
    }

    /** 因为新家具遵循统一素材约束，需要使用目录表单而非导入任意代码。 */
    addFurniture() {
        // 1、新 ID 由后端生成。
        this.openFurniture(null);
    }

    /** 因为布置要保持同一格网，需要显示有限家具类型和整数位置。 */
    openFurniture(identifier) {
        // 1、前端只是编辑建议，真实碰撞和路径仍由后端验证。
        const obj = this.data.scene.room.objects.find(
            crewIdMatches,
            identifier,
        );
        this.furnitureId = identifier;
        el("furniture-type").replaceChildren();
        for (const type of Object.keys(this.data.scene.catalog)) {
            const option = node("option", "", type);
            option.value = type;
            el("furniture-type").append(option);
        }
        el("furniture-type").value = obj?.type || "plant";
        el("furniture-x").value = obj?.x || 12;
        el("furniture-y").value = obj?.y || 10;
        el("furniture-dialog").showModal();
    }

    /** 因为布局编辑会影响后续路径，需要带版本提交并在成功后更新快照。 */
    async saveFurniture(event) {
        // 1、占地重叠、不可达或过期版本均保持原布局。
        event.preventDefault();
        el("save-furniture").disabled = true;
        const values = {
            type: el("furniture-type").value,
            x: Number(el("furniture-x").value),
            y: Number(el("furniture-y").value),
        };
        if (this.furnitureId) values.id = this.furnitureId;
        try {
            await api("scene_edit", values, this.data.scene.room.revision);
            el("furniture-dialog").close();
            await this.refresh();
        } catch (error) {
            showError(error);
        } finally {
            el("save-furniture").disabled = false;
        }
    }

    /** 因为取消布置表单不应落盘，需要只关闭当前编辑层。 */
    closeFurniture() {
        // 1、保留服务器布局版本。
        el("furniture-dialog").close();
    }

    /** 因为空间应占满应用，需要把工作空间导航作为可开合的悬浮抽屉。 */
    toggleWorkspace() {
        // 1、抽屉变化不重新创建场景或任务。
        const open = document.body.classList.toggle("workspace-open");
        el("toggle-workspace").setAttribute("aria-expanded", String(open));
    }

    /** 因为团队面板不应固定挤占画布，需要由用户或人物选择显式展开。 */
    toggleTeam() {
        // 1、收起时停止按需轨迹订阅，执行器继续运行。
        const open = document.body.classList.toggle("team-open");
        el("toggle-team").setAttribute("aria-expanded", String(open));
    }

    /** 因为快捷关闭不应误操作弹窗，需要只在没有人工表单时收起悬浮抽屉。 */
    panelKey(event) {
        // 1、Escape 不取消 Run，不代替任何人工答复。
        if (event.key === "Escape" && !document.querySelector("dialog[open]")) {
            document.body.classList.remove("workspace-open", "team-open");
            el("toggle-workspace").setAttribute("aria-expanded", "false");
            el("toggle-team").setAttribute("aria-expanded", "false");
        }
    }

    /** 因为角色可能走出当前视口，需要通过相机定位而不是传送人物。 */
    focusMember() {
        // 1、没有选中时定位老板，后端布局与任务不改变。
        this.renderer.focusMember(this.selected || "assistant");
    }

    /** 因为快速更改目的地不能从上次逻辑终点瞬移，需要传当前已走到的安全地面格。 */
    movementStart(member) {
        // 1、该坐标只用于显示路径，后端仍会验证边界和碰撞。
        return this.renderer.motion.actors.get(member)?.groundCell || null;
    }

    /** 因为大画布需要查看细节，需要在本地放大相机。 */
    zoomIn() {
        // 1、不修改世界坐标或角色属性。
        this.renderer.camera(1.12);
    }

    /** 因为用户需要查看整体布局，需要在本地缩小相机。 */
    zoomOut() {
        // 1、缩放范围由渲染器限制。
        this.renderer.camera(1 / 1.12);
    }

    /** 因为额外模型有成本且不能借用执行配置，需要要求人工显式开启。 */
    async toggleNarration() {
        // 1、没有单独配置时后端拒绝开启，规则动作始终可用。
        try {
            await api("preferences", {
                narration_enabled: el("narration-enabled").checked,
            });
        } catch (error) {
            el("narration-enabled").checked = false;
            showError(error);
        }
    }

    /** 因为模型表单可编辑两个隔离域，需要切换时清空 Key 并加载安全概况。 */
    async changeModelTarget() {
        // 1、先关闭旧表单，避免旧 Key 留在另一用途的输入框。
        closeSettings();
        await openSettings();
    }
}

/** 因为所有人物查找都要使用稳定身份，需要提供统一具名谓词。 */
function crewIdMatches(value) {
    // 1、名字重名不影响成员选择。
    return value.id === String(this);
}

/** 因为家具可能有多个交互点，需要按 object ID 找到注册锚点。 */
function crewObjectAnchor(anchor) {
    // 1、不能把模型给出的任意位置作为目的地。
    return anchor.object_id === String(this);
}

/** 因为人物位置与定义使用不同字段，需要按 placement 的稳定身份检索。 */
function crewPlacementMember(value) {
    // 1、共享 Agent 定义不意味着共享空间位置。
    return value.member_id === String(this);
}

/** 因为序号变化不应重建团队菜单，需要只比较实际显示的事实字段。 */
function crewTeamFact(value) {
    // 1、保留用户选项与焦点，不因内部模型回合频繁重置表单。
    return [
        value.member_id,
        value.summary,
        value.rule_summary,
        value.active_contexts,
        value.question_count,
    ];
}

/** 因为素材加载只能在异步资源阶段发生，需要给播放器注入按注册 ID 的桥接能力。 */
async function crewLoadAvatar(identifier) {
    // 1、该函数不在帧循环中调用，不接收任意文件路径。
    return await api("avatar_asset", identifier);
}

/** 因为人工问题显示名属于入口人物，需要按表现层提供的稳定人物 ID 查找名称。 */
function crewQuestionPresenter(member) {
    // 1、仅改变表单显示，实际答复仍使用原 request_id 恢复原子任务。
    return member.id === String(this);
}

/** 因为档案室只是基础设施入口，需要按家具类型识别而不把它当可执行员工。 */
function crewArchiveObject(object) {
    // 1、只匹配当前房间注册的档案室，不读取其他空间。
    return object.id === String(this) && object.type === "archive";
}
