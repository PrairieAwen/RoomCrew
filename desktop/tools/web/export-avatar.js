/* 开发用样例导出：从正式矢量骨架生成可供用户编辑的 PNG 图集。 */
"use strict";

/** 因为用户需要真实可导入的制作样例，需要用正式骨架逐帧生成透明图集与清单。 */
(async function exportAvatarTemplate() {
    // 1、所有姿态来自本地绘图代码，不产生任务、模型调用或执行轨迹。
    const base = [
        ["idle", "neutral"],
        ["think", "focused"],
        ["read", "focused"],
        ["type", "focused"],
        ["write", "focused"],
        ["talk", "neutral"],
        ["ask", "curious"],
        ["report", "smile"],
        ["alert", "concerned"],
        ["listen", "neutral"],
    ];
    const specs = [];
    for (const [action, expression] of base)
        specs.push({
            action,
            expression,
            direction: "se",
            posture: "standing",
            count: 6,
            fps: 12,
        });
    for (const action of ["walk", "run"])
        for (const direction of ["e", "se", "sw", "w"])
            specs.push({
                action,
                expression: "neutral",
                direction,
                posture: "standing",
                count: 8,
                fps: action === "run" ? 14 : 9,
            });
    for (const action of ["sit_down", "stand_up"])
        specs.push({
            action,
            expression: "neutral",
            direction: "se",
            posture: "standing",
            count: 6,
            fps: 16,
        });
    for (const [action, expression] of base)
        specs.push({
            action,
            expression,
            direction: "se",
            posture: "seated",
            count: 4,
            fps: 8,
        });
    for (const expression of ["focused", "curious", "concerned", "smile"])
        specs.push({
            action: "idle",
            expression,
            direction: "se",
            posture: "standing",
            count: 2,
            fps: 3,
        });
    const count = specs.reduce(crewCountTemplateFrames, 0),
        columns = 16,
        fw = 128,
        fh = 160;
    const canvas = document.createElement("canvas");
    canvas.width = columns * fw;
    canvas.height = Math.ceil(count / columns) * fh;
    const context = canvas.getContext("2d"),
        rig = new CrewRig(),
        clips = [];
    const view = rig.create({
        color: "#759c8c",
        skin: "#edc39b",
        hair: "#51443e",
        glasses: false,
    });
    let index = 0;
    try {
        // 2、将同一套动作、表情与接触点光栅化，用户可替换每格图像而保留协议。
        for (const spec of specs) {
            const frames = [];
            for (let frame = 0; frame < spec.count; frame++) {
                let seat = spec.posture === "seated" ? 1 : 0;
                if (spec.action === "sit_down")
                    seat = crewEase(frame / (spec.count - 1));
                if (spec.action === "stand_up")
                    seat = 1 - crewEase(frame / (spec.count - 1));
                const period =
                    spec.action === "walk"
                        ? (Math.PI * 2) / 7
                        : spec.action === "run"
                          ? (Math.PI * 2) / 11
                          : 1.5;
                view.pose = null;
                rig.paint(
                    view,
                    {
                        action: spec.action,
                        expression: spec.expression,
                        direction: spec.direction,
                        seatMix: seat,
                        time: (frame / spec.count) * period,
                        clock: 0.5,
                        reduced: false,
                    },
                    1,
                );
                const svg = crewSvg("svg", {
                    xmlns: "http://www.w3.org/2000/svg",
                    width: fw,
                    height: fh,
                    viewBox: `0 0 ${fw} ${fh}`,
                });
                const group = crewSvg("g", {
                    transform: "translate(64,151) scale(1.22)",
                });
                group.append(view.root);
                svg.append(group);
                const image = new Image();
                image.src =
                    "data:image/svg+xml;charset=utf-8," +
                    encodeURIComponent(
                        new XMLSerializer().serializeToString(svg),
                    );
                await image.decode();
                context.drawImage(
                    image,
                    (index % columns) * fw,
                    Math.floor(index / columns) * fh,
                );
                frames.push(index++);
            }
            clips.push({
                action: spec.action,
                expression: spec.expression,
                direction: spec.direction,
                posture: spec.posture,
                frames,
                fps: spec.fps,
                loop: !["sit_down", "stand_up", "report"].includes(spec.action),
            });
        }
        // 3、同一图集帧可复用于兼容动作，不增加重复图片。
        for (const clip of [...clips])
            if (clip.action === "type") clips.push({ ...clip, action: "work" });
        const seatedIdle = clips.find(crewTemplateSeatedIdle);
        clips.push({ ...seatedIdle, action: "sit" });
        window.__avatarExport = {
            ok: true,
            image: canvas.toDataURL("image/png"),
            manifest: {
                format: "roomcrew.avatar",
                version: 1,
                name: "薄荷 · 动作制作样例",
                image: "atlas.png",
                frame_size: [fw, fh],
                pivot: [64, 151],
                pixel_art: false,
                clips,
            },
            frames: index,
        };
    } catch (error) {
        window.__avatarExport = { ok: false, error: error.message };
    }
})();

/** 因为图集应在渲染前计算容量，需要统计每个动作所需帧数。 */
function crewCountTemplateFrames(total, spec) {
    // 1、数量来自固定样例规格，不是模型或外部输入。
    return total + spec.count;
}
/** 因为 sit 动作需要稳定的坐姿回退，需要复用同一图集里的坐姿 idle。 */
function crewTemplateSeatedIdle(clip) {
    // 1、只匹配明确的动作与姿态。
    return clip.action === "idle" && clip.posture === "seated";
}
