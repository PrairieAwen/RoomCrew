/* 界面只通过桌面桥访问产品接口，不读取数据库、配置文件或系统命令。 */
"use strict";

const state = {
    workspace: null,
    workspaceEpoch: 0,
    switching: true,
    settingsVersion: 0,
    settingsSaved: null,
    settingsBusy: false,
    conversation: null,
    cursor: 0,
    run: null,
    sending: false,
    polling: false,
    models: 0,
    tools: 0,
    actors: new Set(),
    calls: new Map(),
    toastTimer: null,
};
let studio = null;
let workspacePanel = null;

/** 因为界面需要频繁定位固定元素，需要用具名入口统一取得节点。 */
function el(id) {
    // 1、所有标识来自本应用静态界面，不构造外部选择器。
    return document.getElementById(id);
}

/** 因为桥调用需要统一处理失败，需要仅接收产品合同中的成功数据或安全错误。 */
async function api(name, ...args) {
    // 1、不记录请求体，尤其不能打印配置表单中的 Key。
    const epoch = state.workspaceEpoch;
    const neutral = [
        "workspace_state",
        "create_workspace",
        "select_workspace",
        "rename_workspace",
    ].includes(name);
    if (!neutral && (!state.workspace || state.switching))
        throw Object.assign(new Error("正在切换会议室"), { stale: true });
    const reply = neutral
        ? await window.pywebview.api[name](...args)
        : await window.pywebview.api.invoke(state.workspace.id, name, args);
    // 2、后端继续在原空间执行；迟到响应不能改变新会议室的画面。
    if (!neutral && epoch !== state.workspaceEpoch)
        throw Object.assign(new Error("已切换工作空间"), { stale: true });
    if (!reply.ok) throw new Error(reply.error || "本地操作失败");
    return reply.data;
}

/** 因为异步界面错误不能静默丢失，需要在窗口内展示精简提示。 */
function toast(message) {
    // 1、用纯文本显示，不执行错误消息中的 HTML。
    el("toast").textContent = String(message);
    el("toast").hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(hideToast, 5500);
}

/** 因为提示不应永久遮挡输入，需要在显示期限结束后隐藏。 */
function hideToast() {
    // 1、只隐藏提示，不影响任务执行。
    el("toast").hidden = true;
}

/** 因为节点内容来自模型和工具，需要统一以文本创建节点，避免内容变成脚本。 */
function node(tag, className, text = "") {
    // 1、不使用 innerHTML 处理外部内容。
    const value = document.createElement(tag);
    value.className = className;
    value.textContent = text;
    return value;
}

/** 因为历史切换不能混入上一会话事件，需要重置游标、统计和工具映射。 */
function resetConversation(conversation) {
    // 1、先更换身份再清空展示，迟到请求会通过身份比较丢弃。
    state.conversation = conversation;
    state.cursor = 0;
    state.models = 0;
    state.tools = 0;
    state.actors = new Set();
    state.calls.clear();
    el("timeline").replaceChildren();
    el("chat-title").textContent = conversation?.title || "新会话";
    el("participants").replaceChildren();
    el("artifacts").replaceChildren(node("p", "muted", "尚无产物文件。"));
    updateStats();
}

/** 因为参与者来自真实调用链，需要统一生成主 Agent 和子 Agent 的身份条目。 */
function makeParticipant(name, description) {
    // 1、参与者只反映轨迹，不赋予真实权限。
    const row = node("div", "participant");
    row.append(node("span", "avatar", name === "助手" ? "R" : "↳"));
    const text = node("div", "", name);
    text.append(node("small", "", description));
    row.append(text, node("span", "participant-dot"));
    return row;
}

/** 因为用户需要对照过程理解执行量，需要同步显示实际记录的调用次数。 */
function updateStats() {
    // 1、计数来自事件，而不是根据模型回答推测。
    el("stat-model").textContent = state.models;
    el("stat-tools").textContent = state.tools;
    el("stat-agents").textContent = state.actors.size;
}

/** 因为主子 Agent 的输出同属一个会话，需要按事件序号连续显示并保留执行者。 */
function renderEvent(event) {
    // 1、先识别真实作用域，让子 Agent 首个事件立即进入参与者列表。
    const timeline = el("timeline");
    const keepBottom =
        timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight <
        150;
    const p = event.payload;
    const actorId = event.member_id || "assistant";
    if (event.kind !== "user.message" && !state.actors.has(actorId)) {
        state.actors.add(actorId);
        el("participants").append(
            makeParticipant(
                event.actor,
                event.scope === "main" ? "接单 Agent" : "协作 Agent",
            ),
        );
    }
    // 2、公开消息和工具事件分别展示；工具的开始与结果按调用 ID 合并。
    if (event.kind === "user.message" || event.kind === "assistant.message") {
        const user = event.kind === "user.message";
        const block = node("article", `message ${user ? "user" : "assistant"}`);
        const label = node("div", "message-label");
        label.append(
            node("span", "mini-avatar", user ? "你" : "R"),
            node("span", "", event.actor),
        );
        if (event.scope !== "main")
            label.append(node("span", "subagent-label", "子 Agent"));
        const content = node("div", "message-text");
        crewRenderMarkdown(content, p.text, {
            onArtifact: openArtifactPath.bind(null, event.conversation_id),
        });
        block.append(label, content);
        timeline.append(block);
    } else if (event.kind === "tool.started") {
        state.tools += 1;
        const key = `${event.run_id}:${event.scope}:${p.tool_call_id || p.call_id}`;
        const previous = state.calls.get(key);
        const block = previous?.block || node("details", "tool-event");
        const summary = previous?.summary || node("summary", "", "◌ ");
        summary.replaceChildren();
        summary.append(
            node("span", "tool-name", p.name),
            node("span", "", `${event.actor} · 调用中`),
        );
        if (!previous)
            block.append(
                summary,
                node("div", "tool-label", "INPUT"),
                node("pre", "", JSON.stringify(p.input, null, 2)),
            );
        state.calls.set(key, {
            block,
            summary,
            name: p.name,
            actor: event.actor,
            completed: false,
            run: event.run_id,
            scope: event.scope,
        });
        if (!previous) timeline.append(block);
    } else if (
        event.kind === "tool.completed" ||
        event.kind === "tool.failed"
    ) {
        const call = state.calls.get(
            `${event.run_id}:${event.scope}:${p.tool_call_id || p.call_id}`,
        );
        const failed = event.kind === "tool.failed" || p.status === "error";
        if (call) {
            call.completed = true;
            call.summary.textContent = `${failed ? "!" : "✓"} ${call.name} · ${call.actor} · ${failed ? "返回错误" : "已返回"}`;
            call.block.append(
                node("div", "tool-label", "OUTPUT"),
                node("pre", "", p.output || p.message || "无文本输出"),
            );
        }
    } else if (event.kind === "model.started") {
        state.models += 1;
        timeline.append(
            node("div", "model-event", `◈ ${event.actor} · 发起模型调用`),
        );
    } else if (
        event.kind === "human.requested" ||
        event.kind === "human.responded"
    ) {
        if (event.kind === "human.requested") {
            const call = state.calls.get(
                `${event.run_id}:${event.scope}:${p.tool_call_id}`,
            );
            if (call) {
                call.paused = true;
                call.summary.textContent = `? ${call.name} · ${call.actor} · 等待人工答复`;
            }
        }
        timeline.append(
            node(
                "div",
                "run-event",
                event.kind === "human.requested"
                    ? `${event.actor} · 等待人工答复，请打开顶部「待答复」`
                    : `${event.actor} · 已收到人工答复`,
            ),
        );
    } else if (
        event.kind === "run.waiting_user" ||
        event.kind === "run.resumed"
    ) {
        timeline.append(
            node(
                "div",
                "run-event",
                event.kind === "run.waiting_user"
                    ? "任务已暂停，等待你的答复；可关闭应用后再继续。"
                    : "继续原任务。",
            ),
        );
    } else if (event.kind.startsWith("run.") && event.kind !== "run.started") {
        for (const call of state.calls.values()) {
            if (!call.completed && !call.paused) {
                call.summary.textContent = `! ${call.name} · ${call.actor} · 本轮结束，未确认完成`;
                call.completed = true;
            }
        }
        const failed =
            event.kind === "run.failed" || event.kind === "run.interrupted";
        const text =
            event.kind === "run.completed"
                ? "本轮执行结束 · 请核对回复与真实产物"
                : p.message || "应用关闭导致本轮中断，请新建会话继续。";
        timeline.append(
            node("div", `run-event ${failed ? "error" : ""}`, text),
        );
        refreshArtifacts().catch(showError);
    }
    // 3、阅读旧消息时保留滚动位置，追踪底部时自动滚动。
    updateStats();
    if (keepBottom) timeline.scrollTop = timeline.scrollHeight;
}

/** 因为异步事件处理器需要共享错误出口，需要把安全错误展示为窗口提示。 */
function showError(error) {
    // 1、生产接口只返回经过转换的错误，不在界面输出底层堆栈。
    if (!error.stale) toast(error.message || "操作失败");
}

/** 因为会话切换后的旧请求可能迟到，需要按身份校验后再应用历史事件。 */
async function loadEvents() {
    // 1、分批拉取所有新增事件，序号让重新加载保持原始顺序。
    if (
        !state.conversation ||
        (!document.body.classList.contains("chat-mode") &&
            !document.body.classList.contains("conversation-open"))
    )
        return;
    const identifier = state.conversation.id;
    let more = true;
    while (more) {
        const events = await api("events", identifier, state.cursor);
        if (state.conversation?.id !== identifier) return;
        for (const event of events) {
            if (event.seq <= state.cursor) continue;
            renderEvent(event);
            state.cursor = event.seq;
        }
        more = events.length === 100;
    }
}

/** 因为会话清单需要反映本地持久状态，需要更新标题和当前运行按钮。 */
function renderOverview(data) {
    // 1、只从后端权威状态决定是否可发送和是否展示停止按钮。
    if (workspacePanel) workspacePanel.render(data.workspaces || []);
    state.run = data.active_run;
    el("pending-count").textContent = data.pending_count || 0;
    el("config-state").textContent = data.configured ? "已配置" : "未配置";
    el("session-count").textContent = data.conversations.length;
    el("send").disabled = Boolean(state.run) || state.sending;
    el("stop").hidden = !state.run;
    el("run-status").classList.toggle("busy", Boolean(state.run));
    el("run-status").lastElementChild.textContent = state.run
        ? "正在执行 · 工具与协作记录持续更新"
        : data.pending_count
          ? "有任务等待你的答复 · 打开右上角待答复"
          : "准备就绪";
    const nav = el("conversations");
    nav.replaceChildren();
    for (const conversation of data.conversations) {
        const button = node(
            "button",
            `conversation-item ${state.conversation?.id === conversation.id ? "selected" : ""}`,
        );
        button.append(
            node("span", "conversation-symbol", "◇"),
            node("span", "conversation-name", conversation.title),
        );
        button.dataset.conversation = JSON.stringify(conversation);
        button.addEventListener("click", selectConversation);
        nav.append(button);
        if (conversation.id === state.conversation?.id)
            el("chat-title").textContent = conversation.title;
    }
}

/** 因为后台任务和窗口操作并行，需要防止轮询叠加并持续追踪同一会话轨迹。 */
async function poll() {
    // 1、单次轮询结束后才安排下一次，不在慢操作时积压请求。
    if (state.polling) return;
    state.polling = true;
    try {
        await loadEvents();
        renderOverview(await api("overview"));
        if (studio) await studio.refresh();
    } catch (error) {
        showError(error);
    } finally {
        state.polling = false;
        setTimeout(poll, 650);
    }
}

/** 因为用户选择历史会话时需要完整回放，需要重置展示后重新读取该会话的轨迹。 */
async function selectConversation(event) {
    // 1、同一会话无需重载；切换只影响观察对象，不取消后台执行。
    const conversation = JSON.parse(event.currentTarget.dataset.conversation);
    if (state.conversation?.id === conversation.id) return;
    resetConversation(conversation);
    try {
        await loadEvents();
        await refreshArtifacts();
    } catch (error) {
        showError(error);
    }
}

/** 因为新任务有时需要完全独立历史，需要通过后端创建新会话并切换观察对象。 */
async function newConversation() {
    // 1、未配置时由后端返回明确提示，不启动默认厂商模型。
    try {
        resetConversation(await api("new_conversation"));
        renderOverview(await api("overview"));
        el("prompt").focus();
    } catch (error) {
        showError(error);
    }
}

/** 因为提交失败不能丢失用户输入，需要受理成功后才清空，并用请求标识避免重复执行。 */
async function sendTask(event) {
    // 1、阻止表单导航及重复提交，空文本不创建任务。
    event.preventDefault();
    const text = el("prompt").value.trim();
    if (!text || state.sending || state.run) return;
    const epoch = state.workspaceEpoch;
    state.sending = true;
    el("send").disabled = true;
    try {
        if (!state.conversation)
            resetConversation(await api("new_conversation"));
        // 2、只发送用户输入和产品 ID，不附带模型配置或 Key。
        let member = el("task-member").value || "assistant";
        // 3、@名字只选择真实已配置成员；同名或多个指派交由用户明确选择。
        const mentions = [...text.matchAll(/(?:^|\s)@([^\s,，。:：]+)/g)];
        if (mentions.length > 1)
            throw new Error(
                "一次请选择一位接单成员；协作由接单 Agent 自行委派。",
            );
        if (mentions.length === 1) {
            const matches = studio.data.members.filter(
                mentionMatches,
                mentions[0][1],
            );
            if (
                matches.length !== 1 ||
                !matches[0].agent_id ||
                !matches[0].enabled
            )
                throw new Error(
                    "@成员不存在、重名或不能接单，请使用下方成员选择框。",
                );
            member = matches[0].id;
        }
        const conversation = state.conversation;
        const result = await api(
            "submit",
            conversation.id,
            text,
            crypto.randomUUID(),
            member,
        );
        // 4、只缓存真实受理的对话与最终接单人，历史切换不能改写这次发送的关联。
        studio.rememberConversation(member, conversation);
        state.run = result.run_id;
        el("prompt").value = "";
        await loadEvents();
    } catch (error) {
        showError(error);
    } finally {
        if (epoch === state.workspaceEpoch) {
            state.sending = false;
            el("send").disabled = Boolean(state.run);
        }
    }
}

/** 因为输入区需要兼容多行编辑，需要区分 Enter 发送和 Shift Enter 换行。 */
function promptKey(event) {
    // 1、输入法组合期间不发送，避免中文选词触发任务。
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        el("composer").requestSubmit();
    }
}

/** 因为用户需要人工停止执行，需要在界面等待后端确认本地协程停止。 */
async function stopTask() {
    // 1、不提前伪造停止成功，等待真实取消结果。
    if (!state.run) return;
    el("stop").disabled = true;
    try {
        await api("stop", state.run);
        await loadEvents();
    } catch (error) {
        showError(error);
    } finally {
        el("stop").disabled = false;
    }
}

/** 因为模型配置属于用户操作，需要只在打开设置时读取非秘密概况并建立表单基线。 */
async function openSettings() {
    // 1、每次打开或切换用途都使旧回调失效；基线永远不含 API Key。
    const operation = {
        version: ++state.settingsVersion,
        epoch: state.workspaceEpoch,
        target: el("settings-target").value,
    };
    modelSettingsBusy(false);
    state.settingsSaved = null;
    try {
        const config = await api("configuration", operation.target);
        if (
            operation.version !== state.settingsVersion ||
            operation.epoch !== state.workspaceEpoch
        )
            return;
        el("model-connection-note").textContent =
            operation.target === "presentation"
                ? "保存并测试当前填写的旁白配置；会向该服务发出一次请求。旁白独立配置，不替代任务执行模型。"
                : "保存并测试当前填写的配置；会向该服务发出一次请求。执行模型必须支持标准工具调用。";
        el("model-label").value = config.label || "默认模型";
        el("model-id").value = config.model || "";
        el("base-url").value = config.base_url || "";
        el("model-proxy").value = config.proxy || "";
        clearKey();
        el("model-timeout").value = config.timeout || 90;
        el("context-window").value = config.context_window || 32768;
        state.settingsSaved = config.configured
            ? modelSettingsSignature(config, operation.target)
            : null;
        el("key-hint").textContent = config.has_key
            ? "已保存 Key，不回显；同一端点留空可保留。"
            : "使用 Windows 本地加密保护，不保存到源码或 .env。";
        settingsResult(
            config.recovery_required
                ? "原配置无法读取，请重新填写完整信息和 Key 后保存。"
                : "修改后可直接点「保存并测试连接」，无需先单独保存。",
            config.recovery_required ? false : null,
        );
        el("settings-dialog").showModal();
    } catch (error) {
        showError(error);
    }
}

/** 因为手动输入的 Key 不应在隐藏表单中长期保留，需要关闭时清除并作废旧回调。 */
function closeSettings() {
    // 1、不保存未提交内容；重新打开会从已保存的公共概况恢复。
    clearKey();
    state.settingsVersion++;
    el("settings-dialog").close();
    modelSettingsBusy(false);
}

/** 因为保存、进行中和失败含义不同，需要将尚未验证的状态与真实成功区分。 */
function settingsResult(message, success = null) {
    // 1、纯文本展示安全反馈；保存成功不能显示为连接成功。
    el("settings-result").textContent = message;
    el("settings-result").className =
        `settings-result ${success === true ? "success" : success === false ? "error" : ""}`;
}

/** 因为保存和测试必须使用同一份输入，需要一次读取有限字段，且不将 Key 存入全局状态。 */
function modelSettingsValues() {
    // 1、原始 Key 仅存在于当前提交的临时对象，后续在提交完成后清除。
    return {
        label: el("model-label").value,
        model: el("model-id").value,
        base_url: el("base-url").value,
        api_key: el("api-key").value,
        proxy: el("model-proxy").value,
        timeout: Number(el("model-timeout").value),
        context_window: Number(el("context-window").value),
    };
}

/** 因为重复测试不应重新绑定历史会话，需要仅用非秘密字段判断当前表单是否修改。 */
function modelSettingsSignature(values, target) {
    // 1、与后端去空白规则一致；不序列化 API Key，也不缓存包含 Key 的输入对象。
    return JSON.stringify([
        target,
        String(values.label || "默认模型").trim() || "默认模型",
        String(values.model || "").trim(),
        String(values.base_url || "")
            .trim()
            .replace(/\/+$/, ""),
        String(values.proxy || "")
            .trim()
            .replace(/\/+$/, ""),
        Number(values.timeout),
        Number(values.context_window),
    ]);
}

/** 因为测试中修改字段会让反馈对应错配置，需要锁定编辑项并合并重复点击。 */
function modelSettingsBusy(busy) {
    // 1、关闭入口保持可用，原本禁用的协议字段不在编辑白名单内。
    state.settingsBusy = busy;
    for (const id of [
        "settings-target",
        "model-label",
        "model-id",
        "base-url",
        "model-proxy",
        "api-key",
        "model-timeout",
        "context-window",
        "save-model",
        "test-model",
    ])
        el(id).disabled = busy;
}

/** 因为关闭、切换用途或空间后旧请求仍可能返回，需要确认反馈仍属于当前这次表单。 */
function modelSettingsCurrent(operation) {
    // 1、HTTP 请求可以继续收尾，但不能清空新表单或覆盖新的测试反馈。
    return (
        operation.epoch === state.workspaceEpoch &&
        operation.version === state.settingsVersion &&
        operation.target === el("settings-target").value &&
        el("settings-dialog").open
    );
}

/** 因为测试不能悄悄使用磁盘旧值，需要先保存当前修改；保存失败时禁止继续探测旧配置。 */
async function persistModelSettings(operation) {
    // 1、没有修改时直接复用已保存绑定，测试期间不写磁盘或改变 reference。
    const values = modelSettingsValues();
    const changed =
        Boolean(values.api_key.trim()) ||
        modelSettingsSignature(values, operation.target) !==
            state.settingsSaved;
    try {
        if (!changed) return false;
        const config = await api(
            "save_configuration",
            values,
            operation.target,
        );
        if (!modelSettingsCurrent(operation))
            throw Object.assign(new Error("配置表单已切换"), { stale: true });
        // 2、只缓存后端确认的公共字段，Key 在完成保存后立即从表单与临时对象清除。
        state.settingsSaved = modelSettingsSignature(config, operation.target);
        el("key-hint").textContent = "已保存 Key，不回显；同一端点留空可保留。";
        return true;
    } finally {
        values.api_key = "";
        if (modelSettingsCurrent(operation)) clearKey();
    }
}

/** 因为用户也可能只想本地保存而不发起模型请求，需要保留独立保存入口并复用同一校验。 */
async function saveSettings(event) {
    // 1、手动保存只写配置；无效表单和重复点击不提交。
    event.preventDefault();
    if (state.settingsBusy || !el("settings-form").reportValidity()) return;
    const operation = {
        epoch: state.workspaceEpoch,
        version: state.settingsVersion,
        target: el("settings-target").value,
    };
    modelSettingsBusy(true);
    try {
        const changed = await persistModelSettings(operation);
        if (modelSettingsCurrent(operation))
            settingsResult(
                changed
                    ? "已加密保存，尚未测试连接。可点击「保存并测试连接」。"
                    : "当前配置已保存，无需重复保存；可直接测试连接。",
                true,
            );
    } catch (error) {
        if (!error.stale && modelSettingsCurrent(operation))
            settingsResult(error.message, false);
    } finally {
        if (modelSettingsCurrent(operation)) modelSettingsBusy(false);
    }
}

/** 因为用户期望验证刚填写的内容，需要先保存当前配置，再按相同用途执行真实连接探测。 */
async function testSettings() {
    // 1、浏览器先验证必填与数值范围，后端仍独立校验；测试时锁定输入避免结果错位。
    if (state.settingsBusy || !el("settings-form").reportValidity()) return;
    const operation = {
        epoch: state.workspaceEpoch,
        version: state.settingsVersion,
        target: el("settings-target").value,
    };
    modelSettingsBusy(true);
    settingsResult("正在保存并测试当前配置，请稍候…");
    let saved = false;
    try {
        await persistModelSettings(operation);
        if (!modelSettingsCurrent(operation)) return;
        saved = true;
        // 2、保存成功后才探测；未修改时保持原 reference，不能因反复测试使会话失效。
        const result = await api("test_connection", operation.target);
        if (modelSettingsCurrent(operation))
            settingsResult(result.message, true);
    } catch (error) {
        if (!error.stale && modelSettingsCurrent(operation))
            settingsResult(
                saved
                    ? `配置已保存，但连接测试失败：${error.message}`
                    : `保存失败，未发起连接测试：${error.message}`,
                false,
            );
    } finally {
        if (modelSettingsCurrent(operation)) modelSettingsBusy(false);
    }
}

/** 因为修改字段后旧的成功提示不再代表当前输入，需要立即提示重新保存并测试。 */
function modelSettingsEdited() {
    // 1、输入事件不发模型请求、不记录 Key，只有明确点击才保存或测试。
    if (!state.settingsBusy)
        settingsResult(
            "配置有未保存的修改；点击「保存并测试连接」验证当前填写的内容。",
        );
}

/** 因为实际文件才是任务交付证据，需要向后端查询产物而不解析模型回答。 */
async function refreshArtifacts() {
    // 1、迟到结果不能覆盖新选择会话的文件清单。
    if (!state.conversation) return;
    const identifier = state.conversation.id;
    const files = await api("artifacts", identifier);
    if (state.conversation?.id !== identifier) return;
    const panel = el("artifacts");
    panel.replaceChildren();
    for (const file of files) {
        const button = node("button", "", `▤ ${file.path}`);
        button.append(node("small", "", `${file.size.toLocaleString()} bytes`));
        button.dataset.path = file.path;
        button.addEventListener("click", openArtifact);
        panel.append(button);
    }
    if (!files.length) panel.append(node("p", "muted", "尚无产物文件。"));
}

/** 因为用户需要核对真实文件内容，需要从受限产物接口读取并以纯文本预览。 */
async function openArtifact(event) {
    // 1、预览不执行文件内容，也不通过文件名拼接任意系统 URL。
    if (!state.conversation) return;
    await openArtifactPath(
        state.conversation.id,
        event.currentTarget.dataset.path,
    );
}

/** 因为 Markdown 链接和产物列表应共用实际文件读取，需要按固定会话身份打开受限预览。 */
async function openArtifactPath(conversationId, path) {
    // 1、会话身份来自点击入口，读取后再次检查选择，不能把迟到文件显示到另一个会话。
    try {
        const file = await api("read_artifact", conversationId, path);
        if (state.conversation?.id !== conversationId) return;
        el("file-title").textContent = file.path;
        el("file-content").textContent = file.text;
        el("file-dialog").showModal();
    } catch (error) {
        showError(error);
    }
}

/** 因为文件预览只是观察界面，需要允许关闭而不影响正在执行的任务。 */
function closeArtifact() {
    // 1、关闭本地预览层。
    el("file-dialog").close();
}

/** 因为用户可能需要更大对话区域，需要允许收起与恢复执行详情侧栏。 */
function toggleDetails() {
    // 1、仅切换布局，不改变事件记录。
    el("details-panel").classList.toggle("hidden");
}

/** 因为快捷键应只在明确组合下触发，需要集中处理新建会话操作。 */
function keyboardShortcut(event) {
    // 1、配置弹窗打开时不抢占用户输入。
    if (
        event.ctrlKey &&
        event.key.toLowerCase() === "n" &&
        !el("settings-dialog").open
    ) {
        event.preventDefault();
        newConversation();
    }
}

/** 因为桌面桥注入晚于静态页面加载，需要在桥就绪后绑定操作并恢复本地历史。 */
async function boot() {
    // 1、先绑定用户操作；所有业务均通过具名桌面接口。
    studio = new CrewStudio();
    el("participants").replaceChildren();
    updateStats();
    el("new-chat").addEventListener("click", newConversation);
    el("open-settings").addEventListener("click", openSettings);
    el("welcome-settings").addEventListener("click", openSettings);
    el("close-settings").addEventListener("click", closeSettings);
    el("settings-dialog").addEventListener("close", clearKey);
    el("settings-form").addEventListener("submit", saveSettings);
    el("settings-form").addEventListener("input", modelSettingsEdited);
    el("test-model").addEventListener("click", testSettings);
    el("composer").addEventListener("submit", sendTask);
    el("prompt").addEventListener("keydown", promptKey);
    el("stop").addEventListener("click", stopTask);
    el("refresh-files").addEventListener("click", refreshFilesClick);
    el("close-file").addEventListener("click", closeArtifact);
    el("toggle-details").addEventListener("click", toggleDetails);
    document.addEventListener("keydown", keyboardShortcut);
    // 2、恢复最近会话身份；空间默认不请求原始轨迹，不预填任务或答案。
    try {
        workspacePanel = new CrewWorkspaces();
        await workspacePanel.initialize();
    } catch (error) {
        showError(error);
    }
    poll();
}

/** 因为成员名称可能重名，需要用精确匹配集合检查用户的 @ 指派。 */
function mentionMatches(member) {
    // 1、不使用模糊匹配替用户选择员工。
    return member.name === String(this);
}

/** 因为 Escape 也能关闭弹窗，需要统一清除仍留在输入框中的密钥。 */
function clearKey() {
    // 1、不依赖关闭按钮这一条交互路径。
    el("api-key").value = "";
}

/** 因为按钮事件不处理 Promise 拒绝，需要为手动刷新补充明确的错误出口。 */
async function refreshFilesClick() {
    // 1、把失败反馈到当前窗口。
    try {
        await refreshArtifacts();
    } catch (error) {
        showError(error);
    }
}

if (window.pywebview?.api) boot();
else window.addEventListener("pywebviewready", boot, { once: true });
