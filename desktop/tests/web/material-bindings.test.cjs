const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const context = vm.createContext({});
vm.runInContext(
    fs.readFileSync("desktop/ui/studio/protocol.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/skins.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/bubble-layout.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/renderer.js", "utf8") +
        "\nglobalThis.api={crewSelectClip,crewBubbleLayout,crewBubbleIntersects,crewBubbleVisual};",
    context,
);

/** 因为人物精确帧覆盖必须由正式播放器使用，需要验证选定序列、速度和循环覆盖默认变体。 */
function verifyFrameOverride() {
    // 1、同动作不同朝向时，显式绑定只选择用户指定的变体，原清单保持不变。
    const clip = {
        action: "report",
        direction: "s",
        posture: "standing",
        expression: "neutral",
        frames: [0, 1],
        fps: 8,
        loop: true,
    };
    const manifest = { clips: [clip] };
    const binding = {
        action: "report",
        clip: "report.s.standing.neutral",
        frames: [1, 0, 1],
        fps: 5,
        loop: false,
    };
    const chosen = context.api.crewSelectClip(manifest, {
        action: "report",
        posture: "standing",
        direction: "e",
        expression: "smile",
        material_binding: binding,
    });
    assert.deepEqual(Array.from(chosen.frames), [1, 0, 1]);
    assert.equal(chosen.fps, 5);
    assert.equal(chosen.loop, false);
    assert.deepEqual(clip.frames, [0, 1]);
}

/** 因为气泡应该跟随对应人物，需要验证移动、固定屏幕尺寸和避开场景按钮。 */
function verifyBubbleAnchors() {
    // 1、没有边界阻挡时，人物移动多少，泡泡同向移动多少。
    const viewport = { left: 12, right: 900, top: 84, bottom: 700 };
    const first = context.api.crewBubbleLayout({ x: 400, y: 350 }, viewport);
    const second = context.api.crewBubbleLayout({ x: 470, y: 390 }, viewport);
    assert.equal(second.left - first.left, 70);
    assert.equal(second.top - first.top, 40);
    assert.equal(first.width, 224);
    // 2、头顶靠近按钮时仍保留人物指向，同时不覆盖按钮或顶栏。
    const toolbar = { left: 620, right: 930, top: 90, bottom: 155 };
    const edge = context.api.crewBubbleLayout(
        { x: 610, y: 105 },
        { ...viewport, obstacles: [toolbar] },
    );
    assert.equal(context.api.crewBubbleIntersects(edge, toolbar), false);
    assert.ok(
        edge.top >= 84 && edge.left >= 12 && edge.left + edge.width <= 900,
    );
    assert.ok(Math.abs(edge.tailX - 610) < 300);
    // 3、人物被平移到视口边缘外时，泡泡仍随人物移动，不能固定在 left=12。
    const outside = context.api.crewBubbleLayout({ x: -300, y: 350 }, viewport);
    const shifted = context.api.crewBubbleLayout({ x: -270, y: 350 }, viewport);
    assert.equal(shifted.left - outside.left, 30);
    assert.ok(Math.abs(outside.left + outside.width / 2 + 300) < 260);
}

verifyFrameOverride();
verifyBubbleAnchors();
/** 因为缺少姿态会移除图集节点，需要验证泡泡不再读取脱离画面的旧裁切层。 */
function verifyVisibleMaterialFallback() {
    // 1、旧裁切引用仍存在时，当前无图集容器必须选择真实骨架头部。
    const staleCrop = {},
        head = {},
        sprite = {};
    assert.equal(
        context.api.crewBubbleVisual({
            sprite: null,
            spriteFrame: staleCrop,
            rig: { head },
        }),
        head,
    );
    assert.equal(
        context.api.crewBubbleVisual({
            sprite,
            spriteFrame: staleCrop,
            rig: { head },
        }),
        staleCrop,
    );
    assert.equal(
        context.api.crewBubbleVisual({
            sprite,
            spriteFrame: null,
            rig: { head },
        }),
        sprite,
    );
}
verifyVisibleMaterialFallback();
console.log("material frames + actor bubble anchors: passed");
