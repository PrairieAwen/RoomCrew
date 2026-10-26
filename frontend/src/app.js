/* 界面只通过桌面桥访问产品接口，不读取数据库、配置文件或系统命令。 */
"use strict";

const state = { conversation: null, cursor: 0, run: null, sending: false, polling: false,
  models: 0, tools: 0, actors: new Set(["main"]), calls: new Map(), toastTimer: null };

/** 因为界面需要频繁定位固定元素，需要用具名入口统一取得节点。 */
function el(id) {
  // 1、所有标识来自本应用静态界面，不构造外部选择器。
  return document.getElementById(id);
}

/** 因为桥调用需要统一处理失败，需要仅接收产品合同中的成功数据或安全错误。 */
async function api(name, ...args) {
  // 1、不记录请求体，尤其不能打印配置表单中的 Key。
  const reply = await window.pywebview.api[name](...args);
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
  state.actors = new Set(["main"]);
  state.calls.clear();
  el("timeline").replaceChildren();
  el("chat-title").textContent = conversation.title || "新会话";
  el("participants").replaceChildren(makeParticipant("助手", "通用 Agent"));
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
  const keepBottom = timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 150;
  const p = event.payload;
  if (!state.actors.has(event.scope)) {
    state.actors.add(event.scope);
    el("participants").append(makeParticipant(event.actor, "独立子任务上下文"));
  }
  // 2、公开消息和工具事件分别展示；工具的开始与结果按调用 ID 合并。
  if (event.kind === "user.message" || event.kind === "assistant.message") {
    const user = event.kind === "user.message";
    const block = node("article", `message ${user ? "user" : "assistant"}`);
    const label = node("div", "message-label");
    label.append(node("span", "mini-avatar", user ? "你" : "R"), node("span", "", event.actor));
    if (event.scope !== "main") label.append(node("span", "subagent-label", "子 Agent"));
    block.append(label, node("div", "message-text", p.text));
    timeline.append(block);
  } else if (event.kind === "tool.started") {
    state.tools += 1;
    const block = node("details", "tool-event");
    const summary = node("summary", "", "◌ ");
    summary.append(node("span", "tool-name", p.name), node("span", "", `${event.actor} · 调用中`));
    block.append(summary, node("div", "tool-label", "INPUT"),
      node("pre", "", JSON.stringify(p.input, null, 2)));
    state.calls.set(p.call_id, { block, summary, name: p.name, actor: event.actor, completed: false });
    timeline.append(block);
  } else if (event.kind === "tool.completed" || event.kind === "tool.failed") {
    const call = state.calls.get(p.call_id);
    const failed = event.kind === "tool.failed" || p.status === "error";
    if (call) {
      call.completed = true;
      call.summary.textContent = `${failed ? "!" : "✓"} ${call.name} · ${call.actor} · ${failed ? "返回错误" : "已返回"}`;
      call.block.append(node("div", "tool-label", "OUTPUT"), node("pre", "", p.output || p.message || "无文本输出"));
    }
  } else if (event.kind === "model.started") {
    state.models += 1;
    timeline.append(node("div", "model-event", `◈ ${event.actor} · 发起模型调用`));
  } else if (event.kind.startsWith("run.") && event.kind !== "run.started") {
    for (const call of state.calls.values()) {
      if (!call.completed) {
        call.summary.textContent = `! ${call.name} · ${call.actor} · 本轮结束，未确认完成`;
        call.completed = true;
      }
    }
    const failed = event.kind === "run.failed" || event.kind === "run.interrupted";
    const text = event.kind === "run.completed" ? "本轮执行结束 · 请核对回复与真实产物" :
      (p.message || "应用关闭导致本轮中断，请新建会话继续。");
    timeline.append(node("div", `run-event ${failed ? "error" : ""}`, text));
    refreshArtifacts().catch(showError);
  }
  // 3、阅读旧消息时保留滚动位置，追踪底部时自动滚动。
  updateStats();
  if (keepBottom) timeline.scrollTop = timeline.scrollHeight;
}

/** 因为异步事件处理器需要共享错误出口，需要把安全错误展示为窗口提示。 */
function showError(error) {
  // 1、生产接口只返回经过转换的错误，不在界面输出底层堆栈。
  toast(error.message || "操作失败");
}

/** 因为会话切换后的旧请求可能迟到，需要按身份校验后再应用历史事件。 */
async function loadEvents() {
  // 1、分批拉取所有新增事件，序号让重新加载保持原始顺序。
  if (!state.conversation) return;
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
  state.run = data.active_run;
  el("config-state").textContent = data.configured ? "已配置" : "未配置";
  el("session-count").textContent = data.conversations.length;
  el("send").disabled = Boolean(state.run) || state.sending;
  el("stop").hidden = !state.run;
  el("run-status").classList.toggle("busy", Boolean(state.run));
  el("run-status").lastElementChild.textContent = state.run ? "正在执行 · 工具与协作记录持续更新" : "准备就绪";
  const nav = el("conversations");
  nav.replaceChildren();
  for (const conversation of data.conversations) {
    const button = node("button", `conversation-item ${state.conversation?.id === conversation.id ? "selected" : ""}`);
    button.append(node("span", "conversation-symbol", "◇"), node("span", "conversation-name", conversation.title));
    button.dataset.conversation = JSON.stringify(conversation);
    button.addEventListener("click", selectConversation);
    nav.append(button);
    if (conversation.id === state.conversation?.id) el("chat-title").textContent = conversation.title;
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
  } catch (error) { showError(error); }
}

/** 因为新任务有时需要完全独立历史，需要通过后端创建新会话并切换观察对象。 */
async function newConversation() {
  // 1、未配置时由后端返回明确提示，不启动默认厂商模型。
  try {
    resetConversation(await api("new_conversation"));
    renderOverview(await api("overview"));
    el("prompt").focus();
  } catch (error) { showError(error); }
}

/** 因为提交失败不能丢失用户输入，需要受理成功后才清空，并用请求标识避免重复执行。 */
async function sendTask(event) {
  // 1、阻止表单导航及重复提交，空文本不创建任务。
  event.preventDefault();
  const text = el("prompt").value.trim();
  if (!text || state.sending || state.run) return;
  state.sending = true;
  el("send").disabled = true;
  try {
    if (!state.conversation) resetConversation(await api("new_conversation"));
    // 2、只发送用户输入和产品 ID，不附带模型配置或 Key。
    const result = await api("submit", state.conversation.id, text, crypto.randomUUID());
    state.run = result.run_id;
    el("prompt").value = "";
    await loadEvents();
  } catch (error) { showError(error); }
  finally {
    state.sending = false;
    el("send").disabled = Boolean(state.run);
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
  try { await api("stop", state.run); await loadEvents(); }
  catch (error) { showError(error); }
  finally { el("stop").disabled = false; }
}

/** 因为模型配置属于用户操作，需要只在用户打开设置时读取非秘密概况。 */
async function openSettings() {
  // 1、配置视图不返回已存 Key，也不写入浏览器存储。
  try {
    const config = await api("configuration");
    el("model-label").value = config.label || "默认模型";
    el("model-id").value = config.model || "";
    el("base-url").value = config.base_url || "";
    el("model-proxy").value = config.proxy || "";
    el("api-key").value = "";
    el("model-timeout").value = config.timeout || 90;
    el("context-window").value = config.context_window || 32768;
    el("key-hint").textContent = config.has_key ? "已保存 Key，不回显；同一端点留空可保留。" : "使用 Windows 本地加密保护，不保存到源码或 .env。";
    settingsResult(config.recovery_required ? "原配置无法读取，请重新填写完整信息和 Key 后保存。" : "", !config.recovery_required);
    el("settings-dialog").showModal();
  } catch (error) { showError(error); }
}

/** 因为手动输入的 Key 不应在隐藏表单中长期保留，需要在关闭设置时清空。 */
function closeSettings() {
  // 1、不保存未提交内容中的 Key。
  el("api-key").value = "";
  el("settings-dialog").close();
}

/** 因为保存和测试需要一致反馈，需要用状态区域区分成功和失败。 */
function settingsResult(message, success = true) {
  // 1、纯文本展示不包含底层异常原文。
  el("settings-result").textContent = message;
  el("settings-result").className = `settings-result ${success ? "success" : "error"}`;
}

/** 因为修改后的参数必须由可信代码验证并加密，需要把配置表单单独提交给配置入口。 */
async function saveSettings(event) {
  // 1、阻止表单导航，并锁定保存与测试按钮避免配置操作相互覆盖。
  event.preventDefault();
  el("save-model").disabled = true;
  el("test-model").disabled = true;
  try {
    await api("save_configuration", { label: el("model-label").value, model: el("model-id").value,
      base_url: el("base-url").value, api_key: el("api-key").value,
      proxy: el("model-proxy").value,
      timeout: Number(el("model-timeout").value), context_window: Number(el("context-window").value) });
    settingsResult("已加密保存。请测试已保存配置；后续任务使用新会话。");
    el("key-hint").textContent = "已保存 Key，不回显；同一端点留空可保留。";
  } catch (error) { settingsResult(error.message, false); }
  finally {
    // 2、无论成功失败都清除表单 Key，避免后续界面操作误读取。
    el("api-key").value = "";
    el("save-model").disabled = false;
    el("test-model").disabled = false;
  }
}

/** 因为用户需要验证真实服务的工具协议，需要调用已保存配置而不是返回本地假成功。 */
async function testSettings() {
  // 1、测试期间明确展示等待，不影响窗口响应。
  el("test-model").disabled = true;
  el("save-model").disabled = true;
  settingsResult("正在请求模型并验证标准工具调用，请稍候…");
  try {
    const result = await api("test_connection");
    settingsResult(result.message);
  } catch (error) { settingsResult(error.message, false); }
  finally { el("test-model").disabled = false; el("save-model").disabled = false; }
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
  try {
    const file = await api("read_artifact", state.conversation.id, event.currentTarget.dataset.path);
    el("file-title").textContent = file.path;
    el("file-content").textContent = file.text;
    el("file-dialog").showModal();
  } catch (error) { showError(error); }
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
  if (event.ctrlKey && event.key.toLowerCase() === "n" && !el("settings-dialog").open) {
    event.preventDefault();
    newConversation();
  }
}

/** 因为桌面桥注入晚于静态页面加载，需要在桥就绪后绑定操作并恢复本地历史。 */
async function boot() {
  // 1、先绑定用户操作；所有业务均通过具名桌面接口。
  el("new-chat").addEventListener("click", newConversation);
  el("open-settings").addEventListener("click", openSettings);
  el("welcome-settings").addEventListener("click", openSettings);
  el("close-settings").addEventListener("click", closeSettings);
  el("settings-dialog").addEventListener("close", clearKey);
  el("settings-form").addEventListener("submit", saveSettings);
  el("test-model").addEventListener("click", testSettings);
  el("composer").addEventListener("submit", sendTask);
  el("prompt").addEventListener("keydown", promptKey);
  el("stop").addEventListener("click", stopTask);
  el("refresh-files").addEventListener("click", refreshFilesClick);
  el("close-file").addEventListener("click", closeArtifact);
  el("toggle-details").addEventListener("click", toggleDetails);
  document.addEventListener("keydown", keyboardShortcut);
  // 2、恢复最近会话和完整轨迹，不预填测试任务或模型答案。
  try {
    const data = await api("overview");
    if (data.conversations.length) {
      resetConversation(data.conversations[0]);
      await loadEvents();
      await refreshArtifacts();
    }
    renderOverview(data);
  } catch (error) { showError(error); }
  poll();
}

/** 因为 Escape 也能关闭弹窗，需要统一清除仍留在输入框中的密钥。 */
function clearKey() {
  // 1、不依赖关闭按钮这一条交互路径。
  el("api-key").value = "";
}

/** 因为按钮事件不处理 Promise 拒绝，需要为手动刷新补充明确的错误出口。 */
async function refreshFilesClick() {
  // 1、把失败反馈到当前窗口。
  try { await refreshArtifacts(); } catch (error) { showError(error); }
}

if (window.pywebview?.api) boot();
else window.addEventListener("pywebviewready", boot, { once: true });
