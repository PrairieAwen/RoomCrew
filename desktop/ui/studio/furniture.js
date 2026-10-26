/* 同一格网下的精细矢量家具，形状不会决定导航或任务权限。 */
"use strict";

class CrewFurniture {
    /** 因为家具与人物应共用投影尺度，需要复用场景的立体绘制能力。 */
    constructor(renderer) {
        // 1、只引用绘图能力，不连接模型或桌面接口。
        this.renderer = renderer;
    }

    /** 因为家具类型必须可注册且尺度一致，需要用有限目录绘制装饰与交互面。 */
    draw(obj) {
        // 1、占地来自后端目录，用户字符串仅作为稳定 ID 和文本。
        const r = this.renderer,
            [w, d] = r.scene.catalog[obj.type],
            p = crewProject([obj.x + w / 2, obj.y + d / 2]);
        const group = crewSvg("g", {
            class: "room-object",
            "data-object": obj.id,
            tabindex: 0,
            role: "button",
            "aria-label": obj.id,
        });
        group.dataset.depth = obj.x + obj.y + (w + d) / 2;
        group.dataset.entity = "object:" + obj.id;
        group.addEventListener("click", r.objectClick.bind(r));
        group.addEventListener("keydown", r.objectKey.bind(r));
        group.append(
            crewSvg("ellipse", {
                cx: p[0] + 4,
                cy: p[1] + 12,
                rx: w * 17,
                ry: d * 7,
                fill: "#766554",
                opacity: 0.12,
            }),
        );
        if (this.paintMaterial(group, obj, p, w, d)) {
            r.depth.append(group);
            return;
        }
        if (["desk", "meeting"].includes(obj.type)) {
            for (const point of [
                [0.25, 0.35],
                [w - 0.55, 0.35],
                [0.25, d - 0.55],
                [w - 0.55, d - 0.55],
            ])
                r.box(
                    group,
                    obj.x + point[0],
                    obj.y + point[1],
                    0.2,
                    0.2,
                    26,
                    "#635447",
                    "#655446",
                );
            r.box(
                group,
                obj.x,
                obj.y,
                w,
                d,
                4,
                obj.type === "desk" ? "#cbb28b" : "#ad8061",
                "#997652",
                27,
            );
            if (obj.type === "desk") this.desk(group, p, obj);
            else this.meeting(group, obj, p);
        } else if (obj.type === "sofa") this.sofa(group, obj, w, d);
        else if (obj.type === "plant") this.plant(group, p, obj);
        else if (obj.type === "screen") {
            r.box(
                group,
                obj.x + 0.1,
                obj.y + 0.2,
                w - 0.2,
                0.3,
                64,
                "#6a7e7b",
                "#4b6360",
            );
            group.append(
                crewSvg("rect", {
                    x: p[0] - 37,
                    y: p[1] - 65,
                    width: 74,
                    height: 42,
                    rx: 4,
                    fill: "#e8e5cf",
                    stroke: "#526864",
                    "stroke-width": 3,
                }),
                crewSvg("path", {
                    d: `M${p[0] - 28},${p[1] - 54} h45 M${p[0] - 28},${p[1] - 46} h30 M${p[0] - 28},${p[1] - 37} h37`,
                    stroke: "#809a84",
                    "stroke-width": 2.2,
                }),
                crewSvg("circle", {
                    cx: p[0] + 26,
                    cy: p[1] - 35,
                    r: 4,
                    fill: "#c49b68",
                }),
            );
        } else {
            r.box(
                group,
                obj.x,
                obj.y,
                w,
                d,
                49,
                obj.type === "fridge" ? "#d5ded1" : "#91aaa8",
                "#8b9f97",
            );
            group.append(
                crewSvg("path", {
                    d: `M${p[0] - 12},${p[1] - 34} h24 M${p[0] - 12},${p[1] - 18} h24`,
                    stroke: "#e7ead9",
                    "stroke-width": 2.5,
                }),
                crewSvg("circle", {
                    cx: p[0] + 8,
                    cy: p[1] - 28,
                    r: 1.6,
                    fill: "#627c70",
                }),
            );
            if (obj.type === "cabinet")
                group.append(
                    crewSvg(
                        "text",
                        {
                            x: p[0],
                            y: p[1] - 53,
                            "text-anchor": "middle",
                            "font-size": 8,
                            fill: "#547364",
                        },
                        "SECURITY",
                    ),
                );
        }
        r.depth.append(group);
    }

    /** 因为环境不能长期停留在低细节几何占位，需要将已核验的家具原图接入相同格网与交互容器。 */
    paintMaterial(group, obj, p, width, depth) {
        // 1、碰撞、锚点和点击事件仍由既有合同控制，只替换外观。
        const mapping = {
            desk: "furniture-02",
            meeting: "furniture-03",
            sofa: "furniture-05",
            plant: "furniture-11",
            fridge: "furniture-09",
            screen: "furniture-10",
            cabinet: "furniture-08",
            bookcase: "furniture-07",
            coffee: "decor-09",
            lamp: "decor-07",
        };
        const identifier =
            obj.id === "guardian-station"
                ? "furniture-06"
                : obj.id === "reception-desk"
                  ? "furniture-01"
                  : mapping[obj.type];
        const material = crewEnvironmentMaterial(identifier);
        if (!material) return false;
        const sizes = {
            plant: 68,
            fridge: 86,
            cabinet: 85,
            bookcase: 112,
            coffee: 65,
            lamp: 55,
            screen: 190,
        };
        const span =
                sizes[obj.type] || Math.max(135, (width + depth) * 24 * 0.95),
            rect = material.frames[0],
            height = (span * rect[3]) / rect[2];
        if (obj.type === "coffee")
            this.renderer.box(
                group,
                obj.x - 0.2,
                obj.y - 0.2,
                1.4,
                1.4,
                26,
                "#c2a27d",
                "#a18566",
            );
        crewEnvironmentPicture(
            group,
            material,
            p[0] - span / 2,
            p[1] + (obj.type === "coffee" ? -23 : 14) - height,
            span,
        );
        group.dataset.material = identifier;
        if (obj.type === "desk") {
            const anchor = this.renderer.scene.anchors.find(
                crewAnchorMatches,
                obj.id,
            );
            if (anchor) this.chair(group, anchor.position, "#71877d");
        }
        if (obj.type === "meeting")
            for (const anchor of this.renderer.scene.anchors)
                if (anchor.object_id === obj.id)
                    this.chair(group, anchor.position, "#657b74");
        return true;
    }

    /** 因为工位应有生活感和明确的工作方向，需要添加显示器、纸张、杯子和座椅。 */
    desk(group, p, obj) {
        // 1、所有细节使用局部坐标，换位置后不需要重画素材。
        group.append(
            crewSvg("path", {
                d: `M${p[0] - 4},${p[1] - 33} v-13 l11,-2 v14`,
                fill: "#566361",
            }),
            crewSvg("rect", {
                x: p[0] - 19,
                y: p[1] - 67,
                width: 43,
                height: 29,
                rx: 3,
                fill: "#405b5f",
                stroke: "#3e5150",
                "stroke-width": 2,
            }),
            crewSvg("path", {
                d: `M${p[0] - 15},${p[1] - 63} h34 l-4,20 h-30Z`,
                fill: "#a5c8bd",
            }),
            crewSvg("path", {
                d: `M${p[0] - 11},${p[1] - 58} h20 M${p[0] - 11},${p[1] - 53} h25 M${p[0] - 11},${p[1] - 48} h14`,
                stroke: "#6d9a8e",
                "stroke-width": 1.4,
            }),
            crewSvg("path", {
                d: `M${p[0] - 10},${p[1] - 31} l28,-1 l-4,7 l-30,0Z`,
                fill: "#758783",
                stroke: "#4f6460",
                "stroke-width": 0.8,
            }),
            crewSvg("path", {
                d: `M${p[0] - 31},${p[1] - 35} l15,-4 l8,9 l-16,4Z`,
                fill: "#eee6cb",
                stroke: "#b4aa8a",
                "stroke-width": 0.6,
            }),
            crewSvg("ellipse", {
                cx: p[0] + 33,
                cy: p[1] - 34,
                rx: 5,
                ry: 3,
                fill: "#f4ead5",
                stroke: "#a29379",
                "stroke-width": 1,
            }),
            crewSvg("path", {
                d: `M${p[0] + 28},${p[1] - 34} v7 q5,5 10,0 v-7 M${p[0] + 38},${p[1] - 32} q7,-1 2,6`,
                fill: "#ead8b6",
                stroke: "#a29379",
                "stroke-width": 1,
            }),
        );
        const anchor = this.renderer.scene.anchors.find(
            crewAnchorMatches,
            obj.id,
        );
        if (anchor) this.chair(group, anchor.position, "#738985");
    }

    /** 因为会议区需要多人座位，需要按照后端注册锚点绘制独立椅子和资料。 */
    meeting(group, obj, p) {
        // 1、每席外观与占座规则使用同一 object ID，不在渲染器新增隐形座位。
        for (const anchor of this.renderer.scene.anchors)
            if (anchor.object_id === obj.id)
                this.chair(group, anchor.position, "#829697");
        group.append(
            crewSvg("path", {
                d: `M${p[0] - 34},${p[1] - 38} l23,-4 l11,10 l-24,5Z M${p[0] + 14},${p[1] - 25} l23,-4 l9,9 l-23,5Z`,
                fill: "#eee5cf",
                stroke: "#bcaa87",
                "stroke-width": 0.8,
            }),
            crewSvg("rect", {
                x: p[0] - 5,
                y: p[1] - 40,
                width: 18,
                height: 12,
                rx: 2,
                fill: "#738f88",
                transform: `rotate(-18 ${p[0]} ${p[1]})`,
            }),
        );
    }

    /** 因为人物落座需要真实的视觉接触点，需要统一绘制椅背、座垫与椅脚。 */
    chair(group, position, color) {
        // 1、地面脚底保持同一投影，不参与路径阻塞计算。
        const p = crewProject(position);
        group.append(
            crewSvg("path", {
                d: `M${p[0] - 10},${p[1] + 2} l2,-18 M${p[0] + 10},${p[1] + 2} l-2,-18`,
                stroke: "#586c66",
                "stroke-width": 2.5,
            }),
            crewSvg("path", {
                d: `M${p[0] - 13},${p[1] - 19} Q${p[0]},${p[1] - 25} ${p[0] + 13},${p[1] - 18} L${p[0] + 12},${p[1] - 11} Q${p[0]},${p[1] - 6} ${p[0] - 13},${p[1] - 12}Z`,
                fill: color,
                stroke: "#586c66",
                "stroke-width": 1,
            }),
            crewSvg("path", {
                d: `M${p[0] - 13},${p[1] - 18} l-1,-20 q14,-8 28,0 l-1,20`,
                fill: color,
                stroke: "#586c66",
                "stroke-width": 1.4,
            }),
        );
    }

    /** 因为休息区需要软装质感，需要绘制靠背、扶手、分块座垫与抱枕。 */
    sofa(group, obj, w, d) {
        // 1、视觉细节遵循固定占地，不改变实际座位数量。
        const r = this.renderer;
        r.box(group, obj.x, obj.y, w, d, 15, "#6b8b7d", "#577463", 5);
        r.box(group, obj.x, obj.y, w, 0.45, 42, "#a1b3a0", "#7c9787", 5);
        for (let i = 0; i < 3; i++)
            r.box(
                group,
                obj.x + 0.25 + i * 1.16,
                obj.y + 0.6,
                1.08,
                1.1,
                7,
                "#b0bda5",
                "#90a38c",
                18,
            );
        r.box(group, obj.x, obj.y, 0.3, d, 28, "#8ca38d", "#6d8974", 5);
        r.box(
            group,
            obj.x + w - 0.3,
            obj.y,
            0.3,
            d,
            28,
            "#8ca38d",
            "#6d8974",
            5,
        );
        const p = crewProject([obj.x + 0.8, obj.y + 1]);
        group.append(
            crewSvg("path", {
                d: `M${p[0] - 10},${p[1] - 33} l15,-4 l9,14 l-16,5Z`,
                fill: "#dbbf8f",
                stroke: "#b39667",
                "stroke-width": 1,
            }),
        );
    }

    /** 因为绿植有助于空间层次，需要用细叶与花盆高光替代简单色块。 */
    plant(group, p, obj) {
        // 1、植物材质不会产生新的碰撞边界。
        group.append(
            crewSvg("path", {
                d: `M${p[0] - 10},${p[1] - 4} l3,14 q7,4 14,0 l3,-14Z`,
                fill: "#c9b290",
                stroke: "#a48c6b",
                "stroke-width": 1,
            }),
            crewSvg("ellipse", {
                cx: p[0],
                cy: p[1] - 4,
                rx: 10,
                ry: 4,
                fill: "#8c7c5b",
            }),
            crewSvg("path", {
                d: `M${p[0]},${p[1] - 4} q-4,-20 0,-50`,
                stroke: "#5c7851",
                "stroke-width": 2,
                fill: "none",
            }),
        );
        for (let i = 0; i < 7; i++) {
            const sign = i % 2 ? 1 : -1,
                base = p[1] - 12 - i * 5;
            group.append(
                crewSvg("path", {
                    d: `M${p[0]},${base} Q${p[0] + sign * 22},${base - 25} ${p[0] + sign * 23},${base - 12} Q${p[0] + sign * 17},${base + 3} ${p[0]},${base}Z`,
                    fill: i % 2 ? "#739564" : "#91aa74",
                    stroke: "#5a7d52",
                    "stroke-width": 0.5,
                }),
            );
        }
    }
}
