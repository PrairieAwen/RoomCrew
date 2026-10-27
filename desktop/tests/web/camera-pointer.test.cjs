const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({});
vm.runInContext(
    fs.readFileSync("desktop/ui/studio/camera.js", "utf8") +
        "\nglobalThis.CrewCamera=CrewCamera;",
    context,
);

/** 因为真实鼠标先产生 pointerdown，需要验证相机不会夺走泡泡或其他交互元素的点击。 */
function verifyPointerOwnership() {
    // 1、在独立图层的泡泡不属于人物组，仍必须排除出空地平移。
    const camera = Object.create(context.CrewCamera.prototype);
    camera.svg = { setPointerCapture: capture, classList: { add: capture } };
    camera.center = [60, 225];
    for (const selector of [
        "button",
        "a",
        "input",
        "select",
        "textarea",
        "[role='button']",
        ".crew-avatar",
        ".room-object",
    ]) {
        camera.drag = null;
        const event = {
            button: 0,
            target: { closest: matchesSelector.bind(null, selector) },
            clientX: 12,
            clientY: 13,
            pointerId: 1,
        };
        camera.down(event);
        assert.equal(camera.drag, null, selector);
    }
    assert.equal(captures, 0);
    // 2、真正空地与中键仍能平移，不能用全局禁用相机绕开问题。
    camera.down({
        button: 0,
        target: { closest: noMatch },
        clientX: 12,
        clientY: 13,
        pointerId: 1,
    });
    assert.equal(camera.drag.x, 12);
    camera.drag = null;
    camera.down({
        button: 1,
        target: { closest: matchesSelector.bind(null, "button") },
        clientX: 15,
        clientY: 16,
        pointerId: 2,
    });
    assert.equal(camera.drag.x, 15);
    assert.equal(captures, 4);
}
let captures = 0;
/** 因为测试节点只需报告最近的交互祖先，需要匹配生产查询中明确包含的选择器。 */
function matchesSelector(expected, selectors) {
    // 1、模拟位于该交互元素内部的文本节点命中其祖先。
    return selectors.split(",").includes(expected) ? {} : null;
}
/** 因为空白画布没有交互祖先，需要返回原生 closest 的未命中语义。 */
function noMatch() {
    // 1、不更改生产判断分支。
    return null;
}
/** 因为交互元素不应触发指针捕获，需要记录相机捕获及平移类切换次数。 */
function capture() {
    // 1、只有有效平移应调用此测试节点方法。
    captures++;
}
verifyPointerOwnership();
console.log(
    "camera pointer ownership: bubbles, controls, empty floor and middle-button passed",
);
