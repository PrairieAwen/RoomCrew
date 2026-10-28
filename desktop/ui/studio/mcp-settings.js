/* 人工 MCP 编辑入口：公开服务定义和临时鉴权输入分开提交。 */
"use strict";

class CrewMCPEditor {
    /** 因为用户不应手写带秘密的 JSON，需要用独立卡片编辑服务和鉴权。 */
    constructor() {
        // 1、Key 仅在密码框中暂存；关闭属性窗口即清除，不使用浏览器存储。
        this.rows = [];
        this.generation = 0;
        this.counter = 0;
        this.locked = false;
        el("mcp-add").addEventListener("click", this.addCustom.bind(this));
        el("mcp-bailian").addEventListener("click", this.addBailian.bind(this));
        el("member-dialog").addEventListener("close", this.closed.bind(this));
        el("member-dialog").addEventListener("cancel", this.clear.bind(this));
    }

    /** 因为 close 事件可能在下次打开后才到达，需要避免清除新人物的表单。 */
    closed() {
        // 1、同步关闭入口已立即清空，原生 Escape 等路径在关闭后兜底清除。
        if (!el("member-dialog").open) this.clear();
    }

    /** 因为关闭或切换空间后迟到的测试不能回写表单，需要清除秘密并作废旧请求。 */
    clear() {
        // 1、主动清空密码后移除节点，同时更新异步请求代数。
        this.generation += 1;
        for (const row of this.rows) row.key.value = "";
        this.rows = [];
        el("mcp-list").replaceChildren();
        el("mcp-empty").hidden = false;
    }

    /** 因为保存过的配置只包含引用，需要还原认证状态而绝不回显已有 Key。 */
    load(servers) {
        // 1、每次打开重建输入，其他人物未保存的 Key 不得被带入。
        this.clear();
        this.setDisabled(false);
        for (const server of servers) this.add(server);
    }

    /** 因为复用定义和监管员不能修改 Agent 能力，需要统一禁用整个 MCP 编辑区。 */
    setDisabled(value) {
        // 1、fieldset 统一约束所有卡片、预设和测试按钮。
        this.locked = Boolean(value);
        el("member-mcp").disabled = this.locked;
    }

    /** 因为自建 HTTP 服务也需要配置，需要新增不带默认权限的空白服务。 */
    addCustom() {
        // 1、最多八个服务，与后端数量限制一致。
        this.add({ name: "", url: "", enabled: true });
    }

    /** 因为百炼搜索具有独立端点和 Key，需要提供明确的搜索预设并提示密钥区别。 */
    addBailian() {
        // 1、预设只填写公开端点，真实 Key 由用户填写，不复用模型 Key。
        this.add({
            name: "bailian_search",
            url: "https://dashscope.aliyuncs.com/api/v1/mcps/EnhancedSearch/mcp",
            enabled: true,
            bearer: true,
        });
    }

    /** 因为每张卡片具有同样的字段结构，需要集中创建有标签和唯一标识的输入。 */
    field(card, label, type, value, suffix) {
        // 1、所有文字用 textContent/value，外部服务名不能写入 HTML。
        const wrapper = node("label", "", label);
        const input = document.createElement(
            type === "select" ? "select" : "input",
        );
        input.id = `mcp-${this.counter}-${suffix}`;
        if (type !== "select") input.type = type;
        input.value = value;
        wrapper.append(input);
        card.append(wrapper);
        return input;
    }

    /** 因为新增和已保存服务应使用相同交互，需要按公开定义生成独立卡片。 */
    add(server) {
        // 1、禁用配置不接受新卡片；上限反馈不触发保存或网络请求。
        if (this.locked) return;
        if (this.rows.length >= 8) {
            toast("每个 Agent 最多配置 8 个 MCP 服务。");
            return;
        }
        this.counter += 1;
        const card = node("section", "mcp-card");
        const row = { card, reference: server.auth_ref, ticket: 0 };
        const grid = node("div", "mcp-grid");
        row.name = this.field(
            grid,
            "服务名称（英文）",
            "text",
            server.name || "",
            "name",
        );
        row.name.maxLength = 40;
        row.name.placeholder = "例如 bailian_search";
        row.enabled = this.field(grid, "启用服务", "checkbox", "", "enabled");
        row.enabled.checked = server.enabled !== false;
        card.append(grid);
        row.url = this.field(
            card,
            "服务地址 · Streamable HTTP",
            "url",
            server.url || "",
            "url",
        );
        row.url.maxLength = 500;
        row.url.placeholder = "https://example.com/mcp";
        row.mode = this.field(card, "鉴权方式", "select", "", "mode");
        for (const [value, label] of [
            ["none", "无认证"],
            ["bearer", "Bearer API Key"],
        ]) {
            const option = node("option", "", label);
            option.value = value;
            row.mode.append(option);
        }
        row.mode.value = server.auth_ref || server.bearer ? "bearer" : "none";
        row.key = this.field(
            card,
            "API Key（仅本地加密保存）",
            "password",
            "",
            "key",
        );
        row.key.autocomplete = "new-password";
        row.key.maxLength = 4096;
        row.key.placeholder = server.auth_ref
            ? "已保存；同一地址留空保留"
            : "填写此 MCP 服务的 API Key";
        const actions = node("div", "mcp-actions");
        row.test = node("button", "secondary-button", "测试当前配置");
        row.test.type = "button";
        row.test.addEventListener("click", this.test.bind(this, row));
        const remove = node("button", "secondary-button", "移除服务");
        remove.type = "button";
        remove.addEventListener("click", this.remove.bind(this, row));
        actions.append(row.test, remove);
        row.status = node("p", "mcp-status");
        row.status.setAttribute("role", "status");
        card.append(actions, row.status);
        card.addEventListener("input", this.changed.bind(this, row));
        card.addEventListener("change", this.changed.bind(this, row));
        // 2、先注册节点再刷新鉴权可见性；保存引用不显示原始秘密。
        this.rows.push(row);
        el("mcp-list").append(card);
        el("mcp-empty").hidden = true;
        this.changed(row);
    }

    /** 因为表单内容改变后旧测试结论已无效，需要清除提示并按模式展示密码框。 */
    changed(row) {
        // 1、切换无认证时清空尚未保存的密码，避免意外继续提交。
        row.ticket += 1;
        row.status.textContent = "";
        const bearer = row.mode.value === "bearer";
        row.key.parentElement.hidden = !bearer;
        if (!bearer) row.key.value = "";
    }

    /** 因为移除服务不应删除其他配置或历史凭据，需要只移除当前人工编辑草稿。 */
    remove(row) {
        // 1、已保存内容直到点击保存才改变，密码立即从 DOM 清除。
        row.key.value = "";
        row.card.remove();
        this.rows.splice(this.rows.indexOf(row), 1);
        el("mcp-empty").hidden = this.rows.length > 0;
    }

    /** 因为服务定义会写入账号库和快照，需要只读取公开字段并验证唯一名称。 */
    server(row) {
        // 1、地址只整理首尾空白，认证不拼进 URL 或服务定义。
        const server = {
            name: row.name.value.trim(),
            url: row.url.value.trim(),
            enabled: row.enabled.checked,
        };
        if (!/^[a-z][a-z0-9_]{0,39}$/.test(server.name))
            throw new Error(
                "MCP 服务名称请使用小写英文、数字和下划线，并以英文开头。",
            );
        if (!server.url) throw new Error("请填写 MCP 服务地址。");
        if (row.reference) server.auth_ref = row.reference;
        return server;
    }

    /** 因为鉴权输入不能混入普通定义，需要独立返回临时可信参数。 */
    auth(row) {
        // 1、空密码表示保留已保存凭据；首次 Bearer 无 Key 由后端明确拒绝。
        return {
            mode: row.mode.value,
            api_key: row.mode.value === "bearer" ? row.key.value : "",
        };
    }

    /** 因为保存 Agent 需要有界的公开服务列表，需要只收集卡片并拒绝重复名。 */
    read() {
        // 1、复用只读配置时不覆盖其能力。
        if (this.locked) return [];
        const servers = this.rows.map(this.server.bind(this));
        if (new Set(servers.map(crewMCPName)).size !== servers.length)
            throw new Error("MCP 服务名称不能重复。");
        return servers;
    }

    /** 因为密码字段只允许走可信配置入口，需要按服务名收集独立鉴权参数。 */
    readAuth() {
        // 1、普通 Agent JSON 中不会出现 api_key、Authorization 或 Header。
        const auth = {};
        if (!this.locked)
            for (const row of this.rows)
                auth[this.server(row).name] = this.auth(row);
        return auth;
    }

    /** 因为先测试后保存更易排错，需要直接测试当前输入并隔离迟到响应。 */
    async test(row) {
        // 1、发现工具不执行工具；密码只提交给可信桥，不持久化测试草稿。
        if (this.locked || row.test.disabled) return;
        const generation = this.generation;
        const ticket = row.ticket;
        row.test.disabled = true;
        row.status.textContent = "正在连接并读取工具目录…";
        try {
            const result = await api(
                "test_mcp_connection",
                this.server(row),
                this.auth(row),
            );
            if (
                generation === this.generation &&
                ticket === row.ticket &&
                this.rows.includes(row)
            )
                row.status.textContent = result.tools.length
                    ? `连接成功 · ${result.tools.length} 个工具：${result.tools.join("、")}。尚未保存的修改请点击保存。`
                    : "连接成功，但服务没有提供工具。";
        } catch (error) {
            if (
                generation === this.generation &&
                ticket === row.ticket &&
                this.rows.includes(row)
            )
                row.status.textContent =
                    error.message || "连接失败，请检查地址、Key 和权限。";
        } finally {
            // 2、无论成功、失败或编辑内容变化，都恢复本卡片按钮，旧窗口不再写回。
            row.test.disabled = false;
        }
    }
}

/** 因为卡片需要校验唯一名称，需要用具名投影而非复制配置对象。 */
function crewMCPName(server) {
    // 1、只投影公开名称，不接触鉴权输入。
    return server.name;
}
