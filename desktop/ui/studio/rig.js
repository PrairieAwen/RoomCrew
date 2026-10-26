/* 高分辨率矢量角色骨架：连续关节、道具、表情与朝向独立求值。 */
"use strict";

class CrewRig {
    /** 因为内置和自制角色需要共用脚底坐标，需要建立统一骨架和角色尺度。 */
    create(member) {
        // 1、所有图形来自本地代码，用户颜色仅用于受验证的填色属性。
        const root = crewSvg("g", { class: "rig-visual" }),
            legs = crewSvg("g"),
            body = crewSvg("g");
        const leftLeg = this.limb(legs, "#3f4b56", 13),
            rightLeg = this.limb(legs, "#4e5c67", 13);
        const leftArm = this.limb(body, member.color, 12);
        const jacket = crewSvg("g");
        jacket.append(
            crewSvg("path", {
                d: "M-13,-77 Q0,-84 14,-77 L19,-36 Q0,-29 -19,-36 Z",
                fill: member.color,
                stroke: "#33443e",
                "stroke-width": 1.2,
            }),
            crewSvg("path", {
                d: "M-8,-78 L0,-57 L9,-78 L6,-42 L-5,-42 Z",
                fill: "#f8f1df",
            }),
            crewSvg("path", {
                d: "M-12,-77 L-3,-65 L-9,-61 L-2,-52 M12,-77 L3,-65 L9,-61 L3,-51",
                fill: "none",
                stroke: "#e6ead76e",
                "stroke-width": 1.6,
            }),
            crewSvg("path", {
                d: "M-16,-44 L-7,-44 M7,-44 L16,-44",
                stroke: "#32423b",
                opacity: 0.45,
                "stroke-width": 1.5,
            }),
            crewSvg("circle", { cx: 0, cy: -44, r: 1.4, fill: "#e9dbb3" }),
        );
        body.append(jacket);
        const rightArm = this.limb(body, member.color, 12);
        const neck = crewSvg("rect", {
            x: -6,
            y: -86,
            width: 12,
            height: 13,
            rx: 5,
            fill: member.skin,
        });
        body.append(neck);
        const head = crewSvg("g");
        head.append(
            crewSvg("ellipse", {
                cx: -21,
                cy: -101,
                rx: 4,
                ry: 6,
                fill: member.skin,
            }),
            crewSvg("ellipse", {
                cx: 21,
                cy: -101,
                rx: 4,
                ry: 6,
                fill: member.skin,
            }),
            crewSvg("path", {
                d: "M-21,-111 C-23,-132 24,-133 23,-108 L20,-96 Q17,-81 1,-80 Q-17,-81 -21,-98 Z",
                fill: member.skin,
                stroke: "#896b5411",
                "stroke-width": 1,
            }),
            crewSvg("ellipse", {
                cx: -13,
                cy: -96,
                rx: 5,
                ry: 2.6,
                fill: "#cf8770",
                opacity: 0.22,
            }),
            crewSvg("ellipse", {
                cx: 14,
                cy: -96,
                rx: 5,
                ry: 2.6,
                fill: "#cf8770",
                opacity: 0.22,
            }),
        );
        const face = crewSvg("g");
        const eyeLeft = crewSvg("ellipse", {
                cx: -9,
                cy: -103,
                rx: 2.8,
                ry: 3.5,
                fill: "#3e3934",
            }),
            eyeRight = crewSvg("ellipse", {
                cx: 10,
                cy: -103,
                rx: 2.8,
                ry: 3.5,
                fill: "#3e3934",
            });
        const browLeft = crewSvg("path", {
            stroke: member.hair,
            "stroke-width": 2.1,
            "stroke-linecap": "round",
            fill: "none",
        });
        const browRight = browLeft.cloneNode();
        const mouth = crewSvg("path", {
            stroke: "#9e6655",
            "stroke-width": 1.6,
            "stroke-linecap": "round",
            fill: "none",
        });
        face.append(
            eyeLeft,
            eyeRight,
            crewSvg("circle", {
                cx: -8.2,
                cy: -104.2,
                r: 0.8,
                fill: "#fcf8ee",
            }),
            crewSvg("circle", {
                cx: 10.7,
                cy: -104.2,
                r: 0.8,
                fill: "#fcf8ee",
            }),
            browLeft,
            browRight,
            crewSvg("path", {
                d: "M2,-101 l2,4 l-3,1",
                stroke: "#bf9277",
                "stroke-width": 1,
                fill: "none",
            }),
            mouth,
        );
        if (member.glasses)
            face.append(
                crewSvg("path", {
                    d: "M-18,-108 h15 v10 h-15z M5,-108 h15 v10 h-15z M-3,-104 h8",
                    fill: "#5f797011",
                    stroke: "#394c48",
                    "stroke-width": 1.5,
                }),
            );
        head.append(face);
        const hair = crewSvg("path", {
            d: "M-23,-102 Q-30,-117 -19,-129 Q-5,-143 9,-134 Q28,-137 26,-114 L21,-101 L17,-117 Q9,-112 5,-118 Q-5,-110 -14,-119 L-19,-100Z",
            fill: member.hair,
        });
        head.append(
            hair,
            crewSvg("path", {
                d: "M-14,-128 Q-3,-136 10,-129 M-18,-122 Q-6,-128 0,-124",
                stroke: "#ffffff17",
                "stroke-width": 2,
                fill: "none",
            }),
        );
        const back = crewSvg("path", {
            d: "M-21,-113 Q-26,-134 0,-135 Q27,-134 23,-110 L20,-94 Q0,-87 -20,-95Z",
            fill: member.hair,
            visibility: "hidden",
        });
        head.append(back);
        body.append(head);
        const props = this.props();
        body.append(
            props.book,
            props.paper,
            props.keyboard,
            props.pen,
            props.phone,
            props.game,
            props.water,
        );
        root.append(legs, body);
        return {
            root,
            legs,
            body,
            jacket,
            head,
            face,
            back,
            leftLeg,
            rightLeg,
            leftArm,
            rightArm,
            eyeLeft,
            eyeRight,
            browLeft,
            browRight,
            mouth,
            props,
            gameToken: props.game.querySelector(".leisure-game-token"),
            waterDrops: props.water.querySelector(".leisure-water-drops"),
            skin: member.skin,
            pose: null,
        };
    }

    /** 因为四肢需要连续弯曲和高光，需要用两段描边及末端节点组成同一关节结构。 */
    limb(parent, color, width) {
        // 1、轮廓、高光和末端使用同一骨架路径，避免分离的部件抖动。
        const outline = crewSvg("path", {
            fill: "none",
            stroke: "#2d3938",
            "stroke-width": width + 1.7,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        });
        const line = crewSvg("path", {
            fill: "none",
            stroke: color,
            "stroke-width": width,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        });
        const end = crewSvg("ellipse", {
            rx: width * 0.48,
            ry: width * 0.28,
            fill: "#29333a",
        });
        parent.append(outline, line, end);
        return { outline, line, end };
    }

    /** 因为工作与摸鱼应有可辨认的道具，需要预建书本、纸笔、手机、游戏机和盆栽并按动作切换。 */
    props() {
        // 1、道具只用于表现，不执行真实键盘或文件命令。
        const book = crewSvg("g", { visibility: "hidden" });
        book.append(
            crewSvg("path", {
                d: "M-19,-63 Q-9,-65 0,-58 Q10,-65 20,-62 L19,-39 Q9,-42 0,-35 Q-9,-42 -20,-40Z",
                fill: "#f9efcf",
                stroke: "#7a8265",
                "stroke-width": 1.5,
            }),
            crewSvg("path", {
                d: "M0,-58 v23 M-15,-57 l10,3 M-16,-51 l11,3 M5,-53 l10,-3 M5,-47 l10,-3",
                stroke: "#a8a58b",
                fill: "none",
                "stroke-width": 1,
            }),
        );
        const paper = crewSvg("g", { visibility: "hidden" });
        paper.append(
            crewSvg("path", {
                d: "M-16,-65 L13,-69 L17,-35 L-12,-31Z",
                fill: "#f4efdc",
                stroke: "#8a917d",
                "stroke-width": 1.2,
            }),
            crewSvg("path", {
                d: "M-10,-58 l17,-2 M-9,-52 l17,-2 M-8,-46 l15,-2 M-7,-40 l11,-2",
                stroke: "#afb5a2",
                "stroke-width": 1,
            }),
        );
        const keyboard = crewSvg("g", { visibility: "hidden" });
        keyboard.append(
            crewSvg("path", {
                d: "M-24,-42 L18,-43 L28,-28 L-18,-27Z",
                fill: "#53676b",
                stroke: "#34484a",
                "stroke-width": 1.2,
            }),
            crewSvg("path", {
                d: "M-16,-38 h31 M-12,-33 h30 M-8,-29 h19",
                stroke: "#c1d7ce",
                "stroke-width": 1.6,
                "stroke-dasharray": "2 2",
            }),
        );
        const pen = crewSvg("path", {
            d: "M10,-57 L24,-70",
            stroke: "#485f70",
            "stroke-width": 2.5,
            visibility: "hidden",
        });
        // 2、生活道具都是本地几何图形，绝不打开手机、启动游戏或控制实体设备。
        const phone = crewSvg("g", { visibility: "hidden" });
        phone.append(
            crewSvg("rect", {
                x: -9,
                y: -65,
                width: 18,
                height: 29,
                rx: 3,
                fill: "#354b54",
                stroke: "#24353d",
                "stroke-width": 1.5,
            }),
            crewSvg("rect", {
                x: -6,
                y: -60,
                width: 12,
                height: 19,
                rx: 1,
                fill: "#b8ddcc",
            }),
            crewSvg("path", {
                d: "M-3,-56 h6 M-3,-52 h4 M-3,-48 h6",
                stroke: "#5e8a7a",
                "stroke-width": 1.5,
            }),
            crewSvg("circle", { cx: 0, cy: -38, r: 1, fill: "#e1d9b5" }),
        );
        const game = crewSvg("g", { visibility: "hidden" });
        game.append(
            crewSvg("path", {
                d: "M-23,-65 h43 l3,28 h-44Z",
                fill: "#46596b",
                stroke: "#2f414e",
                "stroke-width": 1.4,
            }),
            crewSvg("path", { d: "M-19,-61 h35 l2,20 h-35Z", fill: "#263e56" }),
            crewSvg("path", {
                d: "M-17,-44 h32 M-13,-51 h5 M4,-54 h9",
                stroke: "#7ba78d",
                "stroke-width": 2,
            }),
            crewSvg("rect", {
                x: -4,
                y: -51,
                width: 5,
                height: 7,
                rx: 1,
                fill: "#e6bf75",
                class: "leisure-game-token",
            }),
            crewSvg("path", {
                d: "M-21,-37 h44 l7,11 h-52Z",
                fill: "#76918f",
                stroke: "#425b5e",
                "stroke-width": 1.2,
            }),
            crewSvg("path", {
                d: "M-14,-32 h31",
                stroke: "#d0d9c7",
                "stroke-width": 2,
                "stroke-dasharray": "2 2",
            }),
        );
        const water = crewSvg("g", { visibility: "hidden" });
        water.append(
            crewSvg("path", {
                d: "M14,-49 Q5,-68 20,-66 L23,-57",
                fill: "none",
                stroke: "#518878",
                "stroke-width": 3,
            }),
            crewSvg("path", {
                d: "M12,-56 L28,-56 L29,-42 L15,-42Z M27,-50 L36,-44 L36,-40 L25,-45Z",
                fill: "#7eb4a1",
                stroke: "#3f7667",
                "stroke-width": 1.5,
            }),
            crewSvg("path", {
                d: "M35,-39 l2,9 M39,-35 l2,7 M33,-35 l1,8",
                stroke: "#83bfd0",
                "stroke-width": 1.4,
                "stroke-dasharray": "2 3",
                class: "leisure-water-drops",
            }),
            crewSvg("path", {
                d: "M27,-15 L44,-15 L41,-1 L30,-1Z",
                fill: "#b68b64",
                stroke: "#856b50",
                "stroke-width": 1,
            }),
            crewSvg("path", {
                d: "M35,-15 v-18 M35,-22 Q21,-37 25,-24 Q28,-18 35,-20 M35,-25 Q48,-40 45,-26 Q43,-21 35,-22",
                fill: "#739a65",
                stroke: "#527f53",
                "stroke-width": 1.5,
            }),
        );
        return { book, paper, keyboard, pen, phone, game, water };
    }

    /** 因为动作切换应自然衔接，需要计算连续目标关节，再平滑混合到当前显示姿态。 */
    paint(view, sample, dt) {
        // 1、姿态、步态、表情分别求值，移动不会抹掉提问或错误表情。
        const target = crewPose(sample),
            mix = sample.reduced ? 1 : 1 - Math.exp(-Math.min(dt, 0.05) * 18);
        if (!view.pose) view.pose = { ...target };
        for (const key of Object.keys(target))
            view.pose[key] += (target[key] - view.pose[key]) * mix;
        const pose = view.pose,
            seat = sample.seatMix || 0;
        const left = sample.direction.includes("w"),
            back = ["n", "nw", "ne"].includes(sample.direction);
        view.root.setAttribute(
            "transform",
            `scale(${left ? -0.87 : 0.87},.87)`,
        );
        view.body.setAttribute(
            "transform",
            `translate(0,${pose.bob + seat * 15}) rotate(${pose.lean} 0 -36)`,
        );
        view.head.setAttribute("transform", `rotate(${pose.head} 0 -85)`);
        view.face.setAttribute("visibility", back ? "hidden" : "visible");
        view.back.setAttribute("visibility", back ? "visible" : "hidden");
        const hipY = -35 + seat * 14;
        this.paintLimb(
            view.leftLeg,
            [-8, hipY],
            pose.legL,
            pose.kneeL,
            22,
            21,
            false,
            view.skin,
        );
        this.paintLimb(
            view.rightLeg,
            [8, hipY],
            pose.legR,
            pose.kneeR,
            22,
            21,
            false,
            view.skin,
        );
        this.paintArm(
            view.leftArm,
            [-16, -69],
            [pose.handLX, pose.handLY],
            1,
            view.skin,
        );
        this.paintArm(
            view.rightArm,
            [16, -69],
            [pose.handRX, pose.handRY],
            -1,
            view.skin,
        );
        // 2、道具随着动作切换，不把未知素材字段或模型文本写进 SVG。
        for (const [name, prop] of Object.entries(view.props))
            prop.setAttribute(
                "visibility",
                (
                    {
                        book: ["read"],
                        paper: ["write", "report"],
                        keyboard: ["work", "type"],
                        pen: ["write"],
                        phone: ["phone"],
                        game: ["game"],
                        water: ["water"],
                    }[name] || []
                ).includes(sample.action)
                    ? "visible"
                    : "hidden",
            );
        view.props.pen.setAttribute(
            "transform",
            `translate(${Math.sin(sample.time * 11) * 1.5},${Math.cos(sample.time * 11) * 1.5})`,
        );
        if (sample.action === "phone")
            view.props.phone.setAttribute(
                "transform",
                `rotate(${Math.sin(sample.time * 1.8) * 2} 0 -50)`,
            );
        if (sample.action === "game")
            view.gameToken.setAttribute(
                "transform",
                `translate(${Math.sin(sample.time * 3) * 10},${-Math.abs(Math.sin(sample.time * 4)) * 3})`,
            );
        if (sample.action === "water")
            view.waterDrops.setAttribute(
                "stroke-dashoffset",
                sample.reduced ? 0 : -sample.time * 12,
            );
        // 3、面部由有限表情词表驱动，眨眼只修饰眼睛，不改变业务状态。
        const blink = !sample.reduced && sample.clock % 3.7 < 0.12,
            expression = sample.expression;
        view.eyeLeft.setAttribute(
            "ry",
            blink ? 0.45 : expression === "curious" ? 4.5 : 3.4,
        );
        view.eyeRight.setAttribute(
            "ry",
            blink ? 0.45 : expression === "curious" ? 4.5 : 3.4,
        );
        const brows =
            expression === "concerned"
                ? ["M-15,-113 L-5,-116", "M5,-116 L15,-113"]
                : expression === "curious"
                  ? ["M-15,-117 L-5,-118", "M5,-112 L15,-114"]
                  : expression === "focused"
                    ? ["M-15,-113 L-5,-111", "M5,-111 L15,-113"]
                    : [
                          "M-15,-113 Q-10,-116 -5,-113",
                          "M5,-113 Q10,-116 15,-113",
                      ];
        view.browLeft.setAttribute("d", brows[0]);
        view.browRight.setAttribute("d", brows[1]);
        view.mouth.setAttribute(
            "d",
            expression === "curious"
                ? "M-2,-91 Q1,-97 4,-91 Q1,-86 -2,-91"
                : expression === "concerned"
                  ? "M-5,-90 Q1,-95 6,-90"
                  : expression === "smile"
                    ? "M-6,-92 Q1,-84 8,-93"
                    : ["talk", "ask"].includes(sample.action)
                      ? `M-4,-92 Q2,${-88 + Math.sin(sample.time * 13) * 2} 6,-92`
                      : "M-4,-91 Q1,-89 5,-92",
        );
    }

    /** 因为手部动作有明确接触目标，需要用两骨段逆运动学保持拿书、书写和抬手连贯。 */
    paintArm(limb, root, hand, side, skin) {
        // 1、目标限制在手臂可达半径内，肘关节不因动作混合翻转。
        const dx = hand[0] - root[0],
            dy = hand[1] - root[1],
            distance = Math.min(37, Math.max(1, Math.hypot(dx, dy)));
        const angle = Math.atan2(dy, dx),
            bend = Math.acos(distance / 38) * side;
        const elbow = [
            root[0] + Math.cos(angle + bend) * 19,
            root[1] + Math.sin(angle + bend) * 19,
        ];
        const end = [
            root[0] + Math.cos(angle) * distance,
            root[1] + Math.sin(angle) * distance,
        ];
        const path = `M${root} L${elbow} L${end}`;
        limb.outline.setAttribute("d", path);
        limb.line.setAttribute("d", path);
        limb.end.setAttribute("cx", end[0]);
        limb.end.setAttribute("cy", end[1]);
        limb.end.setAttribute("rx", 4.6);
        limb.end.setAttribute("ry", 4.6);
        limb.end.setAttribute("fill", skin);
    }

    /** 因为走跑和坐姿腿部曲线不同，需要统一按关节角度计算膝盖与脚底。 */
    paintLimb(limb, root, upper, lower, length1, length2, hand, skin) {
        // 1、两段曲线共享同一接点，脚掌保留落地感而不是整条腿摆动。
        const first = crewJoint(root, upper, length1),
            end = crewJoint(first, upper + lower, length2);
        const path = `M${root} L${first} L${end}`;
        limb.outline.setAttribute("d", path);
        limb.line.setAttribute("d", path);
        limb.end.setAttribute("cx", end[0] + 2);
        limb.end.setAttribute("cy", end[1]);
    }
}

/** 因为连续动作需要可复用的关节计算，需要把角度转换为两维骨段端点。 */
function crewJoint(root, angle, length) {
    // 1、以向下为零度，方便站立、摆腿与屈膝使用同一坐标系。
    const radians = (angle * Math.PI) / 180;
    return [
        root[0] + Math.sin(radians) * length,
        root[1] + Math.cos(radians) * length,
    ];
}

/** 因为每种状态需要独特且可混合的动作，需要只输出有限的连续关节参数。 */
function crewPose(sample) {
    // 1、站立呼吸作为基底，所有动作在相同骨架坐标上叠加。
    const t = sample.reduced ? 0 : sample.time,
        cycle = t * (sample.action === "run" ? 11 : 7),
        stride = Math.sin(cycle),
        seat = sample.seatMix || 0;
    const pose = {
        bob: Math.sin(t * 2.5) * 0.6,
        lean: 0,
        head: Math.sin(t * 1.6) * 1.2,
        legL: seat * 67,
        legR: seat * 63,
        kneeL: -seat * 63,
        kneeR: -seat * 60,
        handLX: -21,
        handLY: -35,
        handRX: 21,
        handRY: -35,
    };
    // 2、走跑分别控制跨步、屈膝、摆臂和身体前倾，起坐由 seatMix 连续混合。
    if (["walk", "run"].includes(sample.action)) {
        const run = sample.action === "run",
            amount = run ? 43 : 24;
        pose.legL = stride * amount;
        pose.legR = -stride * amount;
        pose.kneeL = Math.max(0, -stride) * (run ? 77 : 28);
        pose.kneeR = Math.max(0, stride) * (run ? 77 : 28);
        pose.handLX = -17 - stride * (run ? 16 : 9);
        pose.handRX = 17 + stride * (run ? 16 : 9);
        pose.handLY = -44 + (run ? -12 : 0) + stride * 7;
        pose.handRY = -44 + (run ? -12 : 0) - stride * 7;
        pose.bob = -Math.abs(Math.sin(cycle * 2)) * (run ? 4.5 : 1.8);
        pose.lean = run ? -7 : -1.5;
    } else if (sample.action === "read") {
        pose.handLX = -20;
        pose.handLY = -48;
        pose.handRX = 20;
        pose.handRY = -45;
        pose.head = -4;
    } else if (["type", "work"].includes(sample.action)) {
        pose.handLX = -14;
        pose.handRX = 15;
        pose.handLY = -40 + Math.sin(t * 16) * 2;
        pose.handRY = -39 - Math.sin(t * 16) * 2;
        pose.head = 3;
    } else if (sample.action === "write") {
        pose.handLX = -16;
        pose.handLY = -47;
        pose.handRX = 10 + Math.sin(t * 11) * 2;
        pose.handRY = -57 + Math.cos(t * 11) * 2;
        pose.head = 5;
    } else if (sample.action === "think") {
        pose.handRX = 5;
        pose.handRY = -88;
        pose.handLX = -14;
        pose.handLY = -47;
        pose.head = -5 + Math.sin(t * 1.5) * 1.5;
    } else if (sample.action === "ask") {
        pose.handRX = 25;
        pose.handRY = -102 + Math.sin(t * 4) * 3;
        pose.handLX = -22;
        pose.handLY = -40;
        pose.head = -3;
    } else if (sample.action === "talk") {
        pose.handRX = 31;
        pose.handRY = -66 + Math.sin(t * 5) * 6;
        pose.handLX = -25;
        pose.handLY = -47;
        pose.head = Math.sin(t * 4) * 2;
    } else if (sample.action === "report") {
        pose.handLX = -16;
        pose.handLY = -48;
        pose.handRX = 28;
        pose.handRY = -63 + Math.sin(t * 4) * 2;
        pose.head = Math.sin(t * 3) * 2;
    } else if (sample.action === "alert") {
        pose.handLX = -32;
        pose.handRX = 32;
        pose.handLY = -58;
        pose.handRY = -58;
        pose.head = -4;
    } else if (sample.action === "phone") {
        pose.handLX = -8;
        pose.handLY = -43;
        pose.handRX = 6 + Math.sin(t * 5) * 2;
        pose.handRY = -52 + Math.sin(t * 5) * 2;
        pose.head = 7 + Math.sin(t * 1.8);
    } else if (sample.action === "game") {
        pose.handLX = -12;
        pose.handRX = 17;
        pose.handLY = -33 + Math.sin(t * 14) * 2;
        pose.handRY = -34 - Math.sin(t * 13) * 2;
        pose.head = 4 + Math.sin(t * 3) * 2;
        pose.lean = Math.sin(t * 2) * 2;
    } else if (sample.action === "water") {
        pose.handRX = 15;
        pose.handRY = -57;
        pose.handLX = -15;
        pose.handLY = -44;
        pose.lean = 5 + Math.sin(t * 2) * 2;
        pose.head = 8;
    } else if (sample.action === "relax") {
        const reach = (Math.sin(t * 1.5) + 1) / 2;
        pose.handLX = -24 - reach * 9;
        pose.handRX = 24 + reach * 9;
        pose.handLY = -52 - reach * 42;
        pose.handRY = -52 - reach * 42;
        pose.head = -reach * 5;
        pose.lean = Math.sin(t * 1.5) * 3;
    } else if (sample.action === "listen") {
        pose.handRX = 17;
        pose.handRY = -53;
        pose.head = Math.sin(t * 3) * 2;
    }
    return pose;
}
