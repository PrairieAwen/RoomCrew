const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const context = vm.createContext({});
vm.runInContext(
    fs.readFileSync("desktop/ui/studio/protocol.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/skins.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/bubble-layout.js", "utf8") +
        fs.readFileSync("desktop/ui/studio/renderer.js", "utf8") +
        "\nglobalThis.api={crewSelectClip,crewBubbleAnchor,crewAtlasBubbleSockets};",
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

/** 因为行走各帧裁切留白不同，需要验证挂点来自整套姿态而非当前帧。 */
function verifyStableSockets() {
    // 1、统一虚拟画布定义局部挂点，站立和坐姿仅按连续姿态插值。
    const manifest = {
        frame_size: [192, 168],
        pivot: [96, 160],
        display_height: 128,
        clips: [
            { posture: "standing", frames: [0, 1] },
            { posture: "seated", frames: [2, 3] },
        ],
        frame_rects: [
            { offset: [0, 3] },
            { offset: [1, 12] },
            { offset: [0, 40] },
            { offset: [2, 47] },
        ],
    };
    const standing = context.api.crewBubbleAnchor(manifest, 0);
    const seated = context.api.crewBubbleAnchor(manifest, 1);
    assert.equal(standing.x, 0);
    assert.ok(Math.abs(standing.y - ((3 - 160) * 128) / 168) < 1e-10);
    assert.ok(Math.abs(seated.y - ((40 - 160) * 128) / 168) < 1e-10);
    const middle = context.api.crewBubbleAnchor(manifest, 0.5);
    assert.ok(Math.abs(middle.y - (standing.y + seated.y) / 2) < 1e-10);
    // 2、反复采样不接收屏幕位置或帧号，镜头和换帧不能重新选边改变挂点。
    for (let frame = 0; frame < 500; frame += 1)
        assert.equal(context.api.crewBubbleAnchor(manifest, 0).y, standing.y);
    assert.equal(context.api.crewBubbleAnchor(null, 0).y, -116);
    assert.equal(context.api.crewBubbleAnchor(null, 1).y, -103);
}

verifyFrameOverride();
verifyStableSockets();
console.log("material frames + stable local speech sockets: passed");
