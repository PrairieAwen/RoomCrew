/* 模型与用户 Markdown 只生成有限 DOM；原文仍由产品轨迹保存。 */
"use strict";

const CREW_MARKDOWN_TAGS = new Set([
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "s",
    "ul",
    "ol",
    "li",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "hr",
]);
const CREW_MARKDOWN =
    typeof markdownit === "function"
        ? markdownit({
              html: false,
              breaks: true,
              linkify: true,
              typographer: false,
              maxNesting: 24,
          })
        : null;
if (CREW_MARKDOWN) {
    CREW_MARKDOWN.validateLink = crewMarkdownLinkAllowed;
    CREW_MARKDOWN.linkify.set({ fuzzyEmail: false, fuzzyLink: false });
}

/** 因为链接可能指向脚本、宿主文件或任务产物，需要先分类并只保留明确允许的目标。
 * 返回网页 URL 或会话虚拟路径；非法目标返回 null，解析不触发任何请求。
 */
function crewMarkdownTarget(value) {
    // 1、网页只允许 HTTP(S)，不能用链接切换主窗口或打开系统协议。
    if (typeof value !== "string" || !value || /[\x00-\x20\x7f\\]/.test(value))
        return null;
    if (/^https?:/i.test(value)) {
        try {
            const url = new URL(value);
            if (
                !["http:", "https:"].includes(url.protocol) ||
                url.username ||
                url.password
            )
                return null;
            return { kind: "web", value: url.href };
        } catch {
            return null;
        }
    }
    // 2、相对链接只进入会话产物读取接口，不作为 file URL 或系统绝对路径使用。
    if (value.startsWith("//") || /[:?#]/.test(value)) return null;
    try {
        const decoded = decodeURIComponent(value);
        if (/[\x00-\x1f\x7f\\:?#]/.test(decoded) || decoded.startsWith("//"))
            return null;
        const pieces = decoded.split("/").filter(crewMarkdownPathPart);
        if (!pieces.length || pieces.includes("..")) return null;
        return { kind: "artifact", value: "/" + pieces.join("/") };
    } catch {
        return null;
    }
}

/** 因为路径允许常见 ./ 与前导斜线，需要移除空段而不吞掉真正的上级跳转。 */
function crewMarkdownPathPart(part) {
    // 1、.. 仍交由上层明确拒绝。
    return part !== "" && part !== ".";
}

/** 因为解析器与 DOM 层应使用同一链接规则，需要复用目标分类结果。 */
function crewMarkdownLinkAllowed(value) {
    // 1、此校验只有字符串判断，没有跳转或文件访问。
    return crewMarkdownTarget(value) !== null;
}

/** 因为消息需要排版且不能执行模型输出，需要将解析 Token 显式构造成白名单 DOM。
 * options.onArtifact 接收会话虚拟路径；大文本或解析异常保留全部纯文本。
 */
function crewRenderMarkdown(target, value, options = {}) {
    // 1、限制解析工作量；不修改原始轨迹，也不把消息交给 innerHTML。
    const source = String(value ?? "");
    target.classList.add("markdown-content");
    target.replaceChildren();
    if (!CREW_MARKDOWN || source.length > 200000) {
        target.classList.add("markdown-plain");
        target.textContent = source;
        return;
    }
    // 2、先离屏构造，失败时整体回退原文，避免展示半段错误结构。
    try {
        const content = document.createDocumentFragment();
        crewMarkdownTokens(CREW_MARKDOWN.parse(source, {}), content, options, {
            remaining: 20000,
        });
        target.classList.remove("markdown-plain");
        target.append(content);
    } catch {
        target.classList.add("markdown-plain");
        target.textContent = source;
    }
}

/** 因为块级和行内语法可嵌套，需要用有界栈还原结构且不复制解析器自身语法规则。 */
function crewMarkdownTokens(tokens, parent, options, budget) {
    // 1、所有文本走 textContent / TextNode，未知属性、HTML 和脚本均不能进入 DOM。
    const stack = [parent];
    for (const token of tokens) {
        if (--budget.remaining < 0) throw new Error("Markdown token limit");
        if (token.hidden) continue;
        const current = stack[stack.length - 1];
        if (token.type === "inline") {
            crewMarkdownTokens(token.children || [], current, options, budget);
        } else if (token.type === "text" || token.type === "code_inline") {
            if (token.type === "code_inline") {
                const code = document.createElement("code");
                code.textContent = token.content;
                current.append(code);
            } else current.append(document.createTextNode(token.content));
        } else if (["softbreak", "hardbreak"].includes(token.type)) {
            current.append(document.createElement("br"));
        } else if (["fence", "code_block"].includes(token.type)) {
            current.append(crewMarkdownCode(token));
        } else if (token.type === "image") {
            const label = document.createElement("span");
            label.className = "markdown-image-label";
            label.textContent = "［图片：" + (token.content || "未命名") + "］";
            current.append(label);
        } else if (token.nesting === -1) {
            if (stack.length > 1) stack.pop();
        } else if (token.type === "link_open") {
            const link = crewMarkdownLink(token, options);
            current.append(link);
            stack.push(link);
        } else if (CREW_MARKDOWN_TAGS.has(token.tag)) {
            const element = document.createElement(token.tag);
            crewMarkdownAttributes(element, token);
            if (token.tag === "table") {
                const wrap = document.createElement("div");
                wrap.className = "markdown-table-scroll";
                wrap.tabIndex = 0;
                wrap.append(element);
                current.append(wrap);
            } else current.append(element);
            if (token.nesting === 1) stack.push(element);
        } else if (token.content)
            current.append(document.createTextNode(token.content));
    }
}

/** 因为表格对齐和列表起点需要保留，需要只复制这两类有限格式属性。 */
function crewMarkdownAttributes(element, token) {
    // 1、不复制事件、任意样式或资源地址；允许值映射为本地 CSS 类。
    const alignment = /^text-align:(left|center|right)$/.exec(
        token.attrGet("style") || "",
    );
    if (alignment && ["td", "th"].includes(token.tag))
        element.classList.add("md-align-" + alignment[1]);
    const start = token.attrGet("start");
    if (token.tag === "ol" && /^\d{1,9}$/.test(start || ""))
        element.start = Number(start);
}

/** 因为网页与会话产物不能共用系统跳转，需要为每类链接创建明确的点击入口。 */
function crewMarkdownLink(token, options) {
    // 1、再次校验解析后的地址；解析器不能替应用决定真实文件访问。
    const target = crewMarkdownTarget(token.attrGet("href"));
    const link = document.createElement(
        target?.kind === "web"
            ? "a"
            : target?.kind === "artifact"
              ? "button"
              : "span",
    );
    if (target?.kind === "web") {
        link.href = target.value;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.referrerPolicy = "no-referrer";
    } else if (target?.kind === "artifact") {
        link.type = "button";
        link.className = "markdown-artifact-link";
        link.title = "查看会话产物：" + target.value;
        link.disabled = typeof options.onArtifact !== "function";
        if (!link.disabled)
            link.addEventListener(
                "click",
                crewMarkdownOpenArtifact.bind(
                    null,
                    target.value,
                    options.onArtifact,
                ),
            );
    }
    return link;
}

/** 因为产物只能在用户点击后读取，需要把已校验的虚拟路径交给界面已有预览用例。 */
function crewMarkdownOpenArtifact(path, open, event) {
    // 1、不能让链接冒泡为其他界面操作；后台仍校验工作空间和会话。
    event.preventDefault();
    event.stopPropagation();
    open(path);
}

/** 因为代码中的星号与 HTML 必须原样保留，需要把 fenced 内容放入纯文本代码节点。 */
function crewMarkdownCode(token) {
    // 1、语言名只做有限文本标签，代码不高亮执行，也不加载插件或远程资源。
    const block = document.createElement("div");
    block.className = "markdown-code";
    const header = document.createElement("div");
    header.className = "markdown-code-header";
    const language = document.createElement("span");
    const name = token.info?.trim().split(/\s+/)[0] || "text";
    language.textContent = /^[\w+-]{1,32}$/.test(name) ? name : "text";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "复制代码";
    copy.addEventListener("click", crewMarkdownCopyCode);
    const pre = document.createElement("pre"),
        code = document.createElement("code");
    code.textContent = token.content;
    pre.append(code);
    header.append(language, copy);
    block.append(header, pre);
    return block;
}

/** 因为用户复制代码需要保持星号和换行，需要在明确点击时读取代码原文写入剪贴板。 */
async function crewMarkdownCopyCode(event) {
    // 1、没有点击不写剪贴板；缺少系统能力或失败时显示明确反馈。
    const button = event.currentTarget;
    const code = button
        .closest(".markdown-code")
        .querySelector("code").textContent;
    try {
        await navigator.clipboard.writeText(code);
        button.textContent = "已复制";
    } catch {
        button.textContent = "复制失败，请选中复制";
    }
    setTimeout(crewMarkdownRestoreCopy.bind(null, button), 2500);
}

/** 因为复制反馈不能永久覆盖按钮，需要在当前节点仍存在时恢复标签。 */
function crewMarkdownRestoreCopy(button) {
    // 1、不修改已切换会话的其他按钮。
    if (button.isConnected) button.textContent = "复制代码";
}
