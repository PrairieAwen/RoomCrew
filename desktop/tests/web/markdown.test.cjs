const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const vm = require("node:vm");
const markdownit = require("../../ui/vendor/markdown-it/markdown-it.min.js");
const context = vm.createContext({ markdownit, URL });
vm.runInContext(
    fs.readFileSync("desktop/ui/message-markdown.js", "utf8"),
    context,
);

/** 因为消息链接是不可信输入，需要逐例检查公共规则与解析器使用同一安全边界。 */
function verifyLinks() {
    // 1、禁止脚本、宿主路径、认证 URL、越级和不明确的协议。
    for (const value of [
        "javascript:alert(1)",
        "data:text/html,x",
        "file:///C:/secret",
        "mailto:a@b.com",
        "//server/path",
        "C:/secret",
        "\\\\server\\share",
        "../secret",
        "/%2e%2e/secret",
        "/a/%2e%2e/b",
        "/%2f%2fserver",
        "/a%5cb",
        "/a%00b",
        "/%zz",
        "#anchor",
        "https://user:pass@example.com",
        "java\nscript:alert(1)",
        "https://example.com\n/x",
    ])
        assert.equal(context.crewMarkdownTarget(value), null, value);
    // 2、允许明确 HTTP(S) 和当前会话产物，中文路径只解码一次。
    assert.equal(
        context.crewMarkdownTarget("https://example.com/a?q=1#b").kind,
        "web",
    );
    assert.equal(context.crewMarkdownTarget("./notes.md").value, "/notes.md");
    assert.equal(
        context.crewMarkdownTarget("/%E6%97%A5%E8%AE%B0%20a.md").value,
        "/日记 a.md",
    );
    const tokens = vm.runInContext(
        'CREW_MARKDOWN.parse("[bad](javascript:alert(1))\\n\\n<b>literal</b>",{})',
        context,
    );
    assert.equal(JSON.stringify(tokens).includes('"type":"link_open"'), false);
    assert.equal(
        JSON.stringify(tokens).includes('"type":"html_inline"'),
        false,
    );
}

/** 因为分发不能依赖 CDN 或漏装本地库，需要校验实际 vendor 和页面加载顺序。 */
function verifyDependency() {
    // 1、与锁定的官方包内容一致，第三方许可证随包保留。
    const manifest = JSON.parse(
        fs.readFileSync(
            "desktop/ui/vendor/markdown-it/dependency.json",
            "utf8",
        ),
    );
    const actual = crypto
        .createHash("sha256")
        .update(
            fs.readFileSync("desktop/ui/vendor/markdown-it/markdown-it.min.js"),
        )
        .digest("hex");
    assert.equal(actual, manifest.sha256);
    assert.ok(
        fs
            .readFileSync("desktop/ui/vendor/markdown-it/LICENSE", "utf8")
            .includes("MIT"),
    );
    const html = fs.readFileSync("desktop/ui/index.html", "utf8");
    assert.ok(
        html.indexOf('src="vendor/markdown-it/markdown-it.min.js"') <
            html.indexOf('src="message-markdown.js"'),
    );
    assert.ok(
        html.indexOf('src="message-markdown.js"') <
            html.indexOf('src="app.js"'),
    );
}
verifyLinks();
verifyDependency();
verifyPlainFallback();
console.log(
    "Markdown links, inert HTML parsing, dependency integrity, offline load order and lossless fallback passed",
);

/** 因为超长消息和本地解析器加载失败不能丢内容，需要检查两类降级都完整保留原文。 */
function verifyPlainFallback() {
    // 1、纯文本分支不依赖 DOM 解析，不截断或删除星号。
    const longText = "**保留原文**".repeat(30000);
    const target = {
        classList: { add: ignoreClass },
        replaceChildren: ignoreClass,
        textContent: "",
    };
    context.crewRenderMarkdown(target, longText);
    assert.equal(target.textContent, longText);
    // 2、模拟本地库未加载，界面仍可显示普通消息。
    const missing = vm.createContext({ URL });
    vm.runInContext(
        fs.readFileSync("desktop/ui/message-markdown.js", "utf8"),
        missing,
    );
    missing.crewRenderMarkdown(target, "**仍可阅读**");
    assert.equal(target.textContent, "**仍可阅读**");
}

/** 因为降级验证不关心 CSS 类，需要提供无副作用的最小节点方法。 */
function ignoreClass() {
    // 1、不改变生产渲染函数或其输入文本。
}
